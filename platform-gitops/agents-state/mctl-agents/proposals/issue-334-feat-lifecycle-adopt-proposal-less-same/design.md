# Design: issue-334-feat-lifecycle-adopt-proposal-less-same

## Current state

**Discovery is proposal-keyed.** `orchestrator/run_shepherd.py::_discover_refs`
(L1032-1140) iterates `state_dir/<service>/proposals/<slug>/.status.yaml` and
builds a `ProposalRef` (L847-865) only when `status` is in
`SHEPHERD_INPUT_STATUSES = {"implemented", "review-fixing", "in-progress"}`
(L402) and a `pr:` URL is present (or recoverable from the deterministic
`feat/agents-<slug>` branch via `_find_pr_url_by_branch`, L1162). A pull request
with no proposal directory therefore cannot be seen at all.

**The decision loop is already PR-shaped.** `process_one` (L2298) calls
`find_pr_for_proposal` (L1320) → `_fetch_pr_snapshot` (L1341) → `read_codex_review`
(L1532) → `decide` (L1782). `decide` reads only a `PRSnapshot` and a
`CodexReview`; nothing in it touches a proposal. Findings are anchored to the
head through `CodexReview.findings_p1_p2` / `fresh_findings_p1_p2` (L905-944),
which is exactly the "pinned to the current head SHA" rule the issue asks for,
including the comment explaining why `created_at` — not GitHub's re-anchored
`commit_id` — is the discriminating filter.

**The fix hand-off is proposal-keyed again.** `apply_followup` (L2062) builds the
findings bundle and forks
`python -m orchestrator.run_implementer --service <svc> --slug <slug>
--review-feedback <bundle> --refusal-out <path>` (L2124-2136).
`orchestrator/run_implementer.py::main` (L2953-2961) rejects `--review-feedback`
without both `--service` and `--slug`, then looks the proposal up with
`find_accepted_proposals(..., statuses={"implemented", "review-fixing"})`
(L1104-1173) and exits 1 when nothing matches.
`review_feedback_one` (L1617-1822) then hardcodes two things a proposal-less PR
cannot satisfy:

- `branch = f"feat/agents-{ref.slug}"` (L1664; the same literal is re-derived in
  `_build_prompt`, L1299);
- `_load_status(ref.status_path)` for the `pr:` URL and `review_attempts`
  (L1701-1710), and `PROPOSAL_DIR=ref.proposal_dir` for the sub-agent (L1723).

Everything else on that path is already PR-generic: `_clone_target` clones
`mctlhq/{service}` (L1225), `_stage_implementer_agent` falls back to
`agents/_generic/.claude/agents/implementer.md` (L1251-1265), and the push is
`git push --force-with-lease={branch}:{old_head}` (`_push_followup`, L1478-1493)
— a head-SHA fence that works on any branch name.

**Ownership vocabulary already exists.** `orchestrator/lifecycle/contract.py`
defines `KIND_PULL_REQUEST` (L15), `PHASE_REVIEW_REMEDIATION` (L20),
`OWNER_SHEPHERD` / `OWNER_RECONCILER` (L32-40), and
`EntityRef.for_pull_request(repo, number, head_sha)` whose id is
`mctlhq/mctl-gitops#1073` (L58-64). `orchestrator/lifecycle/client.py`'s
`OwnershipClient.acquire(entity, phase, owner, *, proposal_ref, policy_ref,
temporal_workflow_id)` (L205) already accepts an empty `proposal_ref`, which is
precisely what ADR-010 §10 pilot path 4 specifies for this case. Every read and
write is gated by `orchestrator/lifecycle/rollout.py`
(`computes_new_answer()` at OBSERVE, `new_answer_may_veto()` at ENFORCE), which
defaults to `off`. `review_feedback_one` already acquires an `ExecutionClaim` on
`(pull-request, <repo>#<n>, review-remediation)` at L1711-1719.

