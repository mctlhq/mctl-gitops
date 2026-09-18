# Adopt proposal-less same-repo PRs with blocking reviews into the shepherd review-feedback loop

## Context

A pull request opened directly against an `mctlhq` repository — by a human, by
ChatGPT, or by any tool that is not the Tier 2 implementer — has no proposal
directory under `platform-gitops/agents-state/<service>/proposals/<slug>/`. The
Tier 3 shepherd discovers work exclusively by globbing that tree
(`orchestrator/run_shepherd._discover_refs`, which requires
`status in SHEPHERD_INPUT_STATUSES` and a `pr:` field), so such a PR is
invisible to it. When a review bot leaves blocking P1/P2 findings on that PR,
nothing automated drives the fix loop: `mctlhq/mctl-gitops#1073` sat with
blocking findings from `claude[bot]` and `agy` and no owner. The only existing
detector of owner-less PRs, `OrphanSignal` in
`orchestrator/temporal/activities/orphans.py`, is itself proposal-keyed and
ADR-010's own table records it as "logged only — read by nothing".

ADR-010 (`docs/adr/010-lifecycle-ownership-contract.md`) already decided the
shape this work must take. Section 10, pilot path 4 names this issue directly:
*"proposal-less adopted PR (#334). Identical row shape, `proposal_ref = ""`,
owner `reconciler` at adoption then handed to `shepherd`. No `.status.yaml` is
created and no proposal is synthesised. The shape exists from phase 1; the
discovery of adoptable PRs is #334's own work."* The ownership and claim
primitives shipped (`orchestrator/lifecycle/contract.py`, `client.py`,
`claim.py`, `policy.py`, `rollout.py`). What is missing is (a) a durable,
lightweight `PRRef` adoption record carrying the attempt budget and outcome,
(b) discovery of adoptable PRs, and (c) a hand-off that can drive
`run_implementer.py --review-feedback` against a branch that is not
`feat/agents-<slug>`. Dependency `mctl-agents#292` made the fix stage reachable
for steward-owned and never-merge repositories (`default_owner_for` /
`merge_authority_for` in `orchestrator/lifecycle/policy.py`), which is what
makes `mctl-gitops` — a member of `run_shepherd.NEVER_MERGE_SERVICES` — a legal
adoption target for remediation without any merge authority.

## User stories

- AS a platform operator I WANT a directly-opened PR that received blocking
  P1/P2 review findings to be picked up automatically SO THAT it does not stall
  indefinitely waiting for me to notice and hand-drive the fix.
- AS a platform operator I WANT every adoption and every fix attempt to record
  repo, PR number, head SHA, triggering reviewer and finding, attempt number,
  owner type and outcome SO THAT I can answer "why did a machine push to this
  PR" from a durable record instead of from workflow logs that have expired.
- AS the pr-steward (or a live DevLoopWorkflow) I WANT adoption to stand down
  whenever I already own a PR SO THAT two actors never push competing fixes to
  one branch.
- AS a repository maintainer I WANT adoption to grant remediation only SO THAT
  branch protection, CODEOWNERS and `NEVER_MERGE_SERVICES` remain the only
  things that decide a merge.
- AS a contributor from a fork I WANT my PR branch never to be mutated by the
  platform SO THAT an untrusted head is never given write-scoped automation.
- AS an mctl-agents maintainer I WANT the adoption path feature-flagged and
  observable before it can mutate anything SO THAT it can be soaked exactly the
  way ADR-010 section 12 requires.

## Acceptance criteria (EARS)

### Discovery

- WHEN the shepherd runs an adoption pass THE SYSTEM SHALL enumerate open pull
  requests in every `config.settings.SERVICES` repository whose resolved
  `run_shepherd._service_mode(service)` is not `SKIP`, and consider each as an
  adoption candidate.
- WHEN a candidate pull request has `isCrossRepository == true` THE SYSTEM SHALL
  reject it as a fork PR, record the rejection reason, and never read its head
  for mutation.
- WHEN a candidate pull request's head ref matches `feat/agents-*` THE SYSTEM
  SHALL reject it as implementer-owned and defer to the proposal-backed path.
- WHEN a candidate pull request is referenced by the `pr:` field of any
  `.status.yaml` discovered by `_discover_refs(state_dir, reconcile=True)` THE
  SYSTEM SHALL reject it, because a proposal already owns it.
- WHEN a candidate pull request has a live `DevLoopWorkflow` according to
  `run_shepherd._dev_loop_owns_answer` THE SYSTEM SHALL reject it.
- WHEN a candidate pull request's service resolves to `SKIP` under
  `_service_mode` (i.e. `lifecycle.policy.default_owner_for` returns
  `pr-steward`) THE SYSTEM SHALL reject it as steward-owned.
- WHEN the lifecycle ownership store answers `get(EntityRef(kind="pull-request",
  id="<owner>/<repo>#<n>", version=<head_sha>), phase="review-remediation")`
  with an answer whose `blocks_others` is true THE SYSTEM SHALL reject the
  candidate.
