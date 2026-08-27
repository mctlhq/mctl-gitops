# Design: issue-196-add-hastenantaccess-rbac-to-verifydomain

## Current state

`internal/api/handlers_domains.go` implements four handlers that proxy to
the Backstage custom-domains plugin at `h.opts.BackstageInternalURL`:

- `ListDomains` (line 46): `GET /api/v1/domains?team=X&service=Y`. Reads
  `team` from the query string, and at line 59 checks
  `if user != nil && !user.HasTenantAccess(team) { 403 }` before proxying to
  `GET {baseURL}/api/custom-domains/domains?team=X[&service=Y]`.
- `AddDomain` (line 93): `POST /api/v1/domains` with a JSON body containing
  `team`, `service`, `domain`. At line 115 performs the identical
  `HasTenantAccess(req.Team)` check before proxying.
- `VerifyDomain` (line 157): `POST /api/v1/domains/{id}/verify`. Reads only
  `id` from the chi URL param, does no authorization check, and proxies
  straight to `POST {baseURL}/api/custom-domains/domains/{id}/verify`.
- `DeleteDomain` (line 191): `DELETE /api/v1/domains/{id}`. Same shape as
  `VerifyDomain` — `id` only, no authorization check, proxies to
  `DELETE {baseURL}/api/custom-domains/domains/{id}`.

All four handlers attach the shared Backstage credential via
`authorizeBackstage` (line 38), whose doc comment already states "Per-team
authorization is still enforced here via user.HasTenantAccess before we
ever reach Backstage" — true for list/add, not (yet) for verify/delete.

`auth.User.HasTenantAccess` (internal/auth/oidc.go:54) checks
`u.Groups` for either `"admins"` (via `IsAdmin()`, line 45) or an exact
match on the requested tenant name. `auth.UserFromContext` (line 68) reads
the `*auth.User` the auth middleware (`internal/auth/oidc.go:191`) put in
the request context; that middleware always populates a user for any
request that reaches a handler (dev-mode `dev-user`/admins, the
`mctl-agent` static service token/admins, or a validated Dex/GitHub/OAuth
identity) — the only way `UserFromContext` returns nil in practice is a
handler invoked directly, bypassing the middleware, as
`handlers_domains_test.go` already does today.

mctl-api holds no local record of which team owns which domain id — the
Backstage custom-domains plugin is the system of record. The MCP tool
`toolVerifyDomain` (internal/mcp/server.go:1523) already works around this:
given `team`+`service`, it first calls `GET /api/v1/domains?team=X&service=Y`
to resolve domain ids, then loops calling
`POST /api/v1/domains/{id}/verify` for each. `toolRemoveCustomDomain`
(internal/mcp/server.go:1480) does not call `DeleteDomain` at all; it
triggers the `remove-custom-domain` Argo Workflow operation
(`internal/operations/registry.go`), a separate code path.

`handlers_domains_test.go` currently has two tests:
`TestDomainProxiesSendBearerToken` (parameterized over list/add/verify/
delete, asserts the Backstage bearer token is always attached) and
`TestDomainProxiesOmitEmptyToken`. Both construct `*Handlers` directly and
call the handler method with no user in the request context.

## Proposed solution

1. Require a `team` query parameter on `VerifyDomain` and `DeleteDomain`,
   matching `ListDomains`'s existing convention. Missing `team` -> 400,
   same style as the existing `missing required param: team` /
   `missing required fields` errors in this file.

2. Add the same authorization guard used by `ListDomains`/`AddDomain`:
   `user := auth.UserFromContext(r.Context()); if user != nil &&
   !user.HasTenantAccess(team) { 403 }`. This is a direct copy of the
   existing pattern (lines 59, 115) for consistency, and preserves the nil
   -user passthrough the existing unit tests rely on, and the admin/
   service-token short-circuit inside `HasTenantAccess` itself.

3. Because `HasTenantAccess(team)` only proves the caller belongs to
   `team` — not that the domain `id` in the URL actually belongs to
   `team` — add an ownership check before forwarding the verify/delete
   call. Reuse the exact upstream call `ListDomains` already makes:
   `GET {baseURL}/api/custom-domains/domains?team=<team>` (via
   `authorizeBackstage`, same as today), decode the `domains` array (same
   shape the MCP tool already decodes at server.go:1550-1553, i.e. objects
   with an `id` field), and confirm the requested `id` is present. If the
   list call fails, respond `502 Bad Gateway` (matching this file's
   existing "backstage unavailable" handling). If `id` is absent from the
   team's list, respond `404 Not Found` — not 403 — so a caller cannot
   distinguish "domain exists but belongs to another team" from "domain
   does not exist," which is the correct IDOR-safe response (this mirrors
   how `handlers_alerts.go` handlers return 404 for
   `AlertStore.GetByPrefix` misses before ever reaching the tenant check).
   Only after this passes does the handler proceed to the existing
   verify/delete proxy call, unchanged.

