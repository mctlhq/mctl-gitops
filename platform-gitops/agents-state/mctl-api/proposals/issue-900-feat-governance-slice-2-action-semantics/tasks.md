# Tasks: issue-900-feat-governance-slice-2-action-semantics

- [ ] 1. Add `internal/workitems/owner_actions.go`: `dev_loop_owner_actions` schema and the two partial unique indexes, `OwnerAction` type, `oa_` id, `CreateOwnerAction` (idempotent per `(requested_by, idempotency_key)` with `content_digest`, one cancel per `(workflow_id, run_id)`, one request_changes/defer per `(approval_ref, action)`), `MarkOwnerActionOutcome` (compare-and-set on state), `GetOwnerAction`, `ListOwnerActions`, `ErrOwnerActionIdempotencyConflict`, `ErrOwnerActionNotFound`. Wire the schema into store start. — DoD: store tests pass against Postgres; no free-text column exists.
- [ ] 2. Extract `resolveDevLoopGrant` from `decideDevLoopApproval` in `internal/api/handlers_dev_loop.go` (read-only: execution lookup, ambiguity, newest grant, 503 on unreadable store). — DoD: `decideDevLoopApproval` uses it; all existing approve tests pass unchanged.
- [ ] 3. Extract `abandonDevLoopRun` from `AbandonDevLoopWorkflow` (describe, pinned signal, NotFound re-describe, run-changed detection) returning a typed result; `AbandonDevLoopWorkflow` writes the same responses and audit as today. — DoD: `handlers_dev_loop_abandon_test.go` passes unchanged; `/abandon` authorization unchanged.
- [ ] 4. Add `bindingRouteDevLoopOwnerAction = "dev_loop_owner_action"` in `internal/api/approval_binding.go`, with `workflow_id` as the id key in the observe audit. — DoD: observe mode audits `approval.binding_absent` with the new route label.
- [ ] 5. (depends on 1-4) Add `internal/api/handlers_dev_loop_owner_actions.go`: `RequestDevLoopOwnerAction`, `ListDevLoopOwnerActions`, `GetDevLoopOwnerAction`; body decode with `refuseIdentityFields` + `DisallowUnknownFields`; `isHumanAdmin` gate with 403 `owner_action_forbidden`; binding checks before any write; request_changes/defer record-only on a pending grant; request_cancel via `abandonDevLoopRun` with outcome mapping `cancellation_pending`, `cancellation_effects_unknown`, `cancelled`, `already_finished`, 409 `cancellation_run_changed`; signal payload reason `owner_action:<oa_id>:<reason_code>`; audit `dev-loop-owner-action` with ids/codes/state only. — DoD: handler compiles, `go vet` and `golangci-lint` clean.
- [ ] 6. (depends on 5) Register routes in `internal/api/router.go`: POST in the dev-loop write group next to `/abandon`, GETs next to `GetDevLoopWorkflow`. — DoD: routes reachable; 503 when Temporal or WorkItems not configured.
- [ ] 7. (depends on 6) Add the three routes to `internal/openapi/openapi.yaml` and `internal/openapi/embed_test.go`. — DoD: openapi tests pass.
- [ ] 8. Add "Owner actions (mctl-api#900)" section to `docs/decision-context-contract.md` with action table, codes, cancel outcome table and "cancel is not rollback". — DoD: doc matches implemented codes.

## Tests

Each guard test below must fail when its guard is removed (mutation check noted per test).

- [ ] T1. Authority: service principal, relayed admin (`RelaySurface`), surface token and non-admin each get 403 `owner_action_forbidden` for all three actions; fake DevLoop client records zero `SignalAbandon` calls and the store has zero rows. Mutation: drop the `isHumanAdmin` check -> test fails.
- [ ] T2. Human-input separation: extend `human_input_vs_action_approval_test.go` so a human-input response with value `"cancel"` (and any other value) records zero `SignalAbandon` calls, zero owner-action rows and an unchanged grant. Mutation: route a "cancel" answer to abandon -> fails.
- [ ] T3. request_changes and defer on a pending grant: grant state remains `pending`, `decided_by`/approved fields empty, no `action_approval.decision` audit, no Temporal call. Mutation: call `DecideActionApproval` -> fails.
- [ ] T4. request_changes/defer on approved, denied, consumed, expired grants -> 409 with `approval_already_decided` / `closedApprovalCodes` codes; no grant -> 409 `approval_grant_missing`. Mutation: remove the pending check -> fails.
- [ ] T5. Stale card: binding naming an older `aar_` -> 409 `approval_context_changed` with `current_approval_ref`; differing digest -> same 409; no row, no signal. Enforce mode without binding -> 422 `approval_binding_missing`. Mutation: skip binding check -> fails.
- [ ] T6. Cancel on a running run with pending grant -> `cancellation_pending`, one `SignalAbandon` pinned to described run id, payload reason `owner_action:<oa_id>:...`, no free text.
- [ ] T7. Cancel on a running run with approved/in_flight/consumed/executed grant -> `cancellation_effects_unknown`. Mutation: map all signalled cases to pending -> fails.
- [ ] T8. Cancel on finished runs: abandoned+not implemented -> `cancelled`; abandoned+implemented -> `cancellation_effects_unknown`; completed without abandon -> `already_finished`; unreadable `DevLoopEnded` -> `cancellation_effects_unknown`; zero signals in all cases.
- [ ] T9. Run changed between describe and signal -> 409 `cancellation_run_changed`, successor not signalled; replay with same key signals nothing to the successor.
- [ ] T10. Idempotency: same key+content twice -> one row, one signal, second `replayed: true`; same key different content -> 409 `owner_action_idempotency_conflict`; second cancel with a different key for the same run -> existing row, zero extra signals; duplicate defer for the same grant -> existing row. Mutation: drop the unique-index replay path -> fails with two signals.
- [ ] T11. Transport failure on signal -> 502 (503 for `ErrUnavailable`), row stays `requested`; replay with same key retries exactly one signal to the stored run id.
- [ ] T12. GET re-observation: a `signalled` cancel whose run has now finished abandoned (not implemented) reports and persists `cancelled`; GET never calls `SignalAbandon`, `StartDevLoopWorkflow` or `RestartAbandonedDevLoopWorkflow`.
- [ ] T13. Privacy: body with unknown field (e.g. `reason`, `comment`) -> 400; audit entries and responses contain only the listed id/code/state keys.
- [ ] T14. Regression: existing `handlers_dev_loop_test.go`, `handlers_dev_loop_abandon_test.go`, approval binding tests and openapi embed tests pass unchanged.

## Rollback

All changes are additive. Revert the PR to remove the routes and handler; the
refactored `/approve` and `/abandon` paths return to their previous inline
form with identical behaviour. The `dev_loop_owner_actions` table may be left
in place (unused) or dropped manually with `DROP TABLE dev_loop_owner_actions`;
no other table references it. Abandon signals already sent are not undone
(cancel was never rollback), and no `aar_` was ever modified by this path, so
no grant data needs repair.
