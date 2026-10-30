# Tasks: issue-584-mctl-list-repos-always-fails-backstage-r

- [ ] 1. Open an mctl-portal issue/PR adding `GET /service/repos`, `GET /service/install-url` and `POST /service/repos/sync` to `plugins/github-app-connect-backend/src/router.ts`, authenticated like `/repo-binding` (`allow: ['service']` plus a `bindingCheckSubject` match), and link it from the mctl-api PR. — DoD: a cross-repo issue/PR exists and the mctl-api PR description names it as a deploy prerequisite.
- [ ] 2. In `internal/api/handlers_repos.go`, add path constants and a `proxyGithubAppConnect` helper. The helper refuses with 503 when the URL or token is unset, sets the Bearer, maps upstream 401/403/404 to 502 with a log line, and limits the body read to 1 MiB. — DoD: the helper compiles, all three handlers use it, and no handler relays an upstream 401.
- [ ] 3. `ListRepos`: refuse a nil user with 401, keep the `HasTenantAccess` 403, call `/service/repos`. (depends on 2) — DoD: T1-T4 pass.
- [ ] 4. Add `githubLoginOf(*auth.User)` that resolves the linked GitHub login and validates it with `auth.ValidGitHubLogin`. — DoD: unit tests cover a GitHub user, a ZITADEL/customer user with a linked login, and a user without one.
- [ ] 5. `GetRepoInstallURL`: refuse a nil user with 401, answer 409 when there is no GitHub login, call `/service/install-url` with `user=<login>`. (depends on 2, 4) — DoD: T5 passes.
- [ ] 6. `SyncRepos`: send `user=<githubLoginOf>` instead of `user.ID`, keep the role and tenant checks, call `/service/repos/sync`. (depends on 2, 4) — DoD: T6 passes, and the existing body-override tests still pass after their expected paths are updated.
- [ ] 7. Update the `router.go` comments and the unset-token warning (lines 84-87, 335-339) to say the routes answer 503 when the token is unset. — DoD: the text matches the behaviour.
- [ ] 8. Run `go fmt`, `go vet`, `golangci-lint` and `go test ./...`. — DoD: all clean.

## Tests
- [ ] T1. Add `fakeGithubAppConnect` to `handlers_repos_test.go`: an httptest server that enforces the plugin's split. User-only routes (`/repos`, `/install-url`, `/repos/sync`) answer 401 `Authentication required` to any Bearer, because a static token is never a user. `/service/*` and `/repo-binding` answer 200 only for `Bearer <service-token>` and 401 otherwise. `TestListReposAgainstServiceAuthBackstage` asserts 200 and the repos body. This test fails on today's code, which gets the 401.
- [ ] T2. `ListRepos` with no user in context answers 401 and makes zero upstream calls. A cross-tenant caller answers 403 with zero upstream calls.
- [ ] T3. When the fake answers 401 or 403 to the credential, `ListRepos` answers 502, not 401.
- [ ] T4. With the token unset, all three handlers answer 503 and make zero upstream calls. This replaces `TestReposProxiesOmitAuthWhenTokenUnset`. `TestReposProxiesSendBearerToken` is updated to the `/service/*` paths.
- [ ] T5. `GetRepoInstallURL` against the fake: 200 with `user=<login>` in the upstream query. A user without a GitHub login gets 409 with zero upstream calls.
- [ ] T6. `SyncRepos` against the fake: the upstream `user` is the authenticated caller's GitHub login even when the body carries `"user":"someone-else"`.

## Rollback
Revert the mctl-api commit and redeploy the previous image. `ListRepos` then fails with 401 as it does today, and nothing else depends on it. The mctl-portal `/service/*` routes are additive, so they can stay or be reverted independently. No data or config migration needs to be undone.
