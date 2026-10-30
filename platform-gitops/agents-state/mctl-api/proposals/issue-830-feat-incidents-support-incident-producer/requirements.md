# Support incident producer principal and admin aggregation of support incidents

## Context

mctl-support (S1c of the tenant support agent epic, mctlhq/.github#243, companion
mctlhq/mctl-support#4) needs to file incidents on behalf of the tenant a support
task is bound to: platform defects, quota requests, policy exceptions and "needs an
owner" escalations. Today `POST /api/v1/incidents` (`internal/api/handlers_alerts.go`
`CreateIncident`) admits only an admin or a tenant member who holds the developer
role. mctl-support holds neither, and it must not be given an admin token.

This proposal adds a dedicated, single-capability service principal,
`support-incident-producer`, modelled on the usage-writer principal
(`MCTL_USAGE_WRITER_TOKEN`, `internal/auth/oidc.go`, `usageWriterGate` in
`internal/api/handlers_usage.go`). It may only create `source=support` incidents
of four known types. The proposal also adds an admin-only read that groups open
support incidents by fingerprint across tenants, so an operator can see that
several tenants hit the same defect. Incidents themselves stay per tenant. The
existing dedup on `(tenant, fingerprint)` is unchanged.

## User stories

- AS the mctl-support service I WANT a credential that can file a support incident for the tenant of my current task SO THAT escalations reach platform operators without me holding admin or tenant membership.
- AS a platform operator I WANT to see open support incidents grouped by fingerprint with the affected tenants SO THAT I can prioritise a defect that hits several tenants.
- AS a security reviewer I WANT the producer credential confined to exactly one route and one source SO THAT a leaked token can do nothing but add support incidents, and every write is attributable to it.

## Acceptance criteria (EARS)

Principal configuration
- WHEN `MCTL_SUPPORT_INCIDENT_PRODUCER_TOKEN` is unset or empty THE SYSTEM SHALL not authenticate any caller as the support-incident-producer principal.
- IF `MCTL_SUPPORT_INCIDENT_PRODUCER_TOKEN` is shorter than 32 characters (`minSurfaceTokenLen`) THEN THE SYSTEM SHALL disable the principal and log at ERROR naming the env var.
- IF `MCTL_SUPPORT_INCIDENT_PRODUCER_TOKEN` equals `MCTL_AGENT_SERVICE_TOKEN`, `MCTL_USAGE_WRITER_TOKEN`, `MCTL_EVIDENCE_WRITER_TOKEN`, `MCTL_REGISTRY_PUBLISHER_TOKEN`, any surface token, or any security-provider token THEN THE SYSTEM SHALL disable the support-incident-producer principal and log at ERROR naming the env var it equals.
- IF any of those other tokens equals `MCTL_SUPPORT_INCIDENT_PRODUCER_TOKEN` THEN THE SYSTEM SHALL also refuse that other token. A shared value disables both sides, the same as the registry-publisher token does today.
- WHEN a request bears the configured producer token THE SYSTEM SHALL authenticate it as `service:mctl-support-incidents`. This principal is not an admin, has no groups or tenant access, and `HasPermission` is false for every permission. The constant-time comparison applies on both the federation registry path and the `MCTL_FEDERATION_DISABLED` legacy path.

Confinement
- WHILE the caller is the support-incident-producer principal THE SYSTEM SHALL answer 403 with code `support_incident_producer_route_not_allowed` to every request except `POST /api/v1/incidents`. This includes `GET`/`PATCH` on incidents, `/ack`, `/resolve`, `resolve-by-fingerprint`, list, summary, the aggregation route and `/mcp`. The refusal happens before any handler runs.
- WHEN the producer posts an incident whose `source` is not exactly `support` THE SYSTEM SHALL answer 403 with code `support_incident_source_not_allowed` and store nothing.
- WHEN the producer posts an incident whose `type` is not one of `platform_defect`, `quota_request`, `policy_exception`, `needs_owner` THE SYSTEM SHALL answer 403 with code `support_incident_type_not_allowed` and store nothing.
- WHEN the producer posts an incident with an empty `fingerprint` or one that does not start with `support:` THE SYSTEM SHALL answer 400 and store nothing.
- WHEN the producer posts a valid support incident THE SYSTEM SHALL accept the `tenant` from the body without a tenant-access or tenant-role check, and store the incident with status `open`. It SHALL ignore any caller-supplied triage fields: `status`, `analysis`, `proposed_fix`, `pr_url`, `pr_number`, `confidence`, acknowledgement and resolution fields.
- WHEN two different tenants post the same support fingerprint THE SYSTEM SHALL store two incidents. WHEN the same tenant posts it again while the first incident is open THE SYSTEM SHALL return the original incident (existing dedup in `alerts.Store.Create`).
- WHILE the caller is not the producer principal THE SYSTEM SHALL keep the existing `CreateIncident` behaviour for that caller.

