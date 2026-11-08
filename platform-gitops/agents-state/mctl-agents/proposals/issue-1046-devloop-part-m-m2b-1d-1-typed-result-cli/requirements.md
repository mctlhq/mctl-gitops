# DevLoop Part M, slice M2b-1d-1: typed watch result, CLI summary and delivery refusal plumbing (#1021)

## Context

Issue mctlhq/mctl-agents#1046 is slice M2b-1d-1 of the sequential plan recorded on #1021. The #1021 proposal
(`platform-gitops/agents-state/mctl-agents/proposals/issue-1021-devloop-part-m-m2b-feedback-tick-and-dea/` in
mctl-gitops, approved digest `sha256:e833d2af0ce3ce1e30699e6a77d221ba34af8948175c1ad75f2f0acd566fb144`) is the
specification. Its design sections "5. Typed result" and "2. One decision for all three exits" (the delivery check)
define this slice, and its task 7 is the only task taken here. Slices M2b-1a' (#1029/#1030), M2b-1b (PR #1039, merge
`883b3a1bf`, marker `merge-watch-terminal-reconcile`) and M2b-1c (#1041/PR #1042, merge `e6b70a307`, activities
`record_merge_watch_reconcile` and `confirm_no_pr`, registered, called by nothing) are already on main.