**Existing safety rails that carry over unchanged.**
`NEVER_MERGE_SERVICES = {"mctl-academy", "mctl-gitops", ".github"}` (L561),
`_service_mode` (L590) resolving FULL / FIX_ONLY / SKIP, the `decide(..., fix_only=True)
→ defer-merge` branch, `MAX_REVIEW_ATTEMPTS = 5` (L420),
`MAX_HARNESS_FAILURES = 3` (L454), `MAX_REFUSALS = 3` (L470), and the per-head
refusal reset keyed on `refusals_head` (L2494-2500).

**What does not exist.** `PRSnapshot` (L958-975) carries no head branch name and
no fork indicator; the GraphQL query at L1352 requests neither `headRefName` nor
`isCrossRepository`. There is no code anywhere in the repo that lists candidate
PRs that have no proposal — `activities/orphans.py` only re-checks PRs that
already have one.

## Proposed solution

Add a second durable record type beside `proposals/`, and two narrow parameters
on the existing execution path so it can act on a branch it did not name. The
whole feature is inert unless `SHEPHERD_ADOPT_PRS` is true.

### 1. The record: `adopted-prs/pr-<number>/.prref.yaml`

New module `orchestrator/pr_adoption.py`:

```
ADOPTED_DIRNAME  = "adopted-prs"
PRREF_FILENAME   = ".prref.yaml"
PRREF_KIND       = "pr-ref"
MAX_EVIDENCE     = 20
```

`PRRef` subclasses `run_shepherd.ProposalRef` so `process_one` and
`_print_summary` consume it unchanged, and overrides `__post_init__` to point
`status_path` at `.prref.yaml`. It adds `repo`, `number`, `head_branch` and
`owner_type`; `service` is `repo.split("/")[-1]`, `slug` is `pr-<number>`, and
`mode` is forced to `FIX_ONLY` at construction so `decide()` can only ever
return `defer-merge` for it. File shape:

```yaml
kind: pr-ref
repo: mctlhq/mctl-gitops
number: 1073
pr: https://github.com/mctlhq/mctl-gitops/pull/1073
head_sha: <40 hex>
head_branch: chore/some-manual-branch
owner_type: shepherd
policy_ref: service-mode:mctl-gitops=fix-only
status: adopted            # adopted | review-fixing | review-stuck | merged | rejected
review_attempts: 0
harness_failures: 0
refusals: 0
refusals_head: null
adopted_at: 2026-09-19T00:00:00Z
updated_at: ...
updated_by: mctl-agents[bot]
evidence:
  - at: 2026-09-19T00:00:00Z
    repo: mctlhq/mctl-gitops
    pr: 1073
    head_sha: <40 hex>
    reviewer: claude[bot]
    finding: "P1: ... (truncated to 300 chars)"
    attempt: 0
    owner_type: shepherd
    outcome: adopted
```

Reads and writes reuse `orchestrator/proposal_state.py::load_status` and
`update_status_file`, which are path-generic (they take a `Path`, atomic-rename
through `_write_status_atomic`, and preserve unknown keys). No second YAML
writer is introduced. `status` is deliberately drawn from the same vocabulary
the shepherd already writes, so `process_one`'s `update_status(ref, ...)` calls
need no branching — the extra state is `adopted`, which is added to
`SHEPHERD_INPUT_STATUSES` only for the adoption path's own re-discovery.

### 2. Discovery

`pr_adoption.discover_adoptable(state_dir, *, budget)` runs once per sweep tick,
after `_filter_dev_loop_owned`, and only when adoption is enabled:

1. **Candidate set.** For each repo in `SHEPHERD_ADOPT_REPOS ∩ SERVICES`,
   `gh api graphql` for open PRs, requesting `number headRefOid headRefName
   isDraft isCrossRepository headRepositoryOwner{login} baseRepository{owner{login}}`.
   `SHEPHERD_ADOPT_REPOS` is parsed with the existing
   `run_shepherd._service_set_from_env` (L508), which already warns on unknown
   names; its default is empty, so the feature adopts nothing until an operator
   names a repo.
2. **Fork gate.** Drop anything with `isCrossRepository` true or
   `headRepositoryOwner.login != baseRepository.owner.login`. Drafts are dropped
   too (`decide()` would only `wait`).
