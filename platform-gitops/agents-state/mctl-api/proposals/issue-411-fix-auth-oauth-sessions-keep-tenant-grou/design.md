# Design: issue-411-fix-auth-oauth-sessions-keep-tenant-grou

## Current state

Group resolution exists twice in `internal/auth`, with different error handling.

- `OAuthServer.ResolveGroups` (`internal/auth/oauth_server.go:637-650`) appends
  `"admins"` when `GitHubValidator.IsAdmin(login)` is true, then appends
  `TenantResolver.GetTenantsForUser(login)` — and swallows the error with
  `if err == nil`, so a resolver failure is indistinguishable from "no tenants".
- The free function `resolveGroups` (`internal/auth/oidc.go:619-637`) does the
  same but logs `"failed to resolve tenant memberships"` on error. This is the
  one used by the raw GitHub-token branch of `Middleware`
  (`internal/auth/oidc.go:560`), which therefore re-resolves on *every request*.

`TenantResolver` is a one-method interface (`internal/auth/oidc.go:161-163`),
satisfied in production by `*gitops.Reader` (wired at `cmd/api/main.go:144`,
`oauthServer.TenantResolver = gitReader`). `Reader.GetTenantsForUser`
(`internal/gitops/reader.go:758`) calls `ListTenants` (`:536`), which reads
`platform-gitops/tenants` from the local checkout under `RLock` and per tenant
calls `Tenant.UserNamespaces(login)` (`:109`) — case-insensitive membership,
compound `<tenant>-<team>` names for multi-team tenants. This is local
filesystem plus YAML parsing, no network. Notably, a missing tenants directory
returns `(nil, nil)`, not an error (`:544`). The checkout is refreshed by
`RefreshLoop` every 60s (`cmd/api/main.go:765`) and `Reader.LastSync()` (`:773`)
records the last success; `/readyz`'s gitops check already uses
`LastSync().IsZero()` as its "never synced" signal (`cmd/api/main.go:673`).

The OAuth session lifecycle freezes that one resolution:

1. `handleOAuthGitHubCallback` resolves groups once
   (`internal/api/oauth_handlers.go:262`) and puts them in the auth code via
   `IssueCode(login, clientID, redirectURI, codeChallenge, groups)`
   (`internal/auth/oauth_server.go`, `authCodeEntry.Groups`).
2. `ExchangeCode` issues both tokens from `entry.Groups`:
   `IssueJWT(entry.Login, entry.Groups)` and
   `IssueRefreshToken(entry.Login, entry.Groups, clientID)`.
3. `IssueRefreshToken` persists them — `RefreshStore.Insert(token, login,
   clientID, groups, expiresAt)`, or `refreshTokenEntry.Groups` in the
   in-memory `refreshTokenStore`.
4. `RefreshAccessToken` re-issues from the stored value on both paths: the
   store path does `login, groups, err := s.RefreshStore.Rotate(...)` then
   `IssueJWT(login, groups)`; the in-memory path does
   `IssueJWT(entry.Login, entry.Groups)` and
   `IssueRefreshToken(entry.Login, entry.Groups, clientID)`.
5. `refreshstore.PostgresStore.rotateTx` (`internal/auth/refreshstore/postgres.go:303-323`)
   unmarshals the predecessor's `groups` and marshals the *same* slice into the
   successor row. So the snapshot survives every rotation and the 30-day
   refresh TTL keeps sliding (`RefreshTokenTTL`, default `30*24*time.Hour`).
6. `ValidateJWT` (`internal/auth/oauth_server.go:935-942`) returns
   `NewGitHubUser(payload.Subject, payload.Groups)`, and authorization reads
   that slice directly: `User.IsAdmin` looks for `"admins"` and
   `User.HasTenantAccess` compares tenant names (`internal/auth/oidc.go:119-139`),
   as used by roughly every handler in `internal/api`.

Net effect: for a JWT session the groups claim is authoritative, is never
recomputed, and lives as long as the refresh chain.

## Proposed solution

Make resolution — not storage — the source of truth for groups on every local
OAuth path, with one shared, error-returning resolver and one explicit
degradation policy.

### 1. A checked resolver in `internal/auth/oauth_server.go`

Add to `OAuthServer`:

