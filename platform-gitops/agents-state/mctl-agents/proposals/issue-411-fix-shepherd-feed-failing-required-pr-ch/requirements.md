# Feed failing required PR checks into the shepherd remediation loop

## Context

The Tier 3 shepherd (`orchestrator/run_shepherd.py`) decides what to do with an
open implementer PR from two inputs only: the PR shape returned by
`_fetch_pr_snapshot` and the semantic review signal returned by
`read_codex_review`. `decide()` (L1816-1890) builds its blocker set exclusively
from `codex_review.fresh_findings_p1_p2(...)`. Required CI is represented by a
single coarse boolean, `PRSnapshot.checks_green`, which is itself derived from
`statusCheckRollup.state` plus `mergeStateStatus` heuristics (L1445-1465) and is
consulted only as a late `return ("wait", None)` guard at L1883.

The consequence is the wedge observed on mctlhq/mctl-agents#409 (proposal
`mctl-agents#364`, head `143312e4`, `status: implemented`,
`review_attempts: 5`): Claude APPROVED with zero P1/P2, `security`, tests and
the Docker smoke check were green, but the required `PR validation / lint` check
failed with a real `mypy` type error in `orchestrator/run_implementer.py:3185`.
With no fresh review finding, `decide()` falls through to the merge arm, hits
`pr.merge_state_status not in MERGEABLE_STATES` (GitHub reports `BLOCKED` when a
required check is red) and returns `("wait", None)` at L1880-1882. `wait`
advances no counter, writes no evidence and never reaches the
`MAX_REVIEW_ATTEMPTS`/`review-stuck` boundary in `process_one` (L2467-2477), so
the PR ticks forever with an actionable, machine-readable, one-line type error
that nobody hands to the implementer.

This proposal makes the shepherd's current-head merge gate the union of
semantic-review blockers and failing *required* check runs on the exact head
SHA, and routes the actionable subset of those check failures into the existing
`--review-feedback` implementer path as first-class CI evidence — not disguised
as review comments. It is scoped to required CI/check runs; blocking findings
from required semantic reviewers such as Agy remain the subject of #240.

## User stories

- AS the platform operator I WANT a PR whose required lint/typecheck/test check
  is red to be repaired by the same review-feedback loop that repairs review
  findings SO THAT a one-line `mypy` error does not strand a finished proposal
  in `implemented` indefinitely.
- AS the Tier 2 implementer I WANT the failing check's name, job, step, concise
  failure text, run URL and head SHA delivered in the same bundle as review
  findings SO THAT I can fix the defect without re-deriving it from GitHub.
- AS the platform operator I WANT an infrastructure failure (cancellation,
  runner outage, timeout) to be retried and then escalated, never rewritten as a
  code defect SO THAT the agent does not burn paid attempts "fixing" a flaky
  runner.
- AS the platform operator I WANT a proposal whose current-head blockers survive
  the attempt budget to land in `review-stuck` naming the unresolved reviewer
  and check blockers SO THAT I get a triage signal instead of a silent wait.
- AS a repository owner I WANT advisory (non-required) checks to stay advisory
  SO THAT an experimental workflow cannot start gating merges by accident.

## Acceptance criteria (EARS)

Reading required check state

- WHEN the shepherd evaluates an open PR THE SYSTEM SHALL read check-run and
  commit-status state pinned to `PRSnapshot.head_sha`, and SHALL discard any
  check whose associated commit OID differs from that head SHA.
- WHEN a check context reports its required-ness THE SYSTEM SHALL classify it as
  required from that signal, and SHALL fall back to the base branch's protection
  required-context list when the per-context signal is absent.
- IF neither the per-context required-ness signal nor the branch-protection
  context list is available for a check THEN THE SYSTEM SHALL treat that check
  as advisory (non-blocking) and SHALL record that the requiredness was
  undetermined.
- WHILE a required check on the current head is still `QUEUED` or `IN_PROGRESS`
  THE SYSTEM SHALL treat the CI signal as incomplete and SHALL NOT emit
  remediation evidence for it.

Blocking the merge gate

- WHEN at least one required check on the current head has concluded in a
  failing state THE SYSTEM SHALL NOT return a `merge` or `defer-merge` decision,
  even when every semantic reviewer has APPROVED and no fresh P1/P2 finding
  exists.
- WHILE the required-check probe cannot be completed (API error, rate limit,
  malformed response) THE SYSTEM SHALL fail closed on merging — no `merge` and
  no `defer-merge` decision SHALL be returned on that tick.
- WHEN no required check on the current head is failing and the semantic review
  is clean THE SYSTEM SHALL preserve today's merge behaviour, including the
  `MERGEABLE_STATES` gate and the `SHEPHERD_MERGE_SETTLE_MIN` settling window.
- WHEN a check that is not required fails THE SYSTEM SHALL NOT add it to the
  blocker set and SHALL NOT let it prevent a merge.

Normalising remediation evidence

- WHEN a failing required check is classified as an actionable code-quality
  failure (lint, typecheck, unit/integration tests, build/compile, security
  scan with file-anchored findings) THE SYSTEM SHALL normalise it into a CI
  blocker record carrying: check name, workflow name, failing job, failing step
  (when derivable), conclusion, a bounded concise failure excerpt, the run/check
  URL and run identity, and the head SHA it was observed on.
- WHEN normalising a failing check THE SYSTEM SHALL prefer file/line-anchored
  check-run annotations for the failure excerpt and SHALL fall back to the check
  run's output summary/text, bounding the retained text so a single check cannot
  dominate the bundle.
- WHEN the shepherd invokes the implementer with `--review-feedback` THE SYSTEM
  SHALL include the CI blocker records in the same bundle as the semantic
  findings, under a distinct key, and SHALL NOT represent a check failure as a
  review comment or assign it a P1/P2 severity.
