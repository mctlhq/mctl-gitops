# Tasks: issue-411-fix-auth-oauth-sessions-keep-tenant-grou

- [ ] 1. Add the checked resolver to `internal/auth/oauth_server.go`: new
  `OAuthServer` fields `GroupsMaxStaleness`, `GroupsDegradedGrace`,
  `GroupsCacheTTL`, package constants `groupsStaleWarnAfter = 15*time.Minute`
  and `defaultGroupsCacheTTL = 30*time.Second` (no default for
  `GroupsMaxStaleness`; 0 = strict mode off) (reviewer amendment 2026-09-27), sentinel
  `errResolverNotConfigured`, and `resolveGroupsChecked(login string) ([]string, error)`
  that always computes `admins` from `GitHubValidator.IsAdmin`, returns the
  sentinel when `TenantResolver == nil`, treats a `GetTenantsForUser` error as a
  failure, and fails when the resolver satisfies
  `interface{ LastSync() time.Time }` and reports a **zero** sync. A stale
  but present checkout succeeds, with a rate-limited warn. It fails only in
  strict mode, `GroupsMaxStaleness > 0`, and that check runs first and
  independently of the fixed 15m warn threshold (reviewer amendment
  2026-09-27, round 2). The sync-age metric is a scrape-time `GaugeFunc`
  (`time.Since(LastSync())`, `-1` while never synced), registered once in
  `cmd/api/main.go`. It is not written from the stale branch. (reviewer amendment 2026-09-27).
  — DoD: unit-testable method exists with doc comments explaining each rule;
  `go vet` and `golangci-lint` clean; no call sites changed yet.

- [ ] 2. Add the degradation policy helper `groupsForSession(login string, stored []string) []string`
  plus `lastResolveOK atomic.Int64` (seeded to now in `NewOAuthServer`), the
  per-login memo (`GroupsCacheTTL`, mutex-guarded map modelled on
  `GitHubValidator.cache` in `internal/auth/github.go`), and the
  `withAdmins` / `tenantsOnly` helpers (depends on 1)
  — DoD: sentinel returns `stored` unchanged; failure inside the grace window
  returns stored tenant groups with `admins` recomputed and logs `slog.Warn`;
  failure beyond the grace window returns admins-only and logs `slog.Warn`;
  grace defaults to `AccessTokenTTL` when `GroupsDegradedGrace` is 0.

- [ ] 3. Reimplement the exported `OAuthServer.ResolveGroups` over
  `resolveGroupsChecked`, discarding the error (depends on 1)
  — DoD: signature unchanged, `internal/api/oauth_handlers.go:262` compiles
  untouched, callback behaviour at login is unchanged.

- [ ] 4. Re-resolve in `RefreshAccessToken`, both paths (depends on 2)
  — DoD: the `RefreshStore` path issues `IssueJWT(login, s.groupsForSession(login, storedGroups))`;
  the in-memory path uses `s.groupsForSession(entry.Login, entry.Groups)` for
  both `IssueJWT` and the successor `IssueRefreshToken`; rotation,
  `deriveSuccessorRefreshToken`, reuse detection, family revocation,
  `ErrClientMismatch` and `ErrServerError` mapping are byte-for-byte unchanged;
  a comment records that the stored groups stay the first-login snapshot on the
  store path because `refreshstore.Store.Rotate` takes no groups.

- [ ] 5. Re-resolve in `ValidateJWT`: return
  `NewGitHubUser(payload.Subject, s.groupsForSession(payload.Subject, payload.Groups))`
  (depends on 2) — DoD: JWT verification (signature, issuer, expiry) unchanged;
  a comment states that the `groups` claim is retained for compatibility and as
  the degraded fallback, not as the authority.

- [ ] 6. Wire configuration in `cmd/api/main.go` beside the existing
  `oauthServer.AccessTokenTTL` / `RefreshTokenTTL` assignments (depends on 1)
  — DoD: `OAUTH_GROUPS_MAX_STALENESS` (default unset = strict mode off (reviewer amendment 2026-09-27)) and `OAUTH_GROUPS_CACHE_TTL`
  (default 30s) read via the existing `parseDuration`; `GroupsDegradedGrace`
  left at 0 so it follows `AccessTokenTTL`; an unset or malformed value falls
  back and never fails boot; the existing "OAuth 2.0 server enabled" `slog.Info`
  line gains the two resolved values.

- [ ] 7. Add an in-package `fakeRefreshStore` test double implementing
  `refreshstore.Store` (Insert / Rotate / RevokeFamily / GC) in a new
  `internal/auth/oauth_server_groups_test.go`, plus a `stubTenantResolver` with
  a settable membership map, a call counter, an injectable error, and an
  optional `LastSync()` (depends on 4)
  — DoD: exercises both refresh paths with no PostgreSQL dependency;
  `go test ./internal/auth/...` passes.

- [ ] 8. Document the behaviour: a `## Authorization group freshness` note in
  `README.md` (or `docs/` alongside `principals.md`) covering the two new env
  vars, the 30s healthy staleness cap, the degraded grace window, the
  fail-closed-to-admins-only end state, the stale-checkout behaviour (keeps
  answering and alerts via the gauge; strict mode is opt-in), and a suggested
  alert rule on `mctl_api_gitops_last_sync_age_seconds` (depends on 6)
  — DoD: an operator reading it can predict what happens to a live session when
  gitops is unreachable for two hours.

