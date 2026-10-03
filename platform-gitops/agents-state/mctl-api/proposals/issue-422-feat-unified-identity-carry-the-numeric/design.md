# Design: issue-422-feat-unified-identity-carry-the-numeric

## Current state

All line numbers below were re-read against `main` at `7e5c1c4` (the design
record's 2026-09-24 numbers had drifted; `oauth_server.go` is now 1631 lines).

**Minting.** `handleOAuthGitHubCallback`
(`internal/api/oauth_handlers.go:208-286`) exchanges the GitHub code for a
GitHub token and then calls

```go
login, err := o.GitHubValidator.Validate(r.Context(), ghToken)   // :254
groups := o.ResolveGroups(login)                                  // :262
mctlCode, err := o.IssueCode(login, pending.ClientID, pending.RedirectURI,
    pending.CodeChallenge, groups)                                // :265
```

`GitHubValidator.Validate` (`internal/auth/github.go:58-61`) is a thin
wrapper that *discards* the numeric id returned by `ValidateIdentity`
(`github.go:66-85`), which already fetches `{login, id}` from
`GET https://api.github.com/user` (`fetchUser`, `github.go:97-129`) and
caches both for 5 minutes in `githubUserInfo` (`github.go:29-33`). So the id
is free at this point and thrown away.

`IssueCode` (`oauth_server.go:1247-1262`) stores an `authCodeEntry`
(`oauth_server.go:1508-1515`: `Login`, `Groups`, `ClientID`, `RedirectURI`,
`CodeChallenge`, `CreatedAt`). `ExchangeCode` (`:1266-1290`) consumes it and
calls `IssueJWT(entry.Login, entry.Groups)` plus
`IssueRefreshToken(entry.Login, entry.Groups, clientID)`.

`IssueJWT` (`:1293-1307`) builds `jwtPayload` (`:1453-1459`):

```go
type jwtPayload struct {
    Issuer    string   `json:"iss"`
    Subject   string   `json:"sub"`
    Groups    []string `json:"groups"`
    IssuedAt  int64    `json:"iat"`
    ExpiresAt int64    `json:"exp"`
}
```

signed HS256 by `signJWT` (`:1461-1472`). There is no identity claim beyond
`sub` = the GitHub login.

**Validating.** `ValidateJWT` (`:1421-1434`) verifies signature, issuer and
expiry via `verifyJWT` (`:1474-1501`) and returns
`NewGitHubUser(payload.Subject, s.groupsForSession(payload.Subject, payload.Groups))`.
`NewGitHubUser` (`internal/auth/oidc.go:108-111`) sets `githubLogin: true`
and leaves the unexported `githubID` (`oidc.go:86`) at zero.

**Identity.** `User.Identity()` (`internal/auth/principal.go:109-131`)
already encodes the rule we need:

```go
case u.githubLogin && u.githubID > 0:
    return Identity{Provider: ProviderGitHub, Subject: strconv.FormatInt(u.githubID, 10),
        Display: u.ID, Kind: KindHuman}, true
case u.githubLogin:
    return Identity{Provider: ProviderGitHub, Display: u.ID, Kind: KindHuman}, true
```

The GitHub PAT path already populates `githubID`
(`oidc.go:594-602` on the pre-registry chain, `userFromVerified`
`oidc.go:751-758` on the registry chain). Only the local OAuth JWT path
cannot, because the token does not carry the id.

**Federation provider.** `localOAuthProvider.Verify`
(`internal/auth/provider_localoauth.go:49-58`) hand-builds the identity and
hard-codes the login-only shape:

```go
Identity: Identity{Provider: ProviderGitHub, Display: u.ID, Kind: KindHuman}
```

`Registry` then re-checks the provider contract (namespace equals `Name()`,
`Subject` non-empty unless `GitHubLoginOnly()`, valid `Kind`) — documented in
`docs/federation.md:74-90`. `userFromVerified` (`oidc.go:751-758`) parses
`Subject` back into `githubID`, so a `Subject`-bearing identity from this
provider already round-trips correctly with no change to that function.

**Resolution.** `Resolver.resolve` (`internal/principals/resolver.go:186-204`):

```go
if !id.GitHubLoginOnly() { return r.store.Provision(ctx, id) }
p, err := r.store.ResolveGitHubLogin(ctx, id.Display)
if err == nil || !errors.Is(err, ErrNotFound) { return p, err }
gid, err := r.lookup(ctx, id.Display)   // GitHubIDLookup → api.github.com
return r.store.Provision(ctx, auth.Identity{Provider: ..., Subject: strconv.FormatInt(gid,10), ...})
```

`ResolveGitHubLogin` (`internal/principals/store.go:275-283`) matches
`lower(x.display)` among non-revoked `provider='github'` rows —
login-spelling matching, the thing the numeric id exists to avoid.
`Provision` (`store.go:170+`) keys on `(provider, issuer, subject)` and
refreshes `display` on hit, which is exactly the canonical path.

**Refresh.** `IssueRefreshToken` (`:1310-1336`) writes either
`refreshstore.Store.Insert(token, login, clientID, groups, expiresAt)` or an
in-memory `refreshTokenEntry` (`:1524-1530`). `RefreshAccessToken`
(`:1339-1401`) gets `(login, groups)` back from `Rotate`
(`internal/auth/refreshstore/store.go:57`) or from the in-memory entry, and
calls `IssueJWT`. Neither store has a column or field for a numeric id.

**Metrics precedent.** `prometheus.NewCounter` + `init()` with
`MustRegister`, as in `internal/principals/resolver.go:52-57` and
`internal/auth/federation.go:318-355`. `docs/federation.md:246-258` holds the
metrics table.

## Proposed solution

One optional claim, threaded from the single place the id is proven to the
single place identity is derived.

### 1. `ghid` on the payload

`internal/auth/oauth_server.go`:

```go
type jwtPayload struct {
    Issuer    string   `json:"iss"`
    Subject   string   `json:"sub"`
    Groups    []string `json:"groups"`
    IssuedAt  int64    `json:"iat"`
    ExpiresAt int64    `json:"exp"`
    // GitHubID is the numeric GitHub user id of Subject, when the mint path
    // proved it (mctl-api#422). Optional: omitted on tokens minted before
    // this change and on refreshes whose family has no recorded id.
    GitHubID  int64    `json:"ghid,omitempty"`
}
```

`omitempty` gives byte-identical payloads to today whenever the id is
unknown, so no existing test fixture or client parser sees a new key.

### 2. Thread the id through minting

- `internal/api/oauth_handlers.go:254`:
  `login, ghID, err := o.GitHubValidator.ValidateIdentity(r.Context(), ghToken)`.
  Failure handling is unchanged (502, same message).
- `IssueCode(login string, githubID int64, clientID, redirectURI, codeChallenge string, groups []string)`
  stores `GitHubID` on `authCodeEntry`.
- `ExchangeCode` passes `entry.GitHubID` to `IssueJWT` and
  `IssueRefreshToken`.
- `IssueJWT(login string, githubID int64, groups []string)` sets
  `GitHubID: githubID`.
- `IssueRefreshToken(login string, githubID int64, groups []string, clientID string)`
  records `GitHubID` on the in-memory `refreshTokenEntry` **and** passes it
  to the persistent store (owner decision 2026-09-30, see "Refresh store"
  below). `RefreshAccessToken` passes the recovered id to `IssueJWT` and to
  the successor on both paths.

### Refresh store: persist the id (owner decision 2026-09-30)

Production runs the Postgres `refreshstore` (mctl-api logs
`oauth refresh token store initialized` at boot), with `AccessTokenTTL` 1h
and `RefreshTokenTTL` 30d (`oauth_server.go:767-768`). If only the in-memory
path carried the id, every production token after the first refresh — almost
all traffic — would lose `ghid`. So the id is persisted with the refresh-token
family:

- **Schema** (`internal/auth/refreshstore/postgres.go`, the idempotent
  `schema` constant): append
  `ALTER TABLE oauth_refresh_tokens ADD COLUMN IF NOT EXISTS github_id BIGINT;`
  Nullable, no default, no backfill, no index (the column is only ever read
  together with the row already fetched by `token_hash`).
- **Interface** (`internal/auth/refreshstore/store.go`):
  - `Insert(rawToken, login string, githubID int64, clientID string, groups []string, expiresAt time.Time) error`
    writes `NULL` when `githubID <= 0`, otherwise the value;
  - `Rotate(...)` returns `(login string, githubID int64, groups []string, err error)`.
    The main path reads `github_id` from the presented row (`NULL` → `0`)
    and **copies it into the successor row's INSERT**; the lost-response
    grace path returns the already-inserted child row's `github_id`. Every
    other error path returns `0`.
- **Callers:** `IssueRefreshToken` passes `githubID` to `Insert`;
  `RefreshAccessToken` takes the id returned by `Rotate` and passes it to
  `IssueJWT`. A `0` means "unknown" and takes the existing login-only branch.
- **Fakes:** every in-repo `Store` implementation used by tests (at least
  `internal/auth/oauth_server_groups_test.go`) gets the same signature.

Families created before the deploy carry `NULL` and stay login-only until the
user logs in again (bounded by the 30-day refresh TTL), which is also when
`oauth_jwt_without_github_id_total` is expected to decay to zero.

Explicit new parameters rather than sibling methods: every call site (one
production site, ~15 test sites) becomes a compile error until it has been
considered, which is also what makes the mutation-verified regression test in
`tasks.md` meaningful.

A non-positive id is treated as absent everywhere (GitHub ids start at 1),
matching the existing `u.githubID > 0` guard in `User.Identity()`.

### 3. Derive the identity, do not re-invent it

`ValidateJWT` sets the id on the user it already builds:

```go
u := NewGitHubUser(payload.Subject, s.groupsForSession(payload.Subject, payload.Groups))
if payload.GitHubID > 0 {
    u.githubID = payload.GitHubID
} else {
    oauthJWTWithoutGitHubID.Inc()
}
return u, nil
```

Same package, so the unexported field stays unexported — the invariant
`docs/federation.md:92-98` states (discriminators set only inside package
`auth`) is preserved; no new exported setter.

`localOAuthProvider.Verify` stops hand-building the identity and asks the
`*User` for it, so the login/id mapping lives in exactly one place
(`User.Identity()`):

```go
id, ok := u.Identity()
if !ok || id.Provider != ProviderGitHub {
    return nil, fmt.Errorf("local oauth: unexpected identity for %q", u.ID)
}
return &Verified{Identity: id, Claims: Claims{Groups: u.Groups}}, nil
```

The defensive provider check keeps the declared-namespace guarantee explicit
(the comment on `Name()` in `provider_localoauth.go:30-36`) instead of
trusting `Identity()` to stay GitHub-shaped forever. Both shapes it can now
return satisfy the registry contract: with `ghid`, `Subject` is non-empty;
without it, `GitHubLoginOnly()` is true.

Because both the registry chain and the retained pre-registry chain
(`oidc.go:567-577`) go through `ValidateJWT`, this single change covers both,
and `MCTL_FEDERATION_DISABLED` parity is preserved for free.

No change is needed in `internal/principals`: a `Subject`-bearing identity
takes the `!id.GitHubLoginOnly()` branch and goes straight to
`Store.Provision` for `(github, <id>)`, which is the acceptance criterion.
The resolver cache key also becomes the canonical
`github||<id>` instead of `github-login|<login>`
(`resolver.go:118-123`), which is a small correctness win: the cache entry no
longer keys on a renameable string.

### 4. Metric

In `internal/auth` (next to the OAuth server, registered in `init()` like
`federation.go:318-355`):

```go
var oauthJWTWithoutGitHubID = prometheus.NewCounter(prometheus.CounterOpts{
    Name: "oauth_jwt_without_github_id_total",
    Help: "Local OAuth JWT validations that carried no ghid claim and resolved through the login-only path.",
})
```

Unlabelled: the only dimension that would matter (login) is unbounded
cardinality and already visible in logs. Incremented in `ValidateJWT`, i.e.
once per authenticated request, which is the operational question being asked
("is anything still using pre-change tokens?"). Documented as such.

### 5. Docs

`docs/federation.md`:

- new subsection under the local-OAuth provider description: the `ghid`
  claim, `sub` still the login, `omitempty`, and that a token without `ghid`
  keeps resolving through the login-only path;
- new row in the metrics table (`:246-258`) for
  `oauth_jwt_without_github_id_total`, with the per-validation caveat;
- the `oauth_refresh_tokens.github_id` column: refreshed tokens keep `ghid`,
  and families created before the change stay login-only (`NULL`) until the
  next login, at most 30 days;
- remove "Carrying the numeric GitHub id into local OAuth JWTs (slice B)"
  from the not-covered list (`:280`), leaving slices C and D.

## Alternatives

1. **Leave the token alone; let the resolver find the id (status quo).**
   Every local-OAuth request keeps depending on login spelling: one database
   query on the happy path (`ResolveGitHubLogin`) and an `api.github.com`
   round-trip for any login the store has never seen, inside the 3 s
   `ResolveTimeout` on the authentication path
   (`internal/principals/resolver.go:41`). It also means a renamed-then-reused
   login can be matched to the wrong principal, which is precisely what
   mctl-api#373 keyed principals on the numeric id to prevent. Dropped: the id
   is already in hand at mint time, so paying for it again at every
   validation is pure waste.

2. **Put the numeric id in `sub`, move the login to a new `login` claim.**
   Canonically cleanest — `sub` would be the stable key. But `sub` is read as
   the login by `ValidateJWT` → `groupsForSession(payload.Subject, ...)`, by
   `NewGitHubUser` (which sets `User.ID`, the value every authorization check,
   audit row and tenant lookup uses), and by any client inspecting the token.
   It is a flag day for in-flight tokens with no backward-compatible shape.
   Dropped, and explicitly excluded by the issue ("`sub` is still the login;
   no other claim changes meaning").

3. **Add a `github_id` column to `refreshstore` and thread the id through
   `Insert`/`Rotate` too.** This would make refreshed access tokens carry
   `ghid` as well, so the new counter would drop to zero once old tokens
   expire. It needs a schema migration in
   `internal/auth/refreshstore/postgres.go`, a change to the exported `Store`
   interface (`store.go:43-57`) and to the in-flight-rotation grace path —
   the same interface/schema blast radius the parent design record refused for
   slice C's group snapshot. **Adopted by owner decision 2026-09-30** (see
   "Refresh store" above): without it production tokens carry `ghid` only
   for the first hour of a login. Unlike slice C's group snapshot this column
   changes no authorization input — only principal resolution — and is
   additive and nullable.

4. **Keep `IssueJWT`'s signature and add `IssueJWTWithGitHubID`.** Zero test
   churn, but it leaves a path that silently mints a token without `ghid`, and
   the next caller to reach for the short name reintroduces the bug the
   regression test is meant to pin. Dropped in favour of the compile-breaking
   parameter.

## Platform impact

**Migrations.** One additive, idempotent statement:
`ALTER TABLE oauth_refresh_tokens ADD COLUMN IF NOT EXISTS github_id BIGINT`,
applied by the existing `schema` constant at store init. No backfill, no
Helm/env change, no new configuration flag. `docs/federation.md` and the code change together.

**Backward compatibility.**

- Tokens minted before the deploy have no `ghid`; `verifyJWT` ignores unknown
  and absent fields, `omitempty` means their payloads are unchanged, and they
  resolve exactly as today (login-only path) until they expire
  (`AccessTokenTTL`, default 1 h). Users are not forced to re-authenticate.
- Rolling deploy with mixed replicas is safe in both directions: a new
  replica mints `ghid`, an old replica ignores it (`encoding/json` drops
  unknown keys); a token minted by an old replica is handled by a new replica
  through the login-only branch.
- `refreshstore` rows written before the change read `github_id = NULL`,
  map to `0`, and refresh exactly as today (login-only); their successors
  keep `NULL`.
- Rollback to an older build after the column exists is safe: the old code
  names its columns explicitly in every `INSERT`/`SELECT`, so it neither
  reads nor writes `github_id`, and its inserts leave it `NULL`. The column
  is not dropped on rollback.
- The exported signature changes (`IssueCode`, `IssueJWT`,
  `IssueRefreshToken`) are internal to this module (`internal/...`), so no
  external consumer breaks. In-repo call sites: `internal/api/oauth_handlers.go`
  plus tests in `internal/auth/oauth_server_test.go`,
  `oauth_server_groups_test.go`, `oauth_clientstore_test.go`,
  `oauth_registry_expiry_test.go`, `federation_test.go:721`.
- MCP tool count is untouched, so the `internal/mcp/server_test.go`
  expectation stands.

**Resource impact.** One extra small integer per token (JWT grows by roughly
15 bytes). Fewer `api.github.com` calls and fewer `external_identities`
login-scan queries on the authentication path. One new unlabelled counter.

**Risks and mitigations.**

- *Risk: resolution switches from `ResolveGitHubLogin` to `Provision` for
  these callers, and a revoked `external_identities` row is refused by
  `Provision` (`store.go:195-197`) while `ResolveGitHubLogin` filters revoked
  rows out (`store.go:281`).* In both cases the request ends refused today
  (the login-only path falls through to `GitHubIDLookup` and then the same
  `Provision`), so the outcome should be identical — pinned by an explicit
  parity test (T6) rather than assumed.
- *Risk: a duplicate principal if a `(github, <id>)` row does not exist while
  a login-matched row does.* `ResolveGitHubLogin` only ever matches rows whose
  subject is that same numeric id (every `provider='github'` row is keyed on
  it, and `principals.Backfill` exists to fill legacy rows), so `Provision`
  finds the same row. Pinned by T6 against the store tests' fixtures; if a
  legacy row without a numeric subject were found, the fix is
  `principals.Backfill`, not this change.
- *Risk: a forged `ghid`.* The claim is inside the HS256 signature over
  `iss.sub.groups.iat.exp.ghid` and this server is the only minter; a
  tampered payload fails `verifyJWT`. `ghid` is never read from an unverified
  token (the unverified peek is `iss` only, `docs/federation.md:61-72`).
- *Risk: the new counter never reaching zero, hiding a real regression.* It
  counts validations of pre-change tokens and of families created before the
  column existed, so it should decay to zero within the 30-day refresh TTL;
  a non-zero value after that points at a mint path that drops the id.
- *Risk: `groups` handling accidentally changed while editing `IssueJWT` and
  `RefreshAccessToken`.* Slice C owns that behaviour; the existing
  `oauth_server_groups_test.go` suite (degraded grace, fail-closed, snapshot
  non-overwrite) must pass untouched apart from mechanical signature updates.

**Rollback.** Revert the commit; see `tasks.md`. The only persisted artefact
is the nullable `github_id` column, which older builds ignore; it is left in
place (dropping it is unnecessary and would be a separate, deliberate
change).
