# Design: issue-343-shepherd-raise-the-review-attempt-cap-fr

## Current state

**The constant.** `orchestrator/run_shepherd.py:300-303`:

```python
# Outer-loop cap on consecutive address-review attempts before giving up
# and flipping to `review-stuck`. Lives here (NOT in decide()) so the
# pure function stays trivially testable. See design.md L122-142.
MAX_REVIEW_ATTEMPTS = 3
```

**The state machine.** `decide(pr, review)` is pure and never sees the counter.
The cap is enforced in `process_one`, in the `address-review` branch
(`orchestrator/run_shepherd.py:1766-1872`):

1. `orchestrator/run_shepherd.py:1767-1772` carries a tick-by-tick walk-through
   written against the old value:
   `tick 1: counter=0 -> call -> counter=1` … `tick 4: counter=3 -> flip to
   review-stuck, NO call`.
2. `:1773-1782` — pre-check: `if ref.review_attempts >= MAX_REVIEW_ATTEMPTS`,
   `update_status(ref, "review-stuck", ...)` with a note that already
   interpolates the constant (`f"{MAX_REVIEW_ATTEMPTS} follow-up attempts; "`),
   and returns without calling `apply_followup` or `trigger_review`.
3. `:1784-1795` — comment explaining transient vs. deterministic classification;
   line 1789 says "must NOT burn one of the **three** slots".
4. `:1796-1851` — `apply_followup` in a `try`. `FollowupSubprocessError` with
   `transient=True` returns `wait` and consumes nothing; `transient=False`
   increments and, at `new_attempts >= MAX_REVIEW_ATTEMPTS`, flips to
   `review-stuck`.
5. `:1857-1871` — happy path: `trigger_review(pr)`, then
   `update_status(ref, "review-fixing", review_attempts=ref.review_attempts + 1)`
   followed by `update_status(ref, "implemented")` so the next tick re-evaluates
   against the new head SHA.

`review_attempts` is cleared on every terminal flip — `merge`
(`:1897-1905`), `flip-to-merged`, `flip-to-rejected` — via
`review_attempts=None`. It is **not** reset by a fresh head push
(`tests/test_run_shepherd.py:1775-1830` pins counter-unchanged-on-wait).

**Other places that quote the cap as a bare `3`:**

- `orchestrator/run_shepherd.py:16` (module docstring): "The 3-attempt cap on
  follow-up loops lives in the OUTER state machine".
- `orchestrator/run_shepherd.py:1789`: "one of the three slots".
- `orchestrator/run_implementer.py:115-120` refers to "the
  `MAX_REVIEW_ATTEMPTS` budget slots" — already symbolic, no change needed.
- `tests/test_run_shepherd.py:8` (module docstring): "T6: outer-loop 3-attempt
  cap".
- `tests/test_run_shepherd.py:1663-1731`:
  `test_outer_loop_review_stuck_after_three_attempts` — a section banner
  "T6: outer-loop 3-attempt cap", a docstring repeating ticks 1-4, hard-coded
  assertions `== 1`, `== 2`, `== 3`, manual `ref.review_attempts = 2` / `= 3`
  reloads, and `assert len(apply_calls) == 3` / `len(trigger_calls) == 3`.
- `tests/test_dev_loop_workflow.py:1686-1694`
  (`test_shepherd_ticks_stop_at_the_cap` docstring): "flips review-stuck after 3
  address-review attempts".
- `README.md:266-272`: a section headed "**Three-attempt cap.**" — "After three
  consecutive `address-review` ticks … the next tick flips the proposal to
  `status: review-stuck`".
- `docs/diagrams/archify/facts.yaml:214`: `max_review_attempts: '3'`.
- `docs/diagrams/archify/proposal-status.lifecycle.json:32`: "The shepherd
  addresses P1/P2 findings up to three times".

**The drift guard.** `tools/diagram_facts.py:62` scrapes the constant with
`r"^MAX_REVIEW_ATTEMPTS = (\d+)"` into `facts["shepherd"]["max_review_attempts"]`
and diffs it against `facts.yaml`. Drift is exit code 3 — a *report*, not a
failure — consumed by `.github/workflows/diagrams-refresh.yml`.
`tests/test_diagram_facts.py:128-143` only asserts the regexes still match
(no `<not found>`), so it passes either way; leaving `facts.yaml` stale would
simply hand the weekly refresh job a spurious drift item.

