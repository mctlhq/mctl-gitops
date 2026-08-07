# Phase 0 agent dev-loop smoke test: issue-to-PR pipeline verification

## Context

Issue #18 is a deliberately minimal smoke test: "Smoke test issue for Phase 0
agent dev-loop verification." `mctl-academy` is Phase 0 — per `README.md`
("Status") and `PLAN.md` section 10, "the application is not built yet."
`PLAN.md` section 10 explicitly names this exercise: "Phase 0 also includes
one end-to-end agent smoke test, run before any real content depends on it:
open a throwaway `agents:intake` issue on `mctl-academy` -> confirm a
`DevLoopWorkflow` appears in the Temporal UI -> investigate CWFT produces a
proposal under `agents-state/mctl-academy/` -> send the `approve` signal ->
merge the `.status.yaml` flip PR -> implement CWFT opens a PR." This proposal
is that investigate-CWFT step; it exists to be approved and carried through
the remaining steps, not because `mctl-academy` currently needs a feature.

`PLAN.md` section 5 ("Approval is two steps, and skipping either fails
silently") is the sharpest documented edge in the pipeline: a Temporal
`approve` signal unblocks `wait_condition`, and a separate `.status.yaml`
`proposed -> accepted` flip (a gitops PR) is what the implement CWFT actually
triggers on. Signal without flip is a silent no-op (`skipped_reason`); flip
without signal blocks forever. The only way to prove both halves work, and
that the implement CWFT reaches an actual pull request against
`mctlhq/mctl-academy`, is to carry one real proposal all the way through —
which is what this proposal is for.

Because `mctl-academy` has no application code yet, the change this proposal
authorizes must be something that is safe to merge with zero product risk:
it must not touch `content/` (CODEOWNER- and evidence-CI-gated, per
`CONTENT-POLICY.md` and `CONTRIBUTING.md`), must not touch
`content/schemas/` or `.github/workflows/` (top review tier per
`claude-review.yml`'s scoring), and must not touch application logic that
does not exist yet. A small, self-contained, docs-only marker file satisfies
all of that while still exercising the full path: investigate CWFT -> human
review of this proposal -> two-step approval -> implement CWFT -> a real PR
-> `claude-review.yml` (a docs-only diff qualifies for its documented
fast-path: "docs or comments only ... approve with a one-line reason") ->
merge.

## User stories

- AS the mctl-academy maintainer I WANT one real issue to travel the full
  `issue -> DevLoopWorkflow -> investigate CWFT -> proposal -> two-step
  approval -> implement CWFT -> PR -> review -> merge` path SO THAT I trust
  the pipeline before any real content or feature proposal depends on it.
- AS the mctl-academy maintainer I WANT the smoke test's code change to be
  inert and reviewable at a glance SO THAT exercising the pipeline carries no
  product or content-gate risk.
- AS a future maintainer reading repo history I WANT the smoke test's
  artifact to be self-documenting SO THAT a stray file in the repo is
  explained rather than mysterious.

## Acceptance criteria (EARS)

- WHEN this proposal's `.status.yaml` is flipped from `proposed` to
  `accepted` AND the corresponding Temporal `approve` signal has been sent
  THE SYSTEM SHALL have the implement CWFT pick up this proposal and open a
  pull request against `mctlhq/mctl-academy`.
- WHEN the implement CWFT opens its pull request THE SYSTEM SHALL produce a
  diff containing exactly one new file, `SMOKE-TEST.md`, at the repository
  root, and no changes under `content/`, `content/schemas/`, or
  `.github/workflows/`.
- WHEN `claude-review.yml` runs against that pull request THE SYSTEM SHALL
  classify it as skip-ineligible-for-content-skip (it is not under
  `content/questions|lessons|sources`) but trivial (docs-only), and approve
  it via the "docs or comments only" fast path described in that workflow's
  prompt.
- THE SYSTEM SHALL give `SMOKE-TEST.md` content that names the source issue
  (#18), states its purpose (Phase 0 agent dev-loop verification per
  `PLAN.md` section 10), and does not claim any capability, schedule, or
  status of the product itself.
- WHILE this proposal is at `status: proposed` THE SYSTEM SHALL NOT have the
  implement CWFT act on it (per `PLAN.md`: "The implement CWFT triggers on
  `status: accepted` alone").
- IF the Temporal `approve` signal is sent without the `.status.yaml` flip
  THEN THE SYSTEM SHALL leave the `DevLoopWorkflow` parked at
  `wait_condition` with no implement CWFT run — the documented "flip without
  signal" failure mode.
- IF the `.status.yaml` flip is merged without the Temporal `approve` signal
  THEN THE SYSTEM SHALL have the implement CWFT run and exit with
  `skipped_reason` — the documented "signal without flip" silent no-op — and
  this SHALL be treated as an expected, informative outcome, not a defect in
  this proposal.
- THE SYSTEM SHALL branch this change as `chore/smoke-test-issue-18` (or
  equivalent, non-`_`-prefixed, per `CONTRIBUTING.md`) and merge with a merge
  commit, never a squash, per `CONTRIBUTING.md` and `CLAUDE.md`.

## Out of scope

- Any change to `content/`, `content/schemas/`, `.github/workflows/`, or any
  application code — none exists yet, and none is warranted by a smoke test.
- Registering `mctl-academy` in `mctl-agents/config/settings.py`
  (`SERVICES` / `NON_ROTATING_SERVICES`), creating
  `platform-gitops/agents-state/mctl-academy/`, or any other one-time
  pipeline-bootstrap step described in `PLAN.md` section 5 — those are
  prerequisites the smoke test exercises, not deliverables of it. This
  proposal assumes the directory this file lands in already demonstrates
  that bootstrap succeeded.
- Deliberately exercising the "signal without flip" and "flip without
  signal" failure modes end-to-end (`PLAN.md` section 10: "Both approval
  steps are exercised deliberately, in the wrong order at least once") is an
  operator action taken around this proposal, not a change requested inside
  it.
- Deployment of the `mctl-academy` service (`PLAN.md` section 8) — unrelated
  to whether the agent dev-loop itself works.
- Removing `SMOKE-TEST.md` after verification. Left as a task for the
  Rollback section below rather than assumed automatic.

## Open questions

- Whether `SMOKE-TEST.md` should be deleted in a follow-up PR once the smoke
  test is confirmed, or left permanently as a record. The issue does not
  say. This proposal takes the more conservative interpretation (leave it,
  document it as a permanent record) and records a rollback task for the
  alternative — see `tasks.md`.
- Whether "smoke test" here is meant to validate only the investigate step
  (this proposal existing at all is already evidence of that) or the entire
  chain through to a merged PR. The issue body is one sentence and does not
  say. This proposal takes the more complete interpretation — see `PLAN.md`
  section 10's own definition of the smoke test, which the issue is clearly
  invoking by using the `agents:intake` label and phrase "Phase 0 agent
  dev-loop verification" — and scopes acceptance criteria to the full chain.
