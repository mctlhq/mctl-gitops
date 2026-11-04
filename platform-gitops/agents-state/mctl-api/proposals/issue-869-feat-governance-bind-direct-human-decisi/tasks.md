# Tasks: Slice 1 of issue-869

**This implementation run is authorized for Slice 1 only (stale-card binding). Action semantics (cancel, request-changes, defer) and the delegation enrollment/policy evaluator are out of scope and must not be implemented in this run.**

Scope is binary: the run is complete only when every task below is done. The only paths that may change are `internal/api/**`, `internal/openapi/openapi.yaml`, the MCP tool schemas under `internal/mcp/**` that wrap the two routes, `cmd/api/main.go` (flag wiring only) and `docs/decision-context-contract.md`. If another path seems necessary, stop and report.

- [ ] 1. `decisionBinding` type, shape validation, and `approval_binding_missing` (422, `details.missing_fields`) wired into the error table in `handlers_action_approvals.go`. — DoD: compiles; the code appears in the refusal table and in OpenAPI.
- [ ] 2. `MCTL_APPROVAL_BINDING` (`off|observe|enforce`, default `observe`), parsed at startup in `cmd/api/main.go`, unknown value fails startup, plumbed into `Handlers` options. — DoD: unit test for each value and for the bad value.
- [ ] 3. Action-approval route: accept `binding`, require path id == `approval_ref`, compare digests inside `guardDecision`. — DoD: tests T1, T2, T3.
- [ ] 4. DevLoop approve route: accept `binding`, resolve the grant by `approval_ref` in `decideDevLoopApproval`, never fall back to the newest, report `current_approval_ref`. — DoD: tests T4, T5, T6.
- [ ] 5. Idempotence: an already approved grant with the same binding returns the existing decision, no second `DecideActionApproval` write. — DoD: T7.
- [ ] 6. Mode behavior: `observe` audits `approval.binding_absent` and increments a per-route counter; `enforce` refuses; `off` is silent. — DoD: T8.
- [ ] 7. Authority unchanged: relay/service/policy principal gets 403 with and without `binding`. — DoD: T9.
- [ ] 8. OpenAPI, MCP tool schemas (`binding` optional) and `docs/decision-context-contract.md` (new code, migration, precedence). — DoD: openapi lint and the repo's schema tests pass.
- [ ] 9. Mutation proof: for each guard, remove it, run the tests, confirm a failure, restore. Guards: path id vs `approval_ref`; newest-grant fallback (reintroduce it); context digest compare; content digest compare; missing-field check; enforce refusal; observe audit; idempotent return; `isHumanAdmin` ahead of the binding code. Record each mutation and result in the PR description. — DoD: no surviving mutation.
- [ ] 10. `go fmt`, `go vet`, `golangci-lint run`, `go test ./...`. — DoD: clean.

## Tests

- [ ] T1. Action-approval decision with a matching binding approves; with a differing `context_digest` -> 409 `approval_context_changed`, grant stays pending.
- [ ] T2. Differing `content_digest` -> 409 `approval_context_changed`.
- [ ] T3. Path id different from `approval_ref` -> 409 `approval_context_changed`.
- [ ] T4. DevLoop approve: the card names grant A, the execution's newest grant is B (A superseded) -> 409 `approval_context_changed` with `current_approval_ref=B`; B is NOT approved.
- [ ] T5. DevLoop approve with the matching newest grant approves it and signals with that `approval_ref`.
- [ ] T6. DevLoop approve where the grant lookup fails -> 503, not the legacy payload.
- [ ] T7. Two identical bound requests produce one decision row and one signal payload.
- [ ] T8. Mode matrix: no binding in `off` ok, in `observe` ok plus audit and counter, in `enforce` 422.
- [ ] T9. Relay principal and service principal get 403 `approval_decider_forbidden`, bound and unbound.
- [ ] T10. A partial binding (any one field missing or malformed) is 422 `approval_binding_missing` in every mode.
- [ ] T11. Terminal-state precedence: a denied or expired grant with a stale binding answers the state code, not `approval_context_changed`.

## Rollback

Revert the change. `MCTL_APPROVAL_BINDING=off` restores the old behavior without a deploy of code. No migration, no table, no data change.
