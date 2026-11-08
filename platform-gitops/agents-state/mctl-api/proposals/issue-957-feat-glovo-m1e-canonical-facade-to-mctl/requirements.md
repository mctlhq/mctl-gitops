# Glovo M1e: canonical facade-to-mctl-api join API (glovo-facade-mctl-api/v1alpha1) and cross-repo contract tests

## Context

Issue mctl-api#957 reports a P1 gap that came out of the independent review of the Glovo M1
proposals. The public facade (mctl-telegram#1235, proposal
`mctl-telegram/proposals/issue-1235-feat-glovo-m1c-deployable-oauth-mcp-faca`) freezes a
wire protocol under `/api/v1/assistants/glovo/v1alpha1/*`. It authenticates with a facade
workload credential and adds two headers: `X-Mctl-Subject-Token` and
`X-Mctl-Selected-Tenant`. mctl-api#953 (M1a) instead exposes `/api/v1/glovo/facade/*` and
expects the user's Glovo-audience token directly. mctl-api#954 (M1b) exposes
`/api/v1/provider-orders/*`, which only an owner or worker may call. These three layouts do
not interoperate, so a facade that passes against its own fake server would still fail
against the real mctl-api.

This proposal makes mctl-api the integration owner of a separate M1e "join" slice. It
freezes one versioned wire API and defines how identity and tenant binding work on it. It
adds thin join handlers that map the seven synthetic Glovo MCP tools onto the M1a
connection registry and the M1b order/`aar_` engine. It ships one shared Go/JSON schema
contract with golden fixtures, and a harness that runs against the real mctl-api router.
Nothing touches a real Glovo API, session, payment or production activation. The proposal
must not claim deploy-readiness until M1a and M1b are independently reviewed and merged.

## User stories

- AS the Glovo MCP facade operator I WANT one frozen, versioned mctl-api route/schema matrix SO THAT the facade built against fixtures works unchanged against the deployed mctl-api.
- AS a human team member I WANT my Glovo session bound to the tenant I explicitly selected at consent SO THAT no facade, header or tool argument can move my orders into another tenant.
- AS a security reviewer I WANT only the facade's narrowly scoped workload identity to reach the join routes, with the user token re-verified by mctl-api on every call, SO THAT neither a stolen facade credential nor a stolen user token is enough to act.
- AS the mctl-telegram facade maintainer I WANT a pinned contract file plus golden fixtures that fail CI on drift SO THAT neither repo can change the wire shape silently.
- AS a launch approver I WANT a typed `not_ready` answer and a compatibility endpoint SO THAT a missing downstream dependency (M1a, M1b, bridge, workers) is visible and never read as "empty".

## Acceptance criteria (EARS)

### Routing and identity
- THE SYSTEM SHALL serve the join API only under `/api/v1/assistants/glovo/v1alpha1/`, with exactly the routes in design.md "Route matrix". It SHALL register nothing under `/mcp` and no host route that shadows `tg.mctl.ai` or the mctl-api `/mcp`.
- WHILE `GLOVO_JOIN_ENABLED` is not `true` THE SYSTEM SHALL leave the join routes unregistered (404), with all other routes unchanged.
- WHEN a request reaches a join route THE SYSTEM SHALL accept it only if the bearer token is the Glovo facade workload identity (`MCTL_GLOVO_FACADE_TOKEN`, compared in constant time). Any other principal, including admins, the service token, support, agent, surface and Glovo-worker principals, SHALL get 401 `not_facade_identity`.
- WHEN the facade workload identity calls any route outside the join prefix (including `/mcp`) THE SYSTEM SHALL refuse it with 401.
- WHEN a join request arrives THE SYSTEM SHALL re-verify `X-Mctl-Subject-Token` with mctl-api's own OAuth verifier. The token must be RS-signed by mctl-api, with `iss` equal to the mctl-api base URL, `aud` containing exactly the configured Glovo resource (`GLOVO_MCP_RESOURCE`, from M1a) and no other mctl audience, and it must be unexpired and not revoked. If any check fails THE SYSTEM SHALL return 401 `subject_token_invalid` and SHALL NOT log, echo or store the raw token. Only its SHA-256 may appear in audit records.
- IF the subject token carries no server-signed `mctl_tenant` claim THEN THE SYSTEM SHALL return 403 `tenant_selection_required`. It SHALL NOT fall back to a sole membership, a pilot row or a default tenant such as `labs`.
- IF `X-Mctl-Selected-Tenant` is present and differs from the verified `mctl_tenant` claim THEN THE SYSTEM SHALL return 403 `tenant_mismatch`. The header SHALL never be used as a source of the tenant.
- WHEN the verified claim names a tenant THE SYSTEM SHALL still run the M1a resolver (principal-mode membership, the pilot allowlist and a current installation) and return that resolver's refusal codes unchanged. The claim narrows the tenant and never widens access.
- WHEN a human completes `/oauth/consent` for the Glovo resource THE SYSTEM SHALL require the human to pick exactly one eligible tenant. It SHALL mint that tenant as `mctl_tenant` into the access and refresh tokens. A tenant not in the eligible set SHALL be refused, and no selection SHALL be preselected.

