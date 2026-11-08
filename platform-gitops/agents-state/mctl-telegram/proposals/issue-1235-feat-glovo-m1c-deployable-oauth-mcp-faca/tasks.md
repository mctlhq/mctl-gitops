# Tasks: issue-1235-feat-glovo-m1c-deployable-oauth-mcp-faca

- [ ] 1. Freeze the wire protocol: write `docs/contracts/glovo-facade-mctl-api.md`
  (`glovo-facade-mctl-api/v1alpha1`, endpoints, headers, error codes, timeouts) and add
  it to `TestGlovoDocsHaveNoCredentialShapes` in `docs/glovo_contract_test.go`. — DoD:
  doc merged in the same PR, `go test ./docs/...` green, image name
  `ghcr.io/mctlhq/mctl-glovo-mcp` and server name `mctl-glovo-mcp` stated in it.
- [ ] 2. `internal/glovo/contract`: embedded copy of `glovo-mcp-tools.json` with a
  byte-equality test against `docs/contracts/glovo-mcp-tools.json`, plus compiled
  schemas (`santhosh-tekuri/jsonschema/v6`). (depends on 1) — DoD: loader returns the
  seven tools and scopes; drift test fails if either copy changes alone.
- [ ] 3. `internal/glovo/config`: parse and validate `GLOVO_MCP_*` env, kill switch
  default false, https-only URLs outside dev loopback, resource equals contract
  resource in non-dev mode. — DoD: table tests for every invalid value; no tenant env.
- [ ] 4. `internal/glovo/authn`: JWKS cache and `Verifier` (go-jose v4, RS256/ES256,
  exact `iss`, exact `aud`, `exp`/`nbf`/`iat` skew, `sub`, `scope`, `mctl_tenant`),
  header-only bearer extraction with query/form token refusal, 401/403 responses with
  `WWW-Authenticate` `resource_metadata`, and the RFC 9728 `MetadataHandler`. (depends
  on 2, 3) — DoD: unit tests for each rejection reason; metadata scopes read from the
  contract.
- [ ] 5. `internal/glovo/mctlapi`: `Client` interface and HTTP implementation of
  v1alpha1 (header forwarding, `X-Mctl-Scope-Ref`, 256 KiB response cap, 5 s timeout,
  retry rules, typed error mapping, traceparent propagation). (depends on 1) — DoD:
  golden request/response fixtures in `testdata/` exercised by `wire_test.go`.
- [ ] 6. `internal/glovo/mctlapi/fakeapi`: fake mctl-api serving v1alpha1 from the same
  fixtures, in-memory JWKS issuer, tenants/members/allowlist/installs, per-user `gcn_`,
  orders, previews, `aar_` with separate `/_fake/approve/{aar}`, `hir_` records,
  revocation, and an effect-call recorder; `cmd/glovo-mcp-fakeapi` behind build tag
  `glovofake`. Personas Alice, Bob (`team-alpha`), Carol (`team-beta`), Dana (not in
  allowlist). (depends on 5) — DoD: `wire_test.go` passes against both the client and
  the fake.
- [ ] 7. `internal/glovo/tools`: seven handlers on the single template (strict args via
  `jsonstrict` + schema, scope check, `Resolve`, one mctl-api call, output schema
  validation, typed refusals as `isError` results), registered with raw schemas. No
  other tool, resource or prompt. (depends on 2, 4, 5) — DoD: `tools/list` golden equals
  the contract.
- [ ] 8. `internal/glovo/facade`: chi router with only the frozen routes, request id,
  64 KiB `MaxBytesReader`, 30 s timeout, per-principal `x/time/rate` limiter and
  inflight semaphore, own Prometheus registry and metrics, OTel spans, audit slog line
  through `audit.NewRedactingHandler`; add new sensitive keys to
  `internal/audit/redact.go`. Pinned MCP protocol-version list. (depends on 4, 7) — DoD:
  handler tests for 404, 413, 429, 503-when-disabled.
- [ ] 9. `cmd/glovo-mcp/main.go`: wiring, `/healthz`, `/readyz` (enabled + JWKS loaded +
  mctl-api health within 2 s), SIGTERM: readiness false, `Shutdown` with 20 s drain,
  `main.version` ldflag. (depends on 3, 8) — DoD: `go run ./cmd/glovo-mcp` against the
  fake serves a full MCP session locally; documented in `docs/glovo-mcp.md`.
- [ ] 10. `internal/glovo/imports_test.go`: `go list -deps ./cmd/glovo-mcp` must not
  contain `internal/telegram`, `internal/oauth`, `internal/db`, `internal/bridge`,
  `go.temporal.io/`, `github.com/gotd/`; and `./cmd/server` must not contain
  `internal/glovo`. (depends on 9) — DoD: test fails on a planted import.
- [ ] 11. `Dockerfile.glovo-mcp`: digest-pinned builder and runtime, non-root 1000,
  static binary, OCI labels, minimal COPY set. (depends on 9) — DoD: `docker build -f
  Dockerfile.glovo-mcp .` succeeds; container `/healthz` 200 with default config and
  `/mcp` 503.
- [ ] 12. CI: `glovo-mcp-image` job in `.github/workflows/build.yml` (build with no
  push, run, probe health, run integration suite); `glovo-mcp-release` job in
  `.github/workflows/release-please.yml` guarded by
  `.github/scripts/gitops-values-present.sh platform-gitops/services/labs/glovo-mcp/values.yaml`,
  skip notice on 404, fail on unreadable. (depends on 11) — DoD: job green on the PR;
  release dry-run shows skip notice; no push of any image.
