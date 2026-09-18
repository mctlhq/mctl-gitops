# Design: issue-334-feat-lifecycle-adopt-proposal-less-same

## Current state

**Shepherd discovery is proposal-keyed and filesystem-bound.**
`orchestrator/run_shepherd._discover_refs` (`run_shepherd.py:1032-1135`) iterates
`state_dir.iterdir()` for service directories, then `<service>/proposals/*`,
loads each `.status.yaml`, and keeps only refs whose `status` is in
`SHEPHERD_INPUT_STATUSES = {"implemented", "review-fixing", "in-progress"}`
(`:402`) and which have a `pr:` URL (recovering it via `_find_pr_url_by_branch`
when missing). The unit of work is `ProposalRef` (`:847-868`) whose fields are
`service, slug, proposal_dir, status, review_attempts, harness_failures,
refusals, refusals_head, pr_url, mode` plus a derived
`status_path = proposal_dir / ".status.yaml"`. A PR with no proposal directory
therefore cannot be represented at all, let alone discovered.

**The review/fix machinery itself is already PR-shaped and reusable.**
`_fetch_pr_snapshot(repo, number)` (`:1341`) builds `PRSnapshot`
(`:957-973`: `number, repo, state, merged, closed_unmerged, merge_commit,
close_comment_or_default, head_sha, head_pushed_at, merge_state_status,
checks_green, is_draft, review_decision`). `read_codex_review(pr)` (`:1532`)
aggregates bot signals into `CodexReview` (`:889-945`) with
`findings_p1_p2(at)` and `fresh_findings_p1_p2(at, since)`; gating bots are
`claude[bot]` (drives `has_responded` and `head_verdict`) and
`chatgpt-codex-connector[bot]` (findings only), while
`copilot-pull-request-reviewer[bot]` is observed-only (`CopilotReview`,
`:948-954`). `decide(pr, codex_review, *, fix_only=False)` (`:1782`) is a pure
function returning `wait | address-review | merge | defer-merge |
flip-to-merged | flip-to-rejected`. `_extract_severity` (`:1484`) and
`_is_fresh_finding` (`:1510`) already implement the P1/P2 and head-freshness
rules. Everything in this paragraph takes a `PRSnapshot`, not a `ProposalRef`.

**The hand-off, by contrast, is slug-shaped.** `apply_followup(service, slug,
findings, skip_subprocess, state_dir)` (`:2062`) builds the bundle via the
`agents/_shepherd` sub-agent and forks
`python -m orchestrator.run_implementer --service <svc> --slug <slug>
--review-feedback <bundle> --refusal-out <path>` (`:2124-2131`). On the other
side, `run_implementer.review_feedback_one(ref, bundle, dry_run)`
(`run_implementer.py:1617`) hardcodes `branch = f"feat/agents-{ref.slug}"`
(`:1665`), refuses to create it if absent on origin
(`_branch_exists_on_origin`, `:1679`), and `_build_prompt` (`:1288-1302`)
likewise hardcodes that branch name and instructs the sub-agent to read spec
files from `$PROPOSAL_DIR`. So today the fix path can only target a branch the
implementer itself named, for a proposal that has spec files.

**Ownership primitives already exist and already name this issue.**
`orchestrator/lifecycle/contract.py` defines `KIND_PULL_REQUEST =
"pull-request"` (`:16`), `PHASE_REVIEW_REMEDIATION = "review-remediation"`
(`:20`), owner types including `OWNER_RECONCILER` (`:35`) and `OWNER_SHEPHERD`
(`:33`), and `EntityRef.for_pull_request(repo, number, head_sha)` (`:58-60`)
producing the id `"{owner}/{repo}#{number}"` with `version` = head SHA.
`OwnershipClient` (`client.py:86`) exposes `get`, `get_many`, `acquire(...,
proposal_ref="", policy_ref="", temporal_workflow_id="")`, `progress`,
`handoff_start`, `handoff_complete`, `release`, `terminal`.
`OwnershipAnswer.blocks_others` (`contract.py:241-286`) is true for
`OWNED_BY_OTHER`, `OWNED_BY_ME` **and** `UNKNOWN` — uncertainty already blocks.
`lifecycle/rollout.py` gives `mode()`, `records_writes()`,
`computes_new_answer()`, `new_answer_may_veto()`, `blocks_on_unknown()`.
`lifecycle/policy.py` gives `default_owner_for`, `merge_authority_for`,
`policy_ref_for` as thin wrappers over `run_shepherd._service_mode` /
`_merge_owner_for`; note that `policy.py` currently has no production caller.

