# Design: issue-584-mctl-list-repos-always-fails-backstage-r

## Current state
- `internal/api/handlers_repos.go`:
  - `authorizeGithubAppConnect` sets `Authorization: Bearer <BackstageGithubAppConnectToken>` when the token is set, and does nothing when it is not.
  - `ListRepos` calls `GET {BackstageInternalURL}/api/github-app-connect/repos?team=`. It checks `HasTenantAccess` only `if user != nil`, so a nil user passes. It relays the upstream status and body verbatim, which is how the plugin's 401 `Authentication required` reaches `mctl_list_repos` callers.
  - `GetRepoInstallURL` has the same shape: `GET .../install-url?team&service&repo`, with the same nil-user pass-through.
  - `SyncRepos` requires a user and checks `HasTenantAccess` and `requireTenantRole(..., reposSyncRole, "repos-sync", RiskLow)`. It then calls `POST .../repos/sync?team=&user=<user.ID>`.
  - All three share `backstageReposClient` (15s timeout).
- `internal/api/build_repo_gate.go` `repoBoundToTeam` is the one working call. It sends `GET .../repo-binding?team&repo` with the same token, refuses when the URL or token is unset, treats non-200 as an error, and validates the echoed body.
- `internal/api/router.go:558-560` registers the three routes. Lines 335-339 log a warning when the token is unset. `Options.BackstageGithubAppConnectToken` is documented at lines 84-87.
- `cmd/api/main.go:1520-1523` reads `BACKSTAGE_INTERNAL_URL` (default `http://backstage.backstage.svc.cluster.local:7007`) and `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN`. `helm/templates/deployment.yaml:146-150` mounts the token from a Secret.
- `internal/api/handlers_repos_test.go`: `captureBackstage` is a fake that answers 200 to every request. `TestReposProxiesSendBearerToken` and `TestReposProxiesOmitAuthWhenTokenUnset` assert only the header, so no test models the plugin's user/service split. That is why the bug passed CI.
- mctl-portal `plugins/github-app-connect-backend/src/router.ts` (read through `gh api` at the default branch):
  - `resolveCallerUserId` uses `httpAuth.credentials(req, { allow: ['user'] })`.
  - `/repos` (line 819) uses `resolveCallerUserId` then `checkTeamAccess`, and reads `store.findVerifiedByTeam(team)`.
  - `/install-url` (line 452) and `/repos/sync` (line 863) use `requireTeamAccess`, which is user-only too. `/repos/sync` also requires `user` to equal the caller unless the caller is an admin.
  - `/repo-binding` (line 482) uses `allow: ['service']` and accepts subject `bindingCheckSubject` or `external:<bindingCheckSubject>`.
  - Result: all three proxied routes are user-only, so the issue's "probably affected" is confirmed.

Deployed state checked:
- `$MCTL_GITOPS_ROOT` is unset. I listed the checkout at `/workdir/mctl-gitops/platform-gitops/services`. It has tenants `admins`, `karabu` and `labs`. `services/admins/` contains no `mctl-api` entry (mctl-api is a platform component and is deployed outside the tenant services tree). A grep for `BACKSTAGE` / `github-app-connect` under `services/` and `tenants/` found nothing.
- mctl-gitops `bootstrap/templates/mctl-platform/mctl-portal.yaml` (the externalAccess entry) is not in this checkout. Not observed, so the subject `mctl-api-repo-binding` and its plugin restriction are taken from the issue text.
- mctl MCP tools: not called. The deployed env of mctl-api is not a tenant service config, and the issue already supplies the Backstage request log. Recorded as a gap under Open questions in requirements.md.
- mctl-portal router.ts: read at the default branch through `gh api repos/mctlhq/mctl-portal/contents/...` (the line numbers above come from that read).

## Proposed solution
Option 1 from the issue, in two coordinated changes.

### A. mctl-portal (prerequisite, separate PR)
Add three routes to `createRouter` that authenticate exactly like `/repo-binding`. Extract a helper, for example `requireBindingPrincipal(req)`: `allow: ['service']`, then match the subject against `bindingCheckSubject` or `external:<subject>`, and answer 401 or 403 otherwise.
- `GET /service/repos?team=`: requires `team` (`TEAM_OR_SERVICE_RE`) and returns `{"repos": sorted unique store.findVerifiedByTeam(team)}`. There is no team-less/all-teams mode.
- `GET /service/install-url?team&service&repo&user`: the same validation as `/install-url`, plus `GITHUB_LOGIN_RE` on `user`. The state is encrypted with `user` as given by mctl-api.
- `POST /service/repos/sync?team&user`: the same body as `/repos/sync`, with `auth.userId` replaced by the asserted `user`. The `team === 'admins'` organization-install branch is unchanged.
The routes do no membership check of their own: mctl-api has authorized the caller. That is the same trust model `/repo-binding` already uses for the same principal. The existing user routes are untouched.

