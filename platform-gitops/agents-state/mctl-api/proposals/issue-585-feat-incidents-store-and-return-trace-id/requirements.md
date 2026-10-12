# Store and return trace_id on incidents (mctl_get_incident)

## Context

`mctl_get_incident` (`internal/mcp/server.go`, `toolGetIncident`) proxies
`GET /api/v1/incidents/{id}` (`internal/api/handlers_alerts.go`, `GetIncident`),
which serializes `alerts.Alert` (`internal/alerts/types.go`). Neither the
`alerts` table (`internal/alerts/store.go`, `alertSchema`) nor the `Alert`
struct has a trace field, so the investigator path defined by
mctlhq/mctl-agent#97 (`mctl_get_incident -> workflow_id + trace_id -> failed
span -> Loki`) breaks at its first step. mctl-agent (2.5.0+) already sends
`trace_id` on the incident POST and on each status PATCH; mctl-api's lenient
JSON decoding silently drops it.

Incidents posted by the onExit legs of `cwft-mctl-agents-{implement,investigate,run,shepherd}`
(`source: "argo-workflows"`, id `argo-<workflow>-<epoch>`) carry no trace at all,
but for workflows submitted through mctl-api the submitting audit row already
holds `parameters.traceparent` (verified on
`mctl-agents-implement-dae24112`: `traceparent=00-431486061c652efb376a860d9d656f25-...`).
This proposal stores and returns a reported trace id, and derives one at read
time for Argo-sourced incidents from that audit row, while never letting trace
handling fail incident processing.

## User stories

- AS an incident investigator (human or mctl-agent) I WANT `mctl_get_incident`
  to return the incident's `trace_id` SO THAT I can open the failed span in
  Tempo and pivot to Loki without guessing.
- AS mctl-agent I WANT the `trace_id` I already send on POST/PATCH to be
  persisted SO THAT every ticket carries its trace with no producer change.
- AS an operator triaging an `argo-workflows` incident I WANT the trace of the
  failed workflow to be recovered from its submit audit record SO THAT historical
  incidents (e.g. dae24112) are traceable without waiting for a new failure.
- AS an investigator I WANT an explicit reason when no trace could be obtained
  SO THAT I never mistake "could not observe" for "no trace exists".

## Acceptance criteria (EARS)

Storage and write path

- WHEN the service starts THE SYSTEM SHALL ensure `alerts.trace_id TEXT NOT NULL DEFAULT ''`
  and `alerts.workflow_name TEXT NOT NULL DEFAULT ''` exist (idempotent
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in `alertSchema`).
- WHEN `POST /api/v1/incidents` carries a `trace_id` that is exactly 32
  lowercase hex characters and not all zeros THE SYSTEM SHALL store it.
- IF a `trace_id` on POST or PATCH is malformed (wrong length, uppercase,
  non-hex, all zeros, or not a string) THEN THE SYSTEM SHALL ignore it, keep
  the stored value unchanged, log it at debug/warn level, and still process the
  request with the same status code it would have returned without the field.
- WHEN `PATCH /api/v1/incidents/{id}` carries a valid `trace_id` THE SYSTEM
  SHALL replace the stored value with it (latest processing run wins).
- WHEN a POST deduplicates onto an existing open incident (same tenant and
  fingerprint) and carries a valid `trace_id` THE SYSTEM SHALL replace the
  stored value; IF the dedup POST carries no valid `trace_id` THEN THE SYSTEM
  SHALL keep the stored value.
- WHEN `POST /api/v1/incidents` carries a `workflow_name` that is a valid
  Kubernetes object name (lowercase RFC 1123 subdomain, at most 253 chars)
  THE SYSTEM SHALL store it; IF it is invalid THEN THE SYSTEM SHALL ignore it
  without failing the request.
- WHILE incidents are processed THE SYSTEM SHALL never return an error status
  for any reason attributable to `trace_id` or `workflow_name`.

Read path

- WHEN an incident with a stored `trace_id` is returned by
  `GET /api/v1/incidents/{id}`, `GET /api/v1/incidents`, the write endpoints, or
  `mctl_get_incident` THE SYSTEM SHALL include `trace_id` and
  `trace_source: "reported"`.
- WHEN an incident has an empty stored `trace_id` THE SYSTEM SHALL omit
  `trace_id` and `trace_source` from the JSON (omitempty).
- WHEN `GET /api/v1/incidents/{id}` returns an incident with `source="argo-workflows"`
  and an empty stored `trace_id` THE SYSTEM SHALL resolve the workflow name
  (stored `workflow_name`, else the `https://workflows.mctl.ai/workflows/<namespace>/<name>`
  URL in `summary`), look up that workflow's audit record, and, if its
  `parameters.traceparent` is a valid W3C version-00 traceparent with a
  non-zero trace id, return that trace id with `trace_source: "workflow_audit"`.