- IF the lifecycle ownership store answers `UNKNOWN` for a candidate THEN THE
  SYSTEM SHALL reject the candidate and record `store-unknown` as the reason,
  never treating an unanswered read as "unowned".
- WHEN a candidate pull request is a draft, is closed, or is merged THE SYSTEM
  SHALL reject it.
- WHEN a candidate survives every rejection above THE SYSTEM SHALL read its
  review state through the existing `run_shepherd._fetch_pr_snapshot` and
  `run_shepherd.read_codex_review`, and SHALL treat it as adoptable only if
  `CodexReview.fresh_findings_p1_p2(pr.head_sha, pr.head_pushed_at)` is
  non-empty.
- WHILE adoption is evaluating a candidate THE SYSTEM SHALL count only findings
  authored by a gating reviewer bot recognised by `read_codex_review`
  (`claude[bot]`, `chatgpt-codex-connector[bot]`), and SHALL NOT let an
  observed-only reviewer (`copilot-pull-request-reviewer[bot]`,
  `CopilotReview`) trigger adoption.
- IF a candidate's changed files intersect a configured human-gated path
  exclusion THEN THE SYSTEM SHALL reject the candidate and record
  `policy-excluded` as the reason.

### Adoption record

- WHEN a candidate is adopted THE SYSTEM SHALL create exactly one durable
  `PRRef` record carrying at minimum: repository, PR number, service, head ref,
  head SHA, owner type, attempt counter and outcome.
- WHILE an adoption is in force THE SYSTEM SHALL NOT create, and SHALL NOT
  require, any proposal directory, `requirements.md`, `design.md`, `tasks.md`
  or proposal `.status.yaml` for the adopted PR.
- WHEN the `PRRef` record is written THE SYSTEM SHALL write it through an
  atomic replace, preserving fields it does not explicitly change, in the same
  manner as `orchestrator.proposal_state.update_status_file`.
- WHEN adoption succeeds THE SYSTEM SHALL acquire lifecycle ownership as
  `owner_type=reconciler` with `proposal_ref=""` and a `policy_ref` produced by
  `lifecycle.policy.policy_ref_for(service)`, then `handoff_start` to
  `owner_type=shepherd`, exactly as ADR-010 section 10 path 4 specifies.
- WHEN the shepherd next processes an adopted PR whose ownership row is in
  `handing-off` to `shepherd` THE SYSTEM SHALL call `handoff_complete` and act
  as the owner from that point.
- WHEN an adopted PR is re-observed on a tick THE SYSTEM SHALL reuse the
  existing `PRRef` record and SHALL NOT create a second record for the same
  repository and PR number.

### Remediation loop

- WHEN an adopted PR carries fresh P1/P2 findings on its current head THE
  SYSTEM SHALL invoke the existing review-feedback implementer path
  (`run_shepherd.apply_followup`, which forks
  `python -m orchestrator.run_implementer --review-feedback <bundle>`) against
  the PR's own head ref.
- WHILE remediating an adopted PR THE SYSTEM SHALL NOT open a new pull request
  and SHALL NOT create a new branch; IF the recorded head ref does not exist on
  origin THEN THE SYSTEM SHALL abort the attempt with a recorded outcome rather
  than create it.
- WHEN a fix commit is pushed to an adopted PR THE SYSTEM SHALL record the new
  head SHA on the `PRRef`, increment the attempt counter, and report
  `progress` to the ownership store with evidence naming the old and new head.
- WHEN a fix push causes a fresh review that again reports P1/P2 findings on the
  new head THE SYSTEM SHALL run another bounded remediation cycle.
- WHEN an adopted PR reaches `run_shepherd.MAX_REVIEW_ATTEMPTS` consecutive
  remediation attempts without clearing its findings THE SYSTEM SHALL set the
  `PRRef` outcome to `review-stuck`, mark ownership terminal with a reason, and
  stop invoking the implementer for that PR.
- WHEN an adopted PR's findings clear and its checks and merge state would
  otherwise permit a merge THE SYSTEM SHALL record outcome `merge-ready` and
  SHALL NOT call `run_shepherd.merge_pr`.
- WHILE processing an adopted PR THE SYSTEM SHALL evaluate `run_shepherd.decide`
  with `fix_only=True` so that the `merge` decision is unreachable for every
  adopted PR regardless of the service's own mode.
- WHEN an adopted PR is merged or closed out of band THE SYSTEM SHALL record
  outcome `merged` or `closed`, release or terminalise ownership, and stop
  processing it.
- WHEN a proposal or live DevLoopWorkflow appears for an already-adopted PR THE
  SYSTEM SHALL stop driving it, release ownership with a recorded reason, and
  set the `PRRef` outcome to `released`.
- WHILE the head SHA observed at decision time differs from the head SHA at the
  point of mutation THE SYSTEM SHALL abandon the attempt rather than patch or
  merge against a head it did not evaluate.