3. **Proposal gate.** Drop any PR whose URL appears as `pr:` in any
   `.status.yaml` under `state_dir` — one pass over the same glob
   `_discover_refs` already walks, cached per tick. Also drop any PR whose
   `headRefName` starts with `feat/agents-`: that prefix is the implementer's
   deterministic branch and belongs to #239, not here.
4. **DevLoop gate.** `run_shepherd._dev_loop_owns_answer` is reused; anything
   not `LEGACY_FREE` is dropped. Unlike the sweep, adoption **fails closed** on
   `LEGACY_UNKNOWN` — the sweep's fail-open default exists because it is a
   safety net for work it already owns, whereas adoption is discretionary and an
   unanswerable probe is not evidence of vacancy.
5. **Steward / policy gate.** `run_shepherd._service_mode(service)` must not be
   `SKIP`. A steward-owned repo becomes adoptable only once an operator moves it
   to `SHEPHERD_FIX_ONLY_SERVICES`, which is the #292 decision expressed in the
   configuration that already exists.
6. **Ownership store gate.** When `rollout.computes_new_answer()`, call
   `OwnershipClient().get(EntityRef.for_pull_request(repo, number, head_sha),
   PHASE_REVIEW_REMEDIATION)`. Adopt only on `UNOWNED` or `OWNED_BY_ME`; refuse
   on `OWNED_BY_OTHER` and on `UNKNOWN`.
7. **Findings gate.** `_fetch_pr_snapshot` + `read_codex_review`, then
   `fresh_findings_p1_p2(pr.head_sha, pr.head_pushed_at)`. Empty → not adoptable.
8. **Adopt.** Write `.prref.yaml` with the first evidence entry, and — when
   `rollout.records_writes()` — `OwnershipClient().acquire(entity,
   PHASE_REVIEW_REMEDIATION, Owner(type=OWNER_SHEPHERD, id=...),
   proposal_ref="", policy_ref=policy.policy_ref_for(service))`. Ownership
   failure never fails the tick: it downgrades to "do not adopt this PR", the
   same fail-safe direction ADR-010 §9 mandates.

Existing `.prref.yaml` records are re-discovered by a sibling glob in
`_discover_refs` (guarded by the same flag) so a record created in an earlier
tick keeps its counters — subject to the durability caveat below.

The number of adoption records processed per tick is capped by
`SHEPHERD_ADOPT_MAX_PRS_PER_TICK` (default 1). This bounds both cost and — more
importantly — the blast radius while `adopted-prs/**` is not yet committed back
to gitops.

### 3. Acting on the record

`process_one` is reused verbatim except for two seams:

- `find_pr_for_proposal` gains an optional `status_path` parameter; a `PRRef`
  passes its `.prref.yaml` so the `pr:` URL resolves from the adoption record
  instead of a `proposals/<slug>/.status.yaml` that does not exist.
- `apply_followup` gains `adopted_pr: str | None`. When set it appends
  `--adopted-pr <pr-url>` in place of `--slug`. The bundle construction, the
  `--refusal-out` temp file, the `--state-dir` forwarding and the whole
  exit-code classification (`_refusal_codes` 47, `_fenced_codes` 48/49,
  harness 46, deterministic 42/43/44, else transient) are untouched, so the
  counter semantics in `process_one` (L2444-2630) apply to adoption records with
  no new code.

On the implementer side:

- `--adopted-pr <pr-url>` is accepted only together with `--review-feedback`,
  and is mutually exclusive with `--slug`.
- `build_adopted_ref(state_dir, pr_url)` reads
  `<state-dir>/<service>/adopted-prs/pr-<n>/.prref.yaml` and returns an ordinary
  `ProposalRef` whose `proposal_dir` is that directory and whose `status_path`
  is that file. A missing record is exit 2 — the implementer never adopts; only
  the shepherd does.
