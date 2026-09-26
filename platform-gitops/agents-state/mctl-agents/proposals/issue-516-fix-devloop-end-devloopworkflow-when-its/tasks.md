# Tasks: issue-516-fix-devloop-end-devloopworkflow-when-its

- [ ] 1. Add `proposal_status: str | None = None` to `PRState` in
  `orchestrator/temporal/activities/pr_state.py`, with a `_STATUS_FIELD_RE`
  beside `_PR_FIELD_RE`, and populate it on every return path that decoded
  `.status.yaml` — including the four `found=False` ones (no `pr:` field,
  unparseable `pr:` URL, wrong-repo refusal, PR 404). Leave it `None` only when
  the file was 404 or undecodable. — DoD: no extra HTTP request is made; the
  field is defaulted so a recorded `PRState` without it still deserializes; the
  docstring says `None` means "could not be read", never "live".

- [ ] 2. Add `LOOP_TERMINAL_PROPOSAL_STATUSES = frozenset({"needs-triage",
  "review-stuck", "rejected", "error"})` and a pure
  `_loop_terminal_status(status: str | None) -> str` helper to
  `orchestrator/temporal/workflows/dev_loop.py`, beside the merge-watch
  constants (~line 405). — DoD: a comment states why `merged` is excluded (the
  PR-state arm at 4991 drives stages 6.2-6.4) and names the live statuses;
  the helper strips and case-folds, returns `""` for `None` and for anything
  outside the set; it is importable and unit-testable without a workflow
  context.

- [ ] 3. Add `PROPOSAL_TERMINAL_PATCH = "proposal-terminal-end"` beside
  `LAUNCH_CORRELATION_PATCH` (line 334) and evaluate it ONCE in `_watch_pr`,
  next to `hop_enabled` (4800), in the `resume is None` arm only. (depends on 2)
  — DoD: the unpatched path schedules no new command; the constant carries a
  comment naming the migration-by-attrition rule
  `tests/test_patch_memoization.py` pins.

- [ ] 4. Add `proposal_terminal_end: bool = False` to `MergeWatchResume`, set it
  in `_watch_pr`'s `resume_record` (4913-4945), and read it in the
  `if resume is not None:` arm (4801-4810) beside `fast_cadence` /
  `shepherd_in_loop` / `track_ownership`. (depends on 3) — DoD: a continued run
  uses the carried value and never re-derives the marker; the field is
  defaulted so pre-existing resume records deserialize.

- [ ] 5. Insert the terminal check in `_watch_pr`'s poll body, immediately after
  the `get_pr_state` read, in BOTH the `state.found` branch (after the
  `MERGED`/`CLOSED` arm, before `poll_index += 1`) and the not-found branch
  (before the `pr_lookup_grace_polls` give-up). Use `break` with a local
  `watch_ended` string, never `return`, and never set `hopping`. (depends on
  1, 2, 3) — DoD: a merged/closed PR still takes its existing arm; a terminal
  status ends the watch at that poll with no further tick, poll or hop; the
  `finally` block still runs.

- [ ] 6. In `_watch_pr`'s `finally` (5091-5166), when `watch_ended` is set, pass
  a `reason` to `self._ownership(...)` that names the observed proposal status
  instead of "merge watch ended without a terminal pull-request state". Leave
  the `op` derivation at 5131 untouched. (depends on 5) — DoD: the relinquishing
  write still happens exactly once; `release` vs `terminal` is still decided by
  the last observed PR state.

- [ ] 7. Add `ended: str = ""` to `_WatchOutcome` (1362), return it at 5170, and
  map it onto `DevLoopResult.ended` in `_finish_after_watch` (3286-3349) with
  the existing abandon string still taking precedence. (depends on 5) — DoD:
  `DevLoopResult.ended == "proposal review-stuck"` on the new path, `""` on the
  full-pipeline path, and unchanged for abandon / closed-issue / expiry; no new
  `DevLoopResult` field.

