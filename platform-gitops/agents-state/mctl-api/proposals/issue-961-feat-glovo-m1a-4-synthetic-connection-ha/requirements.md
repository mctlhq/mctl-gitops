# Glovo M1a slice 4: synthetic connection handlers, worker scope checks and end-to-end tests

## Context

Issue mctlhq/mctl-api#961 is slice 4 of 4 of the failed, over-wide parent #953. Slices 1-3 add
the pieces this slice needs, and none of them is merged in this clone yet:

- #958: the Glovo OAuth resource audience, a fail-closed audience gate and a narrow worker identity.
- #959: the `internal/glovo` connection/installation domain, the Postgres store, audit and atomic revoke.
- #960: the human-selected team OAuth grant, the per-principal pilot allowlist and the scope resolver.

This slice wires those pieces into real HTTP handlers. There are three route families:

- facade (user, Glovo-audience token);
- tenant administration (installation lifecycle);
- worker (narrow connection-scope check).

All of them are inert when the feature is disabled. They return strictly versioned JSON bodies
and typed, closed refusals. The slice also adds end-to-end contract tests that drive the real
router, the real auth gates and a real Postgres schema. The tests use two team tenants and two
users in one tenant, and they prove that every cross-owner, stale or ungranted path fails closed.

Everything is fake. The only provider is `synthetic`. There are no cookies, no consumer
credentials and no Glovo HTTP calls. The feature stays default OFF. Integration with the
canonical facade join API (#957) and the public facade (mctl-telegram#1235) remains NOT READY
until those separately approved dependencies merge. This slice only keeps its schemas and refusal
codes compatible with them. The parent #953 approval grant does not authorize this slice. A new
human approval of this proposal's own digest is required.

## AMEND 2026-11-08 — missing persistence and worker credentials (P1)

**Dependency mismatch:** #958 reserves `service:mctl-glovo-worker` but deliberately does NOT issue a worker token, constructor or worker auth gate. #961 must implement a dedicated strictly scoped worker identity **default OFF**, with no secrets/credentials configured by code merge, or return `worker_api=not_ready` until a separately approved credential slice. No admin, general service or header-based identity may stand in for it. Issuing a live worker secret is a separate P1 deployment approval.

**Persistence gap:** #959 provides only installation, connection, idempotency-request and audit tables; it does **not** provide hashed single-use handoff references or PostgreSQL rate counters. #961 must own explicit additive, idempotent DDL for (connection, hash, expires_at, consumed_at, install_revision), and durable per-(tenant,principal,time bucket) rate counters. A worker must verify and consume the handoff atomically under revocation/reinstall locking; no raw handoff string stored. Two API replicas must not accept a quota-violating concurrent final request.

**Integration gate:** code cannot begin until #958/#959/#960 have merged and real API interfaces match. No silent stub/duplicate auth/store. All fake-only. Default `GLOVO_ENABLED=false`; no DNS, public OAuth activation, Temporal or real Glovo.

## User stories

- AS a team member who explicitly selected a team at OAuth consent I WANT to start, hand off, inspect and revoke my own synthetic Glovo connection SO THAT the connection lifecycle can be proven end to end without real credentials.
- AS a tenant owner I WANT to install, reinstall and remove the Glovo installation for my team SO THAT a reinstall or removal revokes every live connection atomically.
- AS the Glovo worker identity I WANT to check exactly one connection against its tenant, owner and install revision SO THAT I act only inside a narrow, currently valid scope.
- AS a platform security reviewer I WANT handler-level tests over real migrations and grants, covering cross-tenant and cross-user cases, SO THAT fail-closed behaviour is proven, not assumed.
- AS an operator I WANT the whole surface off by default and answering 503 `not_ready` SO THAT merging this code changes nothing in production.

## Acceptance criteria (EARS)

Feature gate
- WHILE `GLOVO_ENABLED` is not `true`, or the Glovo store, the `GLOVO_MCP_RESOURCE` audience or the worker token is not configured, THE SYSTEM SHALL answer every `/api/v1/glovo/*` route with 503 and refusal code `not_ready`. It SHALL do this before reading any request body or touching the store.
- WHILE the feature is disabled THE SYSTEM SHALL issue and verify tokens byte-identically to today, and existing support, DevLoop, Telegram, commerce and MCP routes SHALL behave unchanged.

Versioned schemas and refusals
- WHEN any Glovo route answers with success THE SYSTEM SHALL return a body whose `schema` field is exactly the `glovo-connection/v1alpha1` identifier for that message. A refusal body SHALL be the `glovo.WriteError` shape `{"error": <code>, "error_description": <fixed text>}` with no `schema` or `refusal` envelope (joint contract, round 3), and `error` SHALL come from the closed refusal enum of mctl-api#957 design §4.1.
- WHEN a request body contains an unknown field (including `tenant`, `tenant_id`, `owner`, `owner_principal_id`, `principal_id`, `namespace`, `task_queue`, `install_revision` on facade routes), declares a different `schema`, or is larger than 16 KiB, THE SYSTEM SHALL answer 400 `invalid_request` with no state change.
- THE SYSTEM SHALL NOT invent a new public refusal code outside the closed M0 contract. A missing or unbound team selection SHALL be `ambiguous_tenant`.

Facade (user)
- WHEN a caller with a valid Glovo-audience token and a server-owned selected-team grant calls a facade route THE SYSTEM SHALL derive the tenant, the principal and the active install revision only from that grant and the store. It SHALL re-check live team role membership and the per-principal pilot allowlist on every call.
- IF the token has no selected-team grant, or the grant is expired or revoked, THEN THE SYSTEM SHALL refuse with `ambiguous_tenant` before any store write. This also applies when exactly one team is eligible.
- IF the selected scope is personal, or no team selection is present, THEN THE SYSTEM SHALL refuse with `scope_unsupported` or `ambiguous_tenant` and SHALL never fall back to `labs` or any other default tenant.
- IF the principal is not on the pilot allowlist for the selected tenant, or no longer holds a role in it, THEN THE SYSTEM SHALL refuse with `not_in_pilot` or `no_tenant` respectively, with no state change.
- IF the tenant has no active installation THEN THE SYSTEM SHALL refuse a connect with `no_install`.
- WHEN `POST /api/v1/glovo/facade/connections` is called with an `Idempotency-Key` THE SYSTEM SHALL create one `pending` connection bound to (tenant, principal, installation, install revision). A retry with the same key and the same body SHALL return the original connection with `replayed: true`. The same key with a different body SHALL answer 409 `idempotency_key_reused`.
- IF `Idempotency-Key` is missing or longer than 128 bytes THEN THE SYSTEM SHALL answer 400 `invalid_request`.
- WHEN the owner calls `POST .../connections/{id}/handoff` on a `pending` connection THE SYSTEM SHALL return a single-use opaque synthetic handoff reference with a fixed TTL. It SHALL contain no cookie, credential or provider URL, and SHALL be stored only as a hash.
- WHEN the owner calls `POST .../connections/{id}/revoke` THE SYSTEM SHALL move the connection to `revoked` and append an audit event. Repeating the call SHALL be idempotent.
- WHEN the owner calls `POST .../connections/{id}/reconnect` on an `expired`, `failed` or `revoked` connection, or on an `active` one whose `expires_at <= clock_timestamp()` (database clock at statement time, round 4), THE SYSTEM SHALL create a new connection with a new `gcn_` id. It SHALL never reactivate the old one. IF the prior connection is live THEN THE SYSTEM SHALL refuse with 409 `connection_exists`.
- IF a connection id belongs to another principal, another tenant, or does not exist THEN THE SYSTEM SHALL answer the same 404 `not_found` body.

Administration (tenant owner)
- WHEN a tenant owner (principal-mode role `owner` via `requireTenantRole`) calls `PUT /api/v1/glovo/tenants/{tenant}/installation` THE SYSTEM SHALL create the installation or increment its revision. In the same transaction it SHALL revoke every live connection on the old revision.
- WHEN a tenant owner calls `DELETE` on the same path THE SYSTEM SHALL mark the installation removed and revoke all its connections atomically.
- IF the caller is not the owner of that tenant THEN THE SYSTEM SHALL refuse with 403. Admin status SHALL NOT satisfy the owner check on installation routes.
- WHEN a platform admin calls `PUT|DELETE /api/v1/glovo/pilot/{tenant}/principals/{principal_id}` THE SYSTEM SHALL add or remove exactly that (tenant, principal) allowlist row. No tenant-wide or wildcard row SHALL be accepted.

Worker
- WHEN the worker identity calls `POST /api/v1/glovo/worker/check` with `{schema, connection_id, install_revision}` THE SYSTEM SHALL re-derive the owner's live membership and pilot status and the installation's current revision. It SHALL answer `allowed: true` with tenant, owner and state only if the connection is `active` or `pending` (as named by the route) and the revision is current.
- IF the connection is revoked, expired, failed, on a stale install revision, or its owner lost membership or pilot admission, THEN THE SYSTEM SHALL answer with the matching typed refusal (`connection_revoked`, `connection_expired`, `no_connection` for `failed`, `stale_install`, `no_tenant`, `not_in_pilot`). It SHALL never answer `allowed: true`.
- WHEN the worker calls `POST /api/v1/glovo/worker/connections/{id}/activate` with a handoff reference that matches, is unused and is unexpired, THE SYSTEM SHALL, through #959 `ActivateTx` in one transaction, move `pending_handoff` to `pending_provider` to `active`, set `expires_at`, and consume the reference under the L1/L2/L2b lock order of mctl-api#957 §6b.
- WHEN the worker calls `check`, `activate` or `expire` with only a `gcn_` id THE SYSTEM SHALL read the connection with #959 `GetConnectionForWorker` to learn the owner and the version, and SHALL then use only the locked #959 primitives with them; it SHALL NOT read `glovo_connections` directly. (round 4)
- WHEN a handoff or activate refusal occurs THE SYSTEM SHALL use only the codes of the round-4 table of design section 4: a wrong, foreign, expired or consumed reference is one `not_found`; a connection not in `pending_handoff` is `invalid_transition`. (round 4)
- WHEN #957's `GET /connection` or `POST /connections` is called THE SYSTEM SHALL serve it through `connect.Service` of this slice (design 4a), so the same limits, L2a mutex and handoff apply as on the facade connect route; `handoff_url` is `GLOVO_SYNTHETIC_HANDOFF_BASE_URL` plus the raw reference, and an unset base URL is `not_ready`. (round 4)
- WHILE an `active` connection is past `expires_at` THE SYSTEM SHALL report it as `expired` on every read and check, and SHALL persist the transition on the next mutation or sweep.
- IF the worker identity calls any route outside `/api/v1/glovo/worker/*` (including `/api/v1/glovo/facade/*`, `/mcp`, `/api/v1/agents/dev-loop/*` and any Temporal or DevLoop control route) THEN THE SYSTEM SHALL answer 403 before any handler runs.
- IF any non-worker identity (admin, service token, support or Glovo-audience token, surface or agent principal) calls a worker route THEN THE SYSTEM SHALL answer 403.

Limits, audit and secrets
- WHEN a principal exceeds 10 connect or reconnect requests per hour in a tenant, or a tenant exceeds 50 non-terminal connections, THE SYSTEM SHALL refuse with 429 `rate_limited`. The counters SHALL be Postgres-backed so the limits hold across both replicas, and the tenant limit SHALL be enforced under the L2a tenant mutex row, never by counting under L1 shared alone.
- WHEN any state change, or any refusal on a mutating route that names an existing install or connection, happens THE SYSTEM SHALL append an immutable audit event carrying only ids, states, actor kind and refusal code. Refusals that arrive before a scope, tenant or entity exists SHALL be logged and counted only.
- THE SYSTEM SHALL NOT write tokens, handoff references, `Idempotency-Key` values or request bodies to logs, audit rows or responses, apart from the one-time handoff reference returned to its owner.

## Out of scope

- The order index, `aar_` approvals and receipts (#954), and live basket effects.
- The seven-tool facade join API under `/api/v1/assistants/glovo/v1alpha1/` (#957) and the public facade (mctl-telegram#1235).
- Temporal namespace creation, worker deployment, Temporal auth and DevLoop changes.
- Any real Glovo HTTP API, cookies, session files or secret storage, and real crypto.
- DNS/TLS, the gitops enablement of `GLOVO_ENABLED`, and deployment.
- New MCP tools (the `server_test.go` tool count is unchanged).
- The slice 1-3 primitives themselves. This slice consumes them.

## Open questions

- Slices 1-3 (#958, #959, #960) are not merged in this clone. Their final symbol names, refusal enum and table names may differ from those assumed here, which come from the #953 design. Task 0 requires reconciling against the merged code before any handler is written. The implementer must not re-implement those primitives here.
- State vocabulary: the issue names pending/active/expired/revoked, while the #953 design had pending_handoff/pending_provider/failed. This proposal uses the four public states plus the slice 2 internal sub-states, if they exist, and maps them to the four public states in responses. Reviewers should confirm that this mapping is acceptable.
- Exact limit numbers (10 connects per hour per principal, 50 live connections per tenant, a 10-minute handoff TTL, a 24-hour synthetic expiry) are proposed defaults, not owner-specified.
- `GLOVO_ENABLED` is a new explicit switch on top of the slice 1 `GLOVO_MCP_RESOURCE` presence check. If slice 1 already introduced an equivalent gate, use that one instead.
- Route compatibility with #957: #957 serves the facade join at `/api/v1/assistants/glovo/v1alpha1/` and says whether M1a still needs `/api/v1/glovo/facade/*` is "M1a's call". This proposal keeps the facade routes for a direct Glovo-audience client and for the tests, and shares the schemas and refusal codes. Reviewers may prefer to drop the user facade routes and keep only the admin and worker routes.
