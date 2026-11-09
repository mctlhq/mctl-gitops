# Tasks: issue-961-feat-glovo-m1a-4-synthetic-connection-ha

- [ ] 0. STOP if #958, #959 or #960 are not merged. Reconcile the actual names of
  `IsGlovoAudience`, `IsGlovoWorker`, `glovoAudienceGate`, `glovoWorkerGate`,
  `glovo.Resolver`, `glovo.Store`, the refusal enum, connection states and the #961-owned limit counters (not in #959).
  DoD: a short mapping note is added to `docs/glovo-connections.md`. If any slice is unmerged or
  a primitive is missing, stop and report it, and add nothing that duplicates it.
- [ ] 1. Add the feature gate (depends on 0): `GLOVO_ENABLED` in `cmd/api/main.go`,
  `Handlers.glovoReady()` and `glovoFeatureGate` on the `/api/v1/glovo` subtree. DoD: every
  Glovo route returns 503 `not_ready` when disabled or misconfigured, before decoding.
- [ ] 2. Add versioned wire types (depends on 0) in `internal/glovo/wire`: structs with a `schema`
  constant, a strict decoder (16 KiB, `DisallowUnknownFields`, exact schema), `PublicState`,
  `refusalStatus`, and JSON Schemas under `wire/schema/`. DoD: golden tests show that marshal
  output validates and that every store state and refusal code is mapped.
- [ ] 3. Add the facade handlers (depends on 1, 2) in `internal/api/handlers_glovo_facade.go`:
  context, connect, get, handoff, revoke, reconnect, using the resolver-derived scope only,
  `Idempotency-Key`, hashed single-use handoff references, and the DB rate limits. DoD: routes
  are registered in `router.go` and unit tests pass.
- [ ] 4. Add the admin handlers (depends on 1, 2) in `internal/api/handlers_glovo_admin.go`:
  installation PUT/DELETE behind the principal-mode `requireTenantRole` owner check, and the
  admin-only per-principal pilot allowlist PUT/DELETE. DoD: a reinstall revokes live
  connections atomically, and admins are not auto-admitted to installation routes.
