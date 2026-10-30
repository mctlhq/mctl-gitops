# Design: issue-830-feat-incidents-support-incident-producer

## Current state

Incident API (`internal/api/handlers_alerts.go`, routes in `internal/api/router.go` lines ~621-629)
- `CreateIncident` checks that `h.opts.AlertStore` is non-nil (503 otherwise) and decodes `alerts.Alert` plus trace fields. It requires `id, source, type, tenant, summary, severity`. It then requires `user.IsAdmin() || user.HasTenantAccess(a.Tenant)` and `h.requireTenantRole(..., incidentWriteRole /* developer */, "incident-create", ...)`. It forces `OccurrenceCount=0` and `LastSeenAt=nil`, then calls `AlertStore.Create`. It does **not** audit a successful create. Only role refusals are audited (by `requireTenantRole` -> `auditRoleRefusal`, `internal/api/tenant_role.go`). Mutations use `auditIncidentChange`, which writes `incident-update/ack/resolve` rows with `actor=principalOf(user)`.
- There is no validation of `source` or `type`. Known source constants are `alertmanager`, `polling`, `github_webhook`, `manual` (`internal/alerts/types.go`) and `argo-workflows` (`internal/api/incident_trace.go`). No `support` source exists yet.
- `alerts.Store` (`internal/alerts/store.go`) is a concrete PostgreSQL store (`Options.AlertStore *alerts.Store`). Its schema is created idempotently from `alertSchema` and includes the partial unique index `alerts_tenant_fingerprint_open ON alerts (tenant, fingerprint) WHERE fingerprint <> '' AND status NOT IN ('resolved','suppressed')`. `Create` upserts on that index and, on a dedup hit, returns the original row (with an id different from the request id). `List` and `Summary` are the existing read queries. Store tests skip without `TEST_DATABASE_URL`.
- Route `/incidents/{id}` is two segments under `/incidents`. A new three-segment static route `/incidents/support/aggregation` does not collide in chi.

Principals and gates
- `auth.User` (`internal/auth/oidc.go`) carries unexported discriminators (`service`, `usageWriter`, `evidenceWriter`, `registryPublisher`, `securityProvider`, `ci`, ...). Only constructors and `userFromVerified` set them.
- The usage writer is the model to copy: `UsageWriterUserID = "service:mctl-agents-usage"`, `usageWriterTokenEnv`, `NewUsageWriterUser`, `IsUsageWriter`, and `usageWriterToken()`. That function refuses an empty token silently, and refuses with `slog.Error` a token shorter than `minSurfaceTokenLen` or equal to the service, registry-publisher or any surface token. It also has `usageWriterUserFor` (constant-time compare).
- The registry publisher's `registryPublisherToken()` shows the newer "compare against a list of other envs" shape, with mutual refusal documented. `securityProviderTokens()` (`internal/auth/security_provider.go` ~L145) has its own `others` list.
- Wiring points for a static-token principal:
  - `Middleware` reads tokens and passes them to the legacy chain (`MCTL_FEDERATION_DISABLED`, ~L1017-1028) and to `defaultFederationRegistry` (~L1159).
  - `federation_config.go` ~L195-202 builds the production registry.
  - `provider_static.go` (`usageWriterProvider`: `Name`, `Claims`, `Verify`).
  - `userFromVerified` (~L1228).
  - `User.Identity()` in `internal/auth/principal.go` (~L148), used by `AttachPrincipal`.
- Gates run in the authenticated group of `NewRouter` (`router.go` ~L492-528): `surfacePrincipalGate`, `agentScopeGate`, `agentPrincipalGate`, `usageWriterGate`, `evidenceWriterGate`, `securityProviderGate`, `registryPublisherGate`, `ciPrincipalGate`. `/mcp` is mounted in the same group (~L1042), so a gate also covers `/mcp`. `usageWriterGate` (`handlers_usage.go` L62) is a path+method check that answers `writeErrorCode(403, "usage_writer_route_not_allowed", ...)`.
- `principalOf` (`internal/api/handlers_work_items.go` L114) renders non-service, non-GitHub users as `oidc:<id>`. For the usage writer that gives `oidc:service:mctl-agents-usage`.
- The test pattern is `internal/api/handlers_usage_writer_test.go`. It uses `NewRouter(Options{AuthMiddleware: injectUser(...), MCPServer: ...})`, iterates refused routes, and checks that the one allowed route reaches its handler, which answers 503 with no store. `internal/auth/auth_test.go` has `TestUsageWriterTokenThatCouldBeConfusedIsRefused` and similar.
- Helm: `helm/values.yaml` `usageWriterTokenSecret` and `helm/templates/deployment.yaml` (optional `secretKeyRef` for `MCTL_USAGE_WRITER_TOKEN`), with `helm/render_test.go` covering the env.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/` has no `mctl-api` directory. mctl-api is deployed by `bootstrap/templates/mctl-platform/mctl-api.yaml`, which sets `usageWriterTokenSecret: mctl-api-usage-writer`, `evidenceWriterTokenSecret`, `registryPublisherTokenSecret` and `surfaceTelegramTokenSecret`. Each is gated on an `enabled` flag in `bootstrap/values.yaml` (for example `registryPublisher.enabled: true`). No support-incident-producer secret or flag exists there.
- `services/admins/mctl-support/values.yaml`: mctl-support runs in tenant `admins`, `MCTL_API_URL=https://api.mctl.ai`, `SUPPORT_EXECUTOR=fake` (S1a), `SUPPORT_ALLOWED_TENANTS=namax66`. It has no incident-producer token in env or envFrom today, only the db-creds secret.
- No mctl MCP tool calls were made, so the live pod env of mctl-api was not observed (see Open questions in requirements.md).

