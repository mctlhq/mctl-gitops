# mctl-self-observability-gap: mctl-api cannot introspect its own status, config, or logs via its own MCP tools

## Context
mctl-api hosts a 24-tool MCP server (per `context/architecture.md`) that exposes service-catalog,
status, metrics, and log-inspection tools (`get_service_status`, `get_service_config`,
`get_service_logs`, `get_tenant_metrics`, etc.) for every service registered in the `admins` and
`labs` tenants. Two consecutive daily research cycles (2026-08-22 and 2026-09-19) have confirmed
that these tools cannot correctly introspect **mctl-api itself**:

- `mctl_get_service_config(team=admins, service=mctl-api)` errors with `"service not found:
  admins/mctl-api"`, even though `mctl_get_service_status` for the same `team`/`service` pair
  succeeds and reports `health=Healthy`, `syncStatus=Synced` via ArgoCD.
- `mctl_get_service_status(team=admins, service=mctl-api)` returns a null `service` field — no
  pod-level CPU, memory, or replica data — while the same call presumably works for other
  registered services (not confirmed, but no other service is reported as broken in the inbox).
- `mctl_get_service_logs(team=admins, service=mctl-api, since=24h, lines=100)` returns `count=0`,
  `lines=null` — no log lines retrieved for a 24-hour window, despite the service being reported
  healthy and presumably serving traffic.

Because these are mctl-api's own tools, this is a bug in mctl-api's service-catalog lookup, metrics
aggregation, or log-query pipeline — most likely a catalog-key mismatch between how mctl-api
registers/looks up its own `admins/mctl-api` identity and how it looks up other services, or a
missing/incorrect Loki label selector for its own log stream. This blocks two concrete things:
(1) operators cannot verify the deployed image tag against `context/current-version.md` (last
updated 2026-04-27, unverified for nearly five months) without falling back to ArgoCD's own UI, and
(2) the daily researcher/analyst/spec-writer pipeline described in `CLAUDE.md` cannot get
mctl-api's own resource usage ahead of the pgx and mcp-go upgrade proposals in this same cycle,
which would otherwise help gauge risk (e.g. whether the mcp-go v1.1.0 bump's OTel/tracing surface
is safe to enable given current memory headroom).

## User stories
- AS a platform operator I WANT `mctl_get_service_config(team=admins, service=mctl-api)` to
  return mctl-api's own deployed image tag and config SO THAT I can verify it against
  `current-version.md` without leaving the MCP tool surface.
- AS an SRE I WANT `mctl_get_service_status(team=admins, service=mctl-api)` to return non-null
  pod-level CPU/memory/replica data for mctl-api SO THAT I can monitor its own resource usage the
  same way I monitor every other registered service.
- AS a researcher agent I WANT `mctl_get_service_logs(team=admins, service=mctl-api)` to return
  actual log lines for mctl-api SO THAT the daily research pipeline can diagnose issues in the very
  service producing that pipeline's proposals.
- AS a platform security engineer I WANT confidence that this gap is a lookup/query bug and not a
  symptom of a broader service-catalog registration or authorization defect SO THAT it does not
  mask a cross-tenant or cross-service data-isolation issue (per architecture.md's "mctl-api itself
  authorizes tenant scope — a bug here = cross-tenant leak" known limitation).

## Acceptance criteria (EARS)
- WHEN `mctl_get_service_config` is called with `team=admins, service=mctl-api`, THE SYSTEM SHALL
  return a valid config object (including at minimum the deployed image tag) instead of a
  "service not found" error.
- WHEN `mctl_get_service_status` is called with `team=admins, service=mctl-api`, THE SYSTEM SHALL
  return a non-null `service` field populated with pod-level CPU, memory, and replica-count data,
  consistent with the data returned for other registered `admins`-tenant services.
- WHEN `mctl_get_service_logs` is called with `team=admins, service=mctl-api` and a time window
  during which mctl-api was serving traffic, THE SYSTEM SHALL return a non-zero `count` and
  non-null `lines`, reflecting actual log output for that window.
- IF the root cause is a service-catalog key mismatch (e.g. `admins/mctl-api` vs. an internally
  registered name/alias) THEN THE SYSTEM SHALL be corrected so that mctl-api's self-registration
  uses the same canonical key used by lookup, without requiring callers to know an internal alias.
- IF the root cause is a missing or incorrect Loki label selector for mctl-api's own log stream
  THEN THE SYSTEM SHALL be corrected so that the selector matches mctl-api's actual deployed
  labels.
- WHILE this fix is being investigated and applied, THE SYSTEM SHALL continue reporting
  `mctl_get_service_status`'s top-level ArgoCD health/sync fields correctly for mctl-api (this
  aspect already works and must not regress).
- IF the underlying bug also affects other services' config/status/log lookups (not just
  mctl-api's self-lookup), THEN THE SYSTEM SHALL document that broader scope as a follow-up finding
  rather than silently expanding this proposal's scope.

## Out of scope
- Fixing metrics/log gaps for any service other than mctl-api itself, unless investigation reveals
  the same root cause affects other services (see the last acceptance criterion — that becomes a
  documented follow-up, not part of this proposal's delivered fix).
- Building new dashboards or alerting on top of the restored data (separate, follow-on concern).
- Re-tuning `admins` tenant resource limits/requests based on the newly visible metrics (the inbox
  separately notes admins tenant usage trending up ~66.6% mem / ~67.5% cpu; that is tracked as a
  "worth re-checking next cycle" item, not part of this fix).
- Changes to the pgx or mcp-go upgrade proposals in this same cycle (`pgx-critical-memory-safety-
  cve-v2`, `mcp-go-upgrade-v3`) — this proposal only restores the observability needed to assess
  such changes' impact, it does not depend on or block them.
