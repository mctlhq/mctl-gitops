# Tasks: issue-197-syncrepos-use-authenticated-user-ignore

- [ ] 1. Update `Handlers.SyncRepos` in `internal/api/handlers_repos.go`:
      remove the `User` field from the request-decode struct (keep only
      `Team`); add an early `if user == nil { http.Error(w,
      `{"error":"unauthorized"}`, http.StatusUnauthorized); return }` check
      right after `user := auth.UserFromContext(r.Context())`; drop the
      `req.User == "" && user != nil` default-fill block and the subsequent
      "missing required field: user" 400 check; simplify
      `if user != nil && !user.HasTenantAccess(req.Team)` to
      `if !user.HasTenantAccess(req.Team)` (user is now guaranteed non-nil);
      build the upstream URL with `user.ID` instead of `req.User`. Update the
      handler's doc comment to drop the `"user": "mashkovd"` example.
      — DoD: `go build ./...` succeeds; `SyncRepos` no longer reads any
      `user` value from the request body under any code path.
- [ ] 2. Update `toolSyncRepos` in `internal/mcp/server.go`: change the
      `user` parameter's `mctl.WithString` description to state it is
      accepted for backward compatibility only and ignored server-side
      (identity always comes from the authenticated caller). Leave the
      parameter and its forwarding to `apiPost` in place (depends on 1).
      — DoD: description text updated; no behavior change beyond the string
      (the value was always going to be ignored server-side after task 1).
- [ ] 3. Update `internal/openapi/openapi.yaml`: mark the `user` property
      under `POST /api/v1/repos/sync`'s request body schema as
      `deprecated: true` with a short description noting it is ignored and
      the authenticated identity is always used (depends on 1).
      — DoD: `openapi.yaml` still parses/lints cleanly (whatever validation
      the repo's CI runs on this file, if any); property marked deprecated.
- [ ] 4. Add `internal/api/handlers_repos_test.go` covering the scenarios in
      `## Tests` below, following the `handlers_domains_test.go` pattern
      (`httptest.NewServer` stand-in for Backstage, `withUser` helper for
      injecting `auth.User` into the request context) (depends on 1).
      — DoD: new test file compiles and passes; no existing test's behavior
      changes.
- [ ] 5. Run `go fmt ./...`, `go vet ./...`, and `golangci-lint run` per
      `CLAUDE.md` conventions; fix any findings introduced by tasks 1-4
      (depends on 1-4).
      — DoD: all three commands exit clean on the touched files.

## Tests

- [ ] T1. `TestSyncReposIgnoresBodyUserOverridesWithAuthenticated`: POST
      `/api/v1/repos/sync` with body `{"team":"labs","user":"someone-else"}`
      and `auth.User{ID:"real-caller", Groups:[]string{"labs"}}` in context;
      assert the upstream Backstage request's `user` query parameter equals
      `real-caller`.
- [ ] T2. `TestSyncReposDefaultsToAuthenticatedUserWhenBodyOmitsUser`: same as
      T1 but body is `{"team":"labs"}` (no `user` key); assert the same
      `real-caller` value reaches Backstage — pins today's no-body-user
      behavior so it does not regress.
- [ ] T3. `TestSyncReposNilUserUnauthorized`: POST with no user in context;
      assert `401 Unauthorized` and zero upstream Backstage calls.
- [ ] T4. `TestSyncReposCrossTenantForbidden`: POST with
      `auth.User{ID:"u1", Groups:[]string{"labs"}}` in context and
      `"team":"other-team"` in the body; assert `403 Forbidden` and zero
      upstream Backstage calls (pins existing `HasTenantAccess` behavior,
      now reachable unconditionally since `user` can no longer be nil at
      that point).
- [ ] T5. `TestSyncReposMissingTeamBadRequest`: POST with an empty/absent
      `team` field; assert `400 Bad Request` and zero upstream calls (pins
      existing behavior, unchanged by this proposal).

## Rollback

Revert the commit(s) touching `internal/api/handlers_repos.go`,
`internal/mcp/server.go`, `internal/openapi/openapi.yaml`, and
`internal/api/handlers_repos_test.go`. There is no data migration, persisted
state, or external system change (Backstage's plugin is untouched), so a
plain `git revert` fully restores prior behavior with no follow-up cleanup
required. If only the handler needs to be rolled back urgently (e.g. it
turns out some deployment truly depends on nil-user syncing), the minimal
revert is task 1 alone; tasks 2-4 are independently safe to keep or drop.
