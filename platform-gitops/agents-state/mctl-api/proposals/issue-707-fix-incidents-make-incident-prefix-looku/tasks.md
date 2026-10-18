# Tasks: issue-707-fix-incidents-make-incident-prefix-looku

- [ ] 1. In `internal/alerts/store.go`, add `ErrNotFound`, `ErrPrefixTooShort`, `ErrAmbiguousPrefix` and `MinPrefixLen = 8`. Make `Store.Get` wrap `pgx.ErrNoRows` as `ErrNotFound`. — DoD: `errors.Is(err, alerts.ErrNotFound)` holds for a missing id; other `Get` callers compile and behave unchanged.
- [ ] 2. Add an unexported `escapeLike` (`\` to `\\`, `%` to `\%`, `_` to `\_`). (depends on 1) — DoD: unit-tested without Postgres.
- [ ] 3. Rewrite `Store.GetByPrefix`: exact `Get` first; then `len < MinPrefixLen` returns `ErrPrefixTooShort`; then `WHERE id LIKE $1 ESCAPE '\' ORDER BY id LIMIT 2`, where 0 rows returns `ErrNotFound`, 1 row is returned with evidence, and 2 rows return `ErrAmbiguousPrefix`. Update the doc comment. (depends on 1, 2) — DoD: `ORDER BY created_at DESC LIMIT 1` is gone; `store_trace_test.go` still passes.
- [ ] 4. In `internal/api/handlers_alerts.go`, add `writeIncidentLookupError`, mapping 400, 404, 409, and 500 (with an `slog.Error` for the 500). Use it in `GetIncident`, `UpdateIncident`, `AcknowledgeIncident` and `ResolveIncident`. (depends on 1) — DoD: all four handlers share it; none calls `Update` after a lookup error.
- [ ] 5. In `internal/mcp/server.go`, update the `id` parameter description of `mctl_get_incident`, `mctl_acknowledge_incident` and `mctl_resolve_incident` to describe the unique 8+ character prefix rule. — DoD: tool count unchanged; `go test ./internal/mcp/...` passes.
- [ ] 6. Run `go fmt`, `go vet` and `golangci-lint`, and run the tests with `TEST_DATABASE_URL` set. (depends on 3, 4, 5) — DoD: clean.

## Tests
All store and handler tests below are Postgres-backed (`TEST_DATABASE_URL`), following `newTestStore` and `newTestAlertStore`. Each must fail if the old `LIMIT 1` / unescaped / no-minimum query is restored.

- [ ] T1. `TestGetByPrefix_TooShort`: with `abcdefgh-1` stored, `GetByPrefix("abc")` and `GetByPrefix("")` return `ErrPrefixTooShort`. The old code returned the row.
- [ ] T2. `TestGetByPrefix_NoMatch`: `GetByPrefix("zzzzzzzz")` gives `errors.Is(err, ErrNotFound)`. The old code returned a wrapped `pgx.ErrNoRows`, which is not `ErrNotFound`.
- [ ] T3. `TestGetByPrefix_OneMatch`: with `abcdefgh-1` and `zzzzzzzz-1` stored, `GetByPrefix("abcdefgh")` returns `abcdefgh-1`.
- [ ] T4. `TestGetByPrefix_Ambiguous`: with `abcdefgh-1` (older) and `abcdefgh-2` (newer) stored, `GetByPrefix("abcdefgh")` returns `ErrAmbiguousPrefix` and a nil alert. The old code returned `abcdefgh-2`.
- [ ] T5. `TestGetByPrefix_WildcardsAreLiteral`: with `abcdefgh-1` stored, `GetByPrefix("abcdefg_")`, `GetByPrefix("abc%%%%%")` and `GetByPrefix("%%%%%%%%")` return `ErrNotFound`. With `abc_efgh-1` also stored, `GetByPrefix("abc_efgh")` returns exactly `abc_efgh-1`, with no ambiguity against `abcdefgh-1`.
- [ ] T6. `TestGetByPrefix_ExactWins`: with `argo-run-1` and `argo-run-10` stored, `GetByPrefix("argo-run-1")` returns `argo-run-1`. With short id `abc` stored, `GetByPrefix("abc")` returns it.
- [ ] T7. `TestEscapeLike`: table test for `%`, `_`, `\` and plain input.
- [ ] T8. Handler test, `TestMutatingIncidentHandlers_AmbiguousPrefix_ChangesNothing`: create `abcdefgh-1` and `abcdefgh-2` as admin. Call PATCH (`{"status":"resolved","analysis":"x"}`), `/ack` and `/resolve` with id `abcdefgh` through a chi router, so that `URLParam` resolves. Assert 409 for each. Then `store.Get` both rows and assert that status, analysis, acknowledged_by, resolved_at and updated_at are unchanged. The old code returned 200 and mutated `abcdefgh-2`.
- [ ] T9. Handler status mapping: GET `/incidents/abc` returns 400, `/incidents/zzzzzzzz` returns 404, `/incidents/abcdefgh` (ambiguous) returns 409, and `/incidents/abcdefgh-1` returns 200.

## Rollback
Revert the PR. There is no schema or data change, so a revert and redeploy of mctl-api restores the previous `LIMIT 1` behaviour immediately. If only the stricter 409/400 responses cause client breakage, a smaller partial revert of `writeIncidentLookupError` (mapping everything back to 404) is possible. The store-level fix should stay, because it is the safety property.
