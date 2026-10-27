# Tasks: issue-830-feat-incidents-support-incident-producer

- [ ] 1. Add the principal in `internal/auth/oidc.go`:
  - `SupportIncidentProducerUserID = "service:mctl-support-incidents"`, `supportIncidentProducerTokenEnv = "MCTL_SUPPORT_INCIDENT_PRODUCER_TOKEN"`.
  - Unexported `supportIncidentProducer` field, `NewSupportIncidentProducerUser`, `IsSupportIncidentProducer`.
  - `supportIncidentProducerToken()`: unset logs INFO once. Short, or equal to the service, usage-writer, evidence-writer, registry-publisher, any surface or any security-provider token, logs ERROR naming the env.
  - `supportIncidentProducerUserFor` (constant-time compare). No `HasPermission` case.

  DoD: the principal has no groups, `IsAdmin()==false`, `HasTenantAccess(x)==false`, `HasPermission(p)==false` for every existing permission.
- [ ] 2. Reciprocal refusal (depends on 1). Add `supportIncidentProducerTokenEnv` to the equality checks in `usageWriterToken`, `evidenceWriterToken`, `registryPublisherToken` (`others`), `surfaceTokens` and `securityProviderTokens` (`internal/auth/security_provider.go`). DoD: setting any of those equal to the producer token disables both principals, and each side logs ERROR.
- [ ] 3. Wire authentication (depends on 1):
  - `supportIncidentProducerProvider` in `provider_static.go`.
  - Add it to `defaultFederationRegistry` (new parameter) and to `federation_config.go`'s static list.
  - Add `Middleware`'s legacy chain branch.
  - Add a `userFromVerified` case and a `User.Identity()` case in `principal.go` (`KindService`).

  DoD: the producer token authenticates as `service:mctl-support-incidents` with `MCTL_FEDERATION_DISABLED` both on and off.
- [ ] 4. Add the alert constants in `internal/alerts/types.go`: `SourceSupport = "support"` and the four support types `platform_defect`, `quota_request`, `policy_exception`, `needs_owner`, plus a lookup set. DoD: compiled, with no behaviour change.
- [ ] 5. Add the gate (depends on 1). Create `internal/api/handlers_support_incidents.go` with `supportIncidentProducerGate`, which answers 403 `support_incident_producer_route_not_allowed` unless `POST /api/v1/incidents`. Register it in `router.go` after `registryPublisherGate`. DoD: the producer gets 403 on every other route, including `/mcp`.
- [ ] 6. Change `CreateIncident` (depends on 4, 5):
  - Move the nil-store check after decoding and the producer checks.
  - Producer branch: wrong source -> 403 `support_incident_source_not_allowed`, unknown type -> 403 `support_incident_type_not_allowed`, both with a `denied` audit row. A missing or non-`support:` fingerprint -> 400.
  - Skip the tenant access and role checks for the producer. Force status `open` and clear the triage fields.
  - After `Create`, write the `incident-create` succeeded audit row (`incident_id`, `requested_id`, `tenant`, `source`, `type`, `fingerprint`, `deduplicated`, `actor`).
  - `principalOf` returns `u.ID` for the producer.

  DoD: the non-producer path is unchanged apart from the 503 ordering.
- [ ] 7. Add the store aggregation (depends on 4). `alerts.SupportAggregate` and `(*Store).SupportAggregation`, using the grouped SQL in design.md (`array_agg(DISTINCT tenant ORDER BY tenant)`, open statuses only, non-empty fingerprint, ordered by count desc then fingerprint). DoD: it returns an empty non-nil slice when there are no rows.
- [ ] 8. Add the aggregation handler and route (depends on 5, 7). `SupportIncidentAggregation` returns 503 with no store, 401 with no user, and 403 for a non-admin; otherwise `{"items": [...], "count": n}`. Route: `r.Get("/incidents/support/aggregation", ...)` in `router.go`. DoD: an admin gets rows, everyone else gets 403.
- [ ] 9. Helm and docs:
  - `supportIncidentProducerTokenSecret` in `helm/values.yaml`, plus an optional `secretKeyRef` env in `helm/templates/deployment.yaml` and a case in `helm/render_test.go`.
  - `.env.example`, `README.md`, `CHANGELOG.md`, and new `docs/support-incidents.md`.

  DoD: `go test ./helm/...` passes, and the rendered env appears only when the value is set.