- `review_feedback_one(ref, bundle, dry_run=False, branch=None)`:
  `branch = branch or f"feat/agents-{ref.slug}"`. The adopted call passes
  `head_branch` read from the record, never a model-supplied value. Everything
  downstream — `_branch_exists_on_origin`, `_checkout_existing_branch`,
  `_capture_head_sha`, the `EntityRef.for_pull_request` claim (which already
  reads `pr:` and `review_attempts` from `ref.status_path`), `_has_new_commits`,
  the refusal marker, and `--force-with-lease={branch}:{old_head}` — is
  unchanged.
- A second fork check fires inside the implementer immediately before the clone
  (one `gh api` read of `isCrossRepository`); a true answer exits 2 without
  cloning. Defence in depth: the one mutation this feature performs must be
  refused by the process that performs it, not only by the process that
  scheduled it.
- `_build_prompt` gains `branch` and `adopted` parameters. The adopted variant
  drops the "Spec files live at `$PROPOSAL_DIR`" sentence and the
  `Proposal: platform-gitops/agents-state/...` commit trailer, substituting
  `PR: <url>` and the subject
  `fix(review): address P1/P2 findings on <repo>#<n>`. `PROPOSAL_DIR` still
  points at the record directory (the sub-agent frontmatter references it), and
  the prompt states plainly that it holds an adoption record, not a spec — so
  the agent grounds itself in the findings and the diff rather than hunting for
  a `requirements.md` that does not exist.

### 4. Merge authority

An adoption record is always `FIX_ONLY`. `decide()` therefore returns
`defer-merge` where a proposal would return `merge`, `merge_pr()` is never
reached, and `process_one`'s defensive re-check (L2665-2678) is a second
refusal. `_merge_owner_for` records who does hold merge authority. This is the
mechanical expression of "adoption grants remediation only, not merge
authority"; no branch-protection or CODEOWNERS behaviour changes.

### 5. Flag surface

| Variable | Default | Effect |
|---|---|---|
| `SHEPHERD_ADOPT_PRS` | `false` | Master switch. False → no discovery, no records, no behaviour change. |
| `SHEPHERD_ADOPT_REPOS` | empty | Allowlist of repos eligible for adoption. Empty → nothing adoptable even when the master switch is on. |
| `SHEPHERD_ADOPT_MAX_PRS_PER_TICK` | `1` | Bound on adoption records processed per tick. |

Plus a `--adopt-prs` CLI flag on `run_shepherd` for a targeted local one-shot.
All three are documented in `.env.example` (commented out) and in the README's
Tier 3 section.

## Alternatives

