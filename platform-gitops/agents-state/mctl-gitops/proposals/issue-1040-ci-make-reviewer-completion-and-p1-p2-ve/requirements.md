# CI: make reviewer completion and P1/P2 verdicts a real merge gate

## Context

`mctl-gitops#1038` merged at 13:18Z on one approving review while Agy (the
second, async reviewer wired via `.github/workflows/agy-review.yml`) did not
finish until 13:22Z — after merge — and found a real P2 (tag pagination,
now `#1039`). `platform-gitops/services/.../main-protection` (ruleset
`18465404`, per `docs/runbooks/github-app-scope-audit.md`) only requires one
approving review today; it has no concept of "did the configured reviewer
workflows finish" or "did they find a blocker," so an async reviewer can
answer after the PR is already gone.

Two reviewer workflows exist in this repo already:
`.github/workflows/claude-review.yml` (calls the reusable
`mctlhq/.github/.github/workflows/claude-review.yml`, posts as `claude[bot]`)
and `.github/workflows/agy-review.yml` (calls the reusable
`mctlhq/.github/.github/workflows/agy-review.yml` with `blocking: false`,
posts as `github-actions[bot]` carrying an `<!-- agy-review -->` marker).
Neither their completion nor their verdict is wired into branch protection —
`docs/soc2/compensating-controls.md` calls Claude's P1/P2 gate "a second
reader, not a second human," i.e. informational today. This matters because
it is the second documented instance of the same failure class: the sibling
`mctlhq/mctl-agents#240` proposal (`platform-gitops/agents-state/mctl-agents/
proposals/issue-240-fix-shepherd-aggregate-blocking-findings/`) independently
found that the Tier 3 shepherd's own merge decision has the identical gap —
Agy is not in its gating-bot set at all.

## User stories

- AS the repo owner I WANT merge blocked until every configured reviewer
  workflow has reported a terminal result for the exact PR head SHA SO THAT
  an async reviewer cannot find a blocker after the PR has already merged.
- AS the repo owner I WANT a P1 or P2 finding from any required reviewer to
  fail a single, deterministic check SO THAT I don't have to manually
  cross-reference multiple bot comments before merging.
- AS the repo owner I WANT a new push to invalidate the previous verdict SO
  THAT an approval or "clean" result from an earlier head can never wave
  through code that changed after it was reviewed.
- AS the repo owner I WANT a reviewer quota/tooling failure to be visibly
  blocking (not silently passing) SO THAT infrastructure flakiness cannot
  masquerade as a clean review.
- AS the repo owner I WANT one place to see why merge is blocked SO THAT I
  am not debugging branch protection by reading two bots' raw comments.

## Acceptance criteria (EARS)

- WHEN a pull request against `main` is opened, reopened, or synchronized
  THE SYSTEM SHALL run a single aggregate check (`review-gate`) that reports
  `pending`, `success`, or `failure` against that exact head SHA.
- WHEN `claude-review.yml` and `agy-review.yml` have both reached a terminal
  Actions run conclusion for the PR's current head SHA
  THE SYSTEM SHALL evaluate their posted verdicts and set `review-gate`'s
  final state.
- WHILE any required reviewer workflow has not yet reached a terminal run
  for the current head SHA THE SYSTEM SHALL keep `review-gate` `pending`
  and SHALL NOT report `success`.
- IF any required reviewer's terminal result for the current head SHA
  contains a P1 or P2 finding THEN THE SYSTEM SHALL set `review-gate` to
  `failure`.
- IF every required reviewer's terminal result for the current head SHA is
  clean (no P1/P2) THEN THE SYSTEM SHALL set `review-gate` to `success`.
- WHEN the PR receives a new push THE SYSTEM SHALL treat the previous head
  SHA's `review-gate` result as invalidated and SHALL re-evaluate against the
  new head SHA before `review-gate` can report `success` again.
- IF a required reviewer's run fails, times out, or never starts within a
  bounded window (quota exhaustion, tooling error, workflow never
  triggered) THEN THE SYSTEM SHALL set `review-gate` to `failure` with a
  message identifying the missing/failed reviewer and SHALL require an
  explicit, documented human override to proceed — it SHALL NOT default to
  `success`.