Audit
- WHEN the producer creates an incident, or hits an existing one through dedup, THE SYSTEM SHALL write one `incident-create` audit row with status `succeeded`. Its `UserID` is `service:mctl-support-incidents`. Its parameters are `incident_id` (the stored id), `requested_id`, `tenant`, `source`, `type`, `fingerprint`, `deduplicated` (`true`/`false`) and `actor=service:mctl-support-incidents`. Summary and evidence text are never written to the audit row.
- WHEN the producer is refused on source or type THE SYSTEM SHALL write one `incident-create` audit row with status `denied`. Its parameters are the tenant, source and type, plus the refusal code.

Aggregation
- WHEN an admin calls `GET /api/v1/incidents/support/aggregation` THE SYSTEM SHALL return `{"items": [{"fingerprint", "type", "affected_tenants": [...], "count"}], "count": <rows>}`. It covers incidents with `source=support`, non-empty fingerprint and status not `resolved`/`suppressed`, grouped by `(fingerprint, type)`. `affected_tenants` is sorted and de-duplicated. `count` is the number of open incidents in the group. Rows are ordered by `count` descending, then `fingerprint` ascending.
- WHEN two tenants each have an open support incident with the same fingerprint THE SYSTEM SHALL return one row with `count: 2` that lists both tenants.
- IF the caller is not an admin THEN THE SYSTEM SHALL answer 403. This includes tenant members, surface principals, the usage writer and the producer principal.
- IF the alert store is not configured THEN THE SYSTEM SHALL answer 503 and SHALL NOT return an empty list.
- WHEN there are no open support incidents THE SYSTEM SHALL return `{"items": [], "count": 0}`.

## Out of scope

- A tenant field on usage records. mctl-support keeps per-tenant spend in its own ledger.
- Changing the `(tenant, fingerprint)` dedup or merging incidents across tenants.
- An MCP tool for the aggregation. The MCP tool count is unchanged.
- Restricting who else, such as admins or tenant developers, may post `source=support` incidents.
- The mctl-gitops change that provisions the Vault secret, the `mctl-api-support-incident-producer` ExternalSecret and the bootstrap value that enables it. The same change also wires the token into mctl-support. That is a follow-up in mctl-gitops / mctl-support.
- Resolving or acknowledging support incidents by mctl-support.

## Open questions

- Response envelope of the aggregation. The issue shows a bare array `[{...}]`. This proposal wraps it as `{"items": [...], "count": n}` to match `ListIncidents`. mctl-support does not consume this route (it is admin-only), so the choice only affects operators and the portal.
- Grouping key. The issue says "grouped by fingerprint" and also returns `type`. The mctl-support fingerprint encodes the kind (`support:<kind>:<hash>`), so fingerprint and type move together in practice. This proposal groups by `(fingerprint, type)`, so a mismatch shows up as two rows rather than being hidden.
- Tenant existence. The producer does not need tenant access, so a buggy producer could file an incident for a tenant name that does not exist. This proposal only validates that the tenant is non-empty, as today. A check against the GitOps tenant list could be added later.
- Other writers of `source=support`. An admin or a tenant developer can still post `source=support` incidents and so affect the aggregation counts. This proposal leaves that unchanged.
- Fingerprint format enforcement (`support:` prefix, 400). This relies on the format stated in the issue. If mctl-support#4 sends a different shape, its writes are refused until the two agree.
- Deployed config of mctl-api could not be observed beyond gitops bootstrap: no MCP tool calls were made in this run. Whether the producer token secret already exists is unknown.
