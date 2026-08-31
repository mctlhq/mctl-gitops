# Send credentials on the github-app-connect repo proxy (repos/list/sync/install-url)

## Context

`mctl-api` proxies three routes to Backstage's `github-app-connect` plugin:
`GET /api/v1/repos` (`ListRepos`), `GET /api/v1/repos/install-url`
(`GetRepoInstallURL`), and `POST /api/v1/repos/sync` (`SyncRepos`), all in
`internal/api/handlers_repos.go`. All three issue requests through the shared
`backstageReposClient` without ever setting an `Authorization` header. This
was harmless while `github-app-connect` allowed unauthenticated calls, but
mctl-portal#79 removed `allow: 'unauthenticated'` from the plugin, leaving
only `/callback`, `/popup-done`, and `/webhook` open. Every other route,
including the three above, now requires an authenticated Backstage caller and
returns 401 to `mctl-api`. In production this means `POST
/api/v1/repos/sync` and the `mctl_sync_repos` MCP tool are broken end-to-end,
and `ListRepos` / `GetRepoInstallURL` are exposed to the same failure mode
even though the issue's repro focuses on sync.

This proposal covers the `mctl-api` side only: attach the credential the
`github-app-connect` plugin now requires, using the same pattern
`internal/api/handlers_domains.go` already uses for the `custom-domains`
plugin (`authorizeBackstage`, added after mctl-portal 951d450 closed the same
gap for `/domains*`). The companion Backstage-side changes (granting the
token `plugin: github-app-connect` access, and the on-behalf-of/admin
identity story for the `user` param check in
`plugins/github-app-connect-backend/src/router.ts:726-729`) live in
mctl-portal and are called out as a hard dependency, not implemented here.

## User stories

- AS a team member using the mctl dashboard or the `mctl_sync_repos` MCP
  tool, I WANT `POST /api/v1/repos/sync` to succeed SO THAT I can discover
  newly GitHub-App-installed repos for my team without a 401 from Backstage.
- AS a team member browsing available repos, I WANT `GET /api/v1/repos` and
  `GET /api/v1/repos/install-url` to keep working SO THAT the onboard-service
  flow is not silently broken by the same auth gate that broke sync.
- AS a platform operator, I WANT the credential mctl-api sends to
  `github-app-connect` to be scoped as narrowly as practical SO THAT a leak
  of that token does not also grant access to unrelated Backstage plugins
  (e.g. `custom-domains`).
- AS a platform operator, I WANT the service-token identity mctl-api
  authenticates as to be recognized by `github-app-connect`'s per-user
  authorization check SO THAT proxied calls are not additionally rejected
  with 403 once the 401 is fixed.

## Acceptance criteria (EARS)

- WHEN `mctl-api` proxies `GET /api/v1/repos`, `GET
  /api/v1/repos/install-url`, or `POST /api/v1/repos/sync` to Backstage's
  `github-app-connect` plugin, THE SYSTEM SHALL attach an `Authorization:
  Bearer <token>` header carrying a credential authorized for the
  `github-app-connect` plugin.
- IF the configured `github-app-connect` credential is empty, THEN THE
  SYSTEM SHALL send the request without an `Authorization` header (matching
  `authorizeBackstage`'s existing no-op-when-unset behavior in
  `handlers_domains.go`) rather than sending a malformed `Bearer ` header.
- WHILE per-team authorization is enforced locally via
  `user.HasTenantAccess`, THE SYSTEM SHALL continue to perform that check
  before any proxied request reaches Backstage, unchanged from today.
- WHEN `SyncRepos` builds the upstream request, THE SYSTEM SHALL continue to
  derive the `user` query parameter solely from `auth.UserFromContext` (the
  #197 fix already in `handlers_repos.go` and pinned by
  `handlers_repos_test.go`), never from the request body.
- IF the credential used for `github-app-connect` is a distinct token from
  `BackstageToken` (the `custom-domains` token), THEN THE SYSTEM SHALL read
  it from its own configuration field and environment variable, so the two
  plugins' credentials can be rotated and scoped independently.
- WHEN Backstage's `github-app-connect` router still returns 401/403 after
  this change (e.g. the companion mctl-portal access-grant or identity
  exemption has not shipped yet), THE SYSTEM SHALL propagate that upstream
  status code and body to the caller unchanged (existing passthrough
  behavior in all three handlers), not swallow or remap it.

## Out of scope

- Changing `plugins/github-app-connect-backend/src/router.ts` or
  `app-config.production.yaml` in mctl-portal (granting the token
  `plugin: github-app-connect` access, or building the on-behalf-of /
  admin-override identity exemption for the `user`-param match at
  router.ts:726-729). This proposal only makes mctl-api send a credential;
  Backstage must be configured to accept it. Tracked as a hard dependency.
- Any change to the identity attribution fix from #197
  (`user` always sourced from `auth.UserFromContext`) — it is already
  correct and covered by `handlers_repos_test.go`.
- Retrying, caching, or circuit-breaking Backstage proxy calls.
- Changing the `custom-domains` token or `authorizeBackstage` itself.

## Open questions

- Should mctl-api mint a **second** external token scoped only to
  `plugin: github-app-connect`, or should the existing `BACKSTAGE_TOKEN`
  (currently `accessRestricted` to `plugin: custom-domains`) be *extended*
  to cover both plugins? The issue frames this explicitly as an open
  decision with "different blast radii." This proposal picks the
  **second-token** option (smaller blast radius: a leak of the
  `github-app-connect` credential does not also expose `custom-domains`,
  and the two plugins can be rotated independently) and introduces a new
  `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` env var / `Options.BackstageGithubAppConnectToken`
  field for it. See design.md Alternatives for the rejected single-token
  option. This is a reasonable default, not a blocking question — reviewers
  who prefer the single-token route can swap the env var back to
  `BackstageToken` with a small diff.
- Whether the Backstage-side admin/on-behalf-of exemption for the
  `user`-param match check will accept mctl-api's service-token identity
  automatically, or needs an explicit allowlist entry, is a mctl-portal-side
  decision not resolved here. Proceeding on the assumption that the
  companion mctl-portal change grants the new token an identity Backstage
  recognizes as exempt (equivalent to today's admin exemption at
  router.ts:726-729).
