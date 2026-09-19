# Adopt proposal-less same-repo PRs with blocking reviews into the shepherd review-feedback loop

## Context

Today every PR the Tier 3 shepherd can drive must be anchored to a proposal on
disk: `_discover_refs` in `orchestrator/run_shepherd.py` globs
`agents-state/<service>/proposals/<slug>/.status.yaml` and only builds a
`ProposalRef` for statuses in `SHEPHERD_INPUT_STATUSES`
(`{implemented, review-fixing, in-progress}`). A pull request opened by hand —
or by any tool that is not `run_implementer.py` — has no `.status.yaml`, so it
is invisible to discovery. When `claude[bot]` or the Codex Review connector
leaves blocking P1/P2 findings on such a PR, nothing automated owns the fix
loop and the PR sits until a human drives it. `mctlhq/mctl-gitops#1073` is the
motivating example.

ADR-010 (`docs/adr/010-lifecycle-ownership-contract.md`) already names this as
pilot path 4 — "proposal-less adopted PR (#334) … the *shape* exists from
phase 1; the *discovery* of adoptable PRs is #334's own work" — and explicitly
forbids the shortcut of inventing a proposal to fit the existing discovery
model, because "a store keyed on `agents-state/<service>/proposals/<slug>/`
cannot represent a PR that has no proposal". This proposal therefore adds a
second, lightweight durable record — a `PRRef` written to
`agents-state/<service>/adopted-prs/pr-<number>/.prref.yaml` — that represents
the PR lifecycle directly, plus the discovery pass that creates it and the
plumbing that lets the existing `run_implementer.py --review-feedback` path act
on a branch that is not `feat/agents-<slug>`.

The whole feature ships behind a default-off flag. The companion gitops change
(`mctlhq/mctl-gitops#1278`) that makes the shepherd CWFT stage `adopted-prs/**`
back into gitops is a separate rollout, so until it lands a `.prref.yaml`
written inside the gitops worktree is discarded at the end of each tick.

## User stories

- AS the platform operator I WANT a same-repository mctlhq PR that has
  current-head blocking findings and no proposal to be adopted automatically
  SO THAT the review-fix loop reaches PRs that were not created by the
  implementer.
- AS the platform operator I WANT adoption to be refused whenever a live
  DevLoop, an existing proposal, or a repository steward already owns the PR
  SO THAT exactly one actor mutates a PR branch at a time.
- AS a repository maintainer I WANT adoption to be opt-in per repository and
  to grant remediation only, never merge authority, SO THAT the repository's
  own merge policy stays authoritative.
- AS a reviewer of an incident I WANT every adoption and every fix attempt to
  record repo, PR, head SHA, triggering reviewer and finding, attempt number,
  owner type and outcome SO THAT the loop's behaviour is reconstructible from
  the record alone.
- AS an external contributor I WANT fork PRs to be untouchable by this loop
  SO THAT the platform never pushes to a repository it does not own.

## Acceptance criteria (EARS)

Discovery and adoption

- WHILE `SHEPHERD_ADOPT_PRS` is unset or false THE SYSTEM SHALL perform no
  adoption discovery, create no `.prref.yaml`, and leave `run_shepherd`'s
  observable behaviour byte-identical to today.
- WHEN adoption is enabled and the shepherd runs a sweep tick THE SYSTEM SHALL
  consider only open pull requests in repositories that are both listed in
  `config.settings.SERVICES` and present in the `SHEPHERD_ADOPT_REPOS`
  allowlist (default empty).
- WHEN a candidate PR's current head carries at least one P1 or P2 finding from
  a bot in `run_shepherd.GATING_BOTS`, computed through
  `CodexReview.fresh_findings_p1_p2(pr.head_sha, pr.head_pushed_at)`, THE
  SYSTEM SHALL treat the PR as adoptable subject to the ownership and safety
  gates below.
