# Add HasTenantAccess RBAC to VerifyDomain/DeleteDomain

## Context

`internal/api/handlers_domains.go` proxies four custom-domain operations to
the Backstage custom-domains plugin: `ListDomains`, `AddDomain`,
`VerifyDomain`, `DeleteDomain`. `ListDomains` (line 59) and `AddDomain`
(line 115) both call `user.HasTenantAccess(team)` before proxying the
request. `VerifyDomain` (line 157) and `DeleteDomain` (line 191) do not —
they read only the domain `id` from the URL path and forward straight to
Backstage with the shared `BackstageToken` service credential
(`authorizeBackstage`, line 38). Any authenticated caller who can reach the
API can verify or delete another tenant's custom domain simply by guessing
or enumerating its id (IDOR). This is part of a P0 platform security audit
(2026-08) and has a companion issue in `mctl-portal` for the portal-side
custom-domains-backend, which is explicitly out of scope here.

The fix must close the gap without a local domains datastore in mctl-api:
this service is a stateless proxy, and Backstage is the system of record
for which team owns which domain id.

## User stories

- AS a tenant member I WANT verify/delete of a custom domain to be rejected
  when the domain does not belong to a team I have access to SO THAT another
  tenant cannot tamper with or remove my domains, and I cannot accidentally
  or maliciously affect theirs.
- AS a platform operator I WANT the same authorization pattern already used
  by `ListDomains`/`AddDomain` reused for `VerifyDomain`/`DeleteDomain` SO
  THAT the RBAC model is consistent and auditable across the domains API.
- AS an admin/service caller (mctl-agent static service token, dev-mode
  `dev-user`) I WANT to keep verifying/deleting any tenant's domain SO THAT
  operational tooling and CI workflows are not broken by this change.

## Acceptance criteria (EARS)

- WHEN a request to `POST /api/v1/domains/{id}/verify` or
  `DELETE /api/v1/domains/{id}` is made without a `team` query parameter,
  THE SYSTEM SHALL respond `400 Bad Request` and SHALL NOT call Backstage.
- WHEN an authenticated non-admin user without access to the requested
  `team` calls `VerifyDomain` or `DeleteDomain`, THE SYSTEM SHALL respond
  `403 Forbidden` and SHALL NOT call the Backstage verify/delete endpoint.
- WHEN an authenticated user with access to `team` calls `VerifyDomain` or
  `DeleteDomain` with a domain `id` that does not belong to `team` (per
  Backstage's own records), THE SYSTEM SHALL respond `404 Not Found` and
  SHALL NOT call the Backstage verify/delete endpoint.
- WHEN an authenticated user with access to `team` calls `VerifyDomain` or
  `DeleteDomain` with a domain `id` that does belong to `team`, THE SYSTEM
  SHALL proxy the request to Backstage exactly as it does today (bearer
  service token attached, response body/status passed through).
- WHILE `user` is nil (no user in request context, e.g. a handler invoked
  directly in a unit test without auth middleware), THE SYSTEM SHALL skip
  the tenant-access check, matching the existing `ListDomains`/`AddDomain`
  behavior at handlers_domains.go:59 and :115.
- IF the caller is an admin (`user.IsAdmin()` true, e.g. the `admins` group
  or the `mctl-agent` static service token) THEN THE SYSTEM SHALL allow
  verify/delete on any team's domain, consistent with
  `HasTenantAccess`'s existing admin short-circuit (internal/auth/oidc.go:56).
- WHEN existing behavior for `ListDomains`/`AddDomain`/domain-within-own-team
  verify/delete is exercised, THE SYSTEM SHALL be unchanged (no regression
  in status codes, response bodies, or the `Authorization: Bearer
  <BackstageToken>` header forwarded upstream).

## Out of scope

- The `mctl-portal` custom-domains-backend tenant check (tracked as a
  companion issue in that repo).
- Changing how `ListDomains`/`AddDomain` perform authorization.
- Adding a local (mctl-api-owned) datastore for domain-to-team mapping.
- Changing the global auth middleware's nil-user / dev-mode / static
  service-token semantics (`internal/auth/oidc.go`).

## Open questions

- The issue says "reuse the list/add pattern," but list/add both receive
  `team` directly from the caller (query param or body) — they do not need
  to resolve an id to a team first. `VerifyDomain`/`DeleteDomain` only
  receive an `id`. Interpretation used here: require the caller to also
  pass `team` as a query parameter (mirroring `ListDomains`), then confirm
  via Backstage's own `GET /api/custom-domains/domains?team=<team>` listing
  (the same call `ListDomains` already makes) that the `id` genuinely
  belongs to that team, before forwarding the verify/delete call. This
  avoids trusting the caller's `team` claim on its own and avoids adding a
  new upstream Backstage endpoint dependency. If Backstage instead exposes
  a `GET /api/custom-domains/domains/{id}` lookup that returns the owning
  team directly, that would be a cleaner single-call alternative — the
  design notes this but proceeds with the list-based check since no such
  endpoint is evidenced in this repo's client code.
- `internal/mcp/server.go`'s `toolVerifyDomain` (line 1523) already lists
  domains by `team`+`service` before looping over ids to verify each one,
  so it has `team` in scope and only needs its POST call updated to include
  `&team=`. `toolRemoveCustomDomain` (line 1480) does not call
  `DeleteDomain` directly — it triggers the `remove-custom-domain` Argo
  workflow operation instead, which is out of scope for this proposal.
