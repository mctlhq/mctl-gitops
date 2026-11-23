# Glovo M1e: canonical facade-to-mctl-api join API (glovo-facade-mctl-api/v1alpha1) and cross-repo contract tests

## Context

Amended 2026-11-09 (b): owner decision A (one physical database, explicit URLs, canonical lock order in design §6b), #988/#989 replace the #954 `providerorders` path, and the fingerprint is the mctl-agents#1059 approval-basket fingerprint. design.md has the driver -> change table.

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

## AMEND 2026-11-09 — alignment with the merged facade (mctl-telegram `27c671d2`) and bridge (mctl-api `a9ca5814`)

Crosswalk mismatches M1-M5, M7, M11 and M12 (mctl-gitops `deploy/staged/glovo-m1/CROSSWALK.md`) and the review on this issue (comment 6740430430). design.md "Amendment 2026-11-09" has the full table and the owner decisions D1-D5 of 2026-11-09, which replace the earlier open items.

- THE SYSTEM SHALL answer `POST /resolve` with exactly `{scope_ref, tenant, expires_at}` and SHALL require a valid `X-Mctl-Scope-Ref` on every other join route except `/compatibility`, validated as in design §2b (server-issued, 192-bit random, bound to principal, tenant, install revision and grant family, TTL at most 5 minutes, stored as a hash only, re-validated on every use, never a source of tenant or owner). (owner decision)
- THE SYSTEM SHALL send on 401, 403, 404 and 409 only the wire codes listed in design §4, and SHALL record the internal reason in audit and spans only. The error body SHALL be `{"error","error_description"}` with fixed text. (owner decision, joint contract C1)
- WHEN a write is replayed with the same idempotency key and body THE SYSTEM SHALL return the original body byte for byte and the header `Idempotent-Replayed: true`, and SHALL NOT add a `replayed` field to any body. The one exception is `POST /connections`: a replay returns the same `connection_id` and state with a freshly minted `handoff_url` and `expires_at` (the raw handoff reference is never stored), still with `Idempotent-Replayed: true` (round 4, X-1, #961 §4a).
- THE SYSTEM SHALL NOT define a second wire protocol for reads; it SHALL read through the bridge read extension mctl-api#986. WHILE #986 is not merged and configured THE SYSTEM SHALL answer history, preview, basket and prepare with 503 `not_ready`. P1 acceptance SHALL require all four working against the fake provider. Raw read payloads SHALL NOT be written to a bridge command, a Temporal input, signal or log. (owner decision D1)
- THE SYSTEM SHALL NOT enqueue a bridge command from prepare or from any route of this slice, and SHALL NOT register any HTTP route that enqueues a command or accepts a command id, kind or payload. Dispatch, cancel and the in-process `bridge.Store.Enqueue` inside the dispatch transaction belong to mctl-api#985; this slice SHALL keep integration tests against #985's merged code. (owner decisions option b and D3)
- WHEN prepare commits THE SYSTEM SHALL have written, in the same transaction, the order, the `we_`, the pending `aar_` and one workflow-start record; a dispatcher owned by this slice SHALL start `GlovoControlWorkflow` only after commit, with a deterministic workflow id, CAS on the record and safe retries (design §6c). (owner decision D5)
- THE SYSTEM SHALL run every write of the prepare transaction, and SHALL let #985 run every write of the dispatch transaction, on one `pgx.Tx` from the bridge store's pool, with the #959 connection read on the same transaction. (Amended 2026-11-09 (b), owner decision A, superseding D2.) `GLOVO_DB_URL` (the one `glovo_runtime` pool shared by the #959 and bridge stores) and `WORK_ITEMS_DB_URL` SHALL be set explicitly to one physical database, with no `AUDIT_DB_URL` fallback and no fallback between them; `COMMERCE_DB_URL` SHALL NOT be a Glovo pool. Equal URLs SHALL NOT count as proof; #985 `control.ProveOneDatabase` SHALL pass, and a test SHALL prove the shared `pgx.Tx`. Missing configuration or a failed proof SHALL give `provider_orders: not_ready`. Glovo tables SHALL live in the Postgres schema `glovo`, owned by the migration role, with `glovo_runtime` holding exactly the grants of design §6d.1 and `glovo_migrator` owning every object (owner decision 2026-11-09, R1-R5). SQL grants SHALL NOT replace the tenant, principal, live-connection and `aar_` checks at every write fence. (fallback removal is mctl-api#987)
- THE SYSTEM SHALL take locks only in the canonical order L1..L6 of design §6b; prepare SHALL take L1 and L2 shared before creating the order and the `aar_`.
- THE SYSTEM SHALL never put a raw tenant name, `prn_` or #988's internal `pord_` into a bridge command or a control-workflow input; it SHALL use the `tnr_`/`prr_`/`irv_` join refs of design §2a, minted through #988 `MintJoinRefTx` in #988's `glovo.join_refs`, and the order's own `ordr_`. (amended (b), round 3: the `ordr_` is the order's `order_ref` column, minted by prepare with `NewOrderRef()`, not a join ref; `pord_` stays unexported inside #988)
- WHILE #960's `GLOVO_ENABLED` admission is not live THE SYSTEM SHALL keep answering `invalid_target` for the Glovo resource on `/oauth/authorize` and `/oauth/token`, and consent-time tenant selection SHALL NOT be reachable.

## AMEND 2026-11-08 — refusal code + real transactional prepare consistency

**Independent review P2/contract correctness:** #957 introduces `tenant_selection_required`, which is **not** in the closed Glovo M0 refusal enum and conflicts with the already prepared M1a #953 AMEND (`ambiguous_tenant` for a user who has not explicitly selected a team, including the case of one eligible team). The public MCP contract must not drift silently. For v1alpha1, use the **existing `ambiguous_tenant`** refusal for absence/invalidity of a human-selected-team OAuth grant, even when a sole eligible team exists, unless a **separately reviewed version bump** changes M0, #953 and the facade together. `tenant_mismatch` may be retained as an internal wire-only refusal if mapped to a closed public error; no new public tool enum without schema update.

**Cross-store atomicity:** the proposed `POST /orders:prepare` calls M1b to create `pord_`, `we_` and pending `aar_` "in one transaction", but current WorkItem/approval store has its own persistence/transactions. The proposal MUST name actual shared `pgx.Tx` interfaces and database topology for this operation, or define a recoverable, idempotent saga with no orphan `we_`, `aar_` or wrongly authorized order. Tests inject crashes before/after each stage and prove exactly one active pending request or explicit terminal compensation, **zero fake-provider writes**. Do not claim deploy-ready on an unproven atomic assumption.

The OAuth selected team must be human-chosen, server-owned, bound to access+refresh grant and rechecked each call. Per-principal pilot allowlist only (no wildcard), no `labs` fallback. All cross-repo fixtures MUST match the exact same v1alpha1 schema and refusal mapping.



- AS the Glovo MCP facade operator I WANT one frozen, versioned mctl-api route/schema matrix SO THAT the facade built against fixtures works unchanged against the deployed mctl-api.
- AS a human team member I WANT my Glovo session bound to the tenant I explicitly selected at consent SO THAT no facade, header or tool argument can move my orders into another tenant.
- AS a security reviewer I WANT only the facade's narrowly scoped workload identity to reach the join routes, with the user token re-verified by mctl-api on every call, SO THAT neither a stolen facade credential nor a stolen user token is enough to act.
- AS the mctl-telegram facade maintainer I WANT a pinned contract file plus golden fixtures that fail CI on drift SO THAT neither repo can change the wire shape silently.
- AS a launch approver I WANT a typed `not_ready` answer and a compatibility endpoint SO THAT a missing downstream dependency (M1a, M1b, bridge, workers) is visible and never read as "empty".

## Acceptance criteria (EARS)

### Routing and identity
- THE SYSTEM SHALL serve the join API only under `/api/v1/assistants/glovo/v1alpha1/`, with exactly the routes in design.md "Route matrix". It SHALL register nothing under `/mcp` and no host route that shadows `tg.mctl.ai` or the mctl-api `/mcp`.
- WHILE `GLOVO_JOIN_ENABLED` is not `true` THE SYSTEM SHALL leave the join routes unregistered (404), with all other routes unchanged.
- WHEN a request reaches a join route THE SYSTEM SHALL accept it only if the bearer token is the Glovo facade workload identity (`MCTL_GLOVO_FACADE_TOKEN`, compared in constant time). Any other principal, including admins, the service token, support, agent, surface and Glovo-worker principals, SHALL get 401 with wire code `not_authorized` (internal reason `not_facade_identity`, design §4).
- WHEN the facade workload identity calls any route outside the join prefix (including `/mcp`) THE SYSTEM SHALL refuse it with 401.
- WHEN a join request arrives THE SYSTEM SHALL re-verify `X-Mctl-Subject-Token` with mctl-api's own OAuth verifier. The token must be RS-signed by mctl-api, with `iss` equal to the mctl-api base URL, `aud` containing exactly the configured Glovo resource (`GLOVO_MCP_RESOURCE`, from M1a) and no other mctl audience, and it must be unexpired and not revoked. If any check fails THE SYSTEM SHALL return 401 `not_authorized` (internal reason `subject_token_invalid`) and SHALL NOT log, echo or store the raw token. Only its SHA-256 may appear in audit records.
- IF the subject token lacks a **valid human-selected-team, grant-bound** claim THEN THE SYSTEM SHALL return 403 `ambiguous_tenant` (the M0 closed refusal code) even when exactly one tenant would be eligible. It SHALL NOT use membership count, pilot rows or hosting default `labs` as a substitute; the same code must appear in #953/#1235 and shared fixtures.
- IF `X-Mctl-Selected-Tenant` is present and differs from the verified `stn` claim (mctl-api#960) THEN THE SYSTEM SHALL return 403 `not_authorized` (internal reason `tenant_mismatch`). The header SHALL never be used as a source of the tenant.
- WHEN the verified claim names a tenant THE SYSTEM SHALL still run the M1a resolver (principal-mode membership, the pilot allowlist and, through #959 `GetInstall`, a current installation) and return that resolver's refusal codes unchanged. The claim narrows the tenant and never widens access.
- Consent-time team selection, the `tgr`/`stn` claims and the resolver are owned by mctl-api#960 alone (round 3). THIS SLICE SHALL add no consent path and mint no tenant claim; it SHALL read the tenant only through `User.TeamGrant()` and `scope.Resolver.Resolve`, and bind `scope_ref` to the team grant's `refresh_family_id`.

### Tool mapping
- WHEN the facade calls a join route THE SYSTEM SHALL answer with a body that validates against the frozen v1alpha1 response schema for that route. The response output SHALL equal the contract output object of the matching MCP tool.
- WHEN `POST /orders:prepare` succeeds THE SYSTEM SHALL atomically create, on one transaction, an owner-bound `wi_`/`we_` through #989 `CreateGlovoExecutionTx`, a #988 order (`ordr_`, returned as `order_id`) whose `ExecutionID` is that `we_` from its first row, snapshot 1 from the approval-basket bytes stored with the preview, a pending `aar_` through #989 `CreateGlovoApprovalTx` (idempotency key `glovo-prepare:` + `ordr_`) and a `glovo.control_starts` row (design §6, §6d.2, §6d.3; amended (c)), with the `IntentHash` of #989 `GlovoIntent`. These SHALL be bound to (tenant, principal, connection, install revision, approval-basket fingerprint). (amended (b))
- THE SYSTEM SHALL compute the preview, basket and prepare `fingerprint` as `"sha256:" + hex(sha256(JCS(b)))` over the mctl-agents#1059 approval-basket projection, and SHALL NOT define a basket schema or fingerprint of its own. (amended (b))
- WHEN `POST /previews` is called THE SYSTEM SHALL accept the history-order ref (`pho_`, mctl-agents#1059) in the unchanged wire field `order_ref`. (amended (b)) It SHALL do so only when an earlier history read returned that `pho_` to the same (tenant, principal, connection) (`glovo.join_read_refs`, design §5a; #1059 consumer MUST 10, owned here), and likewise accept a history `cursor` only if it was issued; otherwise 404 `not_found` with zero commands enqueued.
- WHEN `POST /previews` succeeds THE SYSTEM SHALL store the JCS approval-basket bytes returned by #988 `basket.Parse` and their fingerprint with the preview, so that prepare makes no read and does not depend on the read-result TTL. An empty basket or an all-unavailable preview SHALL be answered with `items: []` and `fingerprint: ""`, and prepare of such a preview SHALL be refused with 400 `invalid_arguments` (internal reason `basket_empty`). (amended (c), design §6d.3)
- WHEN a read result is fetched THE SYSTEM SHALL rely on #986 `FetchReadResult` for every binding check and SHALL check only kind, schema version and the per-kind #1059 schema itself; it SHALL NOT expect binding refs echoed in the result. (amended (b)) The handler SHALL make zero provider writes and SHALL return the `aar_` id as `consent_request_id`.
- THE SYSTEM SHALL NOT expose any join route that decides, consumes, reserves or settles an `aar_`, accepts an `hir_` id, or dispatches a provider effect.
- WHEN `GET /orders/{order_id}` is called for an order owned by another principal or another tenant THE SYSTEM SHALL return 404 `not_found`, the same answer as for a missing id.
- WHEN `POST /previews` or `POST /orders:prepare` names a connection, preview or order that is not bound to the resolved (tenant, principal) THE SYSTEM SHALL return 404 `no_connection` for a connection and 404 `not_found` for a preview or order (design §4).

- WHEN `POST /orders:prepare` names a preview that already produced an order under another idempotency key THE SYSTEM SHALL return 409 `fingerprint_changed` (internal reason `preview_consumed`) and create nothing; a failed prepare SHALL leave the preview unconsumed. (round 4, F1 P3)
- THE SYSTEM SHALL store the canonical `GlovoControlInput` bytes in `glovo.control_starts.input` (INSERT-only, digest-checked) in the prepare transaction, and the start dispatcher SHALL send those bytes verbatim and rebuild nothing. (round 4, F2)
- THE SYSTEM SHALL back `GET /connection` and `POST /connections` only with #961 `connect.Service.Current` and `Connect`. (round 4, X-1)
- THIS SLICE SHALL add no OAuth or consent migration; its only migrations are the four `glovojoin.ApplySchema` tables. (round 4, F3)

### Reads through the bridge
- WHEN a history, preview or basket route needs provider data THE SYSTEM SHALL call the in-process `ReadBridge` interface with the #986 `ReadRequest` of design §5 (verified owner principal id, `tnr_`/`prr_`/`gcn_` refs, install revision, subject-token scopes); binding checks are #986's (amended (c)). `ReadBridge` has no wire format of its own (amended 2026-11-09, M5).
- WHILE the mctl-api#986 read extension is not configured THE SYSTEM SHALL return 503 `{"error":"not_ready","error_description":…}` and report `read_bridge: not_ready` on `/compatibility`. It SHALL NOT return empty history, an empty basket or a fabricated preview.
- WHILE an M1a or M1b store is unconfigured or unreachable THE SYSTEM SHALL return 503 `not_ready` naming `connection_registry` or `provider_orders`. Unknown SHALL never be reported as absent.

### Idempotency, limits, tracing
- WHEN `POST /orders:prepare` is repeated with the same `idempotency_key` and the same body THE SYSTEM SHALL return the original body byte for byte, and `POST /connections` the same `connection_id` with a fresh `handoff_url` (round 4, X-1), with the header `Idempotent-Replayed: true` (amended 2026-11-09, M4).
- IF the same `idempotency_key` arrives with a different body THEN THE SYSTEM SHALL return 409 `idempotency_key_reused`.
- IF an `Idempotency-Key` header is present and differs from the body key THEN THE SYSTEM SHALL return 400 `invalid_arguments` (internal reason `invalid_request`).
- THE SYSTEM SHALL rate-limit join routes per subject principal (60/min, writes 10/min) and in aggregate for the facade identity (600/min). Over-limit calls SHALL get 429 `rate_limited` with `Retry-After`.
- WHEN a join request carries a W3C `traceparent` THE SYSTEM SHALL continue that trace. Spans SHALL carry route, refusal code and tenant, and never token material.

### Contract and tests
- THE SYSTEM SHALL ship `internal/glovojoin/contract/glovo-facade-mctl-api.v1alpha1.json` with a pinned SHA-256 digest. Any change to a route, verb, schema, refusal mapping or HTTP status SHALL fail `go test` unless the version or the digest is bumped on purpose.
- THE SYSTEM SHALL ship golden fixtures under `internal/glovojoin/contract/testdata/v1alpha1/`. The harness SHALL replay them against the real `api.NewRouter` with real M1a/M1b stores on `TEST_DATABASE_URL`, not against a self-authored fake.
- `GET /compatibility` SHALL return the contract version and digest, the mctl-api build version and the readiness of each dependency. It SHALL report `deploy_ready: false` while any dependency is `not_ready`.

## Out of scope

- The M1a connection registry, Glovo audience and resolver internals (mctl-api#953) and the M1b slices (#988 orders, #989 `aar_`, #985 dispatch; parent mctl-api#954). This proposal consumes their in-process Go APIs and adds no store of theirs.
- The facade implementation (mctl-telegram#1235) and the fake provider worker (mctl-telegram#1236). The only cross-repo work here is the contract file they must vendor.
- The bridge itself (merged in mctl-api#968; mctl-agents#1043 is history) and the control workflow (mctl-agents#1044).
- Dispatch/cancel routes, the control-worker principal, the `aar_` plus revocation re-check and the atomic `Enqueue` (mctl-api#985); the bridge read extension (mctl-api#986); removing the bridge's `AUDIT_DB_URL` fallback (mctl-api#987); the facade's mapping of the four new codes (mctl-telegram#1264).
- GitOps deployment and enabling the flag in any environment (mctl-gitops#2470).
- Any real Glovo API, login, session, checkout, payment or production activation.
- Personal (non-tenant) scope, which waits on mctlhq/.github#309.

## Open questions

- Resolved round 3: consent-time team selection and the `tgr`/`stn` claims belong to mctl-api#960 (joint contract, "Consent-time team selection" row); M1e adds none (the earlier assignment of `mctl_tenant` to M1e is withdrawn).
- OPEN-957-6 (new, round 3; recommendation: operator step). A bridge whose tables were created earlier by `bridge.NewStore` under the mctl-api role makes `bridge.ApplySchema` refuse (design §6d.1 mode selector), and no slice transfers their ownership. Recommendation: a one-time, reviewed operator runbook step run as a DB admin (`ALTER TABLE ... OWNER TO glovo_migrator` for every bridge table, then `ApplySchema`), never done by `ApplySchema` or by either runtime role. Needs an owner decision before any deployment that already runs `MCTL_BRIDGE_ENABLED`.
- OPEN-957-11 (new, round 5; for the #1044 AMEND, #1044 is not edited here; recommendation: accept). (a) mctl-agents#1044 owns `glovo-control-input.v1alpha1.json` and must enumerate the members and values of `limits` (today it only names the field); this slice vendors the schema and its `SHA256SUMS` and copies `limits` from it. (b) #1044 CI should consume the Go-produced golden `internal/glovojoin/contract/testdata/control-input.golden.json` from this slice. (c) #1044 `tasks.md` task 3 still says route constants mirror "#953/#954"; they mirror mctl-api#985's `internal/glovo/control/contract` files. (d) The M9 mapping for `cancelled` and `expired` commands is OPEN-985-9.
- OPEN-957-10 (new, round 4; recommendation: 15 minutes). `GlovoApprovalTTL`, the lifetime of the pending `aar_` that prepare creates (at most `MaxApprovalTTL`). It is the owner's decision window, the prepare response `expires_at` and the bound of #1044's approval wait. 15 minutes matches the preview window; shorter risks an expired approval before the owner opens it, longer widens the window in which a stale basket stays approvable.
- OPEN-957-8 (new, round 4; recommendation: `GLOVO_SYNTHETIC_HANDOFF_BASE_URL` set per environment in gitops, handoff reference TTL 15 min). The base URL of the synthetic `handoff_url` that #961 `connect.Service.Connect` builds, and the handoff reference's `expires_at`, are a contract value of `POST /connections` and of the facade's `glovo_connect_account`. The owner confirms both before the contract digest is pinned. Unset base URL is `not_ready`.
- OPEN-957-9 (new, round 4; recommendation: pass the `bridge_schema_version` probe via `to_regclass` as in design §6d.1). The mode-selector probe runs on `GLOVO_DB_URL` when set, else the legacy bridge DSN. The owner confirms that reading table existence (not the row) with the legacy role is acceptable.
- OPEN-957-7 (new, round 3; recommendation: 1 h). TTL of `glovo.join_read_refs` rows (issued `pho_` refs and cursors, design §5a). 1 h outlives the 15 min preview window and is independent of the read-result TTL; shorter values make a user who pages history slowly get `not_found`.
- Resolved 2026-11-09 (owner): `X-Mctl-Selected-Tenant` stays a must-match echo, and `scope_ref` stays, specified in design §2b. The merged facade (`27c671d2`) is not changed.
- Resolved 2026-11-09 (b): prepare uses #988 and #989 tx-aware methods (design §6); the #954 `Prepare` question below is history. mctl-api#954 has the worker principal create the `aar_` through `/action-approvals`. The issue requires `glovo_prepare_order` to create a pending `aar_`. (History; the (c) answer is design §6d.)
- The facade workload identity is a static machine token here, following the existing evidence-writer and M1a Glovo-worker pattern. A projected ServiceAccount token checked with TokenReview (the `agent-run-tokens/exchange` pattern) would be stronger if the facade runs in-cluster. Reviewers should choose.
- The M0 tool schema `docs/contracts/glovo-mcp-tools.json` lives in mctl-telegram and could not be read from this clone. The output shapes here are taken from the M0 proposal table (`issue-1227`). The pinned copy must be byte-checked when task 2 lands.
- Superseded 2026-11-09: #968 is the canonical bridge (owner). Reads use the bridge read extension mctl-api#986 (owner decision D1).