- IF a candidate PR has no fresh P1/P2 finding on its current head THEN THE
  SYSTEM SHALL NOT adopt it and SHALL NOT create a `.prref.yaml`.
- WHEN a PR is adopted THE SYSTEM SHALL write
  `agents-state/<service>/adopted-prs/pr-<number>/.prref.yaml` with
  `kind: pr-ref`, `repo`, `pr`, `number`, `head_sha`, `head_branch`,
  `owner_type`, `status: adopted`, zeroed attempt counters and an
  `evidence:` list whose first entry records the adoption.
- WHEN a `.prref.yaml` already exists for a PR THE SYSTEM SHALL reuse it rather
  than adopt again, and SHALL leave the file byte-identical when nothing about
  the PR changed.

Ownership and exclusivity

- IF any `.status.yaml` under the state dir records a `pr:` URL equal to the
  candidate PR's URL THEN THE SYSTEM SHALL refuse adoption, because a proposal
  already owns that PR.
- IF the candidate PR's head branch matches the implementer's deterministic
  prefix `feat/agents-` THEN THE SYSTEM SHALL refuse adoption; such a PR
  belongs to the proposal path (issue #239), not to this one.
- IF `run_shepherd._dev_loop_owns` reports a live `DevLoopWorkflow` for the
  entity THEN THE SYSTEM SHALL refuse adoption.
- IF `run_shepherd._service_mode(service)` resolves to `SKIP` THEN THE SYSTEM
  SHALL refuse adoption, because the repository is owned end-to-end by another
  PR lifecycle (`pr-steward`).
- WHILE `orchestrator.lifecycle.rollout.computes_new_answer()` is true THE
  SYSTEM SHALL consult the ownership store for
  `(pull-request, <owner>/<repo>#<n>, review-remediation)` before adopting, and
  IF an ACTIVE row exists whose owner is not this shepherd THEN THE SYSTEM
  SHALL refuse adoption.
- IF the ownership store cannot answer THEN THE SYSTEM SHALL refuse adoption
  and record the reason, because adoption is a discretionary action and an
  unreachable store means UNKNOWN, never UNOWNED.

Safety

- IF a candidate PR is cross-repository (a fork: `isCrossRepository` true, or
  `headRepositoryOwner.login` different from the base repository owner) THEN
  THE SYSTEM SHALL refuse adoption and SHALL never invoke the implementer
  against it.
- WHILE a PR is driven through an adoption record THE SYSTEM SHALL resolve its
  shepherd mode to `FIX_ONLY`, so `decide()` can only ever return
  `defer-merge` and `merge_pr()` is never called for it.
- WHEN the shepherd acts on an adoption record THE SYSTEM SHALL pin every
  decision and every mutation to the head SHA read in that same tick, and IF
  the recorded `head_sha` differs from the live head THEN THE SYSTEM SHALL
  reset the refusal counter and re-read findings before acting.
- IF a finding predates the PR's `head_pushed_at` THEN THE SYSTEM SHALL NOT let
  it trigger a fix attempt.

Remediation loop

- WHEN an adoption record carries fresh blocking findings THE SYSTEM SHALL
  invoke `run_implementer.py --review-feedback <bundle>` against the PR's own
  head branch, without creating a branch and without opening a pull request.
- WHEN the implementer pushes a follow-up commit THE SYSTEM SHALL post
  `@claude review` via `trigger_review()` so the next tick evaluates a fresh
  review on the new head.
- WHEN a fix attempt completes THE SYSTEM SHALL increment `review_attempts` on
  the `.prref.yaml` using the same charging rules `process_one` already applies
  to proposals (refusals, harness failures and fenced claims are not charged).
- IF `review_attempts` reaches `MAX_REVIEW_ATTEMPTS`, or `harness_failures`
  reaches `MAX_HARNESS_FAILURES`, or `refusals` reaches `MAX_REFUSALS`, THEN
  THE SYSTEM SHALL flip the record to terminal `review-stuck` with the evidence
  that produced it.
- WHEN the PR is merged or closed out of band THE SYSTEM SHALL flip the record
  to terminal `merged` or `rejected` and stop acting on it.
- WHEN the current head has no fresh blocking findings THE SYSTEM SHALL record
  the clean outcome and take no mutating action.

Evidence and bounds

- WHEN the system adopts a PR or completes a fix attempt THE SYSTEM SHALL
  append an evidence entry containing `at`, `repo`, `pr`, `head_sha`,
  `reviewer`, `finding` (truncated), `attempt`, `owner_type` and `outcome`.
- WHILE adoption is enabled THE SYSTEM SHALL process at most
  `SHEPHERD_ADOPT_MAX_PRS_PER_TICK` adoption records per tick (default 1), so
  the loop stays bounded even where the record is not yet durable.
- WHEN adoption is enabled and the shepherd starts THE SYSTEM SHALL print a
  warning that `adopted-prs/**` is not staged back to gitops until
  `mctlhq/mctl-gitops#1278` lands, so an operator reading the log knows the
  attempt counters are not durable yet.

## Out of scope

- Any change to a sibling repository. The shepherd ClusterWorkflowTemplate
  change that stages `adopted-prs/**` into the gitops commit is
  `mctlhq/mctl-gitops#1278` and ships separately.
- Turning adoption on in production. Enablement happens after both this change
  and `mctlhq/mctl-gitops#1278` are merged.
- Direct implementer PRs that already have a proposal but lose shepherd
  ownership (`mctlhq/mctl-agents#239`).
- Granting the shepherd merge authority over adopted PRs, or changing
  `NEVER_MERGE_SERVICES`, branch protection, or CODEOWNERS.
- Adopting fork PRs, closed PRs, draft PRs, or PRs with findings only from
  non-gating reviewers.
- Implementing the ADR-010 reconciler hand-off (`reconciler` -> `shepherd`
  owner transition); this change acquires ownership directly as `shepherd`
  behind the existing rollout gate.
- Migrating existing proposals to the `PRRef` shape.

## Open questions

- ADR-010 pilot path 4 names `reconciler` as the owner at adoption, handing off
  to `shepherd`. That hand-off lives in the Temporal reconciler
  (`orchestrator/lifecycle/reconciler.py`, phase 3), which cannot run the
  review-feedback path. Interpretation taken: the shepherd adopts directly as
  `owner_type: shepherd` and records `policy_ref` from
  `lifecycle.policy.policy_ref_for`, leaving the reconciler hand-off for the
  phase-3 integration the ADR already defers "after #334".
- The issue's motivating example cites blocking findings from "Claude and agy".
  `agy` is not a bot login in `run_shepherd.GATING_BOTS` and the issue's own
  scope says "a review bot". Interpretation taken: only `GATING_BOTS` findings
  trigger adoption; widening the reviewer set is a separate change
  (`mctlhq/mctl-agents#240` aggregates findings across reviewers).
- The issue writes the record path as `adopted-prs/<pr>/.prref.yaml`.
  Interpretation taken: `adopted-prs/pr-<number>/.prref.yaml`, so the directory
  name is also usable as the `--slug`-shaped identifier the implementer and the
  claim identity already expect.
- Whether an adopted PR should ever reach `merge` for a repository that is
  neither `SKIP` nor in `NEVER_MERGE_SERVICES`. Interpretation taken: no —
  every adoption record is `FIX_ONLY`, per "adoption grants remediation only,
  not merge authority".
- `#292`'s decision (options 2 + 3) makes the review-feedback path reachable
  for steward-owned repositories. Whether that is expressed by moving
  `mctl-gitops` from `SHEPHERD_SKIP_SERVICES` to `SHEPHERD_FIX_ONLY_SERVICES`
  is a gitops env change outside this repository. Interpretation taken: this
  change refuses adoption while a repo resolves to `SKIP` and requires the
  operator to move it to fix-only first; no env default is changed here.