- [ ] 13. `docs/glovo-mcp.md` runbook (config table, probes, kill switch, activation
  checklist referencing gates G2, G4, G5, G6) and cross-link from ADR 0010. (depends on
  9) — DoD: doc test pattern consistent with `docs/runbook_test.go` style if applicable.

## Tests

All in `go test -race ./...` unless noted; integration tests start the fake mctl-api
and the facade with `httptest` and drive them with the mcp-go Streamable HTTP client.

- [ ] T0. Contract drift: embedded contract equals `docs/contracts/glovo-mcp-tools.json`;
  served `tools/list` equals the seven tools with identical schemas; no resources or
  prompts listed.
- [ ] T-OAuth1. Discovery: unauthenticated `/mcp` gives 401 with `resource_metadata`;
  both PRM paths return `resource` `https://glovo.mctl.ai/mcp`, issuer, scopes from the
  contract, `bearer_methods_supported` `["header"]`.
- [ ] T-OAuth2. Token rejection table: missing, malformed, `alg=none`, HS256, unknown
  `kid`, wrong signature, wrong `iss`, `aud` = origin only / trailing slash / tg.mctl.ai
  / array without resource, expired, future `nbf`, empty `sub`, no Glovo scope, token
  in query string. Each fails and the fake recorder shows zero mctl-api calls.
- [ ] T-OAuth3. Scope: `glovo:read`-only token can call read tools and gets
  `not_authorized` for `glovo_connect_account` and `glovo_prepare_order` with zero
  mctl-api calls.
- [ ] T1/T2. Cross-tenant: Carol (`team-beta`) using Alice's `order_id`, `order_ref`,
  `preview_id` gets `not_found`, identical to a random id; no effect call recorded.
- [ ] T3. Same tenant, other user: Bob cannot see or use Alice's connection or orders;
  Alice and Bob get distinct `gcn_` ids.
- [ ] T6. Confused deputy: arguments with `tenant`, `tenant_id`, `principal_id`, `url`,
  `owner_id`, extra properties, duplicate keys, over-length strings, `limit` 0 or 21 are
  rejected `invalid_arguments` before any mctl-api call.
- [ ] T14. Tenant resolution: no `mctl_tenant` claim -> `no_tenant`; fake returns
  ambiguous -> `ambiguous_tenant`; personal scope -> `scope_unsupported`; Dana ->
  `not_in_pilot`; membership revoked between two calls -> second call `not_authorized`;
  no fallback to `labs`/`mctl`; recorder shows only `resolve` was called.
- [ ] T-Approve. `glovo_prepare_order` returns an `aar_` `consent_request_id` and state
  awaiting consent; basket read before and after is unchanged; no tool approves;
  approval through `/_fake/approve` only; a `hir_` record never changes order state;
  replaying the same idempotency key returns the same `order_id` (T16).
- [ ] T-ReadOnly. For each read tool the recorder shows only read endpoints; fake
  provider basket mutation counter stays zero.
- [ ] T9. Leak scan: run the whole integration suite with captured slog output,
  `/metrics` text, an in-memory OTel span exporter and all tool results; assert no
  access token, subject token, workload credential, `scope_ref` or handoff token
  appears (patterns from `test/glovo-poc/leakcheck`), and no URL with a query string
  is logged.
- [ ] T12. Rate limits: 11th burst call per principal returns `rate_limited`; another
  principal unaffected; 65th concurrent request gets 429; 64 KiB+1 body gets 413;
  oversize upstream response gives `upstream_invalid`.
- [ ] T-Upstream. Fake returns schema-violating output, extra field, 500, timeout: facade
  returns `upstream_invalid`/`upstream_unavailable`, never the upstream body.
- [ ] T-Health. `/healthz` 200; `/readyz` 503 when disabled, before JWKS load, or when
  fake health fails; SIGTERM test flips readiness and drains an in-flight call.
- [ ] T-Obs. Metrics names and label sets exactly as designed; one span per tool call
  with `traceparent` received by the fake.
- [ ] T15. No Telegram regression: `docs/tool-descriptors*.json`,
  `docs/portal-allowlist.json`, `cmd/server` tests unchanged and green; import-boundary
  test (task 10).
- [ ] T-Probe. CI job: built container plus `cmd/glovo-mcp-fakeapi` and `cmd/mcpprobe`
  (or the mcp-go client) complete initialize, `tools/list`, and one call of each tool.
- [ ] T-Wire. `wire_test.go` golden fixtures pass for the real client and the fake; the
  same test can be pointed at a real mctl-api URL by env var (skipped when unset), which
  is the activation precondition.

## Rollback

Nothing is deployed, published or routed by this proposal: `GLOVO_MCP_ENABLED`
defaults to false, no `services/labs/glovo-mcp/values.yaml` exists so the release
guard publishes no image, and no DNS/TLS is created. Rollback is a plain revert of the
merge commit (`git revert -m 1 <merge>`), which removes `cmd/glovo-mcp`,
`internal/glovo`, `Dockerfile.glovo-mcp`, the CI jobs and docs. `cmd/server` and the
tg.mctl.ai image are untouched, so no Telegram rollout or rollback is involved. If a
later, separately approved deployment misbehaves, set `GLOVO_MCP_ENABLED=false`
(`/mcp` answers 503 and stops contacting mctl-api) or scale the component to zero.
