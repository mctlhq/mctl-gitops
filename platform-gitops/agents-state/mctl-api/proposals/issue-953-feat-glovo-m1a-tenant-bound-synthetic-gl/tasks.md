# Tasks: issue-953-feat-glovo-m1a-tenant-bound-synthetic-gl

- [ ] 1. Add `GlovoResource` to `auth.OAuthServer`, `GLOVO_MCP_RESOURCE` config in `cmd/api/main.go` with validation (absolute https, no fragment, not this API, not `SupportResource`), and resolution in `ResolveResource` — DoD: unset value keeps current behaviour; set value mints `aud = GlovoResource`; unit tests in `internal/auth/oauth_resource_test.go`.
- [ ] 2. Classify Glovo audience in token verification (`oauth_server.go`), precedence Glovo > support > API, `User.IsGlovoAudience()` (depends on 1) — DoD: mixed-`aud` and wrong-`iss` tests pass; support tests unchanged.
- [ ] 3. `internal/api/glovo_audience_gate.go` confining Glovo tokens to `/api/v1/glovo/facade/*`, mounted next to `supportAudienceGate` in `router.go` (depends on 2) — DoD: Glovo token gets 401 on `/mcp` and every non-facade route; other tokens get refused on facade routes with `not_authorized`.
- [ ] 4. `MCTL_GLOVO_WORKER_TOKEN` machine identity in `internal/auth/oidc.go` plus `glovoWorkerGate` — DoD: constant-time compare, disabled when equal to another machine token, confined to `/api/v1/glovo/worker/*`, those routes refuse service, admin, support and mctl-telegram tokens.
- [ ] 5. `internal/glovo` types, refusal enum, state transition table — DoD: table-driven test covering every allowed and forbidden transition.
- [ ] 6. `internal/glovo/store.go` with inline DDL (installations, connections, connection_requests, pilot_allowlist, audit_events with immutability trigger), tenant+owner scoped reads, `withTx` per-tenant advisory lock, retention sweep (depends on 5) — DoD: unique and partial unique indexes present; foreign id returns `ErrNotFound`; UPDATE on audit rows fails.
- [ ] 7. `internal/glovo/scope.go` resolver from authenticated principal via principal-mode tenant roles ∩ pilot allowlist (depends on 2, 6) — DoD: returns `not_authorized`, `no_tenant`, `not_in_pilot`, `ambiguous_tenant`, `scope_unsupported` per requirements; ignores admin and agent scopes; role read failure is 503.
- [ ] 8. Synthetic provider, refusing `SecretRefStore`, DB-backed rate limits and idempotency (depends on 6) — DoD: no network calls; `secret_ref` always NULL; replay returns `replayed: true`; key reuse 409; limits return 429.
- [ ] 9. Handlers `internal/api/handlers_glovo.go` for facade, worker, tenant installation (owner role via `requireTenantRole`) and admin pilot routes with strict JSON decoding and refusal mapping (depends on 3, 4, 7, 8) — DoD: all routes in design.md respond per the refusal table; atomic reinstall and revoke.
- [ ] 10. Wire store in `cmd/api/main.go` (`GLOVO_DB_URL` -> `AUDIT_DB_URL`, `GLOVO_DISABLED`), Helm values documented but default off (depends on 9) — DoD: routes 503 when store or resource absent; startup unchanged otherwise.
- [ ] 11. JSON Schemas in `internal/glovo/schema/`, OpenAPI entries, `docs/glovo-connections.md` (state diagram, schema, refusal table, secret envelope design, test matrix) (depends on 9) — DoD: schema tests validate handler responses against the files.

## Tests

- [ ] T1. Cross-tenant/cross-owner matrix: tenants A and B, principals A1, A2 (same tenant A) and B1; each creates a connection; every principal probing every other id on every facade route gets an identical 404 `not_found`; worker check only allows the owner's current revision.
- [ ] T2. Audience/issuer: API-audience, support-audience, wrong-issuer, expired, and audless tokens refused on facade routes with no store write (assert audit/connection row counts unchanged except refusal audit).
- [ ] T3. Scope: principal with no tenant, with tenants none allowlisted, with two allowlisted tenants, with personal-only scope -> `no_tenant`, `not_in_pilot`, `ambiguous_tenant`, `scope_unsupported`; platform admin without membership -> `no_tenant`.
- [ ] T4. Impersonation: bodies carrying `tenant`, `owner`, `namespace`, `task_queue`, `workflow_id` rejected 400; headers such as `X-Tenant` ignored; scope equals token principal.
- [ ] T5. Lifecycle: connect -> handoff -> activate -> expire; reconnect issues a new id and revokes the old; second live connect hits the partial unique index and is refused; forbidden transitions refused.
- [ ] T6. Revocation propagation: revoke and reinstall bump revision and revoke all live connections in one transaction; subsequent worker checks return `connection_revoked` / `stale_install`; membership removal returns `not_authorized`/`no_tenant` on check; concurrent connect vs reinstall (two goroutines) never leaves a live connection on an old revision.
- [ ] T7. Idempotency and rate limits: replay, key reuse 409, 11th connect in an hour 429, tenant cap 429, all without state change.
- [ ] T8. Secret hygiene: run `internal/secretscan` over captured slog output, audit rows, API responses and test fixtures; `secret_ref` CHECK rejects a non-null insert; refusing secret store returns `ErrSecretsUnsupported`.
- [ ] T9. Regression: existing `internal/auth` support-resource tests, `support_audience_gate` tests, `tg.mctl.ai`/surface identity tests, automation contract and DevLoop handler tests pass unchanged; `TestNewMCPServer_ToolCount` unchanged; with `GLOVO_MCP_RESOURCE` unset token output is identical to before.
- [ ] T10. Worker identity: worker token refused on facade, admin and all non-worker routes; service token, mctl-telegram token and admin token refused on worker routes.
- [ ] T11. Audit immutability: UPDATE and early DELETE on `glovo_audit_events` fail; retention sweep removes only rows past the window.

## Rollback

The feature is off unless both `GLOVO_MCP_RESOURCE` and a database are
configured, and the deployed mctl-api sets neither Glovo variable. To roll back:
unset `GLOVO_MCP_RESOURCE` (or set `GLOVO_DISABLED=true`), which makes every
Glovo route 503 and stops minting Glovo-audience tokens; already minted Glovo
tokens are then refused because the audience no longer matches. If needed,
revert the release. The `glovo_*` tables are additive and can stay in place or
be dropped by a follow-up migration; no existing table is modified.