**The gap is documented, not accidental.** ADR-010 section 10 pilot path 4:
*"proposal-less adopted PR (#334). Identical row shape, `proposal_ref = ""`,
owner `reconciler` at adoption then handed to `shepherd`. No `.status.yaml` is
created and no proposal is synthesised. The shape exists from phase 1; the
discovery of adoptable PRs is #334's own work."* The lifecycle reconciler makes
the same deferral executable: `lifecycle/reconciler.py:212-249` classifies a
zero-owner entity with a live worker as `ACTION_ESCALATE` /
`"zero-owner-live-worker"` and explicitly declines to adopt, because `acquire`
refuses an entity phase that already has an ACTIVE row. The pre-existing
detector, `temporal/activities/orphans.py` (`OrphanSignal`, `detect_orphans`),
is proposal-keyed and, per ADR-010's own table, read by nothing.

**Policy today already makes `mctl-gitops` a fix-only target.**
`NEVER_MERGE_SERVICES = frozenset({"mctl-academy", "mctl-gitops", ".github"})`
(`run_shepherd.py:561`), `_merge_owner_for` returns `"human-codeowner"` for
those (`:587`), and `_service_mode` (`:590`) never resolves them to `FULL`.
That is why the motivating example (`mctl-gitops#1073`) is legal to remediate
and illegal to merge, with no new policy needed.

## Proposed solution

One new module, two small extensions to existing entry points, and no change to
the proposal model.

### 1. `orchestrator/pr_adoption.py` — the `PRRef` and its record

```python
@dataclass
class PRRef:
    repo: str            # "mctlhq/mctl-gitops"
    number: int
    service: str         # repo name; must be in config.settings.SERVICES
    head_ref: str        # the PR's own branch, e.g. "fix/whatever"
    head_sha: str
    owner_type: str      # OWNER_RECONCILER at adoption, OWNER_SHEPHERD after handoff
    attempt: int = 0
    refusals: int = 0
    refusals_head: str | None = None
    outcome: str = "adopted"
    record_dir: Path = ...          # <state_dir>/<service>/adopted-prs/pr-<number>/
    record_path: Path = field(init=False)   # record_dir / ".prref.yaml"

    @property
    def entity(self) -> EntityRef:
        return EntityRef.for_pull_request(self.repo, self.number, self.head_sha)
```

`outcome` is a closed vocabulary, deliberately disjoint from proposal statuses
so no existing reader mistakes one for the other: `adopted`, `review-fixing`,
`merge-ready`, `review-stuck`, `merged`, `closed`, `released`. Terminal set is
`{merge-ready, review-stuck, merged, closed, released}`.

The record is `<state_dir>/<service>/adopted-prs/pr-<number>/.prref.yaml`,
written through a thin wrapper over `proposal_state._write_status_atomic` so it
inherits the atomic-replace, mode-preserving, merge-don't-clobber behaviour
(`proposal_state.py:145-254`). It is a *sibling* of `proposals/`, never inside
it, so `_discover_refs`, the implementer's batch scan, and the mentor digest all
continue to see exactly the proposals they see today. Alongside the scalar
fields the record carries an append-only `attempts:` list — one entry per
adoption or fix attempt with `at, attempt, head_sha, reviewer, finding,
owner_type, outcome` — which is the issue's evidence requirement made durable.

### 2. Discovery — `discover_adoptable_prs(state_dir, *, service_filter=None)`

Candidate enumeration uses `gh pr list --repo mctlhq/<service> --state open
--json number,headRefName,headRefOid,isCrossRepository,isDraft,url,author`
through the existing `_gh_api_json` / `_run` helpers, for every service in
`config.settings.SERVICES` that is both in the `SHEPHERD_ADOPT_SERVICES`
allowlist and not resolved to `SKIP` by `run_shepherd._service_mode`. Rejection
filters run cheapest-first, each emitting one `adoption: skip <repo>#<n>
reason=<slug>` line:

| order | reason slug | source of truth |
|---|---|---|
| 1 | `fork` | `isCrossRepository` |
| 2 | `draft` / `not-open` | `isDraft`, state |
| 3 | `implementer-branch` | `headRefName` matches `feat/agents-*` |
| 4 | `proposal-owned` | index of `pr:` URLs from `_discover_refs(state_dir, reconcile=True)` + `_parse_pr_url` |
| 5 | `devloop-owned` | `run_shepherd._dev_loop_owns_answer` (`:195`) |
| 6 | `steward-owned` | `lifecycle.policy.default_owner_for(service) == OWNER_PR_STEWARD` |
| 7 | `policy-excluded` | changed files intersect `ADOPTION_EXCLUDED_PATHS` globs |
| 8 | `owned` / `store-unknown` | `OwnershipClient.get_many(KIND_PULL_REQUEST, PHASE_REVIEW_REMEDIATION, ids).blocks_others` |
| 9 | `no-blocking-findings` | `read_codex_review(pr).fresh_findings_p1_p2(pr.head_sha, pr.head_pushed_at)` |

Filters 4 and 8 are the two independent answers to "does something already own
this", kept both because they fail in opposite directions: the proposal index is
local and exact but blind to PRs the store knows about, the store is
authoritative but can answer `UNKNOWN`. `UNKNOWN` is a rejection, never an
adoption — the single inversion ADR-010 section 12 insists on. Filter 8 is one
batched read (`get_many`, chunked at `BATCH_CHUNK_SIZE = 100`), not one call per
PR. Filter 9 is deliberately last: it is the only filter that costs a
`_fetch_pr_snapshot` plus a review read per candidate.

### 3. Adoption — the ownership handshake

Adoption follows ADR-010 pilot path 4 literally:

1. `acquire(entity, PHASE_REVIEW_REMEDIATION, Owner(OWNER_RECONCILER, id),
   proposal_ref="", policy_ref=policy.policy_ref_for(service))`.
   `proposal_ref=""` is the record's statement that there is no proposal; the
   `_write` filter drops empty strings, so nothing fabricates one.
2. Write the `PRRef` record with `outcome: adopted`, `owner_type: reconciler`
   and the first `attempts:` entry (the adoption evidence).