**A. Synthesize a proposal directory for the PR.** Write
`proposals/adopted-pr-1073/` with a stub triplet so `_discover_refs` and
`review_feedback_one` work untouched. Dropped: the issue forbids it in as many
words ("Do not synthesize a fake roadmap/proposal merely to fit today's
discovery model"), and ADR-010 L110-118 gives the structural reason — a store
keyed on `proposals/<slug>/` cannot represent a PR that has no proposal, so the
stub would immediately be indistinguishable from a real proposal to the mentor
digest, the reconciler, `detect_orphans`, and `find_accepted_proposals`. It also
invites the Tier 2 batch path to pick the stub up as `accepted`.

**B. Put adoption in the Temporal reconciler** (`orchestrator/lifecycle/reconciler.py`),
matching ADR-010 pilot path 4's `reconciler`-at-adoption wording. Dropped: that
ADR section itself states "the reconciler does not keep what it recovers … it
cannot advance a PR", and `workflows/reconcile.py`'s worker has no gitops
checkout and no deploy key by design, so it can neither write `.prref.yaml` nor
fork `run_implementer`. The reconciler hand-off remains the phase-3 integration
the ADR defers until after this issue; this change acquires as `shepherd`
directly and records `policy_ref` so the later hand-off has something to read.

**C. A separate `run_pr_adopter.py` with its own copy of the review-feedback
path.** Dropped: it would duplicate the exit-code vocabulary (42/43/44/46/47/48/49),
the refusal/harness/attempt charging rules and the claim handling — three things
that have each been corrected by a review finding in the last quarter. The
argument is the one `orchestrator/lifecycle/policy.py`'s own docstring makes
against a second copy of `NEVER_MERGE_SERVICES`: two answers to one question
drift. Two parameters on the existing function is the smaller surface.

**D. Trigger adoption from a GitHub webhook instead of the cron sweep.**
Dropped for this change: there is no webhook receiver in `mctl-agents`, it would
require an mctl-api route and a gitops deployment, and the issue's own
implementation boundary confines this PR to `mctlhq/mctl-agents`. The 30-minute
sweep is adequate for a review-fix loop whose other half is a review bot.

## Platform impact

**Migrations.** None. `adopted-prs/` is a new sibling directory under
`agents-state/<service>/`; nothing reads it today, and nothing existing changes
shape. `_discover_refs`'s proposal glob is untouched.

**Backward compatibility.** `PRSnapshot` gains `head_branch: str = ""` and
`is_cross_repository: bool = False` — both defaulted, so every existing fixture
and every existing construction site in `tests/test_run_shepherd.py` keeps
compiling. `find_pr_for_proposal`, `apply_followup`, `review_feedback_one` and
`_build_prompt` all gain keyword parameters with defaults that reproduce today's
behaviour exactly. With `SHEPHERD_ADOPT_PRS` unset, `run_shepherd`'s observable
output is unchanged.

**The durability caveat, stated plainly.** The shepherd ClusterWorkflowTemplate
in `mctl-gitops` stages only `proposals/**` into its gitops commit. Until
`mctlhq/mctl-gitops#1278` lands, every `.prref.yaml` this code writes lives in
the pod's gitops worktree and is discarded when the tick ends. The practical
consequence is that `review_attempts`, `harness_failures` and `refusals` reset
to zero on each tick, so the `MAX_REVIEW_ATTEMPTS` bound does not hold across
ticks and a PR could be re-adopted and re-fixed indefinitely. Three things
address it and none of them is a workaround: (1) the feature ships default-off
and is not enabled until both PRs are merged; (2)
`SHEPHERD_ADOPT_MAX_PRS_PER_TICK` defaults to 1, so a tick can spend at most one
implementer run on adoption regardless; (3) when adoption is enabled the
shepherd prints a startup warning naming `mctlhq/mctl-gitops#1278` and saying
the counters are not durable, so an operator who enables it early sees why.

**Resource impact.** With the feature off: zero. With it on: one extra GraphQL
list per allowlisted repo per tick, plus at most one extra
`_fetch_pr_snapshot` + `read_codex_review` pair per candidate, and at most
`SHEPHERD_ADOPT_MAX_PRS_PER_TICK` implementer forks. The existing
`SHEPHERD_BUDGET_USD` loop guard in `main()` already charges
`per_call_estimate` per `address-review` decision and covers adoption records
because they flow through the same loop.

**Risks and mitigations.**

| Risk | Mitigation |
|---|---|
| Pushing to a fork | Two independent `isCrossRepository` checks — discovery and pre-clone — plus `--force-with-lease` which cannot create a branch. |
| Double-driving a PR another actor owns | Four gates (proposal, `feat/agents-` prefix, DevLoop liveness, `_service_mode`) plus the ownership store; all fail closed, unlike the sweep's fail-open default. |
| Adoption read as merge authorization (the #344 mistake) | `mode` is `FIX_ONLY` at construction; `decide()` cannot emit `merge`; `merge_pr()` has its own `NEVER_MERGE_SERVICES` refusal; the record stores `owner_type`, never a merge grant. |
| Acting on a stale finding | `fresh_findings_p1_p2(head_sha, head_pushed_at)` is the only findings source; the claim pins `entity_version=old_head`; the push is `--force-with-lease={branch}:{old_head}`. |
| Unbounded loop while the record is not durable | Default-off, per-tick cap of 1, startup warning. |
| Allowlist typo silently adopting nothing | `_service_set_from_env` already warns on names outside `SERVICES`. |
| Cost spike on a repo with many blocking PRs | Per-tick cap plus the existing `SHEPHERD_BUDGET_USD` guard. |
