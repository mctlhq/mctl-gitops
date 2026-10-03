# Carry the numeric GitHub id in local OAuth JWTs (#374 slice B)

## Context

Slice A of mctl-api#374 (shipped in #410) introduced the federation
`Registry` and its providers, including `localOAuthProvider`
(`internal/auth/provider_localoauth.go`), the provider that verifies the
HS256 JWTs this server mints for MCP clients after the GitHub OAuth dance.
That provider returns an `auth.Identity` with `Provider: ProviderGitHub` and
`Display: <login>` but **no** `Subject`, because the login is all the token
carries: `jwtPayload` (`internal/auth/oauth_server.go:1453-1459`) has
`iss`/`sub`/`groups`/`iat`/`exp` and nothing else. Every such request
therefore takes the `Identity.GitHubLoginOnly()` branch of the principal
resolver (`internal/principals/resolver.go:186-204`), which matches on the
*spelling* of a login and, when no known GitHub identity holds it, falls back
to a `GitHubIDLookup` round-trip to `api.github.com`.

The numeric GitHub id is already available at the exact moment the token is
minted: `GitHubValidator.ValidateIdentity` (`internal/auth/github.go:66`)
returns it and caches it, but the OAuth callback
(`internal/api/oauth_handlers.go:254`) calls the thinner
`GitHubValidator.Validate` and drops it on the floor. This proposal carries
that id through `IssueCode` and `IssueJWT` into an optional `ghid` claim, so
a locally issued token resolves to the canonical principal via
`(github, <numeric id>)` — the stable half of a GitHub identity — with no
lookup and no dependence on login spelling. Tokens minted before the change
must keep working unchanged, through the existing login-only path, and must
be observable via a new counter so the tail of old tokens can be watched
draining.

## User stories

- AS the mctl-api principal resolver I WANT a local OAuth JWT to state the
  numeric GitHub id SO THAT I can resolve the canonical principal by its
  stable key instead of by a login's current spelling.
- AS a platform operator I WANT no `api.github.com` round-trip on the
  authentication path for freshly minted local OAuth tokens SO THAT request
  latency and GitHub rate-limit exposure do not depend on an external
  service.
- AS a platform operator I WANT a counter for tokens still resolved through
  the login-only path SO THAT I can see when the pre-change token population
  has drained and judge when the login-only fallback may be retired.
- AS an existing MCP client holding a token minted before this change I WANT
  my token to keep working until it expires SO THAT the rollout is not a
  forced re-login.

## Acceptance criteria (EARS)

- WHEN the GitHub OAuth callback (`handleOAuthGitHubCallback`,
  `internal/api/oauth_handlers.go`) validates the GitHub token THE SYSTEM
  SHALL obtain both the login and the numeric GitHub user id via
  `GitHubValidator.ValidateIdentity`.
- WHEN an authorization code is issued THE SYSTEM SHALL store the numeric
  GitHub id alongside the login on the auth-code entry, and WHEN that code is
  exchanged THE SYSTEM SHALL mint the access token with that id.
- WHEN `OAuthServer.IssueJWT` mints a token for a known numeric GitHub id THE
  SYSTEM SHALL include it as a `ghid` claim on the JWT payload.
- IF the numeric GitHub id is not known at mint time THEN THE SYSTEM SHALL
  omit the `ghid` claim entirely (no `"ghid":0` in the serialized payload).
- WHILE minting local OAuth access tokens THE SYSTEM SHALL keep `sub` set to
  the GitHub login, and SHALL NOT change the meaning of `iss`, `groups`,
  `iat` or `exp`.
- WHEN `OAuthServer.ValidateJWT` verifies a token carrying `ghid` THE SYSTEM
  SHALL produce a `*auth.User` whose `Identity()` is
  `{Provider: "github", Subject: "<ghid>", Display: "<sub>", Kind: "human"}`.
- WHEN such a token is authenticated THE SYSTEM SHALL resolve its principal
  through `Store.Provision` for `(github, <numeric id>)` and SHALL NOT call
  `GitHubIDLookup`.
- WHEN `ValidateJWT` verifies a token with no `ghid` claim THE SYSTEM SHALL
  keep returning the login-only identity (`Subject` empty,
  `Identity.GitHubLoginOnly()` true) so it resolves exactly as it does today,
  and SHALL increment the counter `oauth_jwt_without_github_id_total`.
