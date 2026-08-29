# SyncRepos: use authenticated user, ignore user field from request body

## Context
`Handlers.SyncRepos` (`internal/api/handlers_repos.go`) decodes a `user` field
from the POST body and forwards it, verbatim, to Backstage's
`github-app-connect/repos/sync` endpoint. The field only defaults to the
authenticated caller's ID when the body omits it (`if req.User == "" && user
!= nil { req.User = user.ID }`); if a caller supplies any non-empty `user`
value, that value wins. Any authenticated caller with access to a team (via
`user.HasTenantAccess`) can therefore trigger a repo sync attributed to, or
acting as, an arbitrary other GitHub identity — an authorization/spoofing gap
called out in the 2026-08 platform audit (P1). The `mctl_sync_repos` MCP tool
(`internal/mcp/server.go`) and the OpenAPI spec
(`internal/openapi/openapi.yaml`) both currently advertise this same `user`
body/parameter as a normal, caller-controlled input, so the fix must close
the gap at the handler and stop presenting the field as meaningful to
callers.

## User stories
- AS a platform operator I WANT repo-sync actions to always be attributed to
  the caller who is actually authenticated SO THAT audit trails and
  Backstage-side attribution cannot be spoofed by a request body value.
- AS an API/MCP client developer I WANT the `user` field's status to be
  documented and consistent across the HTTP handler, the MCP tool, and the
  OpenAPI spec SO THAT I do not rely on behavior that no longer exists.

## Acceptance criteria (EARS)
- WHEN `POST /api/v1/repos/sync` is called by an authenticated caller with a
  request body containing any `user` value THE SYSTEM SHALL ignore that
  value and use the authenticated caller's `user.ID` (from
  `auth.UserFromContext`) as the `user` parameter sent to Backstage.
- WHEN `POST /api/v1/repos/sync` is called by an authenticated caller with no
  `user` field in the body THE SYSTEM SHALL behave exactly as before: use the
  authenticated caller's `user.ID`.
- IF the request has no authenticated user in context (nil user, e.g.
  `AuthMiddleware` disabled) THEN THE SYSTEM SHALL reject the request with
  `401 Unauthorized` rather than falling back to a body-supplied or missing
  identity — matching the fail-closed pattern already used by
  `VerifyDomain`/`DeleteDomain` (`internal/api/handlers_domains.go`,
  `TestVerifyDomainNilUserUnauthorized`, `TestDeleteDomainNilUserUnauthorized`)
  for other mutating, identity-sensitive endpoints.
- WHILE processing a sync request THE SYSTEM SHALL continue to enforce
  `user.HasTenantAccess(req.Team)` for the `team` field exactly as it does
  today (this proposal changes only how `user` is derived, not the
  team-access check).
- THE SYSTEM SHALL prove the above via a unit test that POSTs a body with a
  `user` value different from the authenticated identity and asserts the
  upstream Backstage call carries the authenticated identity's ID, not the
  body value.

## Out of scope
- SSH host key pinning (explicitly excluded by the issue).
- Changes to the `team` field or `HasTenantAccess` authorization logic.
- Changes to `ListRepos` / `GetRepoInstallURL`, which never accepted a `user`
  field from the caller.
- Any change to Backstage's `github-app-connect` plugin itself.

## Open questions
- The issue offers two options for the field: remove it from the request
  struct, or keep it and explicitly discard it with a deprecation note. This
  proposal removes the `User` field from the anonymous request struct in the
  handler (Go's `encoding/json` ignores unknown JSON fields by default, so
  existing clients that still send `user` in the body will not break or
  error — the value is simply dropped). The `user` field is kept in the
  `mctl_sync_repos` MCP tool and in `openapi.yaml`, both re-documented as
  accepted-but-ignored/deprecated, so external tooling is not forced to
  change its call shape in this proposal. If maintainers prefer to remove the
  MCP tool parameter and OpenAPI property outright instead of deprecating
  them, that is a follow-up, not blocking.
- No open question on the core fix itself; the issue is fully specified for
  the handler behavior.