4. Extract the "list domains for a team from Backstage" call into a small
   unexported helper (e.g. `func (h *Handlers) backstageDomainIDs(ctx
   context.Context, baseURL, team string) (map[string]struct{}, error)`)
   so `VerifyDomain` and `DeleteDomain` share one implementation instead of
   duplicating the upstream call and JSON decoding twice. `ListDomains`
   itself keeps streaming the raw proxied response through as it does
   today (it doesn't need parsed ids), so it is not changed to use the
   helper.

5. Update `internal/mcp/server.go`'s `toolVerifyDomain` (line 1561) to
   append `&team=` + `url.QueryEscape(team)` to the per-domain verify POST,
   since `team` is already in scope from the preceding list call at line
   1543. Without this change the MCP tool would start getting 400s from
   the now-required `team` parameter. `toolRemoveCustomDomain` needs no
   change — it does not call `DeleteDomain`.

6. Leave `ListDomains`, `AddDomain`, and `authorizeBackstage` untouched.
   Leave the response pass-through behavior (status code, body, headers)
   of `VerifyDomain`/`DeleteDomain` unchanged for the success path.

## Alternatives

- **Trust the caller's `team` query param without verifying id ownership
  against Backstage.** Simpler (one check, no extra upstream call), but
  does not actually close the IDOR: a user with access to their own team
  could pass `?team=their-team` while `id` belongs to another tenant, and
  the request would still sail through to Backstage. Rejected — this is
  exactly the vulnerability class the issue is about.

- **Add a `GET /api/custom-domains/domains/{id}` lookup to Backstage and
  call that instead of listing by team.** Cleaner (one targeted call,
  returns the owning team directly, no need for the caller to supply
  `team` at all — the handler could derive it from the lookup and check
  `HasTenantAccess` against that). Rejected for this proposal because no
  such endpoint is evidenced anywhere in this repo (only
  `/domains`, `/domains/{id}/verify`, `/domains/{id}` DELETE, and the
  team-filtered list are used today), and adding a new upstream contract on
  the Backstage side is outside mctl-api's control and outside this
  issue's stated scope (companion `mctl-portal` issue is about the
  portal's own tenant check, not a new API). Recorded in Open questions as
  the preferred long-term shape if/when Backstage adds it.

- **Maintain a local mctl-api-side domain-to-team index (cache or DB row)
  populated on `AddDomain`.** Would avoid the extra upstream list call per
  verify/delete, but introduces a second source of truth that can drift
  from Backstage (e.g. domains added directly against Backstage, or by an
  older client), adds migration/schema work, and duplicates state the
  issue's "out of scope" section implies should stay in Backstage/portal.
  Rejected as disproportionate to a proxy service.

## Platform impact

- **Migrations:** none. No schema or storage changes.
- **Backward compatibility:** `team` becomes a required query parameter on
  `POST /api/v1/domains/{id}/verify` and `DELETE /api/v1/domains/{id}`.
  This is a breaking change for any existing caller that does not already
  send `team` — identified callers are the MCP tool (`toolVerifyDomain`,
  updated in this proposal) and any external client hitting these two
  routes directly. `toolRemoveCustomDomain` is unaffected since it doesn't
  call `DeleteDomain`. Flagged as a risk below.
- **Resource impact:** `VerifyDomain`/`DeleteDomain` now make two upstream
  Backstage calls instead of one (a list-by-team call, then the original
  verify/delete call) when a `user` is present and non-admin-checked. This
  roughly doubles Backstage-proxy latency and load for these two routes;
  acceptable given they are low-QPS, human-triggered/administrative
  operations, not hot paths.
- **Risks + mitigations:**
  - Risk: external callers of the raw REST routes break on the new
    required `team` param. Mitigation: this is a security fix for a
    P0 IDOR; the requirements capture "unchanged for own-tenant/list/add"
    but the verify/delete contract change is unavoidable given mctl-api
    has no other way to resolve id-to-team. Call this out prominently in
    the PR description / CHANGELOG (this repo uses conventional-commit
    driven changelog generation per `CHANGELOG.md`).
  - Risk: the extra Backstage list call fails or times out where the
    direct verify/delete call previously succeeded, causing new 502s.
    Mitigation: reuses the existing `backstageDomainsClient` (15s timeout)
    and the same error handling shape already used by `ListDomains`.
  - Risk: forgetting to update `toolVerifyDomain` leaves the MCP tool
    broken. Mitigation: task list includes this as an explicit dependent
    task with its own test.
