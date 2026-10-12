# Design: issue-586-fix-audit-getbyworkflow-reports-a-failed

## Current state

- `internal/audit/logger.go`: the `Log` interface declares `GetByWorkflow(name string) *Entry` and `ListByStatus(status, maxAge, limit, after) []Entry`. Neither can report an error. The in-memory `Logger` implements both, and it cannot fail.
- `internal/audit/postgres.go`:
  - `GetByWorkflow` (line 169) creates `context.WithTimeout(context.Background(), 5*time.Second)`, runs `QueryRow ... ORDER BY timestamp DESC LIMIT 1` and returns `nil` on any error from `scanAuditEntry`. `pgx.ErrNoRows` and real failures look the same, and neither is logged.
  - `scanAuditEntry` (line 184) ends with `_ = json.Unmarshal(params, &e.Parameters)`, so a decode failure is silently dropped.
  - `ListByStatus` (line 275) logs and returns `nil` on a query error, skips rows that fail to scan, and never checks `rows.Err()`. A failure during iteration therefore reads as a shorter queue.
  - `List` uses the same pattern.
- `internal/api/handlers_read.go`:
  - `GetWorkflow` (line 393). At line 404 it calls `entry := h.opts.AuditLog.GetByWorkflow(name)`. When `entry == nil`, non-admins get 404 "workflow record not found in audit log". Admins fall back to `Executor.GetWorkflowStatus(ctx, cronWorkflowNamespace, name)` and get 404, 502 or a 200 with the note "expected for cron-driven runs". The failed *live* lookup already maps to 502 with an explanatory comment, and the audit read does not get the same care. With an entry, tenant access is enforced only when `team != ""` (`auditEntryTenant(entry)`, line 847, returns `""` when `Parameters == nil`). A corrupt-params row therefore lets a non-admin through and routes to the wrong namespace.
  - `GetWorkflowLogs` (line 527): `team := auditEntryTenant(h.opts.AuditLog.GetByWorkflow(name))`. An empty team gives 403 "admin group membership required: workflow has no owning team".
