# Tasks: issue-585-feat-incidents-store-and-return-trace-id

- [ ] 1. Add `telemetry.ValidTraceID` and `telemetry.TraceIDFromTraceparent` in `internal/telemetry/telemetry.go`. Make `operations.workflowTraceID` (`internal/operations/executor.go`) use them and remove the duplicate `w3cTraceparent`/`w3cTraceID`/`allZero` regexes. — DoD: existing executor trace tests still pass. New table tests cover valid, uppercase, short, non-hex, all-zero and a version other than 00.
- [ ] 2. Add `LookupByWorkflow(ctx, name) (*Entry, error)` to `audit.Log`. Implement it on `PostgresLogger` (`pgx.ErrNoRows` → `(nil, nil)`, other errors returned) and on the in-memory `Logger`. — DoD: `go build ./...` passes. Tests cover found, not found, and (for Postgres, gated on `TEST_DATABASE_URL`) a cancelled context returning an error.
- [ ] 3. (depends on 1) Schema and store in `internal/alerts`. — DoD: `go vet ./internal/alerts` is clean. Store tests pass against Postgres.
  - Add the `trace_id` and `workflow_name` `ADD COLUMN IF NOT EXISTS` lines to `alertSchema`.
  - Add `TraceID`, `WorkflowName`, `TraceSource` and `TraceUnavailable` to `Alert`, with omitempty tags.
  - Introduce the shared `alertColumns` constant and `scanAlert` helper, and use them in `Create`'s `RETURNING`, `Get`, `GetByPrefix` and `List`.
  - Make `Create` insert both columns. On a dedup hit it replaces `trace_id` only when the new value is non-empty.
  - Make `Update` write `trace_id`.
  - Set `TraceSource="reported"` after the scan when `TraceID != ""`.
- [ ] 4. (depends on 1, 3) Write handlers in `internal/api/handlers_alerts.go`. — DoD: none of the 4 write endpoints can return a non-2xx status because of `trace_id` or `workflow_name`.
  - `CreateIncident` runs `sanitizeIncidentTrace`. It drops an invalid `trace_id` or `workflow_name`, never errors (including when `trace_id` has a non-string JSON type), and clears the response-only fields.
  - `UpdateIncident` accepts `trace_id` as `json.RawMessage` and replaces the stored value only when the value is a valid string.
- [ ] 5. (depends on 1, 2, 3) Add `deriveIncidentTrace` in a new `internal/api/incident_trace.go`, following the design's rule order. It builds on the reported, `not_reported`, `workflow_name_unknown`, `audit_unavailable`, `audit_record_not_found`, `audit_record_forbidden` and `no_traceparent_in_audit_record` cases, with a 2 s lookup timeout. Wire it into `GetIncident` after the tenant check, with a `canRead` that mirrors the `GetWorkflow` gate (`auditEntryTenant`). — DoD: GET on an argo incident with a matching audit row returns `trace_id` and `trace_source="workflow_audit"`. Every failure path returns 200 with exactly one `trace_unavailable` reason. Nothing is written back. `ListIncidents` sets `trace_unavailable="not_derived_on_list"` on every item whose stored `trace_id` is empty (no audit lookup on list), and keeps `trace_source="reported"` on items with a stored trace.
- [ ] 6. (depends on 5) Update the `mctl_get_incident` tool description in `internal/mcp/server.go` to cover `trace_id`, `trace_source` and `trace_unavailable`, including that an absent value means "not known" and that list results carry `not_derived_on_list` instead of a derived trace. — DoD: the description is updated and the `server_test.go` tool count is unchanged.
- [ ] 7. Run `go fmt`, `go vet` and `golangci-lint`, and run `go test ./...` with and without `TEST_DATABASE_URL`. — DoD: all clean.
- [ ] 8. (after deploy, verification only) — DoD: both acceptance calls return the expected values.
  - `mctl_get_incident argo-mctl-agents-implement-dae24112-1791756910` returns `trace_id=431486061c652efb376a860d9d656f25` with `trace_source=workflow_audit`.
  - The next mctl-agent ticket's `mctl_get_incident` returns its `trace_id` with `trace_source=reported`.

