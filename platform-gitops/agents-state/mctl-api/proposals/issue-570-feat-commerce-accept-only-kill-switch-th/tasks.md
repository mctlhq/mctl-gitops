# Tasks: issue-570-feat-commerce-accept-only-kill-switch-th

- [ ] 1. Add `CommerceAcceptDisabled bool` to `config` in `cmd/api/main.go`, loaded with `killSwitchOn(os.Getenv("COMMERCE_ACCEPT_DISABLED"))`. Leave `config.validate` unchanged so the dispatch key is still validated. DoD: the field is populated in `loadConfig`, and `go vet ./cmd/...` passes.
- [ ] 2. Add `CommerceAcceptDisabled bool` to `Options` in `internal/api/router.go`, with a comment stating its scope (quotes and accepts only) and that `Commerce == nil` takes precedence. Pass it from `main.go` where `Commerce: commerceStore` is set. Log a `slog.Warn` when the store is built and the switch is on. (depends on 1) DoD: the value reaches `Handlers.opts`, and the warning appears only when the store exists.
- [ ] 3. Add `refuseIfAcceptDisabled` to `internal/api/handlers_commerce.go`. It writes a `denied` audit entry and returns 503 via `writeErrorCode` with `commerce.ReasonUnsupportedExecution`. Call it in `MintCommerceQuote` and `AcceptCommerceInvocation` right after `requireCommerceTenant` and before body decoding. (depends on 2) DoD: no other handler references the flag, and the store is not called when it is on.
- [ ] 4. Update the docs. In `docs/commerce-ledger.md`, add a Configuration table row and a "Pausing acceptance" section: what is refused, what stays live, precedence with `COMMERCE_DISABLED`, and the disable and enable order (accept switch first, drain via reconcile/finalize/release until `/invocations/overdue` and the non-terminal rows are empty, then optionally `COMMERCE_DISABLED`; reverse order on enable). Add a README.md env table row and `COMMERCE_ACCEPT_DISABLED: ""` under `env:` in `helm/values.yaml`. (depends on 3) DoD: the docs match the implemented behaviour, and `helm/render_test.go` still passes.
- [ ] 5. Run `go fmt`, `go vet ./...`, `golangci-lint run` and `go test ./...` (with `TEST_DATABASE_URL` for the Postgres-backed tests). (depends on 1-4) DoD: all green.

## Tests

- [ ] T1. `cmd/api/main_test.go`: `loadConfig` maps `COMMERCE_ACCEPT_DISABLED` through `killSwitchOn` (`""`/`off` mean off, `true`/`1` mean on). A config with `CommerceAcceptDisabled: true` and an unusable dispatch key still fails `validate`, unlike `CommerceDisabled`.
- [ ] T2. `internal/api/handlers_commerce_test.go` (Postgres fixture): with `f.h.opts.CommerceAcceptDisabled = true`, a tenant owner's `POST …/quotes` and `POST …/invocations` return 503 with `"code":"unsupported-execution"`, and no new `commerce_quotes` or `commerce_invocations` row exists for the fixture capability.
- [ ] T3. Ordering: with the switch on, a user without access to the tenant still gets 404, and a user with no canonical principal still gets 403 `identity-unresolved`, not `unsupported-execution`. A no-store handler still gets 503 "commerce ledger not configured". This extends `TestCommerceHandlers_NilStoreIs503` with the flag set.
- [ ] T4. Drain while paused (the issue's required proof):
  1. With the switch off, publish terms, set a budget, mint, and accept two invocations. Reserve one of them.
  2. Turn the switch on.
  3. Expire the accepted row's quote and the reserved row's reservation deadline with `UPDATE` through `f.pool`, as `handlers_commerce_budget_test.go` already does.
  4. Call `ReconcileCommerceExpired` as admin.

  Assert that the first row is `refused` with `quote-expired` and the second is `released` with `reservation-expired`, both terminal.
- [ ] T5. Other routes stay live while paused. On a third row accepted before the switch: reserve, dispatch, then finalize. On a fourth: reserve, then release. Both reach a terminal phase. `GET` invocation, transitions, budget, `/invocations/overdue` and terms reads all return 200.
- [ ] T6. Audit: the refused quote and accept each write a `denied` audit entry with the correct operation name. Use the fixture's audit sink or a fake `AuditLog`.
- [ ] T7. Mutation check, in the style of the "Tests" section of `docs/commerce-ledger.md`: removing either call to `refuseIfAcceptDisabled` makes T2 fail, and moving it before `requireCommerceTenant` makes T3 fail.

## Rollback

- Operational: unset `COMMERCE_ACCEPT_DISABLED` (or set it to `false`) and roll the pods. Acceptance resumes with no data effect, because the switch writes no rows other than audit entries.
- Code: revert the PR. The default is off and there is no migration, so reverting changes nothing for a deployment that never set the variable. If the variable was set in the deployed values, remove it in the same change. Otherwise, after the revert it would silently mean nothing and acceptance would resume.