### B. mctl-api (this repo)
In `internal/api/handlers_repos.go`:
1. Add constants for the three service paths, and a shared helper `proxyGithubAppConnect(w, r, method, pathAndQuery, logAttrs...)` that:
   - refuses with 503 when `BackstageInternalURL` or `BackstageGithubAppConnectToken` is empty (as `repoBoundToTeam` does; no anonymous call);
   - sets the Bearer header (reusing `authorizeGithubAppConnect`);
   - maps an upstream 401/403 to 502 `{"error":"backstage refused the platform credential"}`, with `slog.Error` carrying the upstream status and route; maps an upstream 404 (route not deployed yet) to 502; relays 200, 400 and 5xx bodies as it does today (5xx relayed as 502);
   - reads the body through `io.LimitReader` (1 MiB).
2. `ListRepos`: refuse a nil user with 401 (`writeError`), keep the `HasTenantAccess` 403, call `GET /api/github-app-connect/service/repos?team=`.
3. `GetRepoInstallURL`: refuse a nil user with 401, resolve the caller's GitHub login (see below), call `/service/install-url` with `user=<login>`.
4. `SyncRepos`: keep the current checks, resolve the GitHub login instead of using raw `user.ID`, call `POST /service/repos/sync?team&user=`.
5. GitHub login resolution: a small `githubLoginOf(user *auth.User) (string, bool)` that returns the linked GitHub login (the field behind `auth.Identity{Provider: ProviderGitHub, Display: GitHubLogin}` / `ClaimCustomerGitHubLogin`) and validates it with `auth.ValidGitHubLogin`. When there is none, return 409 `{"error":"a linked GitHub identity is required"}`. For GitHub-authenticated users this is the same value `user.ID` carries today, so their behaviour does not change.
6. `router.go`: update the comment at lines 84-87 and the warning at 338. With the token unset, the routes now answer 503 instead of proxying anonymously.
7. Update the tool descriptions in `internal/mcp/server.go` only if they mention the auth failure. No tool is added or removed, so the `server_test.go` count is unchanged.

Why this way: the repo list is plugin data (`store.findVerifiedByTeam`), and `/repo-binding` already establishes the service-principal pattern and the token, so no new secret or identity bridge is needed. Authorization stays in one place, mctl-api.

## Alternatives
- Forward a Backstage user identity from mctl-api (issue option 2). mctl-api users are not Backstage sessions. This would need token exchange or impersonation in Backstage, which is a much larger trust change. Dropped.
- Serve `ListRepos` by calling `/repo-binding` per repository. That endpoint answers yes/no for a known repo and cannot enumerate. Dropped.
- Read the plugin's Postgres tables from mctl-api. This couples mctl-api to the plugin's schema and needs a new DB credential across a service boundary. Dropped.
- Relax the existing `/repos` route to `allow: ['user','service']`. Possible for `/repos`, but `/install-url` and `/repos/sync` derive the user from the credential, so they would need a separate "asserted user" path anyway. Separate `/service/*` routes keep the UI routes' semantics unchanged and make the trusted surface explicit. Kept as a fallback if the portal reviewer prefers it; mctl-api only changes a path constant.

## Platform impact
- No migrations, new secrets or new env vars. The token and its externalAccess entry are reused.
- Ordering: the mctl-portal routes must deploy first. If mctl-api ships first, the three routes answer 502 instead of 401. Both are broken, and the new error is clearer, so the order is not dangerous, but the PR should state the dependency.
- Behaviour changes:
  - A nil user on `ListRepos` and `GetRepoInstallURL` now gets 401 from mctl-api.
  - An unset token now gives 503 instead of an anonymous call.
  - A principal without a GitHub login gets 409 on install-url and sync. Today such a call either fails in the plugin or, after this change, would bind to a non-login, so refusing is safer.
- Security: the service routes trust mctl-api's asserted `team` and `user`. The credential is restricted to the github-app-connect plugin and to the single subject. mctl-api asserts only the authenticated caller's own login, never body input. Admin bypass auditing (`auditAdminBypass`) moves to mctl-api's own audit of these calls. The portal side should still log subject, team and user on each service call.
- Resources: negligible.
