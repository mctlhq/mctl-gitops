# Glovo M1a: tenant-bound synthetic Glovo connections and MCP principal resolution

## Context

The Glovo multi-tenant M0 contract (mctl-telegram#1227, PR #1233) defines the
assistant flow, but mctl-api has no durable registry of who owns a Glovo
connection, in which tenant, under which installation revision, and no way to
resolve a token presented to the protected MCP resource
`https://glovo.mctl.ai/mcp` to an MCTL `prn_` principal and tenant. The
automation contract (#948/#950) is contract-only and grants no Glovo
authorization.

This proposal adds a bounded M1a slice to mctl-api: a new RFC 8707 resource
audience for Glovo, an authoritative server-side principal/tenant/pilot
resolution, an installation and per-owner per-tenant connection registry with
a strict state machine, typed fail-closed refusals, atomic revocation and
reinstall revision bumps, an immutable audit trail, a reserved (unused)
secret-reference interface, and a narrow machine identity for the provider
worker. Only a synthetic (fake) provider exists. Two tenants, and two users
inside one tenant, must be isolated from the first release.

## Owner-selected M1 team-scope correction — AMEND 2026-11-08

**Normative override of the investigator's automatic-tenant inference:** owner [.github#324](https://github.com/mctlhq/.github/issues/324) explicitly chose **an explicitly selected team tenant**, not "the sole team left after membership ∩ allowlist". The OAuth authorization-code/consent flow for the protected Glovo resource MUST require the authenticated human to choose a concrete team before a usable Glovo-scoped token is issued. mctl-api verifies *live* principal-role membership and pilot inclusion for that team, stores a server-side binding with the OAuth grant, and mints a non-user-editable selected-team claim tied to that same grant and `aud=https://glovo.mctl.ai/mcp`. On refresh the scope remains bound to the original team or is revoked; switching teams requires a new explicit authorization selection. Tool/body/query/header fields never select a tenant.

- **Absence of explicit selection MUST fail closed**, even if there is exactly one eligible team. Until a new refusal code is separately accepted, map missing or inconsistent selection to existing `ambiguous_tenant`; invalid/no-longer-eligible selected team maps to `not_in_pilot` or `not_authorized`. Check membership, pilot allowlist, tenant selection, install revision at every facade request and worker authority checkpoint.
- **M1 pilot allowlist is per principal AND team**, not automatic tenant-wide enrollment. Database key `(tenant_id, principal_id)` and no `principal_id NULL` wildcard (future broader cohort requires a separate decision). At least two distinct principals in one tenant can be explicitly allowlisted and must have independent `gcn_` connections. A team owner with a valid MCTL membership but *not* allowlisted cannot access or mint a connection.
- Preserve OAuth issuer/audience validation, protection against multi-`aud` confusion, no personal scope (until #309), zero fallback to `labs`/Telegram principal, and no connection effects from an unselected token. Write negative tests for one-team-but-unselected, two-team switching attempts, revoked membership mid-session, expired grant, wrong-scope token, and tenant-wide allowlist bypass.
- This AMEND is proposal material only, no grant or runtime code and no deploy.

## User stories

- AS a tenant member using the Glovo MCP facade I WANT my connection to be
  bound to my principal and my tenant SO THAT nobody else, including a model
  changing tool arguments, can use or see it.
- AS the thin Glovo MCP facade I WANT one API call that resolves the bearer
  token to a principal, tenant and pilot status, or a typed refusal, SO THAT I
  never decide tenant or owner from caller-supplied input.
- AS the synthetic provider worker I WANT a narrow machine identity and an
  explicit control-plane check SO THAT a revoked or stale connection stops
  every active and pending workflow before any provider I/O.
- AS a tenant owner I WANT to revoke a connection or reinstall the Glovo
  integration atomically SO THAT every older connection becomes unusable at
  once.
- AS a platform operator I WANT immutable audit events and documented schemas
  SO THAT the slice can be independently reviewed before any real provider is
  wired.

## Acceptance criteria (EARS)

Resource and principal resolution
- WHEN an access token is presented whose `aud` contains the configured Glovo
  resource (`GLOVO_MCP_RESOURCE`, intended value `https://glovo.mctl.ai/mcp`)
  and whose `iss` equals the API's OAuth issuer THE SYSTEM SHALL mark the
  caller as a Glovo-audience caller and resolve its `prn_` principal from the
  token, never from a header, query or body field.
- IF the token's audience does not include the Glovo resource, or its issuer
  differs, THEN THE SYSTEM SHALL refuse every `/api/v1/glovo/*` facade route
  with `not_authorized` and perform no store write and no provider I/O.
- WHILE a caller holds a Glovo-audience token THE SYSTEM SHALL confine it to
  the `/api/v1/glovo/*` facade routes and answer 401 `invalid_token` on every
  other route, `/mcp` included.
- IF `GLOVO_MCP_RESOURCE` is unset THEN THE SYSTEM SHALL refuse to mint a Glovo
  audience token (`invalid_target`) and answer 503 on every `/api/v1/glovo/*`
  route.
- WHEN the principal could not be resolved THE SYSTEM SHALL refuse with
  `not_authorized` (fail closed; the Glovo slice never degrades to a
  login-only identity).
- WHEN the caller is resolved THE SYSTEM SHALL require a **previous human-selected team tenant** bound to the Glovo OAuth authorization grant and audience; mctl-api SHALL re-check the principal's current role membership and **principal-specific** pilot allowlist in that selected team on each call, and SHALL:
  - refuse `no_tenant` if the principal has no team membership;
  - refuse `not_in_pilot` if the selected team is not allowlisted for the principal;
  - refuse `ambiguous_tenant` if the OAuth grant has no explicit selection, **even if one team is eligible**, or the bound selection is inconsistent;
  - refuse `scope_unsupported` for a personal-only scope, until .github#309 resolves it;
  - refuse on stale/expired/revoked grants or membership, and require new interactive authorization when switching teams.
- THE SYSTEM SHALL ignore any tenant, owner, Temporal namespace, task queue,
  workflow id or hosting-tenant default (including `labs`) supplied in a
  request body, query, header or MCP tool argument when resolving scope.

Installations and connections
- THE SYSTEM SHALL keep one Glovo installation per tenant with an opaque id
  (`gin_` ULID) and a monotonically increasing integer `install_revision`.
- WHEN an eligible caller connects THE SYSTEM SHALL create a connection with
  id `gcn_` (ULID) bound to (tenant, owner principal, installation,
  install_revision), provider `synthetic`, in state `pending_handoff`.
- THE SYSTEM SHALL allow only these transitions: `pending_handoff ->
  pending_provider`, `pending_provider -> active`, `pending_handoff |
  pending_provider -> failed`, `active -> expired`, any non-terminal state ->
  `revoked`; `expired`, `failed` and `revoked` are terminal.
- WHEN a caller reconnects THE SYSTEM SHALL revoke the previous live
  connection and create a new `gcn_` id in the same transaction; a connection
  id is never reused.
- WHILE the installation is not present THE SYSTEM SHALL refuse connect with
  `no_install`; IF the connection's install_revision is lower than the
  installation's current revision THEN THE SYSTEM SHALL refuse with
  `stale_install`.
- THE SYSTEM SHALL permit at most one live (non-terminal) connection per
  (tenant, owner principal, installation), enforced by a partial unique index,
  and SHALL uniquely index (tenant, owner, connection id, install_revision).
- WHEN the synthetic provider activates a connection THE SYSTEM SHALL record
  no provider session token, credential or session file; the secret reference
  stays null.

Refusals and isolation
- THE SYSTEM SHALL return refusals as a typed JSON body
  `{"error": <code>, "error_description": <text>}` with code from the closed
  set `not_authorized, no_tenant, ambiguous_tenant, scope_unsupported,
  not_in_pilot, no_install, stale_install, no_connection, connection_revoked,
  connection_expired, not_found`.
- IF a caller names a `gcn_` or `gin_` id that does not exist, or that belongs
  to another tenant or another owner THEN THE SYSTEM SHALL answer 404
  `not_found` with a byte-identical body, so existence is not disclosed.
- WHEN a refusal is returned THE SYSTEM SHALL perform no provider I/O and no
  state change, apart from an audit event for the refusal.

Revocation and control-plane check
- WHEN an owner revokes a connection, or a tenant owner reinstalls (bumping
  `install_revision`) THE SYSTEM SHALL in one transaction update the rows,
  move every affected non-terminal connection to `revoked`, and append audit
  events.
- WHEN the provider worker, authenticated by `MCTL_GLOVO_WORKER_TOKEN`, calls
  the control-plane check with (connection id, install_revision) THE SYSTEM
  SHALL answer `allowed` only if the connection is active or pending, its
  revision is current, the owner is still a member of the tenant and the
  tenant is still in the pilot; otherwise it SHALL answer the matching
  refusal code.
- WHILE a tenant membership of the owner is removed THE SYSTEM SHALL refuse the
  control-plane check and every facade call for that owner's connection in
  that tenant.
- THE SYSTEM SHALL confine the worker identity to the worker routes; it SHALL
  NOT accept an mctl-telegram token, the service token or a facade token on
  them.

Idempotency, quotas, audit, secrets
- WHEN connect or reconnect is repeated with the same `Idempotency-Key` from
  the same principal and tenant THE SYSTEM SHALL return the original
  connection with `replayed: true`; IF the same key is reused with a different
  request THEN THE SYSTEM SHALL refuse 409 `idempotency_key_reused`.
- IF a principal exceeds 10 connect/reconnect calls per rolling hour, or a
  tenant exceeds 100 non-terminal connections THEN THE SYSTEM SHALL refuse 429
  `rate_limited` without a state change.
- THE SYSTEM SHALL append an immutable audit event (`gae_` ULID) for every
  state change and refusal, never update or delete one inside the retention
  window (default 400 days), and SHALL NOT include tokens, credentials or
  provider payloads in audit events or logs.
- THE SYSTEM SHALL define a secret-reference interface (opaque `gsr_` ids,
  envelope encryption with a random per-connection DEK wrapped by an
  independent KEK) whose M1 implementation refuses every write.

Regression
- WHILE the Glovo resource is configured THE SYSTEM SHALL keep existing API
  tokens, support-audience tokens, `tg.mctl.ai` authentication, automation
  and DevLoop routes behaving exactly as before.

## Out of scope

- Real Glovo account login, provider session storage, checkout or payment,
  any real provider write.
- The thin MCP facade itself (separate source repo) and any new mctl-api MCP
  tools; the MCP tool count does not change.
- DNS, Ingress, TLS for `glovo.mctl.ai`, Temporal authentication flip,
  namespace creation, deploying or enabling this in production.
- M1b orders and approval receipts.
- Personal (non-tenant) scope; it is refused until mctlhq/.github#309 decides.
- A KEK/KMS implementation; only the interface and design are reserved.

## Open questions

- Multi-tenant principals: the issue requires `ambiguous_tenant` when more
  than one tenant qualifies. This proposal does not add a tenant selector
  (that would reintroduce caller-chosen tenant). Is a per-principal pinned
  pilot row (one allowlisted tenant per principal) the intended long-term
  disambiguation, or will the facade later carry a server-issued tenant
  binding in the token?
- Personal scope outcome depends on mctlhq/.github#309; until then
  `scope_unsupported`.
- Who manages the pilot allowlist: this proposal makes it admin-only API rows.
  Confirm it should not live in gitops tenant files instead.
- Whether the installation is created by a tenant owner (proposed) or only
  by a platform admin during pilot.
- Quota numbers (10/hour per principal, 100 live per tenant) and retention
  (400 days) are placeholders for review.
- `glovo.mctl.ai` is not deployed and the deployed mctl-api has no
  `GLOVO_MCP_RESOURCE`; the exact issuer the facade will see (api.mctl.ai's
  OAuth issuer) must be confirmed by the facade design.