```go
// GroupsMaxStaleness, when > 0, enables strict mode: a checkout whose last
// successful sync is older than this counts as a failed resolution. 0 (the
// default) disables it; a stale checkout is then used and alerted on.
GroupsMaxStaleness time.Duration
// GroupsDegradedGrace bounds how long stored groups may stand in for a
// failed resolution. 0 selects AccessTokenTTL.
GroupsDegradedGrace time.Duration
// GroupsCacheTTL memoizes a successful resolution per login. 0 selects
// defaultGroupsCacheTTL (30s).
GroupsCacheTTL time.Duration
```

and a method:

```go
// resolveGroupsChecked resolves groups for login, reporting failure instead of
// hiding it. "admins" always comes from GitHubValidator.IsAdmin, which is
// in-process configuration and cannot fail.
func (s *OAuthServer) resolveGroupsChecked(login string) ([]string, error)
```

Rules, in order:

- `admins` is computed from `IsAdmin(login)` unconditionally. It is never taken
  from a stored or claimed value, which satisfies the issue's "the `admins`
  group must follow the same rule" without any fallback complexity.
- `TenantResolver == nil` returns `(nil, errResolverNotConfigured)`. Callers
  treat that sentinel as "feature off" and keep the stored/claimed groups
  verbatim. This preserves behaviour for deployments and unit tests that
  construct an `OAuthServer` with no resolver
  (`internal/auth/oauth_server_test.go` does exactly this).
- Freshness gate: this applies if the resolver also satisfies
  `interface{ LastSync() time.Time }`, which `*gitops.Reader` does
  (`reader.go:773`, updated on every successful 60s fetch at `reader.go:358`).
  - A **zero** `LastSync` means the checkout was never synced. That is a
    failure. It stops the `(nil, nil)` of an absent checkout (`reader.go:544`)
    from being read as "this user has no tenants" and silently stripping every
    session's access on a pod whose first clone failed.
  - A **stale but present** checkout (`time.Since(LastSync()) >
    groupsStaleWarnAfter`, a package constant of 15m) is **not** a failure. The
    resolution succeeds from the checkout as it is. A rate-limited `slog.Warn`
    logs at most once per minute with the sync age, and a Prometheus gauge
    `mctl_api_gitops_last_sync_age_seconds` is set, registered the way
    `internal/auth/federation.go` registers its metrics.
  - Strict mode is opt-in: only when `GroupsMaxStaleness > 0`
    (`OAUTH_GROUPS_MAX_STALENESS`, default unset) is a checkout older than that
    treated as a failure.
  - A resolver that cannot report sync state (test doubles, future
    implementations) skips the gate.

  Why stale is not a failure by default (reviewer amendment 2026-09-27): `LastSync` stops advancing when
  the fetch fails, and the commonest cause is GitHub being down. gitops lives
  on GitHub, so a membership removal cannot be pushed then either. Failing
  closed after `15m + grace` would lock every tenant user out, admins aside,
  about 75 minutes into any GitHub incident, with no security gain. The other
  cause, a fetch broken only on mctl-api's side (expired PAT, revoked deploy
  key) while GitHub accepts pushes, is covered by alerting on the gauge. Strict
  mode stays available for operators who prefer lockout to lag.
- `GetTenantsForUser` error is a failure, wrapped with `fmt.Errorf("resolve
  tenant groups for %q: %w", login, err)` per the repo's error convention.
- On success, record `s.lastResolveOK` (an `atomic.Int64` of Unix nanos) and
  memoize the result for `GroupsCacheTTL` in a small mutex-guarded
  `map[string]groupsCacheEntry`, mirroring the existing `GitHubValidator.cache`
  pattern (`internal/auth/github.go:36-51`). Expired entries are evicted
  opportunistically on write, so the map cannot grow without bound (reviewer amendment 2026-09-27). `lastResolveOK` is seeded at
  `NewOAuthServer` with the process start, so a pod that boots with a broken
  gitops still has a bounded grace window rather than an open-ended one.

A second helper applies the policy so the three call sites stay one-liners:

```go
// groupsForSession returns the groups a token should carry for login, given
// the groups previously recorded for that session.
func (s *OAuthServer) groupsForSession(login string, stored []string) []string
```

- resolution succeeded: return the resolved groups.
- `errResolverNotConfigured`: return `stored` unchanged.
- other failure, and `time.Since(lastResolveOK) <= grace`: return
  `withAdmins(login, tenantsOnly(stored))` — stored tenant groups, `admins`
  recomputed. Log `slog.Warn("oauth: group resolution degraded; using stored
  tenant groups", "user", login, "error", err)`.
