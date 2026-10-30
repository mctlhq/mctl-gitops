# Make mctl_list_repos (and the other repo proxies) work with mctl-api's service credential

## Context
`GET /api/v1/repos?team=<team>` (`ListRepos`, `internal/api/handlers_repos.go`) proxies to
Backstage `GET /api/github-app-connect/repos` with the static external-access token
`BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` as a Bearer. In mctl-portal
(`plugins/github-app-connect-backend/src/router.ts`), `/repos` resolves the caller through
`resolveCallerUserId`, which calls `httpAuth.credentials(req, { allow: ['user'] })`. The
static token is a *service* principal (subject `mctl-api-repo-binding`), so `/repos` always
answers 401 `Authentication required`, and `mctl_list_repos` has never worked with this token.
The same applies to `GetRepoInstallURL` (portal `/install-url`, which calls `requireTeamAccess`)
and `SyncRepos` (portal `/repos/sync`, which calls `requireTeamAccess`). Only `/repo-binding`
accepts the service principal (`allow: ['service']`, subject checked against
`bindingCheckSubject`).

mctl-api already authorizes the caller (`HasTenantAccess(team)`, and `requireTenantRole` for
sync) before it proxies. The fix is to give the plugin service-authenticated routes that trust
the configured mctl-api principal, as `/repo-binding` does. mctl-api then calls those routes.
The proxied calls must also stop surfacing an upstream credential failure as if the end user
were unauthenticated.

## User stories
- AS a platform user calling `mctl_list_repos` I WANT the repos connected to my team returned SO THAT I can pick a `dockerfile_repo` to onboard.
- AS a platform user calling `mctl_grant_repo_access` / `mctl_sync_repos` I WANT these calls to reach the plugin successfully SO THAT I can connect and refresh repositories without the portal UI.
- AS a platform operator I WANT a failure of mctl-api's own Backstage credential to show up as an upstream error, not as "Authentication required" SO THAT a misconfiguration is not mistaken for a caller problem.

## Acceptance criteria (EARS)
- WHEN an authenticated caller with tenant access to `team` calls `GET /api/v1/repos?team=<team>` THE SYSTEM SHALL call the plugin's service-authenticated repo-list route with `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` and return 200 with the plugin's `{"repos":[...]}` body.
- WHEN an authenticated caller with tenant access calls `GET /api/v1/repos/install-url` THE SYSTEM SHALL call the plugin's service-authenticated install-url route, passing the authenticated caller's identity as the user the state is bound to, and return the plugin's `{url,state}` body.
- WHEN an authenticated caller with the `reposSyncRole` calls `POST /api/v1/repos/sync` THE SYSTEM SHALL call the plugin's service-authenticated sync route with the team and the authenticated caller's GitHub login, never a value from the request body.
- IF there is no authenticated user in the request context THEN THE SYSTEM SHALL answer 401 from mctl-api itself, before any upstream call (this applies to all three handlers, including `ListRepos` and `GetRepoInstallURL`, which currently let a nil user through).
- IF the caller lacks tenant access to `team` THEN THE SYSTEM SHALL answer 403 without calling Backstage.
- IF the plugin answers 401 or 403 to mctl-api's service credential THEN THE SYSTEM SHALL answer 502 with a generic "backstage refused the platform credential" error and log the upstream status, not relay a 401 to the caller.
- IF `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` is unset THEN THE SYSTEM SHALL answer 503 (not configured) for these routes without calling Backstage.
- IF the authenticated caller has no GitHub login that the plugin can bind state or a sync to THEN THE SYSTEM SHALL refuse install-url and sync with a 4xx that says a linked GitHub identity is required, and SHALL NOT call Backstage.
- WHILE the plugin's service routes are not deployed THE SYSTEM SHALL keep answering with an explicit upstream error (404/502 mapped to 502), never a fabricated empty repo list.

## Out of scope
- Forwarding a Backstage user session from mctl-api (option 2 in the issue). mctl-api users are ZITADEL/GitHub/OAuth identities, not Backstage sessions.
- Reading the plugin's database directly from mctl-api.
- Changing the user-authenticated routes the portal UI uses (`/repos`, `/install-url`, `/repos/sync` stay exactly as they are).
- Changing the token or its externalAccess restriction in mctl-gitops, except where the new routes need it (see Open questions).
- The `/repo-tags` and `/service-config` plugin routes.

## Open questions
- Cross-repo dependency: the service routes must land in mctl-portal (`plugins/github-app-connect-backend/src/router.ts`) before or with this change. This proposal assumes the paths `GET /service/repos`, `GET /service/install-url` and `POST /service/repos/sync`, gated by the same `bindingCheckSubject` check as `/repo-binding`. The mctl-portal reviewer may pick different names. mctl-api only needs the paths to be constants.
- User identity for install-url and sync: the plugin binds state to `user` and syncs the user's *personal* GitHub App installation, keyed by GitHub login (`GITHUB_LOGIN_RE`). `SyncRepos` sends `user.ID` today. For ZITADEL/customer principals that may not be a GitHub login (`auth.ClaimCustomerGitHubLogin` exists in `internal/auth/customer.go`). This proposal assumes mctl-api derives the GitHub login from the user's linked GitHub identity and refuses when there is none. The implementer must confirm which `auth.User` field carries it.
- Admin bypass: the portal's `checkTeamAccess` lets platform admins read any team. mctl-api's `HasTenantAccess` is assumed to already encode the same rule for admins. The service route trusts mctl-api's decision and does no membership check of its own.
- Could not read the externalAccess entry (mctl-gitops `bootstrap/templates/mctl-platform/mctl-portal.yaml`) because it is outside the available `platform-gitops/` checkout. Assumed from the issue: it is restricted to the github-app-connect plugin, so new routes on that plugin are covered without a config change.
