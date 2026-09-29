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
- IF a refresh token is exchanged and the numeric GitHub id is not recorded
  for that refresh-token family THEN THE SYSTEM SHALL mint the new access
  token without `ghid` (login-only path, counter incremented) rather than
  guessing an id or failing the refresh.
- WHEN `docs/federation.md` is read after this change THE SYSTEM
  documentation SHALL describe the `ghid` claim, the new counter, and the
  refresh-token limitation, and SHALL no longer list slice B as out of
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
- Adding a `github_id` column to `refreshstore` (schema migration) so that
  refreshed access tokens also carry `ghid` — recorded as a follow-up.
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
- Refreshed access tokens: the persistent refresh store
  (`internal/auth/refreshstore/store.go:43-57`) has no place for the id, and
  `Rotate` returns only `(login, groups)`. Proceeding with "in-memory
  refresh-token entries carry the id, the persistent path does not", which
  means a refreshed token on the Postgres path takes the login-only path.
  That path is cheap after first sight, because
  `Store.ResolveGitHubLogin` (`internal/principals/store.go:275-283`) answers
  from the database and only an unknown login reaches `GitHubIDLookup`. A
  `github_id` column is the clean fix and is listed as a follow-up.
- `ghid` is emitted as a JSON number. GitHub ids are well inside float64
  exact-integer range today (~10^8), and this server both mints and parses
  the claim with `encoding/json` into `int64`, so no precision issue arises
  in practice. No string-encoded variant is introduced.
- The issue does not say whether `IssueCode`/`IssueJWT` should grow a
  parameter or a sibling method. Proceeding with an explicit new parameter so
  every call site is a compile error until it is considered.
