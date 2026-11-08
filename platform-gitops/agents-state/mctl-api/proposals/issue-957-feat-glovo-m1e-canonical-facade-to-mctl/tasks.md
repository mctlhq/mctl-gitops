# Tasks: issue-957-feat-glovo-m1e-canonical-facade-to-mctl

Gate: tasks 6-9 need the M1a (#953) and M1b (#954) packages merged. Until then, build
tasks 1-5 against the narrow interfaces `glovojoin.Connections` and `glovojoin.Orders`
using in-test doubles, and do not claim deploy-readiness anywhere.

- [ ] 1. Write the frozen contract `internal/glovojoin/contract/glovo-facade-mctl-api.v1alpha1.json` (route matrix, request/response schemas, refusal and status table, idempotency, limits, timeouts, OAuth resource metadata, dependency version gates), plus `contract.go` (embed, `Version`, `Digest`) and `docs/glovo-join.md` (matrix, source owners, launch compatibility matrix). — DoD: `contract_test.go` validates the file, pins the digest and fails on any byte change without a digest bump.
- [ ] 2. Add the pinned M0 tool schema copy `testdata/glovo-mcp-tools.json` with its digest, and the golden fixtures `testdata/v1alpha1/<route>/*.json` (success, every refusal, replay). (depends on 1) — DoD: a test asserts every 200 schema equals the tool `output_schema` and every fixture validates against the contract.
- [ ] 3. Add the facade workload principal: `NewGlovoFacadeUser()` in `internal/auth/oidc.go`, the env `MCTL_GLOVO_FACADE_TOKEN` in `cmd/api/main.go` (startup refusal if it equals any other machine token), and `internal/api/glovo_join_gate.go` mounted right after `supportAudienceGate` in `NewRouter`. — DoD: the facade reaches only the join prefix, and every other principal gets 401 `not_facade_identity` there.
- [ ] 4. Add `glovojoin.SubjectVerifier`, which reuses the local-OAuth verify path for `X-Mctl-Subject-Token` (iss, exact Glovo aud, exp, revocation, principal), strips the header, and records only the token hash. Add the `mctl_tenant` claim check and the `X-Mctl-Selected-Tenant` must-match rule. (depends on 3) — DoD: unit tests cover each refusal code, and a log-capture test proves no token bytes are logged.
- [ ] 5. Add consent-time tenant selection for `GLOVO_MCP_RESOURCE` in `/oauth/consent` (eligible tenants from the M1a resolver, nothing preselected). Persist the choice on the authorization code and the refresh family, and mint `mctl_tenant`. (depends on 4; coordinate with the M1a owner, see open question) — DoD: a token minted without a selection is refused by the join API with `tenant_selection_required`, and a non-eligible selection is refused at consent.
- [ ] 6. Add `internal/glovojoin` handlers for the nine routes in design.md section 3, with strict JSON decode (unknown and duplicate keys refused), the scope check, the header/body idempotency rule from `handlers_action_approvals.go:411`, and refusal mapping. Register them under `GLOVO_JOIN_ENABLED` in `router.go` with their own rate-limit group. (depends on 1-4, M1a/M1b interfaces) — DoD: every golden fixture passes against the handler.
- [ ] 7. Add the `ReadBridge` interface, `GlovoReadRequest`/`GlovoReadResult` (`glovo-read/v1alpha1`), `NotReadyBridge` (default) and `FixtureBridge` (build tag `glovojoin_fixture`). Add the `glovo_join_previews` store with inline DDL. (depends on 6) — DoD: without a bridge the read routes return 503 `not_ready/read_bridge`, a mismatched echo becomes `dependency_unavailable`, and the release build contains no `FixtureBridge`.
- [ ] 8. Wire the prepare and status paths to M1b `Prepare`/`OwnerStatus` (`pord_` + `we_` + pending `aar_` in one transaction, zero provider writes) and connection status/create to M1a. (depends on 6, M1a/M1b merged) — DoD: the harness shows prepare creates exactly one pending `aar_` and no effect row, and a replay returns `replayed: true`.
- [ ] 9. Add `GET /compatibility` and `glovojoin.Readiness`, and update the OpenAPI spec (`internal/openapi/openapi.yaml`). (depends on 6-8) — DoD: `deploy_ready` is false whenever any dependency is not ready, and the OpenAPI spec lists the join routes.
- [ ] 10. Add the harness `internal/glovojoin/harness_test.go` and `cmd/glovo-join-harness` (fixture tag) against the real `api.NewRouter` and Postgres stores. Add the CI job in `.github/workflows/validate.yml`. (depends on 8) — DoD: the CI job runs the full matrix on `TEST_DATABASE_URL`.
- [ ] 11. Open a cross-repo follow-up for mctl-telegram#1235: vendor the contract and fixtures, drop `X-Mctl-Scope-Ref` and `gsc_`, and treat `X-Mctl-Selected-Tenant` as an echo only. Point its integration test at `cmd/glovo-join-harness`. (depends on 1, 2) — DoD: an issue or PR is linked from `docs/glovo-join.md` with the pinned digest.

## Tests

- [ ] T1. Contract digest and version pin; fixture schema validation; equality of tool output schemas.
- [ ] T2. Gate matrix: every principal kind (admin, service, support-aud, agent, delegated agent, surface relay, M1a worker, CI, facade) × every join route, plus facade × `/mcp` and other `/api/v1` routes.
- [ ] T3. Subject token: wrong issuer, API audience only, support plus Glovo audience mixed, expired, revoked `jti`, token in the query string, missing header. Each gets its exact code, and no token bytes appear in logs.
- [ ] T4. Tenant: missing `mctl_tenant` gives `tenant_selection_required`, with no fallback to the sole membership or `labs`. Header mismatch gives `tenant_mismatch`. A claim tenant outside the allowlist or without an install gives the M1a code unchanged.
- [ ] T5. Idempotency: same key and body gives a replay; same key with a different body gives 409; header/body key mismatch gives 400.
- [ ] T6. Negative matrix through the real handlers: two tenants (A cannot see B's connection, preview or order); two owners in one team (owner 2 gets 404 on owner 1's `pord_`); a stale install; a revoked grant; the wrong connection or order id; an `aar_` approved and then the connection revoked before the physical fake provider mutation (the M1b fence refuses, and the join status shows the refusal); a replayed `aar_` receipt (refused by M1b and never reachable from join routes); `hir_` ids rejected by the schema; a duplicate provider command (one effect only); no checkout/pay route exists (route-table assertion).
- [ ] T7. Bridge: `NotReadyBridge` gives 503 `not_ready`; a result with a mismatched request id, connection or revision gives `dependency_unavailable`; `Synthetic:false` is refused.
- [ ] T8. Rate limits: the per-subject and aggregate facade limits return 429 with `Retry-After`. `traceparent` is propagated, and span attributes contain no token.
- [ ] T9. With `GLOVO_JOIN_ENABLED` off, all join routes return 404 and the existing router tests are unchanged. The MCP tool count in `server_test.go` is unchanged.

## Rollback

Set `GLOVO_JOIN_ENABLED=false` (the default) and unset `MCTL_GLOVO_FACADE_TOKEN`. The join
routes then disappear and the facade gets 404 or 401, which it surfaces as `not_ready`. The
consent change is inert for every resource other than `GLOVO_MCP_RESOURCE`. The
`glovo_join_previews` table and the nullable selected-tenant column are additive and can
stay, or be dropped by a follow-up. Reverting the PR restores the previous router exactly,
since no existing route or gate behaviour is modified. No provider writes are possible in
this slice, so there is no external state to unwind.
