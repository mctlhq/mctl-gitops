# Design: issue-585-feat-incidents-store-and-return-trace-id

## Current state

- `internal/alerts/types.go`: `Alert` has no trace or workflow field. The JSON
  tags define the REST/MCP wire shape.
- `internal/alerts/store.go`: `alertSchema` is applied on every start by
  `NewStore` (`CREATE TABLE IF NOT EXISTS` plus `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
  for `fingerprint`, `occurrence_count` and `last_seen_at`). This is the
  repo's migration mechanism for this table. `Create` is an
  `INSERT ... ON CONFLICT (tenant, fingerprint) WHERE ... DO UPDATE` (dedup)
  with an explicit `RETURNING` column list. `Update` sets a fixed list of
  columns. `Get`, `GetByPrefix` and `List` each repeat the same SELECT column
  list and `Scan` target list (four copies).
- `internal/api/handlers_alerts.go`:
  - `CreateIncident` decodes the body straight into `alerts.Alert`, so unknown
    fields like `trace_id` are dropped today.
  - `UpdateIncident` decodes into an anonymous patch struct with six pointer
    fields. `trace_id` is not one of them.
  - `GetIncident` and `ListIncidents` `writeJSON` the store's struct as is.
  - `AcknowledgeIncident` and `ResolveIncident` call `Store.Update` with the
    row they read, so any new column must round-trip through `Get` → `Update`
    unchanged.
  - `h.opts.AlertStore` is the concrete `*alerts.Store`. Handler tests that
    touch it need `TEST_DATABASE_URL` (`newTestAlertStore`, as used in
    `internal/api/tenant_role_test.go`).
- `internal/mcp/server.go` `toolGetIncident`: proxies
  `GET /api/v1/incidents/{id}` and returns the body verbatim. A new response
  field reaches MCP automatically. Only the tool description needs to mention it.
- `internal/audit/logger.go`, `internal/audit/postgres.go`: the `audit.Log`
  interface has `GetByWorkflow(name) *Entry`. `PostgresLogger.GetByWorkflow`
  returns `nil` both on `ErrNoRows` and on any query error, with its own 5 s
  timeout. It cannot tell "not found" from "could not look". The in-memory
  `Logger` is the only other implementation.
- `internal/api/handlers_read.go` `GetWorkflow`: the existing reader of the
  same audit row. It gates non-admins with
  `team := auditEntryTenant(entry); team != "" && !HasTenantAccess(team)`.
  It redacts parameters with `audit.RedactEntry`. A traceparent is 55 chars
  with no credential marker, so it is not redacted.
- `internal/operations/executor.go`: `w3cTraceparent`, `w3cTraceID`, `allZero`
  and `workflowTraceID` already implement "a valid, non-zero W3C trace id, or
  nothing", for the live workflow object.
- `internal/telemetry/telemetry.go`: `TraceIDFrom` and `TraceparentFrom` are
  the shared trace helpers.
- Producers (mctl-gitops, read-only):
  `argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml` (onExit
  "Incident leg", around line 1240) posts `id=argo-${WORKFLOW_NAME}-$(date +%s)`,
  `source: "argo-workflows"`, `tenant: "admins"`, and a `summary` that ends with
  `https://workflows.mctl.ai/workflows/argo-workflows/${WORKFLOW_NAME}`. It
  sends no `workflow_name` and no trace. `traceparent` is a workflow parameter
  in the implement and investigate templates only.

Deployed state checked:

- `mctl_get_incident argo-mctl-agents-implement-dae24112-1791756910`: exists.
  It has `source=argo-workflows`, `tenant=admins`, and a summary ending in
  `https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-implement-dae24112`.
  There is no trace field, which confirms the gap.
- `mctl_get_workflow_status mctl-agents-implement-dae24112`: the audit record
  exists (`userId=mctl-agent`, `operation=mctl-agents-implement`).
  `parameters.traceparent=00-431486061c652efb376a860d9d656f25-7a16c732dc164e9e-01`,
  and there is no `tenant_name`/`team_name` parameter, so `auditEntryTenant`
  returns "". The live object reports
  `trace.source=traceparent-argument, trace_id=431486061c652efb376a860d9d656f25`.
  The audit row is therefore persisted and served in production.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`:
  read the onExit incident body (above).
- `$MCTL_GITOPS_ROOT/services/*/`: no `mctl-api` service directory was found.
  mctl-api's deployed values were not observed here, so this is a gap and not
  evidence of absence. See Open questions in requirements.md.
- I did not call `mctl_get_incident 6ebe8c19-7b63-40ad-ace4-1a8bfc0b56f8`. The
  issue's report that it has no trace is taken as given.

## Proposed solution

### 1. Shared trace-id validation (`internal/telemetry`)

Add `telemetry.ValidTraceID(s string) bool`. It returns true for exactly 32
lowercase hex characters that are not all zeros. Also add
`telemetry.TraceIDFromTraceparent(tp string) (string, bool)` for version 00
with a non-zero trace id. Switch `operations.workflowTraceID` to these helpers
and delete the private duplicates. That keeps one definition of "valid trace
id" across the workflow-status path and the incident path. `alerts` and `api`
must not import `operations` just for a regex.

### 2. Schema and store (`internal/alerts`)

- `alertSchema` gains:
  `ALTER TABLE alerts ADD COLUMN IF NOT EXISTS trace_id TEXT NOT NULL DEFAULT '';`
  `ALTER TABLE alerts ADD COLUMN IF NOT EXISTS workflow_name TEXT NOT NULL DEFAULT '';`
  Both are additive and idempotent. Existing rows get `''`. No index is needed,
  because lookups are by id.
- `Alert` gains stored fields:
  `TraceID string `json:"trace_id,omitempty"``,
  `WorkflowName string `json:"workflow_name,omitempty"``.
  It also gains response-only fields that are never persisted:
  `TraceSource string `json:"trace_source,omitempty"``
  (`"reported"` | `"workflow_audit"`) and
  `TraceUnavailable string `json:"trace_unavailable,omitempty"``.
- Factor the four duplicated SELECT column lists and scan lists into one
  `alertColumns` const and one `scanAlert(row pgx.Row, a *Alert)` helper. This
  makes it impossible for one read path to drop the new column. A regression
  test pins it.
- `Create`: insert `trace_id` and `workflow_name`. In the dedup branch add
  `trace_id = CASE WHEN EXCLUDED.trace_id <> '' THEN EXCLUDED.trace_id ELSE alerts.trace_id END`.
  Do not touch `workflow_name` on dedup: the original row's summary and
  workflow stay consistent. Return both in `RETURNING`.
- `Update`: also set `trace_id`. The handler only changes it when a valid
  value is supplied, and ack/resolve round-trip the stored value. Leave
  `workflow_name` immutable after create.
- After scanning, set `TraceSource = "reported"` whenever `TraceID != ""`, so
  list, create and write responses label stored values consistently.

### 3. Write handlers (`internal/api/handlers_alerts.go`)

- `CreateIncident`: decode as today. Then call `sanitizeIncidentTrace(&a)`,
  which:
  - clears `TraceID` if `!telemetry.ValidTraceID`;
  - clears `WorkflowName` unless it matches the RFC 1123 subdomain rule
    (reuse `k8s.io/apimachinery/pkg/util/validation.IsDNS1123Subdomain`,
    already a dependency through apierrors);
  - always clears the response-only `TraceSource` and `TraceUnavailable`,
    like the existing handling of `OccurrenceCount`/`LastSeenAt`.

  A wrong JSON type for `trace_id` (e.g. a number) would fail
  `json.Decode` today and return 400. To keep "trace never fails the request",
  `Alert.TraceID` is decoded via a small `lenientString` type, or the handler
  decodes `trace_id` separately with `json.RawMessage`. In either case a
  non-string value is treated as invalid and ignored.
- `UpdateIncident`: add `TraceID json.RawMessage `json:"trace_id"`` to the
  patch struct. If it unmarshals to a string and is valid, set
  `existing.TraceID`. Otherwise ignore it with a `slog.Debug`.
- Never surface a validation error for these fields.

### 4. Read-time derivation (`internal/api/incident_trace.go`, new)

A pure, unit-testable function:

```go
type workflowAuditLookup interface {
    LookupByWorkflow(ctx context.Context, name string) (*audit.Entry, error) // (nil, nil) = not found
}

func deriveIncidentTrace(ctx context.Context, a *alerts.Alert, lookup workflowAuditLookup,
    canRead func(entry *audit.Entry) bool)
```

The rules, in order:

1. `a.TraceID != ""`: set `TraceSource="reported"` and stop.
2. `a.Source != "argo-workflows"`: set `TraceUnavailable="not_reported"` and stop.
3. The workflow name is `a.WorkflowName`. If that is empty, use the first match
   of `^https://workflows\.mctl\.ai/workflows/[a-z0-9-]+/([a-z0-9][a-z0-9.-]*)`
   found in `a.Summary`, anchored on whitespace or the start of the string and
   then IsDNS1123Subdomain-checked. If neither gives a name, set
   `workflow_name_unknown`. The id is never parsed.
4. If `lookup` is nil, the lookup errors, or it times out (a 2 s context
   derived from the request), set `audit_unavailable` and log at warn.
5. If the lookup returns `(nil, nil)`, set `audit_record_not_found`.
6. If `!canRead(entry)`, set `audit_record_forbidden`.
7. If `TraceIDFromTraceparent(entry.Parameters["traceparent"])` fails, set
   `no_traceparent_in_audit_record`.
8. Otherwise set `TraceID` and `TraceSource="workflow_audit"`, and clear
   `TraceUnavailable`.

`GetIncident` calls it after the tenant check. `canRead` mirrors `GetWorkflow`
exactly: `user.IsAdmin() || team == "" || user.HasTenantAccess(team)`, with
`team := auditEntryTenant(entry)`. The derivation therefore discloses nothing
that `GET /api/v1/workflows/{name}` would not already disclose to the same
caller, even when a caller crafts an `argo-workflows` incident whose summary
names someone else's workflow. The result is never written back.

### 5. Audit lookup that distinguishes "missing" from "failed" (`internal/audit`)

Add `LookupByWorkflow(ctx, name) (*Entry, error)` to the `audit.Log` interface:

- `PostgresLogger` runs the same query as `GetByWorkflow`, with the caller's
  context, and maps `pgx.ErrNoRows` to `(nil, nil)` and any other error to
  `(nil, err)`.
- The in-memory `Logger` cannot fail, so it returns `(entry-or-nil, nil)`.

`GetByWorkflow` stays as is for its existing callers. The interface has only
these two implementations (checked with grep for `ListByStatus(` receivers), so
the change is contained.

### 6. MCP and docs

- Extend `toolGetIncident`'s description. It now returns `trace_id` and
  `trace_source` when known, and otherwise a `trace_unavailable` reason. A
  missing `trace_id` must be read as "not known", never as "no trace exists".
- The tool count is unchanged, so the `server_test.go` count is unaffected.
- No OpenAPI spec covers incidents today (grep found none), so there is
  nothing to regenerate.

## Alternatives

1. **Producer-side only.** Change the onExit legs to send `trace_id` from
   `{{workflow.parameters.traceparent}}`. This needs a gitops change, covers
   only new incidents (dae24112 would stay untraceable), and covers only
   implement and investigate. It was dropped as the primary path. It remains a
   cheap follow-up because the stored value would then take precedence through
   rule 1.
2. **Backfill or write-through.** Derive the trace at read time and persist it,
   or run a one-off backfill. That makes GET mutate state, races with PATCH,
   and needs a migration job. Read-time derivation is cheap (one indexed audit
   query on a single-incident GET), so it was dropped.
3. **Derive from the live Kubernetes workflow (`workflowTraceID`).** This would
   also cover cron-spawned runs, but it needs a cluster call per GET and fails
   once Argo garbage-collects the workflow. Historical incidents are exactly
   the ones whose workflow objects are gone. The audit row is durable, and it
   is what the issue names. Dropped. It could be added later as a second
   source with its own `trace_source`.
4. **Parse the workflow name from the incident id (`argo-<wf>-<epoch>`).** The
   issue explicitly rejects this. On a dedup hit the id also belongs to a
   different run than later occurrences. Dropped in favour of the structured
   `workflow_name` with the summary-URL fallback.

## Platform impact

- **Migration:** two additive `ADD COLUMN IF NOT EXISTS ... NOT NULL DEFAULT ''`
  statements, run by `NewStore` at startup. On PostgreSQL 11+ a constant
  default is metadata-only, so there is no table rewrite. It is safe with
  rolling replicas: old pods ignore the columns, and new pods write them.
- **Backward compatibility:** all response fields are new and omitempty or
  additive. Clients with lenient decoders, which includes mctl-agent, are
  unaffected. Requests that worked before still work, and no new 4xx is
  introduced. One case changes on purpose: a POST whose `trace_id` has a
  non-string JSON type was a 400 before and is now accepted.
- **Resource impact:** at most one extra indexed audit query per
  `GET /incidents/{id}`, only for `argo-workflows` incidents without a stored
  trace, bounded by a 2 s timeout. List is unaffected.
- **Risks and mitigations:**
  - Cross-tenant disclosure through crafted summaries is gated by the same
    rule as `GetWorkflow` (section 4).
  - A slow audit DB could slow incident reads. The timeout and the fail-open
    `audit_unavailable` reason handle this.
  - A future refactor could drop the column from one SELECT. The single
    `scanAlert` helper and a round-trip regression test handle this.
  - Mislabelled provenance is handled by the explicit `trace_source`, so
    derived and reported values are never conflated.