## Proposed solution

### 1. Principal (`internal/auth`)
New in `oidc.go`, next to the registry-publisher block:
```go
const (
    SupportIncidentProducerUserID   = "service:mctl-support-incidents"
    supportIncidentProducerTokenEnv = "MCTL_SUPPORT_INCIDENT_PRODUCER_TOKEN" //nolint:gosec
)
func NewSupportIncidentProducerUser() *User
func (u *User) IsSupportIncidentProducer() bool
func supportIncidentProducerToken() string     // registryPublisherToken shape
func supportIncidentProducerUserFor(configured, token string) *User // constant time
```
- Add an unexported field `supportIncidentProducer bool` to `User`. `HasPermission` gets no new case, so it answers false. There are no groups, so `IsAdmin` and `HasTenantAccess` are false.
- `supportIncidentProducerToken()` behaves as follows:
  - Empty token: return `""` and log INFO once (`sync.Once`, like `registryPublisherUnsetLogged`).
  - Token shorter than `minSurfaceTokenLen` (32): ERROR.
  - Token equal to any of `MCTL_AGENT_SERVICE_TOKEN`, `usageWriterTokenEnv`, `evidenceWriterTokenEnv`, `registryPublisherTokenEnv`, the `surfaceTokenEnv` values or the security-provider token env: ERROR `... equals another principal's token; support-incident-producer principal disabled` with `equals=<env>`.
  - Comparison values are re-read raw from the environment, as the other readers do.
- Reciprocity: add `supportIncidentProducerTokenEnv` to the refusal checks of `usageWriterToken`, `evidenceWriterToken`, `registryPublisherToken`'s `others`, `surfaceTokens` and `securityProviderTokens`. A shared value then disables both principals instead of letting provider order decide.
- Wiring:
  - `provider_static.go` gets a `supportIncidentProducerProvider`, a copy of `usageWriterProvider`.
  - It is added to `defaultFederationRegistry` (new parameter) and to `federation_config.go`'s static provider list.
  - `Middleware` reads the token once and adds it to the legacy `else if` chain after the registry publisher.
  - `userFromVerified` gets a new case for `SupportIncidentProducerUserID`.
  - `User.Identity()` in `principal.go` gets a new case, `Kind: KindService`.

### 2. Gate (`internal/api/handlers_support_incidents.go`, new)
```go
const supportIncidentProducerRoute = "/api/v1/incidents"
func supportIncidentProducerGate(next http.Handler) http.Handler
```
The gate answers 403 `support_incident_producer_route_not_allowed` unless `r.Method == POST && r.URL.Path == supportIncidentProducerRoute`. It is registered in `router.go` right after `registryPublisherGate`, so it also covers `/mcp` and the aggregation route.

### 3. CreateIncident changes (`handlers_alerts.go`)
- Move the `AlertStore == nil` check after body decoding and the producer checks. All producer refusals are then testable without Postgres, as `TestUsageWriter_IsConfinedToAppendingRecords` does. For other callers the only visible change is that malformed JSON returns 400 instead of 503 when the store is unset.
- After the required-field check, branch on `user.IsSupportIncidentProducer()`:
  - `a.Source != "support"` -> 403 `support_incident_source_not_allowed`, audit `denied`.
  - `!supportIncidentTypes[a.Type]` -> 403 `support_incident_type_not_allowed`, audit `denied`.
  - The allowed types are `platform_defect`, `quota_request`, `policy_exception` and `needs_owner`.
  - Empty fingerprint or no `support:` prefix -> 400.
  - Otherwise skip the `HasTenantAccess` / `requireTenantRole` checks. Force `Status = open`, and clear `Analysis`, `ProposedFix`, `PRURL`, `PRNumber`, `Confidence`, `AcknowledgedBy`, `AcknowledgedAt`, `ResolvedAt` and `ResolvedBy`.