- other failure, beyond grace: return `withAdmins(login, nil)` — fail closed to
  admins-only. Log `slog.Warn("oauth: group resolution unavailable beyond
  grace; dropping tenant groups", ...)`.

Why last-known-then-fail-closed rather than fail-closed immediately: a single
failed `git fetch` is an ordinary event (`Reader.refresh` logs it and keeps the
previous checkout), and turning every transient failure into a platform-wide
loss of tenant access would be a self-inflicted outage — including for flows
that have nothing to do with membership changes. Why bounded rather than
last-known forever: the issue's explicit requirement is that "removal must not
be defeated by a resolver outage lasting longer than one access-token TTL", and
an unbounded fallback is exactly today's bug with extra steps. The window is
measured from the last *successful* resolution anywhere in the process, not
per-session, because the failure being tolerated is a property of the resolver.
Why not refuse the refresh: that signs the user out, and the re-login path would
fail on the same resolver, so the user could not recover until gitops did — a
strictly worse outcome than a session that keeps working with admins-only
groups and heals on its next exchange.

`ResolveGroups` stays as the exported wrapper it is today (it is called from
`internal/api/oauth_handlers.go:262`) and is reimplemented over
`resolveGroupsChecked`, ignoring the error, so the callback keeps its current
"best effort at login" behaviour and no handler signature changes.

### 2. Both refresh paths

In `RefreshAccessToken`, the store path becomes
`groups := s.groupsForSession(login, storedGroups)` after `Rotate` returns, and
`IssueJWT(login, groups)`. The in-memory path becomes
`groups := s.groupsForSession(entry.Login, entry.Groups)` used for both
`IssueJWT` and the successor `IssueRefreshToken`, so the two paths agree. All
rotation mechanics — `deriveSuccessorRefreshToken`, reuse detection and family
revocation, `ErrClientMismatch`, `ErrServerError` mapping — are untouched.

Stored groups deliberately remain the first-login snapshot on the store path:
`refreshstore.Store.Rotate` has no parameter for new groups and adding one
would change the interface, the `PostgresStore` implementation and the
in-flight-rotation grace path. Because the fallback is bounded to one
access-token TTL, the snapshot's staleness is no longer load-bearing. On the
in-memory path the successor row naturally records the freshly resolved groups,
since `IssueRefreshToken` is called with them; the asymmetry is harmless and is
documented in a comment.

### 3. `ValidateJWT`

`ValidateJWT` returns `NewGitHubUser(payload.Subject, s.groupsForSession(
payload.Subject, payload.Groups))`. This is what actually fixes the reported
symptom: the `karabu` failure was a *same-session* one, and a fix confined to
the refresh paths leaves it broken for up to a full access-token TTL. The
precedent is already in the tree — the raw GitHub-token branch of `Middleware`
re-resolves on every request (`internal/auth/oidc.go:560`) against the same
local checkout — so per-request resolution is already accepted cost for one
class of caller. The `GroupsCacheTTL` memo (default 30s) bounds the added work
on the `/mcp` hot path to at most one tenants-directory walk per login per 30s
and caps added staleness at 30s, versus the 1h–30d staleness today.

### 4. Wiring and configuration

`cmd/api/main.go`, next to the existing `oauthServer.AccessTokenTTL` /
`RefreshTokenTTL` assignments (around `:144`):

```go
// Unset/0 = strict mode off: a stale checkout is used and alerted on, not failed (reviewer amendment 2026-09-27).
oauthServer.GroupsMaxStaleness = parseDuration(os.Getenv("OAUTH_GROUPS_MAX_STALENESS"), 0)
oauthServer.GroupsCacheTTL = parseDuration(os.Getenv("OAUTH_GROUPS_CACHE_TTL"), 30*time.Second)
// GroupsDegradedGrace left at 0 → AccessTokenTTL, the bound the issue names.
```

Both use the existing `parseDuration` helper, so an unset or malformed value
falls back rather than failing boot. Defaults are chosen so no operator action
is needed; the Helm chart needs no change unless an operator overrides them.

## Alternatives