This slice adds the typed result fields, the reconcile-required tail of `_finish_after_watch`, the
`_reconcile_required` delivery refusal flag with its two `_deliver` checks, and the `cli.py` summary lines. All of it
is plumbing: nothing in this slice sets `_reconcile_required` or produces a `watch_end` other than `""`, so no
existing or new history can reach the new branches in production. It matters because 1d-2 to 1d-4 need a typed,
tested landing place for the watch decision before the 6983-line workflow is touched again, and because the first
M2b-1 attempt failed by being too large for one implementer pass (#1025).

This issue is provenance, not approval: the proposal needs its own digest-bound human approval.

## User stories

- AS an operator reading `cli.py status` I WANT a reconcile-required watch to be printed with its record, and never as
  `not watched`, SO THAT a missing PR state is never read as "no PR".
- AS a reader of `DevLoopResult` (the CLI, `start.restart_if_restartable`, mctl-api `restartIfAbandoned`) I WANT the new
  fields to be defaulted SO THAT results recorded before this change still decode, and a result recorded after it
  still decodes in an older reader.
- AS the implementer of slices 1d-2 to 1d-4 I WANT the result shape, the delivery refusal and the CLI to exist and be
  tested already SO THAT those slices only add the decision and the record.
- AS the owner I WANT this slice to change no command, no marker and no activity on any path SO THAT it can be
  reverted on its own and every replay fixture stays green unedited.

## Acceptance criteria (EARS)

Types (task 1):

- R1. THE SYSTEM SHALL add to `_WatchOutcome` (`orchestrator/temporal/workflows/dev_loop.py`) the fields
  `watch_end: str = ""` and `reconcile_record: str = ""`.
- R2. THE SYSTEM SHALL add to `DevLoopResult` the fields `watch_end: str = ""`, `last_observed_pr: PRState | None = None`
  and `reconcile_record: str = ""`, appended after the existing last field `security`, each with a default.
- R3. WHEN a `DevLoopResult` payload recorded before this change is decoded through Temporal's default data converter
  THE SYSTEM SHALL produce a `DevLoopResult` whose three new fields are `""`, `None` and `""`, and whose other fields
  are unchanged.
- R4. WHEN a `DevLoopResult` payload written by this change is decoded into the pre-change class THE SYSTEM SHALL decode
  it without error, dropping exactly the three new fields (Temporal's converter ignores unknown keys, as already pinned
  for the M1 classes in `tests/test_pre_m1_compat.py`). This is a pinned hazard, not a feature.

Result tail (task 2):

- R5. WHEN `_finish_after_watch` receives an outcome with `watch_end == "reconcile-required"` THE SYSTEM SHALL return a
  `DevLoopResult` with `pr=None`, `last_observed_pr=outcome.last`, `reconcile_record=outcome.reconcile_record`,
  `watch_end="reconcile-required"`, `outcome="merge_watch_reconcile_required"`, `deploy=None`, `security=None`,
  `incidents=None`, and SHALL log one `MERGE_WATCH_RECONCILE_REQUIRED` warning naming the target repo, the workflow id,
  the `ended` text and the record.
- R6. WHEN `watch_end == "reconcile-required"` THE SYSTEM SHALL set `DevLoopResult.ended` to `outcome.ended` if it is
  non-empty, else to `MERGE_WATCH_RECONCILE_ENDED_FALLBACK`
  (`"merge watch: pull-request state not established; reconciliation required"`), and this SHALL take precedence over
  `ABANDONED_ENDED_PREFIX` even when `self._abandoned` is True.
- R7. WHILE `watch_end == "reconcile-required"` THE SYSTEM SHALL schedule no deploy observation, no
  `security_record_landed` and no incident watch, even if `outcome.last` is a merged PR, AND SHALL still evaluate the
  three existing `workflow.patched(...)` calls in `_finish_after_watch` in their existing order (the gating is done by
  passing `None` as the PR state, never by an early return).
- R8. WHEN `watch_end` is any other value (`""`, and the values later slices produce: `final-read`, `no-pr-confirmed`,
  `abandoned-unverified`) THE SYSTEM SHALL return exactly today's `DevLoopResult` plus `watch_end` copied from the
  outcome, `last_observed_pr=None` and `reconcile_record=""`; `pr`, `ended`, `outcome`, `deploy`, `security` and
  `incidents` SHALL be computed as today.
- R9. THE docstrings of `DevLoopResult.pr` and `_watch_pr` SHALL be corrected: `pr` is None on reconcile-required (see
  `last_observed_pr`), an OPEN `pr` does not by itself mean the deadline expired with the PR verified open, and on
  `abandoned-unverified` `pr` is the last observed state and not verified current state.

Delivery refusal (task 3):

- R10. THE SYSTEM SHALL add a constant `MERGE_WATCH_RECONCILE_REFUSAL = "merge-watch-reconcile-required"` beside the
  delivery landing code, and SHALL NOT add it to `RESUME_DEFERRAL_REASONS`.
- R11. THE SYSTEM SHALL initialise `self._reconcile_required = False` in `DevLoopWorkflow.__init__`, as plain instance
  state, and SHALL NOT set it anywhere in production code in this slice, NOR carry it in `MergeWatchResume`.
- R12. WHEN `_deliver` has bound a delivery (`bound.bound` True, execution recorded) and the delivery is not
  `accepted_after_gates`, IF `self._reconcile_required` is True THEN THE SYSTEM SHALL land it via
  `_land_delivery(opened, "Failed", MERGE_WATCH_RECONCILE_REFUSAL, engine_ref)` and return, before the existing
  `wait_condition`.
- R13. WHEN the existing `wait_condition` in `_deliver` returns, IF `self._reconcile_required` is True THEN THE SYSTEM
  SHALL land the delivery `Failed` with `MERGE_WATCH_RECONCILE_REFUSAL`, ahead of the hop carry and the existing
  `Succeeded`/`Failed` landing.
- R14. WHILE `self._reconcile_required` is False THE SYSTEM SHALL behave in `_deliver` exactly as today: the
  `wait_condition` predicate is unchanged, and no new command, timer, marker or activity is scheduled.
- R15. IF a delivery carries a `pending_phase`, or is `accepted_after_gates`, or never binds, THEN THE SYSTEM SHALL keep
  today's outcome for it (`pending_phase` landed as recorded; `feedback-not-ready`; `request-not-fulfilled` or the
  bind's own outcome), regardless of the flag. No delivery SHALL land `Succeeded` while the flag is True.

CLI (task 4):

- R16. WHEN `cli.status` prints a completed result with `watch_end == "reconcile-required"` THE SYSTEM SHALL print
  `  pr:          reconcile required (<reconcile_record>)` (or `(no record)` when it is empty) and SHALL NOT print the
  `not watched` line, the check sitting before the `elif result.implement and result.implement.succeeded` branch.
- R17. WHEN `watch_end == "no-pr-confirmed"` and `pr` is None THE SYSTEM SHALL print `  pr:          none (confirmed)`.
- R18. WHEN `watch_end == "abandoned-unverified"` and `pr` is not None THE SYSTEM SHALL append
  ` (last observed before abandon, not verified current)` to the existing `pr:` line.
- R19. WHEN `watch_end == ""` THE SYSTEM SHALL print exactly what it prints today.

Invariants:

- R20. THE SYSTEM SHALL add no `workflow.patched` call, no new activity, no new command and no change in command order;
  `MERGE_WATCH_RECONCILE_PATCH`, `record_merge_watch_reconcile` and `confirm_no_pr` SHALL keep exactly their current
  call sites and registrations.
- R21. Every existing test and every committed replay fixture SHALL pass with no edit and no re-record;
  `tests/test_merge_watch_worker_gap.py` SHALL be unchanged and keep its current result; `tests/test_pre_m1_compat.py`
  SHALL need no edit (its pin table `_M1_CLASSES`/`M1_ADDED` does not contain `DevLoopResult`).
- R22. IF any of the issue's STOP conditions occurs during implementation THEN the implementer SHALL stop and report on
  #1046 with no workaround.

## Out of scope

- Every producer of a `watch_end` value or of `_reconcile_required = True`: the final read, settle, decision, record,
  heartbeat, retain-claim, cancellation re-raises, `_no_pr_proven`, `_gate_ran_head`, `tick_blocked_until` (slices
  1d-2 to 1d-4).
- Any caller of `record_merge_watch_reconcile` or `confirm_no_pr`, any patch marker, any new activity, any new fixture.
- Turning `tests/test_merge_watch_worker_gap.py` green (1d-2).
- The B4 decision (#1007), the #1022 detector, any release, deployment, Vault or GitOps rollout. Release hold stays ON;
  #1003, gitops#2394 and mctl-api#934 stay Draft.
- mctl-api readers: unchanged; they decode `ended` and `implement` only.
- The pre-existing untyped-handle question in `cli.status` (see Open questions); not fixed here.

## Open questions

- Q1. `cli.status` obtains its handle with `client.get_workflow_handle(workflow_id)` (no result type) and then reads
  `result.ended` as an attribute (`orchestrator/temporal/cli.py:70-95`). With Temporal's default converter an untyped
  `result()` decodes to a dict, so this path may already fail at runtime; `tests/test_temporal_cli.py` stubs the handle
  and cannot see it. `start.restart_if_restartable` uses the typed `get_workflow_handle_for(DevLoopWorkflow.run, ...)`.
  Interpretation taken: out of scope (fixing it changes the CLI's handle acquisition, which the issue does not list);
  the new CLI tests feed a real `DevLoopResult` object like the existing stubs, and the reviewer should decide whether a
  separate issue is wanted. If the implementer finds the CLI cannot be tested without changing this, that is a STOP.
- Q2. R6 of #1021 asks the `MERGE_WATCH_RECONCILE_REQUIRED` log line to name the slug and the exit. `_finish_after_watch`
  has no slug parameter today. Interpretation taken: the line names repo, workflow id, `ended` (which the 1d-3 producer
  will make name the exit) and record; the slug is added in 1d-3 when the producer carries it, so the two call sites of
  `_finish_after_watch` are not changed here.
- Q3. Whether the `wait_condition` predicate in `_deliver` should also wake on `_reconcile_required`. Interpretation
  taken: no, the predicate stays unchanged (R14), as #1021 specifies two checks only; on a watch `_gates_passed` is True,
  so the wait resolves at once, and keeping the predicate unchanged keeps the first check observable by mutation.
- Q4. mctl-api's `restartIfAbandoned` (`internal/api/handlers_dev_loop.go`) was not re-read in this run; the statement
  that it decodes only `ended` and `implement` is taken from the #1021 design. The implementer or reviewer should cite it
  at its default branch in the PR (as #1021 R15 requires), with no change to mctl-api.