- WHILE the federation registry is active THE SYSTEM SHALL have
  `localOAuthProvider.Verify` return the identity above, and that identity
  SHALL satisfy the registry's provider contract (declared namespace
  `github`, non-empty `Subject` or `GitHubLoginOnly()`, a valid `Kind`) so
  `federation_provider_contract_violations_total` stays zero.
- WHILE `MCTL_FEDERATION_DISABLED` is set THE SYSTEM SHALL behave
  identically on the retained pre-registry chain
  (`internal/auth/oidc.go:567-577`), since both paths go through
  `ValidateJWT`.
- WHEN a refresh token is issued THE SYSTEM SHALL record the numeric GitHub
  id with it on both refresh paths: the in-memory `refreshTokenEntry` and
  the persistent `refreshstore` (new nullable column
  `oauth_refresh_tokens.github_id BIGINT`).
- WHEN a refresh token is rotated THE SYSTEM SHALL copy `github_id` from the
  presented row to its successor, return it from `Rotate` (including the
  lost-response grace path, which returns the child row's value), and mint
  the new access token with `ghid` set from it — so a client keeps carrying
  `ghid` for the whole life of the refresh-token family, not only on its
  first access token. Production uses the Postgres store, access tokens live
  1h and refresh tokens 30d (`internal/auth/oauth_server.go:767-768`), so
  without this almost all production traffic would stay on the login-only
  path.
- WHEN the schema is applied THE SYSTEM SHALL add the column with
  `ALTER TABLE oauth_refresh_tokens ADD COLUMN IF NOT EXISTS github_id BIGINT`
  in the existing idempotent `schema` constant
  (`internal/auth/refreshstore/postgres.go`): additive, nullable, no default,
  no backfill, no index. Rows written before the change keep `NULL`.
- IF a refresh token is exchanged and its stored `github_id` is `NULL` or
  non-positive THEN THE SYSTEM SHALL mint the new access token without `ghid`
  (login-only path, counter incremented) rather than guessing an id or
  failing the refresh; the successor row keeps `NULL`, so such a family stays
  login-only until the user logs in again (≤ 30 days).
- WHILE an older mctl-api build runs against the migrated table (rollback)
  THE SYSTEM SHALL keep working unchanged: it neither reads nor writes the
  new column, and rows it inserts get `NULL`.
- WHEN `docs/federation.md` is read after this change THE SYSTEM
  documentation SHALL describe the `ghid` claim, the new counter, the
  `github_id` refresh-store column and the NULL fallback for pre-change
  families, and SHALL no longer list slice B as out of
  scope.

## Out of scope

- Slice C: re-resolving groups on refresh (`OAUTH_REFRESH_REGROUP`) — a
  separate issue; this proposal must not change group resolution timing.
- Slice D: the audience flag day and removal of the legacy Dex shim, the
  pre-registry chain and `MCTL_FEDERATION_DISABLED`.
- mctlhq/mctl-api#376: agent actor / on-behalf-of identity. Agent run tokens,
  `NewRelayedUser`, the surface relay and the `mctl-agents-approve`
  `approver` input are untouched.
- Making `sub` the numeric id, or any other change to what an existing claim
  means.
- Any change to authorization: `ghid` feeds principal *resolution* only.
  `User.ID` and `User.Groups` still decide access, exactly as in phase 1 of
  mctl-api#373.
- Changing `GitHubValidator`, the GitHub PAT path (which already carries the
  id, `internal/auth/oidc.go:594-602`), or `principals.Backfill`.

## Open questions

- `oauth_jwt_without_github_id_total` is incremented in `ValidateJWT`, which
  runs once per authenticated request, so the counter measures *requests*
  served from pre-change tokens, not distinct tokens. That is the useful
  operational signal (when does the old population stop being used) and is
  cheap; the alternative (deduplicating by token) would need per-token state.
  Proceeding with per-validation counting and documenting it in
  `docs/federation.md`.
- Refreshed access tokens — **resolved by owner decision 2026-09-30**: the
  persistent refresh store gets a nullable `github_id` column in this slice
  (see acceptance criteria above). The earlier "in-memory only, column as a
  follow-up" option was rejected because production uses the Postgres path,
  where it would have limited `ghid` to the first hour of each login.
- `ghid` is emitted as a JSON number. GitHub ids are well inside float64
  exact-integer range today (~10^8), and this server both mints and parses
  the claim with `encoding/json` into `int64`, so no precision issue arises
  in practice. No string-encoded variant is introduced.
- The issue does not say whether `IssueCode`/`IssueJWT` should grow a
  parameter or a sibling method. Proceeding with an explicit new parameter so
  every call site is a compile error until it is considered.