- [ ] 9. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run`, `go test ./...`
  and confirm the MCP tool count expectation in `internal/mcp/server_test.go` is
  untouched (depends on 5, 6, 7)
  — DoD: all green, no new lint findings, no tool-count edit in the diff.

## Tests

All new tests live in `internal/auth/oauth_server_groups_test.go` unless noted.
Every test in T1–T6 must fail if the stored-groups behaviour is restored (i.e.
if `IssueJWT` is fed the store's groups again) — assert on the JWT's groups via
`server.ValidateJWT` with `TenantResolver` temporarily detached, or by decoding
the payload directly, so the assertion targets the *issued* claim and not the
validate-time re-resolution.

- [ ] T1. `RefreshStore` path, grant direction: fake store holds
  `["acme"]`, resolver answers `["acme","karabu"]`; the refreshed access token
  carries `karabu`. Reproduces the reported `karabu` failure.
- [ ] T2. `RefreshStore` path, revoke direction: store holds
  `["acme","karabu"]`, resolver answers `["acme"]`; the refreshed access token
  does not carry `karabu`.
- [ ] T3. In-memory path, grant direction: same as T1 with
  `RefreshStore == nil` via `IssueRefreshToken` + `RefreshAccessToken`.
- [ ] T4. In-memory path, revoke direction: same as T2, and additionally the
  *successor* refresh token carries the re-resolved groups.
- [ ] T5. `admins` gained: `NewGitHubValidator([]string{"dmitrii"})` with stored
  groups lacking `admins`; the refreshed token carries `admins`.
- [ ] T6. `admins` lost: `NewGitHubValidator(nil)` with stored groups containing
  `admins`; the refreshed token does not carry `admins`.
- [ ] T7. Degraded within grace: resolver returns an error,
  `GroupsDegradedGrace = time.Hour`; the refreshed token carries the stored
  tenant groups and the recomputed `admins`, and the refresh still succeeds and
  still rotates.
- [ ] T8. Fail closed beyond grace: resolver returns an error,
  `GroupsDegradedGrace` set to a negative/tiny value (or `lastResolveOK` pushed
  back via the test-only setter); the refreshed token carries no tenant groups,
  retains `admins` when the login is an admin, and the refresh still succeeds.
- [ ] T9. Never-synced checkout is not "no tenants": resolver returns
  `(nil, nil)` and reports `LastSync()` zero; stored tenant groups survive
  (within grace) rather than being wiped.
- [ ] T9a. Stale-but-present checkout still answers (reviewer amendment 2026-09-27): `LastSync()` 2h
  old, `GroupsMaxStaleness` unset, resolver answers `["acme","karabu"]`; the
  token carries the resolved groups, `lastResolveOK` advances (no drift toward
  fail-closed), and the gauge reports ~7200s. Must fail if staleness is turned
  back into a failure by default.
- [ ] T9b. Strict mode: same as T9a with `GroupsMaxStaleness = 15*time.Minute`;
  the resolution is treated as failed and takes the degraded/fail-closed path.
  Second case: `GroupsMaxStaleness = 5*time.Minute` with `LastSync()` 10m old,
  below the 15m warn threshold, also fails. The stricter operator setting wins.
- [ ] T9c. Memo eviction: after `GroupsCacheTTL` passes, writes for other logins
  evict the expired entry (map size stays bounded).
- [ ] T9d. Gauge tracks recovery: a scrape of
  `mctl_api_gitops_last_sync_age_seconds` reports ~7200 with `LastSync()` 2h old
  and ~0 right after `LastSync()` is advanced, with no auth traffic in between.
  It reports -1 while `LastSync()` is zero. Must fail if the metric is written
  only on the stale branch.
- [ ] T10. `TenantResolver == nil` back-compat: stored groups pass through
  unchanged on refresh and on `ValidateJWT`; the existing
  `internal/auth/oauth_server_test.go` tests keep passing untouched.
- [ ] T11. `ValidateJWT` re-resolves: a token minted with `["acme"]` validates
  to a user with `["acme","karabu"]` after the resolver's membership map changes,
  and a token minted with `["acme","karabu"]` validates without `karabu` after
  removal.
- [ ] T12. Memo bounds resolver calls: with `GroupsCacheTTL = time.Minute`, N
  successive `ValidateJWT` calls for the same login produce exactly one
  `GetTenantsForUser` call; two distinct logins produce two.
- [ ] T13. Rotation regression: the existing
  `TestOAuthServerRefreshRotatesToken` and `TestOAuthServerRevokeRefreshToken`
  still pass unmodified, and a replayed rotated-out token is still rejected on
  the fake-store path (reuse detection untouched).
- [ ] T14. `go test ./...` at repo root, plus `cd e2e && go test -v` if an OAuth
  environment is available; no e2e change is expected.

## Rollback

Every change is confined to `internal/auth/oauth_server.go`, one new test file,
a few lines in `cmd/api/main.go`, and documentation. There is no migration, no
schema change, no interface change and no token-format change, so rollback is a
revert plus a redeploy of the previous image tag
(`mctl_rollback_service team=platform service=mctl-api target_tag=<previous>`);
existing access tokens, refresh chains and client registrations keep working
across the revert in both directions, because the `groups` claim is still
written on both sides.

Two cheaper mitigations before reverting, in escalation order:

1. If re-resolution is suspected of causing false denials, raise
   `OAUTH_GROUPS_CACHE_TTL` (e.g. `1h`) to reduce resolver dependence on the
   validate path, and unset `OAUTH_GROUPS_MAX_STALENESS` (strict mode off, the
   default) if it was enabled and the gitops checkout is known to be lagging for
   an unrelated reason.
2. If the `ValidateJWT` change alone is the problem, revert only task 5 — the
   refresh-path fix and the issue's acceptance criteria stand on their own.

Restoring the old behaviour for a single stuck session never requires a
rollback: the user signs out and back in, which resolves groups at the callback
as it does today.
