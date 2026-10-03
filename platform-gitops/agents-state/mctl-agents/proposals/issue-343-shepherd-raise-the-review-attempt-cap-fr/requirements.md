# Shepherd: raise the review-attempt cap from 3 to 5

## Context

The Tier 3 PR shepherd drives implementer-opened PRs to merge. When a review
bot leaves P1/P2 findings on the current head, `process_one` in
`orchestrator/run_shepherd.py` returns `address-review`, forks the implementer
with `--review-feedback`, re-triggers the reviewer, and counts the round in
`review_attempts:` inside the proposal's `.status.yaml`. Once the counter
reaches `MAX_REVIEW_ATTEMPTS` (`orchestrator/run_shepherd.py:303`, today `3`)
the next tick flips the proposal to terminal `review-stuck` and stops calling
the implementer.

Issue #343 asks for the cap to be `5`. The evidence given is from
`mctlhq/portfolio`: two proposals needed a single honest follow-up round and
landed, while two others hit 3/3 and required a human to unblock. A review that
finds something new *on the fix* is the normal shape of a second round, so three
slots leave no room for a legitimate third or fourth. The change is a constant
plus the prose and tests that quote it: the repository currently states the cap
as a bare `3` in a module docstring, a worked tick-by-tick example, an inline
comment, a test name and docstring, a `README.md` section heading, the
architecture fact file `docs/diagrams/archify/facts.yaml:214`, and a diagram
note in `docs/diagrams/archify/proposal-status.lifecycle.json:32`. Those must
move with the value, otherwise the code and its own documentation disagree and
`tools/diagram_facts.py` reports drift on the next weekly refresh.

The issue is explicit that this is not a fix for #342 (attempts spent on a
finding the approved proposal already excluded) and not a decision on the
exit-42 question from #336. It buys room for honest rounds only.

## User stories

- AS the Tier 3 shepherd I WANT five consecutive `address-review` rounds before
  giving up SO THAT a review that finds something new on the fix-up can still be
  resolved without human intervention.
- AS a platform operator I WANT the `review-stuck` note and every comment, test
  and doc to quote the cap from `MAX_REVIEW_ATTEMPTS` SO THAT reading any one of
  them tells me the real current limit.
- AS a maintainer changing the cap again later I WANT the boundary pinned by a
  test written against the constant SO THAT bumping the number does not require
  rewriting assertions by hand.
- AS the diagrams-refresh job I WANT `docs/diagrams/archify/facts.yaml` to match
  the code SO THAT the next run reports no false drift on
  `shepherd.max_review_attempts`.

## Acceptance criteria (EARS)

- WHEN `orchestrator/run_shepherd.py` is imported THE SYSTEM SHALL expose
  `MAX_REVIEW_ATTEMPTS == 5`.
- WHILE a proposal's `review_attempts` is strictly less than
  `MAX_REVIEW_ATTEMPTS` and `decide()` returns `address-review` THE SYSTEM SHALL
  call `apply_followup`, call `trigger_review`, increment `review_attempts` by
  one, and leave the proposal at `status: implemented`.
- IF `decide()` returns `address-review` and `review_attempts` is greater than
  or equal to `MAX_REVIEW_ATTEMPTS` THEN THE SYSTEM SHALL flip the proposal to
  terminal `review-stuck`, call neither `apply_followup` nor `trigger_review`,
  and write a note that interpolates `MAX_REVIEW_ATTEMPTS` so it reads "across 5
  follow-up attempts".
- WHEN `process_one` is driven through four consecutive `address-review` returns
  THE SYSTEM SHALL leave the proposal at `status: implemented` with
  `review_attempts == 4`, and on the fifth consecutive return SHALL still call
  the implementer (`review_attempts == 5`), and only on the sixth SHALL flip to
  `review-stuck` — a boundary that fails at the old value of `3`.
- WHILE the cap is exhausted by *deterministic* follow-up subprocess failures
  (`FollowupSubprocessError` with `transient=False`) THE SYSTEM SHALL keep
  counting one attempt per failure and flip to `review-stuck` only when the
  incremented counter reaches `MAX_REVIEW_ATTEMPTS`, unchanged in behaviour
  apart from the new bound.
- IF a follow-up subprocess fails transiently THEN THE SYSTEM SHALL NOT consume
  an attempt (existing behaviour, must not regress).
- WHEN the repository is grepped for the cap THE SYSTEM SHALL contain no test,
  comment, docstring or doc that states it as a bare `3`;
  `grep -rn "MAX_REVIEW_ATTEMPTS - 1\|attempts=3" tests/` SHALL return only
  assertions written against the constant.
- WHEN `python3 tools/diagram_facts.py` reads the repository THE SYSTEM SHALL
  report `shepherd.max_review_attempts` as `5` with no drift against
  `docs/diagrams/archify/facts.yaml`.
- WHEN `uv run pytest tests/test_run_shepherd.py` runs THE SYSTEM SHALL pass;
  `uv run pytest tests/`, `uv run ruff check orchestrator config tests` and
  `uv run mypy` SHALL also pass (the PR-validation gate).

## Out of scope

- Anything inside `decide()`. The cap deliberately lives in the outer state
  machine (`orchestrator/run_shepherd.py:300-303`) so the pure function stays
  trivially testable with hand-built fixtures.
- The `review_attempts` reset semantics on a new head SHA — today the counter is
  never reset by a fresh push (see
  `tests/test_run_shepherd.py:1775-1830`); that is its own decision.
- The exit-42 question from #336 (an implementer refusing work that contradicts
  the approved spec should arguably not consume an attempt). Noted in the issue
  as worth pairing later, not done here.
- #342 (attempts burned on findings the approved proposal already excluded).
  This change does not reduce those rounds and must not be read as closing it.
- Making the cap configurable via an environment variable.
- `SHEPHERD_TICKS_MAX` / `SHEPHERD_TICK_EVERY_POLLS` in
  `orchestrator/temporal/workflows/dev_loop.py` — they already allow enough
  ticks (12) for six shepherd evaluations.
- `SHEPHERD_BUDGET_USD` (`orchestrator/options.py:89`) — the per-tick budget is
  unchanged; only the number of ticks a wedged proposal may consume grows.

## Open questions

- The issue's line numbers are stale relative to the clone
  (`MAX_REVIEW_ATTEMPTS` is at `run_shepherd.py:303`, not `:280`; the worked
  example is at `:1768-1772`, not `:1643-1647`; the literal-`3` assertions are
  at `tests/test_run_shepherd.py:1706-1722`, not `:1427-1428`). The intent is
  unambiguous, so the implementer should locate the symbols by grep rather than
  by line number.
- The issue does not mention `docs/diagrams/archify/facts.yaml:214`,
  `docs/diagrams/archify/proposal-status.lifecycle.json:32`, `README.md:266-269`
  or the bare-`3` comments in `orchestrator/run_shepherd.py:16`,
  `orchestrator/run_shepherd.py:1789` and `tests/test_dev_loop_workflow.py:1690`.
  Acceptance criterion 1 ("no test or comment in the repository states the cap as
  a bare 3") is read here as covering all of them; they are in scope.
- Acceptance criterion 2 as literally written ("four consecutive
  `address-review` returns ... then a fifth that flips it to `review-stuck`")
  describes a cap of 4. Read against criterion 1 and 3 (cap `5`, note reading
  "across 5 follow-up attempts"), the intended boundary is five honest rounds
  then a flip on the sixth tick. This proposal implements cap `= 5` and asserts
  `review_attempts == 4` after four rounds, still `implemented`, per the
  criterion's first half — and drives the remaining rounds from the constant so
  the test is correct for either reading.
