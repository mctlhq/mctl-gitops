# github-app-connect: service-principal routes for repos list, install-url and sync

## Context

mctl-api's `mctl_list_repos`, `mctl_grant_repo_access` and `mctl_sync_repos` tools always fail with `401 Authentication required` (mctlhq/mctl-api#584). mctl-api proxies them to `GET /repos`, `GET /install-url` and `POST /repos/sync` of `plugins/github-app-connect-backend/src/router.ts`. It authenticates with the static externalAccess token whose subject is `mctl-api-repo-binding` and which is restricted to the `github-app-connect` plugin. Those three routes resolve the caller with `httpAuth.credentials(req, { allow: ['user'] })` (`resolveCallerUserId` / `requireTeamAccess`), so a service principal can never pass. Only `GET /repo-binding` accepts that principal (`allow: ['service']` plus the `bindingCheckSubject` check). An external tenant owner reported on 2026-10-25 that they could not connect a repository through MCP.

This proposal is part A of the accepted design for mctl-api#584 (mctl-gitops `platform-gitops/agents-state/mctl-api/proposals/issue-584-mctl-list-repos-always-fails-backstage-r/`). It adds three `/service/*` routes that authenticate exactly like `/repo-binding`. mctl-api has already authorized the caller, and the routes take the GitHub login it asserts. Part B in mctl-api switches its proxies to these routes. Part A must be deployed first.

## User stories

- AS mctl-api (service principal `mctl-api-repo-binding`) I WANT to list a team's connected repositories, mint a GitHub App install URL and trigger a repository sync on behalf of a user I have already authorized SO THAT `mctl_list_repos`, `mctl_grant_repo_access` and `mctl_sync_repos` work for MCP users.
- AS a tenant owner using MCP I WANT to connect and list my repositories SO THAT I can onboard a service without the portal UI.
- AS a platform operator I WANT every service-principal call logged with subject, team and user SO THAT calls made on a user's behalf can be audited.
- AS a portal UI user I WANT the existing user routes to behave exactly as before SO THAT nothing changes for me.

## Acceptance criteria (EARS)