**The counter's ceiling in the durable loop.** `DevLoopWorkflow` ticks the
shepherd every `SHEPHERD_TICK_EVERY_POLLS = 8` polls of
`MERGE_POLL_INTERVAL = 30 min` (≈4 h), up to `SHEPHERD_TICKS_MAX = 12`
(`orchestrator/temporal/workflows/dev_loop.py:125-146, 1170-1171`). Five honest
rounds plus the flip need six ticks, well inside 12 — so no Temporal constant has
to move. The standalone `mctl-agents-shepherd` cron is not tick-limited at all.

## Proposed solution

A single-value change plus a consistency sweep. No structural change: the cap
stays a module constant in the outer state machine, exactly where the issue says
it belongs.

1. **`orchestrator/run_shepherd.py:303`** — `MAX_REVIEW_ATTEMPTS = 3` → `5`.
   Extend the comment above it with one sentence recording *why* five (#343:
   three left no room for a review that finds something new on the fix) and the
   explicit non-claim (this does not address #342's dishonest rounds).

2. **`orchestrator/run_shepherd.py:1767-1772`** — rewrite the worked example so
   it matches the new cap. Keep the shape (it is the clearest statement of the
   off-by-one) but make the terminal tick generic rather than a hard-coded
   `tick 4`:

   ```
   #   tick 1: counter=0 -> call -> counter=1
   #   ...
   #   tick 5: counter=4 -> call -> counter=5
   #   tick 6: counter=5 == MAX_REVIEW_ATTEMPTS -> flip to review-stuck, NO call
   ```

   Phrase the last line against `MAX_REVIEW_ATTEMPTS` so the next bump only
   touches the elided middle.

3. **Symbolic prose everywhere else.** `run_shepherd.py:16` → "The
   `MAX_REVIEW_ATTEMPTS` cap on follow-up loops lives in the OUTER state
   machine"; `run_shepherd.py:1789` → "one of the `MAX_REVIEW_ATTEMPTS` slots";
   `tests/test_run_shepherd.py:8` and the T6 banner → "outer-loop
   `MAX_REVIEW_ATTEMPTS` cap"; `tests/test_dev_loop_workflow.py:1690` → "flips
   review-stuck after `MAX_REVIEW_ATTEMPTS` address-review attempts". Preferring
   the symbol over the digit is what stops this issue recurring on the next bump.

4. **`README.md:266-272`** — retitle to "**Review-attempt cap.**" and state
   "after five consecutive `address-review` ticks". This is operator-facing
   narrative prose where a concrete number is the point, so the digit stays —
   but the heading loses the hard-coded word "Three" so only one number needs
   editing next time.

5. **`tests/test_run_shepherd.py:1663-1731`** — rewrite T6 as
   `test_outer_loop_review_stuck_at_max_review_attempts`, driven by the
   constant. Loop `for i in range(1, run_shepherd.MAX_REVIEW_ATTEMPTS + 1)`,
   asserting `decision == "address-review"`, `review_attempts == i`, and
   `status == "implemented"` on each pass, reloading
   `ref.review_attempts = read_status(ref)["review_attempts"]` between ticks the
   way the cron does. After the loop, one more `process_one` must return
   `review-stuck` with `status == "review-stuck"`, and
   `len(apply_calls) == len(trigger_calls) == run_shepherd.MAX_REVIEW_ATTEMPTS`.

   Add the explicit boundary assertion the issue asks for *inside* that loop
   rather than as a separate test: at `i == 4`, assert the proposal is still
   `implemented` with `review_attempts == 4` and that no `review-stuck` flip has
   happened. Guard it with `if run_shepherd.MAX_REVIEW_ATTEMPTS >= 4` so the
   loop stays honest if the constant is ever lowered, and add a standalone
   `assert run_shepherd.MAX_REVIEW_ATTEMPTS == 5` regression test
   (`test_max_review_attempts_is_five`, citing #343) as the one place the literal
   `5` is allowed to appear. That pairing is what makes the suite fail at the old
   value — a purely constant-driven test would pass at `3` as well, which is the
   trap in acceptance criterion 2.

6. **Note text.** `run_shepherd.py:1775-1782` already interpolates
   `MAX_REVIEW_ATTEMPTS`, so criterion 3 holds for free — but pin it: assert the
   `review-stuck` note contains `"across 5 follow-up attempts"`-equivalent text
   built from the constant (`f"{run_shepherd.MAX_REVIEW_ATTEMPTS} follow-up
   attempts"`). Today's wording is "Codex P1/P2 findings persisted across N
   follow-up attempts; human triage required." — keep it and only assert on the
   interpolated fragment, so the test does not pin the whole sentence.

7. **Architecture facts.** `docs/diagrams/archify/facts.yaml:214` →
   `max_review_attempts: '5'` and
   `docs/diagrams/archify/proposal-status.lifecycle.json:32` → "up to five
   times". Doing it in this PR keeps the weekly diagrams-refresh run at "no
   drift"; both are one-token edits and the alternative is a follow-up PR
   authored by an agent for the same two tokens.

## Alternatives

**Make the cap configurable (`SHEPHERD_MAX_REVIEW_ATTEMPTS` env var), mirroring
`SHEPHERD_MERGE_SETTLE_MIN` at `run_shepherd.py:311-330`.** Tempting — it would
let an operator tune per-repo without a release. Dropped: the issue asks for a
value change, not a knob; an env-driven cap makes `tools/diagram_facts.py`'s
scrape ambiguous (code default vs. deployed value) and splits the cap across the
repo and gitops values, so "what is the cap" stops having one answer. The
settle-window precedent exists because that value is genuinely per-environment;
this one is a product decision.

**Leave the comments and the test literals alone and change only the constant.**
Smallest diff, but not viable: the current T6 asserts `review_attempts == 3` at
`tests/test_run_shepherd.py:1714` and expects the fourth tick to flip, so the
suite fails outright at `5`. Even with a minimal patch to that one test, the
repository would be left
with a worked example and a README section describing a cap the code no longer
has, which is exactly the failure mode the issue calls out. Dropped.

**Lower the cost of a round instead of raising the cap** — e.g. suppress
re-litigation of excluded findings (#342) or stop counting exit-42 refusals
(#336). Strictly better use of the same five rounds, and the issue says so. But
both are separate decisions with their own design work, and neither unblocks the
two portfolio proposals that hit 3/3 on honest rounds. Dropped as out of scope,
recorded in `requirements.md` so the link survives.

**Reset `review_attempts` on a new head SHA instead of raising the cap.** Would
effectively make the cap "consecutive rounds with no progress", which is closer
to the intent. Dropped: the issue explicitly lists reset semantics as out of
scope, and the change is behaviourally much larger — a reviewer that re-finds
something on every push would never hit the cap, turning a bounded loop into an
unbounded one.

## Platform impact

- **Migrations:** none. `review_attempts:` is an integer already present in
  `.status.yaml`; nothing in the on-disk schema changes and no proposal needs
  rewriting.
- **Backward compatibility:** proposals mid-loop at `review_attempts: 3` are
  currently wedged at `review-stuck` (terminal) and stay there — the new cap does
  **not** resurrect them; a human or `mctl_trigger_reconcile` still has to move
  them back to `implemented`. Proposals sitting at `review_attempts: 1` or `2`
  simply gain extra rounds on the next tick. Worth stating in the PR body so the
  operator does not expect `issue-9-p7` and `issue-42-p9` to self-heal.
- **Resource impact:** the worst case per wedged proposal grows from 3 to 5
  implementer forks — each one an SDK run against `SHEPHERD_BUDGET_USD`
  (`orchestrator/options.py:89`, default `5.00` per tick) plus, under
  `DevLoopWorkflow`, one Hetzner volume per tick
  (`tests/test_dev_loop_workflow.py:1686-1694`). That is roughly a 67 % increase
  in the tail cost of a proposal that never converges. Bounded, and
  `SHEPHERD_TICKS_MAX = 12` still caps in-workflow ticks.
- **Risk: slower human signal.** A genuinely stuck proposal now takes ~6 ticks
  (≈24 h at the 4 h in-workflow cadence) to reach `review-stuck` instead of ~4.
  Mitigation: none needed structurally — `review-fixing`/`implemented` proposals
  remain visible to `mctl_trigger_shepherd --dry-run` and the mentor digest
  throughout; the issue accepts this trade explicitly.
- **Risk: #342 amplification.** Rounds spent re-litigating an excluded finding
  now burn five slots instead of three. Mitigation: state the non-claim in the
  constant's comment and in the PR body so the next reader does not mistake this
  for a fix; keep #342 open.
- **Risk: quiet doc drift.** Mitigated by sweeping `facts.yaml` and the lifecycle
  diagram note in the same PR, and by preferring the symbol over the digit in
  every comment and test touched.
- **CI:** `.github/workflows/pr-validation.yml` runs `pytest`, `ruff` and
  `mypy`; all three must pass. The change touches no types and adds no imports,
  so `mypy`/`ruff` exposure is limited to line length in the rewritten comments.
