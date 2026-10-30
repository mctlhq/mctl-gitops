# fix(audit): GetByWorkflow must report a failed audit read as an error, not as "no record"

## Context

`PostgresLogger.GetByWorkflow` (`internal/audit/postgres.go:169`) returns `nil` for every
error from `scanAuditEntry`. That includes `pgx.ErrNoRows`, but also pool failures, query
failures, timeouts (it uses its own 5 s context detached from the request) and scan errors.
Nothing is logged. `scanAuditEntry` also discards a `params` JSON decode error
(`_ = json.Unmarshal(params, &e.Parameters)`), so a corrupt row comes back looking like a
submission that had no parameters. Both are cases of "could not observe" being reported as
"observed absent".

The two production callers in `internal/api/handlers_read.go` act on that wrong answer.
`GetWorkflow` (`GET /api/v1/workflows/{name}`, which backs the MCP tool
`mctl_get_workflow_status`) treats an audit outage as a cron-driven run. Non-admins get a
404, and admins get a cron-namespace fallback: a wrong 404, or a 200 with a misleading note
and no `audit` block. `GetWorkflowLogs` returns 403 "workflow has no owning team". A corrupt
`params` value also has a security side: `auditEntryTenant` returns `""`, and `GetWorkflow`
only enforces tenant access when `team != ""`, so a non-admin is let through. This proposal
makes the failure visible end to end and gives each caller a correct response.

## User stories

- AS an operator investigating an incident I WANT `GET /api/v1/workflows/{name}` to say "audit log unavailable" during an audit-store outage SO THAT I do not conclude that an operator-submitted workflow is a cron run or does not exist.
- AS a tenant member I WANT a retryable 503 instead of a 404 or 403 when the audit store cannot be read SO THAT I know my workflow may still exist and that I should retry.
- AS the mctl-agent investigator (via `mctl_get_workflow_status`) I WANT an audit outage to come back as an error, not as "no trace / cron run", SO THAT I do not draw a wrong conclusion from missing data.
- AS a platform maintainer I WANT the audit read API to return errors and to mark undecodable parameters SO THAT every caller can tell absence from failure.

## Acceptance criteria (EARS)

- WHEN `GetByWorkflow` runs a query that finds no row (`pgx.ErrNoRows`) THE SYSTEM SHALL return `(nil, nil)`.
- IF the audit query or scan fails for any other reason (pool or connection error, timeout, cancelled context, scan error) THEN `GetByWorkflow` SHALL return `(nil, err)` with an error that wraps the cause.
- WHEN `GetByWorkflow` is called THE SYSTEM SHALL derive its query context from the caller's context (the request context for HTTP handlers) and still bound it with the existing 5 s timeout.
- WHILE the in-memory `audit.Logger` is in use THE SYSTEM SHALL return a `nil` error from `GetByWorkflow` and otherwise keep today's behaviour.
- IF a row's `params` column is not valid JSON for `map[string]string` THEN `scanAuditEntry` SHALL still return the row, with `Entry.ParametersUnreadable = true` and `Parameters == nil`, and SHALL log the entry id and the decode error at error level.
- IF `GetByWorkflow` returns an error THEN `GET /api/v1/workflows/{name}` SHALL respond with 503 and the message "audit log unavailable, workflow may exist", for admins and non-admins alike. It SHALL NOT call the cron-namespace live lookup and SHALL log the error server-side.
- IF the entry returned for `GET /api/v1/workflows/{name}` has `ParametersUnreadable` set THEN THE SYSTEM SHALL respond with 503 instead of authorizing or routing on an unknown tenant.
- IF `GetByWorkflow` returns an error, or an entry with `ParametersUnreadable`, on the non-admin path of `GET /api/v1/workflows/{name}/logs` THEN THE SYSTEM SHALL respond with 503 rather than 403 "workflow has no owning team", and SHALL log the error.
- WHEN `GetByWorkflow` returns `(nil, nil)` THE SYSTEM SHALL keep today's behaviour: 404 for non-admins on `GetWorkflow`, the cron-namespace fallback for admins, and 403 "no owning team" for non-admins on `GetWorkflowLogs`.
- WHEN `GetByWorkflow` returns a readable entry THE SYSTEM SHALL return the same response as today on both endpoints.
- IF `ListByStatus` fails to query or to iterate its rows (including `rows.Err()`) THEN it SHALL return a non-nil error, AND the audit reconciler SHALL log the failure and end the pass without treating the queue as empty-and-done.
- IF a pending reconciler row has `ParametersUnreadable` set THEN the reconciler SHALL skip it with a warning and SHALL NOT expire it on a NotFound from a namespace derived from an unknown tenant.

## Out of scope

- The incident trace derivation and `LookupByWorkflow` from mctl-api#585.
- Any change to the audit schema (`audit_events`).
- Changing `Log.List(limit)` and its three HTTP callers (`ListAgentRuns`, `ListWorkflows`, `ListAudit` in `internal/api/handlers_read.go`). They still collapse a query failure into an empty list. They are recorded in the PR body as a follow-up so that this change stays reviewable.
- Write-path error handling (`Log`, `UpdateStatus`).

## Open questions

- Coordination with mctl-api#585. If #585 merges first with `LookupByWorkflow(ctx, name) (*Entry, error)`, the implementer should migrate both callers to it and delete `GetByWorkflow` instead of changing its signature. The handler and test changes in this proposal stay the same. The proposal assumes #585 has not merged: `LookupByWorkflow` does not exist in the clone.
- When parameters are unreadable, `GetWorkflow` returns 503 for admins too, even though an admin could in principle see the rest of the row. This was chosen for simplicity and safety, because the namespace cannot be derived without the tenant. A reviewer may prefer a 200 for admins with an explicit note. Recorded, not blocking.