3. `handoff_start(entity, phase, owner=reconciler, epoch, to=Owner(OWNER_SHEPHERD, id))`.
4. The shepherd's adoption pass calls `handoff_complete(entity, phase,
   incoming=Owner(OWNER_SHEPHERD, id))` and rewrites `owner_type: shepherd`
   before it may mutate anything. Between steps 3 and 4 the row is
   `handing-off` — the deterministic unowned state `reconciler.classify`
   already recognises (`ACTION_COMPLETE_HANDOFF`, reason `handoff-incomplete`),
   so an interrupted adoption is repaired by the existing 15-minute reconcile
   sweep rather than by new code. This also gives `handoff_start` its first
   production caller.

If `acquire` does not answer `OWNED_BY_ME`, adoption aborts and writes nothing.

### 4. Remediation — `process_adopted_one(prref, *, dry_run)`

A sibling of `process_one`, not a generalisation of it: `process_one` is
~420 lines of proposal-status transitions and the risk of threading a second
entity type through it outweighs the duplication. The new function reuses,
unchanged: `_fetch_pr_snapshot`, `read_codex_review`, `read_copilot_review`,
`decide`, `_extract_severity`, `_is_fresh_finding`, `trigger_review`,
`_attempt_is_fresh`'s claim helper, and `apply_followup`.

- `decide(pr, review, fix_only=True)` **always**, for every adopted PR
  regardless of the service's own `_service_mode`. This is the mechanical
  expression of "adoption grants remediation only": the `merge` arm is
  unreachable, so `merge_pr` is never called from this path. A `defer-merge`
  decision maps to outcome `merge-ready` and a log line naming
  `policy.merge_authority_for(service)` as whoever may actually merge.
- `address-review` re-reads the head immediately before mutating and aborts if
  it moved since `decide` ran; the bundle, the attempt entry and the
  `ExecutionClaim` (`ClaimClient.acquire(..., entity_version=head_sha, ...)`,
  executor `OWNER_IMPLEMENTER`) are all pinned to the same SHA.
- After a successful push: `attempt += 1`, new `head_sha` recorded,
  `outcome: review-fixing`, and `progress(entity, phase, owner, epoch,
  evidence=f"pushed {old}->{new} for {reviewer} {severity}")`. `progress` is
  called only here — never on an observing tick — matching its contract.
- `attempt >= run_shepherd.MAX_REVIEW_ATTEMPTS` (5) with findings still
  present: `outcome: review-stuck`, `terminal(..., reason="review-stuck after
  N attempts")`, no further implementer forks. The existing
  `MAX_HARNESS_FAILURES` (3) and `MAX_REFUSALS` (3) bounds are honoured the
  same way, with `refusals_head` resetting the refusal budget on a head change.
- `flip-to-merged` / `flip-to-rejected` become `outcome: merged` / `closed` plus
  `terminal(...)`. A proposal or live DevLoop appearing for an adopted PR
  yields `outcome: released` plus `release(...)`, re-checked on every tick so
  late-arriving legitimate ownership always wins.

### 5. Hand-off plumbing — explicit branch, no proposal dir

`apply_followup` gains two keyword-only parameters, both defaulting to today's
behaviour: `branch: str | None = None` and `pr_url: str | None = None`. When
set, the forked argv becomes
`python -m orchestrator.run_implementer --review-feedback <bundle>
--refusal-out <path> --pr-repo <repo> --pr-number <n> --pr-branch <head_ref>`
with no `--service`/`--slug`. `run_implementer` gains a matching
`adopted_review_feedback_one(prref_like, bundle)` that differs from
`review_feedback_one` in exactly three places: `branch` comes from the argument
instead of `f"feat/agents-{ref.slug}"`; `_clone_target` is keyed on repo rather
than proposal; and `_build_prompt` takes a `branch` argument and, when there is
no proposal, uses a variant that omits every `$PROPOSAL_DIR` reference and
states that the PR description and the findings are the entire specification.
`_branch_exists_on_origin`, `_checkout_existing_branch`,
`_stage_implementer_agent`, `_capture_head_sha`, the refusal-marker protocol and
the `_review_feedback_exit_code` sentinels are untouched, so the shepherd's
existing handling of harness failures and refusals applies verbatim.

### 6. Entry points and flags

`run_shepherd.main()` gains `--adopt-prs` (and env `SHEPHERD_ADOPT_PRS`,
default off) plus `SHEPHERD_ADOPT_SERVICES` (empty allowlist by default) and
`ADOPTION_EXCLUDED_PATHS` (default: `.github/workflows/**`, `charts/**`,
`**/values.yaml`). The pass runs after proposal-backed processing so an adoption
error can never affect the existing tick, and its results append to
`_print_summary`. `--dry-run` prints candidates and decisions and writes
nothing. Below `rollout.ENFORCE` the pass discovers, records and logs but never
forks the implementer — so `observe` measures adoption volume before adoption can
touch a branch.

## Alternatives

**Synthesise a stub proposal directory for each adopted PR.** Zero new discovery
code: write `agents-state/<service>/proposals/adopted-pr-<n>/.status.yaml` with
`status: implemented` and `pr:` set, and the existing loop drives it. Rejected —
the issue forbids it in as many words ("Do not synthesize a fake
roadmap/proposal merely to fit today's discovery model"), and it is
operationally worse than it looks: the fake proposals enter the implementer's
batch scan, the mentor digest, the reconcile sweep's
`(devloop-proposal, implement)` observation and every proposal count an operator
reads, while `review_feedback_one` would still fail because `feat/agents-adopted-pr-<n>`
does not exist on origin.

**Put attempt counter and outcome only in the lifecycle store, with no gitops
record.** Attractive: no new gitops path, no companion CWFT change, and
`ExecutionClaim` already has `attempt` and `outcome` fields. Rejected as the
primary design — claims are per-attempt and terminalise (`released`, `expired`,
`fenced`), so counting attempts across them needs durable aggregation that does
not exist in mctl-api today; and at `enforce` an unreachable store already
blocks mutation, which would make the attempt budget unreadable in exactly the
outage where a bounded loop matters most. Kept as the documented fallback if a
reviewer prefers one store (requirements.md, first open question).

**Adopt inside the Temporal reconcile sweep instead of the shepherd.**
`reconcile_lifecycle_ownership` already runs every 15 minutes with the active
DevLoop set known, and already classifies the zero-owner case. Rejected —
`reconciler.py:230-249` declines adoption for a stated structural reason
(`acquire` refuses an entity phase that already has an ACTIVE row, so a planted
`reconciler` row would refuse the legitimate DevLoop), and the worker has
neither the `gh` CLI plumbing, the SDK bundle step, nor the ability to fork
`run_implementer`. The chosen split keeps the reconciler as the repairer of
`handing-off` rows, which is the role it already has.

**Extend `pr-steward` in `mctl-claude-remote` to adopt these PRs.** Rejected —
ADR-010 records why the steward could not participate: it is a headless
`claude -p` process with a GitHub App token and no gitops write path, and it
cannot reuse `run_implementer` at all. Doing this there means a second
implementation of the fix loop in another repository.

## Platform impact

**Migrations.** None to existing data. No proposal `.status.yaml` is read
differently or written by this path, no field is added to or removed from the
proposal schema, and no ownership row shape changes — ADR-010 phase 1 already
allows `proposal_ref=""`. The one new artefact is the `adopted-prs/` directory,
created on first adoption.

**Backward compatibility.** Every change is additive and flag-gated. With
`SHEPHERD_ADOPT_PRS` unset, `_discover_refs`, `process_one`, `decide`,
`apply_followup` (both new parameters defaulted to `None`) and
`review_feedback_one` behave byte-identically to today, which is the property
task T8 asserts directly. No Temporal workflow code changes, so no history
incompatibility and no new `workflow.patched` marker.

**Cross-repo dependency (the main risk).** The `adopted-prs/` path must be
staged by the shepherd's commit step in the `mctl-gitops` CWFT; the pathspec
comment in `proposal_state.py:205-214` shows the investigate CWFT stages
`':(glob)…/proposals/*/**'`, which would not match a sibling directory. Until
the companion change lands, records are written but never committed, so every
tick re-adopts from `attempt: 0` and the bound is not actually bounded.
Mitigation: the production flag stays off until the CWFT change merges (task 9),
and `process_adopted_one` refuses to fork the implementer when it observes an
`attempt: 0` record for a PR whose head already carries a
`fix(agents):`-authored commit by `mctl-agents[bot]` — a cheap independent
signal that the counter was lost.

**Resource impact.** One `gh pr list` per allowlisted service per tick (at most
15 today, and the allowlist starts empty), one batched ownership read per tick,
and one `_fetch_pr_snapshot` + review read per surviving candidate. At the
15-minute shepherd cadence this is well inside GitHub's authenticated rate
limit, and the filter ordering means the expensive reads only run for PRs that
passed every cheap rejection. Implementer forks are bounded by
`MAX_REVIEW_ATTEMPTS` per PR exactly as for proposal-backed PRs, so SDK spend
scales with adopted PRs, not with open PRs.

**Risks and mitigations.**

- *Two actors push to one branch.* Mitigated by the ownership `acquire` (a
  second actor gets `OWNED_BY_OTHER`), the `ExecutionClaim` pinned to
  `entity_version`, filters 4-6 and 8, and the re-check of release conditions on
  every tick. `UNKNOWN` blocks rather than permits.
- *Adoption mutates something a human meant to gate.* Mitigated by the empty
  default allowlist, the path-exclusion globs, `fix_only=True` making `merge`
  unreachable, and `NEVER_MERGE_SERVICES` plus branch protection remaining the
  authoritative merge gate.
- *Fork PR mutation.* Rejected at filter 1 on `isCrossRepository` before the
  head SHA is even read, and again asserted in T4.
- *Stale finding drives a patch.* Mitigated by `fresh_findings_p1_p2(head_sha,
  head_pushed_at)` — the same defence `mctl-agents#359`/`#336` produced for
  re-anchored comments — plus the immediate pre-mutation head re-read.
- *An adopted PR churns SDK spend.* Bounded by `MAX_REVIEW_ATTEMPTS`,
  `MAX_HARNESS_FAILURES`, `MAX_REFUSALS`, and the terminal `review-stuck`
  outcome, all reused rather than re-implemented.
- *Silent no-op.* Every rejection logs a reason slug, so "zero adoptions" is
  always distinguishable from "never ran" — the failure mode ADR-010 records for
  `OrphanSignal` and `detect_orphans`.