## Tests

- [ ] T1. Store round trip (`internal/alerts/store_test.go`, needs `TEST_DATABASE_URL`). `Create` with `TraceID` and `WorkflowName`, then `Get`, `GetByPrefix` and `List` all return both values. `Update` replaces `TraceID`. Ack-style `Get`→`Update` preserves it.
- [ ] T2. Dedup (store). A second `Create` with the same fingerprint and a new valid trace replaces `trace_id`. A third with an empty trace keeps it. `workflow_name` stays at the original.
- [ ] T3. Regression (store). Assert that every read path (`Get`, `GetByPrefix`, `List`, `Create`'s RETURNING) populates `TraceID`, so the test fails if the column is removed from `alertColumns` or `alertSchema`. Also add a pure JSON test that marshals `Alert{TraceID: "..."}` and asserts the `"trace_id"` key, so it fails if the field or tag is removed.
- [ ] T4. Invalid input is ignored, not rejected (handler, `httptest`, DB-gated like `TestIncidentWrites_RoleGate`). Cover POST with `trace_id` set to uppercase, 31 chars, all zeros, or the number `123`: each returns 201 with no stored trace. PATCH with an invalid `trace_id` returns 200 and keeps the previous value. PATCH with a valid value replaces it.
- [ ] T5. Derivation, pure unit test with no DB, using `audit.NewLogger()` or a fake `workflowAuditLookup`. Cover:
  - an argo incident whose summary URL names a workflow with an audit traceparent, giving `workflow_audit`;
  - the same via a stored `workflow_name`;
  - the dae24112 fixture (summary text copied from production), giving `431486061c652efb376a860d9d656f25`.
- [ ] T6. Derivation failure cases. Each returns no `trace_id` and exactly one reason:
  - audit miss gives `audit_record_not_found`;
  - lookup error gives `audit_unavailable`;
  - nil lookup gives `audit_unavailable`;
  - a summary with no URL and no `workflow_name` gives `workflow_name_unknown`;
  - an audit row without `traceparent` gives `no_traceparent_in_audit_record`;
  - an audit row whose tenant the non-admin caller lacks gives `audit_record_forbidden`;
  - a non-argo source without a trace gives `not_reported`;
  - a stored trace takes precedence (`reported`) and the lookup is never called.
- [ ] T7. Telemetry helper table tests (task 1).
- [ ] T8. List marking (handler, DB-gated like T4). `GET /api/v1/incidents` over one incident with a stored trace and one argo incident without: the first has `trace_id` and `trace_source="reported"`, the second has no `trace_id` and `trace_unavailable="not_derived_on_list"`, and the audit lookup is not called.
- [ ] T9. Mutation proof (DoD for T3, T5 and T8; required before the PR is marked ready). For each, put the bug back and run the test: drop `trace_id` from `alertColumns` (T3 must fail), make `deriveIncidentTrace` return before the audit lookup (the dae24112 case in T5 must fail), and remove the `not_derived_on_list` marking (T8 must fail). Restore the fix and show green. Record each mutation, the failing test name and its failure line in the PR body. A test that stays green under its mutation does not count as a regression test.

## Rollback

- The change is additive. Revert the mctl-api commit and redeploy the previous image. Old code ignores the `trace_id` and `workflow_name` columns: its INSERT and UPDATE do not name them, so the defaults apply, and its SELECTs do not read them.
- Leave the columns in place: they are harmless, and re-deploying the fix reuses them. If they must be removed, run `ALTER TABLE alerts DROP COLUMN IF EXISTS trace_id, DROP COLUMN IF EXISTS workflow_name;` manually, and only after the reverted image is fully rolled out.
- No producer or gitops change is part of this proposal, so nothing else needs reverting.