- The non-producer path stays as it is.
- After a successful `Create` by the producer, write an audit row with `h.logAudit`:
  - Operation `incident-create`, `UserID = SupportIncidentProducerUserID`, status `succeeded`, risk low.
  - Parameters: `incident_id` (stored id), `requested_id`, `tenant`, `source`, `type`, `fingerprint`, `deduplicated` (`stored.ID != a.ID`), `actor`.
- `principalOf` gets a case returning `u.ID` for the producer, so `actor` is `service:mctl-support-incidents` and not `oidc:service:...`.
- New constants: `alerts.SourceSupport = "support"` in `internal/alerts/types.go`, and the type set as `alerts.SupportType*` constants.

### 4. Aggregation
- Store (`internal/alerts/store.go`), new method:
  ```go
  type SupportAggregate struct {
      Fingerprint     string   `json:"fingerprint"`
      Type            string   `json:"type"`
      AffectedTenants []string `json:"affected_tenants"`
      Count           int      `json:"count"`
  }
  func (s *Store) SupportAggregation(ctx context.Context) ([]SupportAggregate, error)
  ```
  SQL:
  ```sql
  SELECT fingerprint, type, array_agg(DISTINCT tenant ORDER BY tenant), count(*)
  FROM alerts
  WHERE source = 'support' AND fingerprint <> '' AND status NOT IN ('resolved','suppressed')
  GROUP BY fingerprint, type
  ORDER BY count(*) DESC, fingerprint
  ```
  Existing indexes (`alerts_status`, and the partial unique index) are adequate at current volume. No new index is needed.
- Handler `SupportIncidentAggregation` in `handlers_support_incidents.go`:
  - 503 if there is no store.
  - 401 if there is no user.
  - 403 `admin access required` unless `user.IsAdmin()`.
  - Otherwise returns `{"items": rows (never null), "count": len(rows)}`.
- Route: `r.Get("/incidents/support/aggregation", h.SupportIncidentAggregation)`, placed with the incident routes.

### 5. Configuration and docs
- `helm/values.yaml`: `supportIncidentProducerTokenSecret: ""`.
- `helm/templates/deployment.yaml`: optional `secretKeyRef` for `MCTL_SUPPORT_INCIDENT_PRODUCER_TOKEN`, a copy of the usage-writer block.
- `helm/render_test.go`: one case.
- `.env.example`, `README.md` env table and `CHANGELOG.md`.
- A short `docs/support-incidents.md` describing the principal, its confinement, the allowed types and the aggregation.

## Alternatives

1. **Mint mctl-support a scoped agent run token (`AgentScopeSupport`) that also allows incident creation.** The support scope is bound to one tenant and read-only by design (`internal/auth/agent_scope.go`), and run tokens are per task. Adding a write would widen a scope that guards the model loop itself. The issue also asks for a long-lived producer credential that is separate from the agent's run token, so a prompt-injected agent cannot file incidents directly. Dropped.
2. **Give mctl-support membership with the developer role in every tenant it serves.** This grants far more than incident creation (deploys, config) and would need GitOps membership churn per tenant. Dropped.
3. **Validate source/type inside the gate by buffering the body.** That keeps all producer rules in one place, but the gate would parse and re-buffer the body, and it would duplicate `CreateIncident`'s decoding. Route confinement in the gate plus field confinement in the handler matches how `ciPrincipalGate` + `authorizeCIDeploy` split the same concern. Dropped.
4. **Compute the aggregation in Go over `Store.List`.** `List` is limit-bounded and would silently truncate. Doing it in SQL is exact and cheap. Dropped.

## Platform impact

- **Migrations:** none. No schema change. The aggregation reads existing columns.
- **Backward compatibility:** the producer principal does not exist until the env var is set, so existing deployments are unchanged. The non-producer `CreateIncident` path is unchanged except for the order of the 503 check, as described above. No MCP tool changes, so the `server_test.go` count is unchanged.
- **Security:**
  - The principal skips tenant authorization on one write. The gate, the source/type allowlist, the forced `open` status and the audit row bound what it can do.
  - Risk: a leaked token lets an attacker create noise incidents for any tenant name. Mitigations: rotate the token, unset it to disable the principal, and use the audit row to identify all writes. The per-user 300/min rate limit also applies.
  - Risk: a token collision with another principal. Mitigation: mutual refusal plus ERROR logs.
- **Resources:** one extra grouped query on admin request only. Negligible.
- **Rollout dependency:** mctl-gitops must add the secret and the bootstrap value, and mctl-support must send the token. Until then nothing changes.