- [ ] 10. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`. DoD: clean.

## Tests

- [ ] T1. `internal/auth`, token reading. Unset: no principal, and the token does not authenticate. Shorter than 32: disabled, ERROR logged. Equal to each of the service, usage-writer, evidence-writer, registry-publisher, a surface and a security-provider token: disabled, ERROR logged naming the env, and the other principal is disabled too (reciprocity).
- [ ] T2. `internal/auth`, authentication. A valid token yields `IsSupportIncidentProducer()`, ID `service:mctl-support-incidents`, not admin, no tenant access, and `HasPermission` false for usage:write, evidence:write, security ingest/remediate. Test it through the default registry and the `MCTL_FEDERATION_DISABLED` chain. `Identity()` returns `ProviderService` / `KindService`.
- [ ] T3. `internal/api`, through `NewRouter` with `MCPServer` mounted. The producer gets 403 `support_incident_producer_route_not_allowed` on:
  - `GET /api/v1/incidents`, `GET /api/v1/incidents/summary`, `GET /api/v1/incidents/abc`
  - `PATCH /api/v1/incidents/abc`, `POST /api/v1/incidents/abc/ack`, `POST /api/v1/incidents/abc/resolve`, `POST /api/v1/incidents/resolve-by-fingerprint`
  - `GET /api/v1/incidents/support/aggregation`, `GET /api/v1/whoami`, `GET /api/v1/tenants`, `POST /api/v1/usage/records`
  - `POST /mcp`, `GET /mcp`, `POST /api/v1/incidents/`

  `POST /api/v1/incidents` with a valid support body passes the gate and gets 503 from the handler (no store). A companion test runs the same router minus the gate (handlers mounted directly) and shows that at least `PATCH /incidents/{id}` and `/mcp` are no longer refused with the gate code. This demonstrates the gate is load-bearing.
- [ ] T4. `internal/api`, no DB. The producer posting `source=manual` (and `alertmanager`) gets 403 `support_incident_source_not_allowed`. `type=other` gets 403 `support_incident_type_not_allowed`. A missing fingerprint, or `fingerprint=x`, gets 400. A `denied` audit row exists for the 403 cases. Valid bodies reach 503. A non-producer tenant member posting to a tenant it does not belong to still gets 403 (behaviour unchanged).
- [ ] T5. `internal/api`, with `TEST_DATABASE_URL`:
  - The producer posts the same `support:platform_defect:abc123` fingerprint for tenants `t1` and `t2`. The result is two incidents with distinct ids, and status `open` even when the body said `resolved`.
  - The admin aggregation returns one row `{fingerprint, type: platform_defect, affected_tenants: [t1, t2], count: 2}`.
  - A repeat post for `t1` returns the original id with `deduplicated=true` in the audit row, and the aggregation count stays 2.
  - Resolving t1's incident drops the count to 1. A non-support source incident with the same fingerprint is excluded.
- [ ] T6. `internal/api`, aggregation authorization. A tenant member, a surface principal, the usage writer and the producer (handler called directly, bypassing the gate) each get 403. With no store: 503 for the admin.
- [ ] T7. `internal/api`, audit. A successful producer create writes exactly one `incident-create` `succeeded` row, with `UserID=service:mctl-support-incidents`, `actor=service:mctl-support-incidents`, and the tenant, source, type and fingerprint parameters. No summary or evidence text appears in the parameters.
- [ ] T8. `internal/alerts` store test (with `TEST_DATABASE_URL`). `SupportAggregation` ordering, de-duplicated tenants, and an empty non-nil result.
- [ ] T9. `helm/render_test.go`. `MCTL_SUPPORT_INCIDENT_PRODUCER_TOKEN` is rendered with `optional: true` only when `supportIncidentProducerTokenSecret` is set.

## Rollback

- Operational: unset `MCTL_SUPPORT_INCIDENT_PRODUCER_TOKEN` (remove the secret, or disable the bootstrap flag in mctl-gitops) and roll mctl-api. The principal then no longer exists and every request with that token is 401. Incidents it already created stay as ordinary `source=support` incidents and can be resolved by admins.
- Code: revert the PR. There is no schema change and no data migration, so a revert is safe at any time. The aggregation route disappears, and the incident data is unaffected.