- THE SYSTEM SHALL NOT write a derived trace id back to the `alerts` row (the
  read stays side-effect free).
- IF the derivation cannot produce a trace id THEN THE SYSTEM SHALL return the
  incident with HTTP 200, no `trace_id`, and `trace_unavailable` set to exactly
  one of: `workflow_name_unknown`, `audit_unavailable` (no audit log configured
  or the lookup errored), `audit_record_not_found`, `no_traceparent_in_audit_record`,
  `audit_record_forbidden`.
- WHEN `GET /api/v1/incidents/{id}` returns an incident whose source is not
  `argo-workflows` and has no stored trace id THE SYSTEM SHALL set
  `trace_unavailable: "not_reported"`.
- WHILE the caller is not an admin THE SYSTEM SHALL only derive a trace id from
  an audit record the caller could read through `GET /api/v1/workflows/{name}`
  (same tenant gate as `GetWorkflow` via `auditEntryTenant`), otherwise
  `trace_unavailable: "audit_record_forbidden"`.
- IF the audit lookup errors or exceeds its timeout THEN THE SYSTEM SHALL still
  return the incident (HTTP 200) with `trace_unavailable: "audit_unavailable"`.
- WHEN `mctl_get_incident argo-mctl-agents-implement-dae24112-1791756910` is
  called after deploy THE SYSTEM SHALL return `trace_id=431486061c652efb376a860d9d656f25`
  and `trace_source="workflow_audit"`.

## Out of scope

- Storing `span_id` on the incident (#97: a span id names a transient attempt).
- Querying Tempo or Loki from mctl-api.
- Read-time derivation on the list endpoint (it returns stored values only; see
  Open questions).
- Changing the onExit legs in mctl-gitops to send `workflow_name` or `trace_id`
  (a follow-up in another repo; the summary-URL fallback covers today's producers).
- Backfilling `trace_id` into existing rows.
- Deriving trace ids for cron-spawned workflows that have no audit row (they
  get `trace_unavailable: "audit_record_not_found"`).

## Open questions

- List endpoint derivation: the issue asks the list endpoint to "return it".
  This proposal returns the stored value on list but runs the audit derivation
  only on the single-incident GET, to avoid up to 50 audit queries per list
  call. If the investigator path needs derived ids on list, a batched audit
  lookup can be added later.
- Dedup semantics for `trace_id`: the issue states "latest run wins" for PATCH
  only; this proposal applies the same rule to a dedup-hit POST. For Argo
  incidents the deduplicated row keeps the first run's summary URL, so the
  derived trace is the first run's, consistent with the summary shown.
- `trace_unavailable` vocabulary is chosen here; mctl-agent consumers may
  want different names. They are additive and can be renamed before any
  consumer depends on them.
- Deployed state: the mctl-api deployment values were not found under
  `$MCTL_GITOPS_ROOT/services/` (it is not a tenant service there), so the
  runtime config (e.g. whether the audit log is Postgres-backed in production)
  was confirmed only indirectly, via `mctl_get_workflow_status` returning a
  persisted audit row for a workflow submitted the previous day.