Authentication (shared helper `requireBindingPrincipal`):
- WHEN a request to any `/service/*` route carries no valid service credential THE SYSTEM SHALL answer 401 `{"error":"Authentication required"}` and do no work.
- WHEN a request to any `/service/*` route carries a user credential (including a platform admin's) THE SYSTEM SHALL answer 401 and do no work.
- IF `githubAppConnect.bindingCheckSubject` is unset THEN THE SYSTEM SHALL refuse every `/service/*` request with 403 `{"error":"Not allowed"}`, whatever subject the credential carries (including `external:`, `external:undefined` and `undefined`).
- IF the service credential's subject is neither `bindingCheckSubject` nor `external:<bindingCheckSubject>` THEN THE SYSTEM SHALL answer 403 `{"error":"Not allowed"}` and do no work.
- WHEN the subject equals `bindingCheckSubject` (static token) or `external:<bindingCheckSubject>` (jwks token) THE SYSTEM SHALL continue to parameter validation.
- WHILE handling a `/service/*` request THE SYSTEM SHALL check authentication before it validates parameters, so an unauthenticated caller cannot use 400 answers to probe the routes.
- WHEN `/repo-binding` is called THE SYSTEM SHALL keep its current behavior (status codes and body) after it is moved onto the shared helper.

`GET /service/repos?team=<team>`:
- IF `team` is missing or does not match `TEAM_OR_SERVICE_RE` THEN THE SYSTEM SHALL answer 400.
- WHEN an authorized principal calls it with a valid `team` THE SYSTEM SHALL answer 200 `{"repos": [...]}` containing the sorted, de-duplicated `repo_full_name` values from `store.findVerifiedByTeam(team)`.
- THE SYSTEM SHALL NOT offer a team-less or all-teams mode on this route, and SHALL NOT call `store.findAllVerified()` from it.
- IF the store read throws THEN THE SYSTEM SHALL answer 500 `{"repos": []}` and log the error.

`GET /service/install-url?team&service&repo&user`:
- IF `team` or `service` is missing or does not match `TEAM_OR_SERVICE_RE`, `repo` is missing or does not match `REPO_FULL_NAME_RE`, or `user` is missing or does not match `GITHUB_LOGIN_RE` THEN THE SYSTEM SHALL answer 400.
- WHEN an authorized principal calls it with valid parameters THE SYSTEM SHALL answer 200 `{"url", "state"}` in the same shape as `/install-url`. The encrypted state SHALL carry `{team, service, repo, user, nonce}`, where `user` is the asserted `user` parameter.
- WHEN GitHub later redirects to `/callback` with such a state THE SYSTEM SHALL handle it exactly as a state from `/install-url`. This includes `resolveBindableRepos` checking the asserted `user` against the installation, and recording the row as `callback:<user>`.

`POST /service/repos/sync?team&user`:
- IF `team` is missing or does not match `TEAM_OR_SERVICE_RE`, or `user` is missing or does not match `GITHUB_LOGIN_RE` THEN THE SYSTEM SHALL answer 400.
- WHEN an authorized principal calls it with valid parameters THE SYSTEM SHALL run the same sync as `/repos/sync`, with the asserted `user` in place of the authenticated caller's id. It SHALL write rows with `created_by: sync:<lowercased user>` and answer 200 `{"repos": [...]}`.
- WHILE `team === 'admins'` THE SYSTEM SHALL also include the App's organization installations, unchanged from `/repos/sync`.
- IF any GitHub call fails during the sync THEN THE SYSTEM SHALL answer 500 `{"repos": []}` without touching the team's rows, as `/repos/sync` does.

Audit and non-regression:
- WHEN any `/service/*` route accepts a request THE SYSTEM SHALL log an info line with `audit: 'service_principal'`, route, subject, team, and user (where the route takes one), plus service and repo for install-url.
- WHILE handling `/service/*` THE SYSTEM SHALL NOT perform a tenant membership or admin check (mctl-api is the authorization authority for these calls, the same trust model `/repo-binding` uses).
- WHEN a service credential (including `mctl-api-repo-binding`) calls `GET /repos`, `GET /install-url` or `POST /repos/sync` THE SYSTEM SHALL keep refusing it with 401, as today.

## Out of scope

- mctl-api changes (part B, mctl-api#584): switching its proxies to `/service/*`, resolving the caller's GitHub login, and its own authorization and audit.
- Any change to the user routes `/repos`, `/install-url`, `/repos/sync`, `/popup-state`, `/callback` or their semantics.
- New externalAccess entries, tokens, Vault paths or `bindingCheckSubject` values. The existing `mctl-api-repo-binding` entry and `bindingCheckSubject: mctl-api-repo-binding` are reused as deployed.
- Moving to jwks-based external access.
- A service-principal equivalent of `/popup-state`, `/repo-access`, `/install-status`, `/repo-tags` or `/service-config`.

## Open questions

- The issue lists "403/500-safe refusal" for an unset `bindingCheckSubject`. This proposal uses 403 `Not allowed` to match `/repo-binding` and its existing tests.
- The issue does not say whether `service` on `/service/install-url` gets `TEAM_OR_SERVICE_RE` validation. The user route `/install-url` does not validate it. The service route validates it, because a stricter check costs nothing and the value lands in the binding row's `service_id`.
- The issue does not say whether service-originated sync rows should be told apart from UI-originated ones. They keep the `sync:` prefix, because `VERIFIED_CREATED_BY_PREFIXES` in `store.ts` only counts `popup:`, `callback:`, `sync:` and `legacy:` rows as verified. A new prefix would make those rows invisible. The audit log line identifies the service origin instead.
