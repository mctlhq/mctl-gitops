# Tasks: issue-205-github-app-connect-service-principal-rou

- [ ] 1. In `plugins/github-app-connect-backend/src/router.ts` (`createRouter`), add `requireBindingPrincipal(req)` and `auditServiceCall(route, subject, fields)`. `requireBindingPrincipal` uses `allow: ['service']` and answers 401 on no credential. It answers 403 `Not allowed` when `bindingCheckSubject` is unset or the subject is neither `bindingCheckSubject` nor `external:<bindingCheckSubject>`. — DoD: the helpers compile under strict TS, and the logic is a pure move of the current `/repo-binding` check.
- [ ] 2. Refactor `GET /repo-binding` to use `requireBindingPrincipal` (depends on 1). — DoD: the existing `describe('GET /repo-binding')` tests in `router.auth.test.ts` pass unchanged.
- [ ] 3. Extract the body of `POST /repos/sync` into `syncTeamRepos(team, user, createdByLogin, res)`. `/repos/sync` calls it with `auth.userId` as `createdByLogin`. — DoD: the existing `POST /repos/sync` tests, including `carries over only verified bindings`, pass unchanged. Rows still use `created_by: sync:<login lowercased>`.
- [ ] 4. Add `GET /service/repos?team=` (depends on 1). It validates `team` with `TEAM_OR_SERVICE_RE`, else 400, audits, and answers sorted unique `repo_full_name` from `store.findVerifiedByTeam(team)`, or 500 `{repos: []}` on error. There is no team-less mode. — DoD: tests T1-T3 pass.
- [ ] 5. Add `GET /service/install-url?team&service&repo&user` (depends on 1). It validates team and service (`TEAM_OR_SERVICE_RE`), repo (`REPO_FULL_NAME_RE`) and user (`GITHUB_LOGIN_RE`), audits, and answers `{url, state}`. The state is `{team, service, repo, user, nonce}`, with the asserted `user`. — DoD: tests T1-T2 and T4 pass.
- [ ] 6. Add `POST /service/repos/sync?team&user` (depends on 1, 3). It validates team and user, audits, and calls `syncTeamRepos(team, user, user, res)`. The `admins` organization branch is unchanged. — DoD: tests T1-T2 and T5 pass.
- [ ] 7. Add a short comment block above the `/service/*` routes stating the trust model: mctl-api authorizes, there is no membership check here, and the routes are for mctl-api#584. Add a CHANGELOG-relevant conventional commit (`feat(github-app-connect): ...`). — DoD: lint and `yarn tsc` are clean, and the plugin test suite is green.

## Tests

All tests go in `plugins/github-app-connect-backend/src/router.auth.test.ts`. They use `buildRouter(..., { bindingCheckSubject: 'mctl-api-repo-binding' })`, `dispatch()`, and the `x-test-service` / `x-test-user` headers of `fakeHttpAuth`.

- [ ] T1. For each of `GET /service/repos?team=labs`, `GET /service/install-url?team=labs&service=api&repo=acme/api&user=carol` and `POST /service/repos/sync?team=labs&user=carol`:
  - 200 for `x-test-service: mctl-api-repo-binding` (static form);
  - 200 for `x-test-service: external:mctl-api-repo-binding`;
  - 401 with no headers;
  - 403 for `plugin:catalog`, `external:mctl-api` and `mctl-api`.
  - For sync, mock `fetch` so the user's installation lookup returns 404, which gives 200 `{repos: []}`.
- [ ] T2. For each `/service/*` route:
  - 401 for a signed-in user, even a platform admin (`x-test-user: root` with `admins:root` owner);
  - 403 for every subject (`external:`, `external:undefined`, `undefined`, `mctl-api-repo-binding`) when `bindingCheckSubject` is unset;
  - no store or `fetch` call in any refused case;
  - an unauthenticated request with invalid params answers 401, not 400.
- [ ] T3. `/service/repos`:
  - returns sorted unique repos from `findVerifiedByTeam('labs')`, given duplicates and unsorted input;
  - 400 for a missing team, `team=../x` and `team=a/b`;
  - `findAllVerified` is never called;
  - 500 `{repos: []}` when the store throws.
- [ ] T4. `/service/install-url`:
  - 400 for a missing or invalid team, service, repo or user (`user=../orgs/x`, `user=-bad`);
  - on 200, `decryptState(body.state, sha256(privateKey))` yields `user: 'carol'` plus the given team, service and repo, and `body.url` embeds the state;
  - a `/callback` with that state and an installation owned by `carol` records `callback:carol`.
- [ ] T5. `/service/repos/sync`:
  - 400 for invalid team or user;
  - with a mocked personal installation for `carol`, `replaceTeam` receives rows with `created_by: 'sync:carol'`;
  - for `team=admins` the organization-installations call (`/app/installations?per_page=100`) is made, and for other teams it is not;
  - a failing GitHub call answers 500 and `replaceTeam` is not called.
- [ ] T6. No widening: `GET /repos?team=labs`, `GET /install-url?...` and `POST /repos/sync?...` called with `x-test-service: mctl-api-repo-binding` still answer 401.
- [ ] T7. Audit: a spy on `logger.info` sees `audit: 'service_principal'` with route, subject, team and (where applicable) user on each accepted `/service/*` call, and no such line on refused calls.

## Rollback

The change is additive and needs no migration or config, so roll back by reverting the commit and redeploying the previous portal image. Before reverting, make sure mctl-api part B (mctl-api#584) is not yet live, or revert it first: once part B ships, removing these routes makes `mctl_list_repos`, `mctl_grant_repo_access` and `mctl_sync_repos` fail again (502 from mctl-api). For an emergency that keeps the image, set `repoBinding.enabled: false` in mctl-gitops `bootstrap/values.yaml`. That unsets `bindingCheckSubject`, so every `/service/*` route and `/repo-binding` answer 403. This also disables mctl-api's build-gate binding lookup, so use it only for a token compromise.