### Tool mapping
- WHEN the facade calls a join route THE SYSTEM SHALL answer with a body that validates against the frozen v1alpha1 response schema for that route. The response output SHALL equal the contract output object of the matching MCP tool.
- WHEN `POST /orders:prepare` succeeds THE SYSTEM SHALL atomically create, through the M1b service, a `pord_` order, an owner-bound `we_` execution and a pending `aar_` approval. These SHALL be bound to (tenant, principal, connection, install revision, preview fingerprint). The handler SHALL make zero provider writes and SHALL return the `aar_` id as `consent_request_id`.
- THE SYSTEM SHALL NOT expose any join route that decides, consumes, reserves or settles an `aar_`, accepts an `hir_` id, or dispatches a provider effect.
- WHEN `GET /orders/{order_id}` is called for an order owned by another principal or another tenant THE SYSTEM SHALL return 404 `order_not_found`, the same answer as for a missing id.
- WHEN `POST /previews` or `POST /orders:prepare` names a connection, preview or order that is not bound to the resolved (tenant, principal) THE SYSTEM SHALL return 404 with the matching `*_not_found` code.

### Reads through the bridge
- WHEN a history, preview or basket route needs provider data THE SYSTEM SHALL send a versioned `GlovoReadRequest` message through the `ReadBridge` interface and accept only a `GlovoReadResult` that matches the request id, tenant, connection and install revision.
- WHILE no bridge transport is configured THE SYSTEM SHALL return 503 `{"error":"not_ready","dependency":"read_bridge"}`. It SHALL NOT return empty history, an empty basket or a fabricated preview.
- WHILE an M1a or M1b store is unconfigured or unreachable THE SYSTEM SHALL return 503 `not_ready` naming `connection_registry` or `provider_orders`. Unknown SHALL never be reported as absent.

### Idempotency, limits, tracing
- WHEN `POST /connections` or `POST /orders:prepare` is repeated with the same `idempotency_key` and the same body THE SYSTEM SHALL return the original result with `"replayed": true`.
- IF the same `idempotency_key` arrives with a different body THEN THE SYSTEM SHALL return 409 `idempotency_key_reused`.
- IF an `Idempotency-Key` header is present and differs from the body key THEN THE SYSTEM SHALL return 400 `invalid_request`.
- THE SYSTEM SHALL rate-limit join routes per subject principal (60/min, writes 10/min) and in aggregate for the facade identity (600/min). Over-limit calls SHALL get 429 `rate_limited` with `Retry-After`.
- WHEN a join request carries a W3C `traceparent` THE SYSTEM SHALL continue that trace. Spans SHALL carry route, refusal code and tenant, and never token material.

### Contract and tests
- THE SYSTEM SHALL ship `internal/glovojoin/contract/glovo-facade-mctl-api.v1alpha1.json` with a pinned SHA-256 digest. Any change to a route, verb, schema, refusal mapping or HTTP status SHALL fail `go test` unless the version or the digest is bumped on purpose.
- THE SYSTEM SHALL ship golden fixtures under `internal/glovojoin/contract/testdata/v1alpha1/`. The harness SHALL replay them against the real `api.NewRouter` with real M1a/M1b stores on `TEST_DATABASE_URL`, not against a self-authored fake.
- `GET /compatibility` SHALL return the contract version and digest, the mctl-api build version and the readiness of each dependency. It SHALL report `deploy_ready: false` while any dependency is `not_ready`.

## Out of scope

- The M1a connection registry, Glovo audience and resolver internals (mctl-api#953) and the M1b order index, effect and `aar_` dispatch engine (mctl-api#954). This proposal consumes their in-process Go APIs and adds no store of theirs.
- The facade implementation (mctl-telegram#1235) and the fake provider worker (mctl-telegram#1236). The only cross-repo work here is the contract file they must vendor.
- The bridge transport itself (mctl-agents#1043) and the control workflow (mctl-agents#1044).
- GitOps deployment and enabling the flag in any environment (mctl-gitops#2470).
- Any real Glovo API, login, session, checkout, payment or production activation.
- Personal (non-tenant) scope, which waits on mctlhq/.github#309.

## Open questions

- mctl-api#953 explicitly adds no tenant selector and leaves `ambiguous_tenant` open. This proposal assigns the consent-time selection and the `mctl_tenant` claim to M1e. The M1a owner must confirm this does not conflict with M1a's resolver, or take the claim into M1a.
- mctl-telegram#1235 froze `X-Mctl-Selected-Tenant` as the source of the tenant and introduced a `gsc_` `scope_ref`. v1alpha1 here demotes the header to a must-match echo and drops `scope_ref`, since every call is fully re-verified. The facade proposal must be amended to match.
- mctl-api#954 has the worker principal create the `aar_` through `/action-approvals`. The issue requires `glovo_prepare_order` to create a pending `aar_`. This proposal needs M1b to expose an in-process `Prepare` that creates `pord_` + `we_` + pending `aar_` in one transaction. If M1b keeps creation in the worker, prepare answers `not_ready` until the worker exists.
- The facade workload identity is a static machine token here, following the existing evidence-writer and M1a Glovo-worker pattern. A projected ServiceAccount token checked with TokenReview (the `agent-run-tokens/exchange` pattern) would be stronger if the facade runs in-cluster. Reviewers should choose.
- The M0 tool schema `docs/contracts/glovo-mcp-tools.json` lives in mctl-telegram and could not be read from this clone. The output shapes here are taken from the M0 proposal table (`issue-1227`). The pinned copy must be byte-checked when task 2 lands.
- The transport of mctl-agents#1043 is not yet chosen. Only the message envelope and the `ReadBridge` interface are frozen here.