- IF a review finding predates the current head's push time
  (`head_pushed_at`) THEN THE SYSTEM SHALL NOT let it trigger an adoption or a
  fix attempt.

### Evidence, safety and rollout

- WHEN the system adopts a PR or completes a fix attempt THE SYSTEM SHALL record
  repository, PR number, head SHA, triggering reviewer login, a digest of the
  triggering finding, attempt number, owner type and outcome on the `PRRef`
  record.
- WHEN a candidate is rejected THE SYSTEM SHALL emit one operator-legible log
  line naming the PR and the rejection reason, so "no adoptions" is
  distinguishable from "never evaluated".
- WHILE the adoption feature flag is disabled THE SYSTEM SHALL behave exactly as
  today: no candidate enumeration, no records written, no ownership calls, and
  no change to proposal-backed processing.
- WHILE `lifecycle.rollout.mode()` is below `enforce` THE SYSTEM SHALL evaluate
  and record adoption decisions but SHALL NOT invoke the implementer for an
  adopted PR.
- WHEN the shepherd is run with `--dry-run` THE SYSTEM SHALL print every
  adoption candidate and decision and SHALL write no record, acquire no
  ownership, and fork no subprocess.
- WHEN adoption processing raises for one candidate THE SYSTEM SHALL log it and
  continue with the remaining candidates and with all proposal-backed
  processing, mirroring `_discover_refs`'s per-proposal error containment.

## Out of scope

- Direct implementer PRs that lose shepherd ownership while a proposal exists
  (`mctl-agents#239`) — adjacent, explicitly excluded by the issue.
- Fork pull requests, under any policy setting.
- Granting merge authority to any adopted PR, or changing
  `run_shepherd.NEVER_MERGE_SERVICES`, `merge_pr`, branch protection or
  CODEOWNERS.
- Synthesising a proposal, roadmap item, or issue for an adopted PR; no
  `requirements.md` / `design.md` / `tasks.md` is generated.
- Aggregating review findings across reviewers beyond what `read_codex_review`
  already does (`mctl-agents#240`).
- Making `merge_owner` a read field, or any other `mctl-agents#344` item.
- Adoption of pull requests outside the `mctlhq` organisation, and of repositories
  not listed in `config.settings.SERVICES`.
- Opening new ingress or a GitHub webhook receiver; discovery stays a polled
  read, consistent with ADR-006 stage 6.1.
- Building the `lifecycle-policy.yaml` unification that ADR-010 section 12
  describes; this proposal consumes `lifecycle.policy` as it stands.

## Open questions

- **Where the `PRRef` record lives.** The issue says "lightweight `PRRef`
  adoption record" without naming a store. This proposal puts it in the gitops
  state tree at `platform-gitops/agents-state/<service>/adopted-prs/pr-<n>/.prref.yaml`
  (durable, operator-auditable, survives an mctl-api outage, reuses the atomic
  writer) with ownership itself in the lifecycle store. A reviewer who prefers
  a single store should say so before task 2 lands: the alternative is
  attempt/outcome in mctl-api alongside `ExecutionClaim.attempt`, which removes
  a gitops write but makes the attempt budget unavailable during a store
  outage. Recorded in design.md under Alternatives.
- **The new gitops path must be staged by the committing workflow.** The
  comment in `orchestrator/proposal_state.py` notes the investigate CWFT stages
  `':(glob)…/proposals/*/**'`. A sibling `adopted-prs/` directory needs the
  shepherd CWFT's commit step in `mctl-gitops` to stage it too, which is a
  change in another repository. Proceeding on the assumption that this
  companion change is acceptable; task 9 tracks it, and until it lands the
  records are written but not committed (they would be recreated each tick,
  which resets the attempt budget — the reason task 9 is a blocker for
  enabling the flag in production, not merely a follow-up).
- **Which reviewer logins count as "agy".** The issue names "Claude and agy" as
  the reviewers on `mctl-gitops#1073`, but `read_codex_review` recognises
  `claude[bot]`, `chatgpt-codex-connector[bot]` and
  `copilot-pull-request-reviewer[bot]`. Proceeding with the existing gating set
  and no new reviewer identity; if `agy` is a distinct bot login that is not one
  of those three, adding it is a one-line change to the recognised set and a
  fixture, and is called out in tasks T9.
- **Per-repository adoption opt-in.** The issue requires human-gated
  repositories and paths to stay excluded "unless policy explicitly allows
  remediation" but does not enumerate them. Proceeding with an explicit
  allowlist (`SHEPHERD_ADOPT_SERVICES`, empty by default) plus a path-exclusion
  glob list, so adoption is opt-in per repository rather than opt-out.
- **Attempt-budget reset semantics across head changes.** `ProposalRef` carries
  `refusals_head` so a refusal budget restarts when the branch moves, while
  `review_attempts` does not reset. Proceeding with the same asymmetry for
  `PRRef` (attempt counter monotonic, refusal counter head-scoped) for
  consistency with the proposal-backed loop.