1. **One-line fix: `IssueJWT(login, s.ResolveGroups(login))` in both refresh
   paths.** This is exactly what the issue proposes and is the smallest
   possible change, but `ResolveGroups` swallows the resolver error and
   `GetTenantsForUser` returns `(nil, nil)` for a missing checkout
   (`internal/gitops/reader.go:544`). On a pod whose initial clone failed —
   which `RefreshLoop` only logs (`reader.go:215`) — every refresh would mint a
   token with no tenant groups and no error anywhere, converting a gitops blip
   into a platform-wide authorization outage with no fallback and no signal.
   Dropped in favour of the same change routed through an error-returning
   resolver with an explicit policy. It remains the behaviour of the checked
   resolver's happy path, so the spirit of the issue's proposal is kept.

2. **Extend `refreshstore.Store.Rotate` to write freshly resolved groups into
   the successor row.** This would make the stored groups a true
   last-known-good value and would make the fallback meaningful for longer.
   Dropped: it changes an interface with a live PostgreSQL implementation
   including an in-flight-rotation grace lookup
   (`internal/auth/refreshstore/postgres.go:230-265`), for a value that is only
   consulted inside a one-hour degraded window. It is the natural follow-up if
   the grace window is ever widened.

3. **Cap staleness by shortening `OAUTH_TOKEN_TTL` only, with no
   re-resolution.** Rejected because it does not fix anything: the groups claim
   is regenerated from the same frozen store on each refresh, so a shorter
   access token just rotates the stale claim more often, while raising token
   traffic. It also cannot fix revocation, since the stale value never changes.

4. **Change `gitops.Reader.ListTenants` to return an error when the tenants
   directory is absent.** Cleaner in the abstract, and it would make the
   freshness gate unnecessary. Dropped for this change because `ListTenants` has
   many callers (`internal/api/handlers_read.go`, `gitopsReady` at
   `cmd/api/main.go:673`, tenant handlers) and flipping a `(nil, nil)` to an
   error is a cross-cutting behaviour change that deserves its own issue.
   Recorded as an open question.

## Platform impact

- **Migrations:** none. No schema change to `oauth_refresh_tokens`, no change to
  the `refreshstore.Store` or `clientstore.Store` interfaces, no new MCP tool
  (so the `server_test.go` tool-count expectation is unaffected).
- **Backward compatibility:** JWT format is unchanged — the `groups` claim is
  still emitted, it simply stops being the authority on validate. Existing
  access tokens, refresh tokens and dynamic registrations keep working; no
  client re-registration or re-login. A deployment with no `TenantResolver`
  (`TenantResolver == nil`) behaves bit-for-bit as today, which is what keeps
  the existing `internal/auth` unit tests meaningful.
- **Resource impact:** the refresh path gains one memoized tenants-directory
  walk; refreshes are at most hourly per session, so this is noise. The validate
  path gains at most one walk per login per `GroupsCacheTTL` (30s) — the same
  work the GitHub-token path already does per request, and bounded by the memo.
  `ListTenants` takes the reader's `RLock`, which does not contend with other
  readers and is only excluded during the 60s-interval refresh.
- **Risks and mitigations:**
  - *Mass loss of access if the resolver silently answers empty.* Mitigated by
    the never-synced check, and by the fact that a failure takes the
    stored-groups path rather than the empty path.
  - *Mass loss of access during a GitHub outage.* Avoided by default: a stale
    but present checkout keeps answering, and only the opt-in strict mode turns
    staleness into a failure (reviewer amendment 2026-09-27).
  - *Revocation lag while mctl-api's own fetch is broken.* Bounded by how
    fast the operator reacts to the `mctl_api_gitops_last_sync_age_seconds`
    alert. This is accepted in exchange for not locking users out; strict mode
    removes the lag at the cost of lockout.
  - *Revocation lag.* Bounded by `GroupsCacheTTL` (30s) in the healthy case and
    by `GroupsDegradedGrace` (one access-token TTL, default 1h) in the degraded
    case. Both are strict improvements on the current unbounded behaviour.
  - *Admin lockout.* `admins` derives from `IsAdmin`, in-process configuration
    that cannot fail, so admins keep working even in the fail-closed state —
    which is also what makes fail-closed operable during an outage.
  - *Hot-path regression on `/mcp`.* Mitigated by the memo; if measurements
    disagree, setting `OAUTH_GROUPS_CACHE_TTL` higher, or reverting just the
    `ValidateJWT` change, leaves the issue's acceptance criteria satisfied.
  - *Log noise during an outage.* Degraded and fail-closed paths log at `warn`
    with the login and reason; they are per refresh/validate-miss, not per
    request, because of the memo.