- [ ] 8. Document the new exit in the `dev_loop.py` module docstring (which
  already enumerates the bounded-park exits added by mctl-agents#420) and in
  `docs/adr/006-dev-loop-merge-deploy-monitor.md` if that ADR enumerates the
  watch's exit conditions. (depends on 5) — DoD: a reader of either file learns
  that a terminal proposal status ends the watch, and that `merged` does not.

- [ ] 9. Add an operator note to the proposal's own record (and to the issue on
  close) that a terminal proposal now closes the loop, so moving a proposal back
  to `accepted` relies on `ImplementSweepWorkflow` or on mctl-api#404's explicit
  restart rather than on the parked execution. (depends on 5) — DoD: the
  behaviour change is written down where an operator triaging `needs-triage`
  will see it.

## Tests

- [ ] T1. `tests/test_temporal_activities.py`: `get_pr_state` returns
  `proposal_status` from the same `.status.yaml` read, on the `found=True` path
  AND on the no-`pr:`-field path; `None` when the file 404s or is undecodable.
- [ ] T2. `tests/test_dev_loop_workflow.py`: a `review-stuck` proposal on an
  OPEN PR ends the watch within one poll; `DevLoopResult.ended` names the
  status and `DevLoopResult.pr` still carries the last observed `PRState`.
- [ ] T3. A `needs-triage` proposal with no `pr:` link ends on the FIRST poll —
  assert it does not spend `cadence.pr_lookup_grace_polls`.
- [ ] T4. No in-loop shepherd tick is submitted at or after the terminal poll,
  and any tick already in flight is settled (no "workflow completed with a
  pending task" error).
- [ ] T5. A `merged` proposal status does NOT end the watch early: the
  merged-PR path still reaches `_observe_deploy` / `_watch_incidents`.
- [ ] T6. An unreadable status (`None`) and an unknown status (e.g.
  `"implemented"`, `"accepted"`) keep the watch polling — fail-open.
- [ ] T7. The terminal end issues exactly one relinquishing lifecycle write,
  with the op derived from the PR state and a `reason` naming the proposal
  status; the row is not left active (mirror
  `test_ownership_released_when_the_watch_ends_without_a_terminal_pr`).
- [ ] T8. `tests/test_patch_memoization.py`-style: an execution whose history
  predates `proposal-terminal-end` keeps polling past a terminal status.
- [ ] T9. `tests/test_workflow_replay.py`: prepatch and patched `dev_loop`
  fixtures both replay against the new definitions, plus a guard test that the
  prepatch history predates the `proposal-terminal-end` marker (in the family of
  `test_dev_loop_full_prepatch_history_predates_the_launch_correlation_marker`).
  Restore fixtures from git rather than re-recording them.
- [ ] T10. A hop across `continue_as_new` carries `proposal_terminal_end`, and
  the continued run ends on a terminal status exactly like the run it replaced.
- [ ] T11. Unit test `_loop_terminal_status` directly: whitespace, mixed case,
  `None`, empty string, `"merged"` (not terminal for the loop), and every member
  of the set.

## Rollback

Two levels, cheapest first.

1. **Neutralise without touching control flow.** Set
   `LOOP_TERMINAL_PROPOSAL_STATUSES = frozenset()` and deploy. The marker and
   the branch stay in place, `_loop_terminal_status` returns `""` for every
   input, the check never fires, and no command sequence changes — so no
   in-flight execution that already recorded the marker can be wedged. This is
   the preferred rollback.
2. **Full revert.** Revert the single commit (three files plus tests). Do this
   only if level 1 is insufficient, and expect the hazard it avoids: an
   execution whose history recorded `proposal-terminal-end` replays against code
   that no longer calls `workflow.patched` for it. Drain first — list running
   `dev-loop-*` executions, and for any mid-watch loop send the existing
   `abandon` signal (a graceful, cluster-access-free exit that still releases
   the lifecycle claim) rather than `terminate`.

Per-loop escape hatch in either direction: the `abandon` signal already ends a
merge watch at its next poll boundary, and `ImplementSweepWorkflow` still picks
up any proposal an operator returns to `accepted`.