- `internal/api/audit_reconcile.go`: `reconcileOnce` (line 96) pages `r.log.ListByStatus("submitted", ...)` and stops at `len(pending) == 0`. A DB failure ends the pass and is logged only inside postgres.go. `reconcileBatch` derives the namespace from `auditEntryTenant(e)` (line 141). A NotFound after `gcGrace` marks the row `expired`. With corrupt params, a tenant op would be looked up in the wrong namespace, return NotFound and be wrongly expired.
- `internal/mcp/server.go:448-462`: `mctl_get_workflow_status` is a thin wrapper over `GET /api/v1/workflows/{name}`, so the REST status code is what the MCP caller sees.
- Tests: `internal/api/workflow_logs_test.go` builds a router with `logsRouter(archive, logger audit.Log)` and fakes (`fakeExecutor`, `fakeGitReader`, `fakeArgoCD`). No test exercises `GetWorkflow`'s audit-miss path today. `GetByWorkflow` is called directly in `internal/api/argo_webhook_test.go`, `internal/api/audit_reconcile_test.go` and `internal/audit/status_test.go`. Postgres tests are gated on `TEST_DATABASE_URL` (`internal/audit/postgres_test.go`).
- `AGENTS.md` is not in the clone. The "could not observe is not observed absent" rule is taken from the issue text.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/*/`: listed the tenants (admins, karabu, labs, ...). There is no `mctl-api` service directory, so mctl-api's deployed values could not be observed from this checkout. This does not mean mctl-api is not deployed.
- `cmd/api/main.go:356-357` (clone): the Postgres audit logger is selected when `AUDIT_DB_URL` is set, and the in-memory one is used otherwise. Whether production sets it was not verified from gitops. The issue describes production DB failures, which implies the Postgres logger.
- mctl MCP tools were not called. The change is code-only and does not depend on deployed configuration.

## Proposed solution

### 1. Audit read API (`internal/audit`)

- Change the interface method to `GetByWorkflow(ctx context.Context, name string) (*Entry, error)`.
  - Postgres: `ctx, cancel := context.WithTimeout(ctx, 5*time.Second)` uses the caller's context. Then `errors.Is(err, pgx.ErrNoRows)` returns `(nil, nil)`, and any other error returns `(nil, fmt.Errorf("audit postgres: get by workflow %q: %w", name, err))`. This needs `github.com/jackc/pgx/v5` as an import (already a module dependency through pgxpool).
  - In-memory `Logger`: same lookup as today, returns `(entry, nil)`. It ignores ctx.
- Change the interface method to `ListByStatus(...) ([]Entry, error)`.
  - Postgres returns a wrapped error on a query failure and on `rows.Err()`. Rows that fail to scan are still logged and skipped, because one bad row must not starve the queue.
  - The in-memory implementation returns `nil` error.
- Handle `params` decode failures with a marker rather than an error. Add `ParametersUnreadable bool` to `Entry` with tag `json:"-"`, so it is not served and the redact path is unchanged. In `scanAuditEntry`, a failed `json.Unmarshal` sets `Parameters = nil` and `ParametersUnreadable = true`, and logs `slog.Error("audit postgres: params decode failed", "id", e.ID, "error", err)`. The row is still returned.
  - Reason for the marker: rows that are otherwise good stay visible to `List` and `ListByStatus`. Each caller that authorizes or routes on parameters can then refuse explicitly instead of reading `nil` as "no parameters".
  - Document this choice in a comment on the field.
- `auditEntryTenant` keeps its signature. Callers check `ParametersUnreadable` before using it.

### 2. Callers (`internal/api`)

- `GetWorkflow`: `entry, err := h.opts.AuditLog.GetByWorkflow(r.Context(), name)`.
  - If `err != nil`, call `slog.Error("audit read failed for workflow lookup", "workflow", name, "error", err)` and then `writeError(w, http.StatusServiceUnavailable, "audit log unavailable, workflow may exist")`. Return before both the `entry == nil` cron fallback and the 404.
  - If `entry != nil && entry.ParametersUnreadable`, return 503 "audit record for workflow is unreadable (parameters could not be decoded); owning team cannot be determined" and log it.
  - The `entry == nil` branch is unchanged.
- `GetWorkflowLogs` non-admin gate: read `entry, err` first. If there is an error or `ParametersUnreadable`, log it and return 503. Otherwise keep the current logic.
- `auditReconciler.reconcileOnce`: on a `ListByStatus` error, `slog.Warn("audit reconcile: queue read failed", "error", err)` and end the pass (the next tick retries).
- `reconcileBatch`: `if e.ParametersUnreadable { slog.Warn(...); continue }` before deriving the namespace.
- `cmd/api`: no change is expected. Any other `GetByWorkflow` or `ListByStatus` call site found by `go build ./...` is updated in the same way.

### 3. Sweep result (recorded in the PR body)

- Fixed: `GetByWorkflow` and its two callers, `ListByStatus` and the reconciler, and `scanAuditEntry`'s param decode.
- Listed as a follow-up and not changed here: `Log.List(limit)` returns `nil` on a query failure, and `ListAgentRuns`, `ListWorkflows` and `ListAudit` (`handlers_read.go:278, 356, 807`) render that as an empty list.

## Alternatives

1. **Add `LookupByWorkflow(ctx, name) (*Entry, error)` next to `GetByWorkflow` (the #585 approach), and migrate only these callers.** This leaves a second method that still swallows errors and that invites new callers. It is rejected unless #585 has already merged. In that case, reuse `LookupByWorkflow` and delete `GetByWorkflow` (see Open questions).
2. **Fail the whole read when params cannot be decoded (`scanAuditEntry` returns an error).** This is simpler for `GetWorkflow`, but `ListByStatus` and `List` would drop the row. The reconciler would never see it, and a single corrupt row would disappear from the audit listing. Rejected in favour of the marker.
3. **Keep `*Entry` and expose a separate `LastError()` or sentinel entry.** This has hidden state and is racy across concurrent requests. Rejected.

## Platform impact

- No schema change and no migration. `Entry.ParametersUnreadable` is in-memory only (`json:"-"`).
- API behaviour changes only during failures. An audit-store outage now gives 503 instead of 404, 403 or a cron 200. Healthy-path responses are byte-identical. MCP `mctl_get_workflow_status` surfaces the 503 as a tool error, which is the intended signal.
- Interface change: `audit.Log` is internal to the module. All implementers (`Logger`, `PostgresLogger`) and test call sites (about 16 in `argo_webhook_test.go`, `audit_reconcile_test.go` and `status_test.go`) are updated in the same PR. `go build ./...` catches any that are missed.
- Using the request context means a client disconnect now cancels the audit query. That is correct, because no response would be delivered anyway.
- Risk: a flapping audit DB now turns into visible 503s instead of quiet wrong answers. That is intended, and the errors are logged, so they become observable.
- Risk: rows with corrupt params now refuse `GetWorkflow` for admins. This is recorded under Open questions.
- Resource impact: none.