- [ ] 5. Implement or prove a default-OFF dedicated worker machine identity (not minted in #958); then add the worker handlers (depends on 1, 2) in `internal/api/handlers_glovo_worker.go`:
  check, activate, expire, with per-call re-derivation of membership, allowlist, install
  revision and expiry, and the explicit `IsGlovoWorker` check. DoD: the worker reaches only
  these routes, and no other identity reaches them.
- [ ] 6. Add the additive handoff and quota DB schema with negative concurrency tests, then add audit and logging (depends on 3, 4, 5): an audit event for every mutation and every
  refusal on a mutating route, and `slog` fields limited to ids, states and codes. DoD: covered
  by T5.
- [ ] 7. Add the end-to-end test harness (depends on 3, 4, 5) in
  `internal/api/glovo_e2e_test.go`: real `NewRouter`, real store on `TEST_DATABASE_URL`, tokens
  minted through the real OAuth consent flow with a selected team, the real worker token, and
  fixtures with two tenants and two users in one tenant. DoD: the tests run in the CI
  `validate.yml` Postgres job and do not skip there.
- [ ] 8. Write the docs and OpenAPI (depends on 3-5): `docs/glovo-connections.md` (state diagram,
  routes, schemas, refusals, test matrix, anti-regression list, default OFF, integration NOT
  READY until #957 and mctl-telegram#1235) and the `internal/openapi` entries. DoD: the OpenAPI
  tests pass, and the MCP tool count is unchanged.
- [ ] 9. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`. DoD: all are clean.

## AMEND 2026-11-08 — additional acceptance

- [ ] A1. Add a default-OFF Glovo-only worker machine identity and gate, or keep worker routes `not_ready`; never use a general admin/service token as substitute. #958 reserves ID but does not issue a token.
- [ ] A2. Add additive, idempotent, hash-only handoff table and cross-replica PostgreSQL quota counters. Demonstrate **one** handoff consume even under concurrent worker requests, and zero activation if revoke or expiry wins.
- [ ] A3. Two API instances racing at the final hourly/tenant quota slot cannot exceed the rate limit.
- [ ] A4. Block if #958/#959/#960 are not merged and their actual interfaces do not match. No duplicated shims or unreviewed prerequisite implementation.
- [ ] A5. No live credentials, DNS, P1/P2 rollout, Temporal client auth change or real Glovo provider.

## Tests

- [ ] T1. Feature off: every `/api/v1/glovo/*` route (enumerated with `chi.Walk`) returns 503
  `not_ready`, and token issuance and verification match the baseline.
- [ ] T2. Happy path for `a1` in `alpha`: connect (201 `pending`), handoff, worker activate,
  worker check (`allowed`), facade context shows `active`, revoke, worker check returns
  `connection_revoked`.
- [ ] T3. Isolation: `a2` on `a1`'s connection id gets 404, and `b1` on an `alpha` id gets 404.
  Both bodies are byte-identical to the 404 for a missing id. The worker check against the
  wrong revision returns `stale_install`.
- [ ] T4. Fail-closed inputs:
  - token with no grant, and `u3` eligible but unselected: `ambiguous_tenant`;
  - personal scope: `scope_unsupported`;
  - not allowlisted: `not_in_pilot`;
  - role removed mid-session, or allowlist row deleted: refused on the next facade call and the
    next worker check;
  - forged `tenant`/`owner`/`install_revision` body fields: 400;
  - forged `X-Mctl-Selected-Tenant` header: ignored, scope unchanged;
  - wrong-audience and multi-aud tokens: 401;
  - no `labs` fallback.
- [ ] T5. Audit and no leak: the expected audit rows exist for each mutation and refusal.
  `secretscan` and raw-string scans of the `slog` buffer, audit rows and non-handoff responses
  find no token, handoff reference or idempotency key.
- [ ] T6. Lifecycle:
  - reinstall revokes live connections, and the old revision then returns `stale_install`;
  - DELETE installation revokes all connections;
  - expiry (worker expire, or time past `expires_at`) makes reads and checks return `expired`;
  - reconnect returns a new `gcn_` id with `replaces_id`, and the old connection stays terminal;
  - reconnect from `active` returns `invalid_transition`;
  - a handoff reference cannot be reused or used after expiry.
- [ ] T7. Idempotency and limits: a same-key replay returns `replayed:true`. The same key with a
  different body returns 409 `idempotency_key_reused`. A missing key returns 400. The eleventh
  connect in an hour returns 429. Concurrent connect and revoke (parallel goroutines against the
  real DB) leave no live connection on a stale revision.
- [ ] T8. Identity confinement: the worker token gets 403 on facade routes, `/mcp`,
  `/api/v1/agents/dev-loop/*`, admin installation routes and `/api/v1/whoami`. An admin, the
  service token, a support-audience token and a Glovo-audience token each get 403 or 401 on
  worker routes. A Glovo-audience token gets 401 outside `/api/v1/glovo/facade/*`.
- [ ] T9. Schema contract: every response and refusal validates against
  `internal/glovo/wire/schema`. Unknown fields, a wrong `schema` or a body over 16 KiB returns
  400.
- [ ] T10. Regression: the existing support-audience, DevLoop, commerce and MCP tool-count tests
  are unchanged and pass.

## Rollback

The feature is default OFF (`GLOVO_ENABLED` unset), so production behaviour does not change on
merge. If an issue appears after a later enablement, unset `GLOVO_ENABLED` in gitops: every route
returns to 503 `not_ready`. For a code rollback, revert the PR. This slice adds no new tables,
and any index added in task 0 is additive and harmless if left behind. Slice 2's tables and data
remain and are unused.