- WHEN the implementer renders a bundle that contains CI blocker records THE
  SYSTEM SHALL render them in their own clearly labelled section, distinct from
  the code-review findings section.
- WHEN a bundle contains no CI blocker records THE SYSTEM SHALL render and
  behave exactly as it does today.

Staleness and self-clearing

- WHEN a new commit is pushed to the PR branch THE SYSTEM SHALL re-derive the
  CI blocker set against the new head SHA only, and SHALL ignore every check
  result observed on any earlier head.
- WHEN a follow-up push makes a previously failing required check succeed on the
  new head THE SYSTEM SHALL drop the corresponding CI blocker with no operator
  action and SHALL clear any durable CI-blocker projection written into
  `.status.yaml`.

Infrastructure failures and probe outages

- WHEN a required check on the current head concludes as `CANCELLED`,
  `TIMED_OUT`, `STALE`, `ACTION_REQUIRED`, `SKIPPED`, `NEUTRAL`, or a startup
  failure THE SYSTEM SHALL classify it as non-actionable infrastructure and
  SHALL NOT include it in the implementer's remediation evidence.
- WHEN a required check fails and its failure text matches the infrastructure
  signature set (runner lost, network/registry unreachable, rate limit,
  step timeout, out of disk) with no file-anchored annotations THE SYSTEM SHALL
  classify it as non-actionable infrastructure.
- WHEN the only current-head blockers are non-actionable infrastructure failures
  THE SYSTEM SHALL re-run the failing required workflow run at most
  `SHEPHERD_CI_INFRA_RERUN_MAX` times per head SHA, SHALL NOT charge a review
  attempt for those re-runs, and SHALL count them on a dedicated per-head
  counter.
- IF the infrastructure re-run budget for the current head is exhausted while a
  required check is still failing non-actionably THEN THE SYSTEM SHALL transition
  the proposal to `review-stuck` with a note naming the check, stating that the
  failure was classified as infrastructure and that the proposal is blameless.
- IF the required-check probe fails on `SHEPHERD_CI_PROBE_FAILURES_MAX`
  consecutive ticks THEN THE SYSTEM SHALL transition the proposal to
  `review-stuck` with a note naming the probe outage and stating that
  `review_attempts` was never charged.

Attempt budget and terminal state

- WHEN actionable CI blockers exist on the current head THE SYSTEM SHALL route
  them through the existing `address-review` decision, the existing
  `apply_followup` subprocess, and the existing `MAX_REVIEW_ATTEMPTS` budget,
  and SHALL NOT introduce a second remediation loop or a second attempt counter
  for them.
- IF `review_attempts` has reached `MAX_REVIEW_ATTEMPTS` while current-head
  blockers (reviewer findings, required check failures, or both) remain THEN THE
  SYSTEM SHALL transition the proposal to `review-stuck` with a note that
  enumerates the unresolved blockers by reviewer and by check name.
- WHILE a proposal is being remediated for CI blockers THE SYSTEM SHALL keep the
  existing exit-code classification of the implementer subprocess (refused /
  fenced / harness / deterministic / transient) and its existing counter
  semantics unchanged.
- WHEN the shepherd emits its per-tick operator log line THE SYSTEM SHALL
  include the count of required-check blockers and their check names.

## Out of scope

- Aggregating blocking findings from required semantic reviewers such as Agy
  into the blocker set — that is #240. This proposal treats only CI/check runs.
- Any change to branch protection, rulesets, or any mechanism that would let the
  shepherd merge a PR GitHub considers unmergeable.
- A second CI-fixing agent, tier, cron, or workflow. The existing review-feedback
  implementer path is the only remediation channel.
- Reading raw job logs via `gh run view --log-failed`. Only check-run
  annotations and check-run output text are consulted in this proposal.
- Changing `MAX_REVIEW_ATTEMPTS` (5, set by #343) or the settling window.
- The proposal-less adopted-PR discovery path in `orchestrator/pr_adoption.py`
  beyond whatever it inherits for free from a widened `decide()` payload.
- Durable ownership handoff of the review loop (#239) and the `PRRef` adoption
  roadmap (#334) beyond keeping both compiling and passing.

## Open questions

- Should an actionable required-check failure produce an `address-review`
  decision when the primary reviewer has *not yet* responded on the current
  head? Today `decide()` returns `wait` at L1843-1845 before any blocker is
  computed. Proceeding with the conservative reading: the CI blocker set is
  computed at the same point as the review blocker set, i.e. after
  `has_responded`, so one remediation round carries all evidence for a head.
  The cost is that a PR whose reviewer never responds while CI is red still
  waits — the same pre-existing wedge, not a new one.
- GitHub exposes per-context required-ness on the status-check rollup, but that
  field is not available on every schema version or for every ruleset shape.
  Proceeding with: per-context signal first, branch-protection required-context
  list second, advisory otherwise, with `mergeStateStatus` retained as the
  fail-closed merge backstop.
- The actionable/infrastructure classifier is heuristic. Proceeding with a
  conclusion-based classification plus an annotation-presence test plus a small
  denylist of infrastructure signatures, all configurable, defaulting to
  "infrastructure" only when the evidence positively says so — an unclassifiable
  failure is treated as actionable, because handing the implementer a real
  defect it cannot fix costs one attempt, while silently treating a real defect
  as infrastructure restores the wedge this proposal exists to remove.
- Whether the normalised CI evidence should also be mirrored into a durable
  `ci_blockers` projection in `.status.yaml` for operator audit, or only into the
  bundle and the `review-stuck` note. Proceeding with a minimal head-pinned
  projection (check names plus head SHA) so the "cleared automatically" behaviour
  is observable on disk.