- THE SYSTEM SHALL evaluate only P1/P2 severity for `review-gate`'s pass/fail
  decision; P3 (and lower) findings SHALL NOT be folded into this check's
  verdict, preserving whatever P3 policy individual reviewer workflows
  already implement independently.
- WHEN `review-gate` is registered as a required status check on the
  `main-protection` ruleset THE SYSTEM SHALL make it the only
  ruleset-required reviewer-derived check, so heterogeneous reviewer
  workflows are not each made an independent branch-protection contract.

## Out of scope

- Mutating the `main-protection` ruleset's required-status-check list itself
  — the GitHub connector available to this investigation can read rulesets
  but not write them (per `CLAUDE.md`); registering `review-gate` as
  required is an explicit owner/admin action taken after this lands and is
  verified green on real PRs.
- Changing the reusable workflows in `mctlhq/.github`
  (`claude-review.yml`, `agy-review.yml`) — those are a different repo.
  This proposal's `review-gate` is designed to work against their current,
  unmodified output; any upstream marker-format change is a separate,
  coordinated proposal (see `design.md`'s Alternatives and Open questions).
- The Tier 3 shepherd's own merge-decision logic (`mctl-agents`'
  `orchestrator/run_shepherd.py`) and its Agy-gating gap — that is
  `mctlhq/mctl-agents#240`, a different repo and a different consumer of
  the same reviewer signals (an external polling agent vs. this repo's
  branch-protection check). The two should stay independently deployable.
- Extending `review-gate` to any repo other than `mctl-gitops`. The issue's
  "suggested shape" mentions org/repo rulesets in general; this proposal
  scopes the concrete implementation to this repo, where the regression
  (`#1038`) actually happened.
- P3-blocking policy for any repo — explicitly preserved as-is, not
  introduced or removed here.
- Building a generic reviewer-registry/plugin system. Two reviewers
  (Claude, Agy) are hard-configured; a third would be a follow-up.

## Open questions

- Agy's exact bot/actor login and literal severity-marker syntax are not
  visible from this clone — the reusable workflow lives in `mctlhq/.github`.
  `mctlhq/mctl-agents#240`'s investigation recorded the same gap and the
  same resolution: pull real API payloads (`gh api .../issues/<n>/comments`,
  `.../pulls/<n>/comments`, `.../reviews`) from a real mctl-gitops PR that
  Agy has reviewed before writing the parser, rather than guessing a
  format. Recorded assumption: reuse `github-actions[bot]` plus the
  `<!-- agy-review -->` marker as the actor/marker filter, matching what
  `review-watch`'s `SKILL.md` documents, and extend severity extraction
  defensively once a real payload is captured.
- Whether Agy should be `required` (gates on silence/timeout, like Claude)
  given this repo currently sets `blocking: false` for it. The issue's
  desired invariant says "every required reviewer workflow... must reach a
  terminal state before merge," which presupposes Agy becomes required.
  Recorded assumption: yes — flipping `agy-review.yml`'s `blocking` input
  to reflect the same policy `review-gate` enforces, so the two don't
  disagree, is in scope as a one-line config change alongside the new
  workflow.
- `docs/soc2/compensating-controls.md` and `docs/soc2/risk-register.md`
  both record `main-protection`'s `current_user_can_bypass=never` for this
  repo (verified 2026-09-03) — i.e. the repo owner cannot ruleset-bypass a
  stuck required check. `docs/soc2/emergency-change.md` still lists
  "ruleset bypass" as an allowed emergency action, which does not currently
  hold for this ruleset. Recorded assumption: the human-override path for a
  stuck/failed `review-gate` is an operator manually posting a `success`
  commit status for that SHA via `gh api repos/.../statuses/{sha}` (a plain
  repo write, not a ruleset bypass), logged the same way
  `emergency-change.md` already requires for other emergency actions. This
  does not require a ruleset change and should be written up as an
  amendment to `emergency-change.md` alongside this proposal so the gap
  between the two docs is closed rather than left implicit.
- Exact timeout window for "reviewer never responded." Recorded assumption:
  45 minutes, matching `deploy-signal.py`'s existing
  `DEFAULT_GRACE_MINUTES` precedent for "how long is a legitimate CI/GitOps
  delay vs. a stall worth alerting on" in this same repo.
