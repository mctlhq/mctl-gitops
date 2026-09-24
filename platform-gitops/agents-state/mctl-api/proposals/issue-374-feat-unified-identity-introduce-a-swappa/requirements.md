# Swappable OIDC federation and broker boundary

## Context

Today mctl-api terminates four kinds of bearer token in one function,
`auth.Middleware` (`internal/auth/oidc.go:469-575`): static service tokens,
local MCP OAuth JWTs (HS256), Dex JWTs, and — as the fallback for anything
that is not a JWT — GitHub tokens validated against `api.github.com/user`.
Which verifier runs is decided by an unverified peek at the JWT `iss` claim
(`oidc.go:531`, `jwtIssuer` at `oidc.go:224`). There is exactly one OIDC
verifier, `DexVerifier`, bound to one issuer (`DEX_ISSUER_URL`), and its
audience check is silently skipped when `DEX_CLIENT_ID` is empty
(`oidc.go:178-184`). Adding a second identity provider, or replacing Dex,
means editing the middleware.

Issue #374 asks for the boundary that makes this swappable: the step
*before* the existing principal model, turning a verified external token into
`(provider, issuer, subject)` plus claims. Everything downstream —
`auth.Identity`, `PrincipalResolver` (`internal/auth/principal.go:75`),
`principals.Resolver`, `LinkMirror`, the surface-link flow — stays exactly as
it is; this proposal adds a provider registry in front of them and no new
identity tables. Authorization stays on `User.ID`/`User.Groups` and
`IsAdmin` (that move is #377), but the GitHub couplings are pushed behind
named seams so #377 can replace them without touching any provider.

## User stories

- AS a platform operator I WANT to add or replace an OIDC identity provider
  by writing one configuration entry SO THAT swapping Dex for another IdP is
  a deployment change, not a code change to the auth middleware.
- AS a platform operator I WANT every OIDC provider to have an explicitly
  configured issuer and audience SO THAT a token minted for another relying
  party cannot be replayed against mctl-api.
- AS a security reviewer I WANT the federation boundary to be incapable of
  expressing "service principal S speaks as subject X" SO THAT adding a
  provider can never turn mctl-agent into a generic impersonation relay.
- AS a platform engineer I WANT every existing token type (GitHub PAT, local
  OAuth JWT, Dex JWT, static service tokens) to keep working byte-identically
  through the new boundary SO THAT the cut-over is observable and reversible.
- AS a platform engineer I WANT local MCP OAuth access tokens to carry the
  numeric GitHub user id SO THAT principal resolution for those callers stops
  depending on a live GitHub lookup (`internal/principals/resolver.go:190-203`).
- AS a tenant member I WANT my group membership to be re-resolved when my
  access token is refreshed SO THAT a gitops membership change takes effect
  within an access-token lifetime instead of a refresh-token lifetime.

## Acceptance criteria (EARS)

Registry and routing

- WHEN the API starts THE SYSTEM SHALL build a federation registry of
  verification providers from configuration, each with a unique provider
  name and, for token-issuer providers, a unique normalized issuer URL.
- IF two configured providers declare the same provider name, or the same
  issuer URL, THEN THE SYSTEM SHALL refuse to start with a configuration
  error naming both entries.
- IF a configured provider name collides with a reserved name (`github`,
  `dex` when not the legacy Dex entry, `service`, `dev`) or with a surface
  name registered in `internal/surfaceid` (`telegram`, `portal`), THEN THE
  SYSTEM SHALL refuse to start, because its `external_identities` rows would
  collide with existing identities (`docs/principals.md`, "Surface identity
  links: mirrored, not replaced").
- WHEN a bearer token arrives THE SYSTEM SHALL select at most one provider to
  verify it: a static-secret provider by constant-time token match, a JWT
  provider by exact match of the token's unverified `iss` against that
  provider's configured issuer, and otherwise the single registered
  opaque-token provider.
- IF no provider claims a token THEN THE SYSTEM SHALL answer 401 and
  increment `federation_token_verifications_total{provider="none",result="unclaimed"}`.
- WHILE a token is being routed THE SYSTEM SHALL treat the unverified `iss`
  peek as routing information only, and SHALL never derive identity, kind,
  groups, or trust from an unverified claim.

Verification contract

- WHEN a provider verifies a token successfully THE SYSTEM SHALL receive a
  verified result carrying an `auth.Identity` (`Provider`, `Issuer`,
  `Subject`, `Display`, `Kind`) and provider-native claims, and nothing else.
- IF a provider returns a verified result whose `Identity.Provider` is not
  that provider's own declared name THEN THE SYSTEM SHALL reject the request
  with 401 and log a provider-contract violation.
- IF a provider returns a verified result with an empty `Subject` (except the
  GitHub login-only case already modelled by `auth.Identity.GitHubLoginOnly`,
  `internal/auth/principal.go:69`) THEN THE SYSTEM SHALL reject the request
  with 401.
- WHILE any provider is in use THE SYSTEM SHALL construct `*auth.User` only
  inside package `auth`, so that `service`, `githubLogin`, `usageWriter`,
  `surface`, `actingPrincipal` and `relaySurface` remain unforgeable by a
  provider (the unexported-field rule documented at `oidc.go:45-79`).

Non-impersonation

- WHILE verifying any token THE SYSTEM SHALL NOT allow a provider to produce
  an acting-principal, relay-surface, or on-behalf-of subject; the verified
  result type SHALL have no field able to express one.
- IF a verified token's claims contain delegation-shaped claims (`act`,
  `on_behalf_of`, `azp` used as a subject, or any vendor equivalent) THEN THE
  SYSTEM SHALL ignore them for identity purposes.
- WHILE this change is in effect THE SYSTEM SHALL leave the only two existing
  on-behalf paths untouched: the `mctl-agents-approve` `approver` input gated
  on `IsService()` (`internal/api/handlers_write.go:155-196`) and the surface
  relay (`internal/api/handlers_surface_identity.go:176-239`,
  `auth.NewRelayedUser` at `oidc.go:287`).

Issuer and audience validation

- WHEN an OIDC provider is configured through the new provider configuration
  THE SYSTEM SHALL require a non-empty audience list, and SHALL refuse to
  start if it is empty.
- WHEN an OIDC provider verifies a JWT THE SYSTEM SHALL require the token's
  `iss` to equal that provider's configured issuer and its `aud` to contain
  at least one configured audience.
- WHILE the legacy `DEX_ISSUER_URL`/`DEX_CLIENT_ID` configuration is still in
  use AND `DEX_CLIENT_ID` is empty THE SYSTEM SHALL keep accepting tokens
  (compatibility) and SHALL increment
  `federation_audience_check_skipped_total{provider="dex"}` on every such
  verification, and SHALL log a startup warning naming the variable to set.
- WHEN the legacy shim is removed (cut-over step 5 in design.md) THE SYSTEM
  SHALL refuse to start with an OIDC provider that has no audience.

Compatibility of existing token types

- WHEN a valid GitHub token is presented THE SYSTEM SHALL produce the same
  `*auth.User` as before: `ID` = login, `githubLogin` set, `githubID` set,
  `Groups` from `IsAdmin` plus `TenantResolver.GetTenantsForUser`
  (`oidc.go:620-637`).
- WHEN a valid local MCP OAuth JWT is presented THE SYSTEM SHALL produce the
  same `*auth.User` as `OAuthServer.ValidateJWT` produces today
  (`internal/auth/oauth_server.go:677-686`).
- WHEN a valid Dex JWT is presented THE SYSTEM SHALL produce the same
  `*auth.User` as `DexVerifier.Verify` produces today (`oidc.go:190-215`),
  including `dexIssuer`/`dexSubject`, so that `external_identities` rows with
  `provider='dex'` keep resolving to the same principals.
- WHEN a static service, surface, or usage-writer token is presented THE
  SYSTEM SHALL produce the same principal as `NewServiceUser`,
  `NewSurfaceUser`, `NewUsageWriterUser`, with the same refusal rules for
  short, shared, or duplicated tokens (`oidc.go:367-441`).
- WHEN no `Authorization` header is present AND `AUTH_REQUIRED=false` THE
  SYSTEM SHALL produce the dev principal unchanged (`oidc.go:503`).
- WHILE verification succeeds THE SYSTEM SHALL continue to call
  `attachPrincipal` exactly as today (`oidc.go:565, 594-611`): 403 on a
  disabled principal, 401 on a refused identity, and fail-open with
  `principal_resolution_failed_total` on any other resolution failure.

Local OAuth token contents

- WHEN the local OAuth server issues an access token after a GitHub callback
  THE SYSTEM SHALL include the numeric GitHub user id as an additional JWT
  claim (`ghid`), obtained by calling `GitHubValidator.ValidateIdentity`
  instead of `Validate` in the callback (`internal/api/oauth_handlers.go:250`).
- WHEN a local OAuth JWT carrying `ghid` is verified THE SYSTEM SHALL produce
  an identity of `(provider=github, subject=<ghid>, display=<login>)`, so
  resolution no longer takes the login-only path
  (`internal/principals/resolver.go:186-204`).
- IF a local OAuth JWT does not carry `ghid` (minted before this change) THEN
  THE SYSTEM SHALL fall back to the existing login-only identity and
  increment `oauth_jwt_without_github_id_total`.
- WHILE this change is in effect THE SYSTEM SHALL keep the JWT `sub` equal to
  the GitHub login, because tenant membership is still matched on the login
  (`internal/gitops/reader.go:109-130, 758`) and moving it is #377.

Refresh-time group freshness

- WHEN an access token is issued through the `refresh_token` grant AND
  `OAUTH_REFRESH_REGROUP` is not `false` THE SYSTEM SHALL re-resolve groups
  with the same `OAuthServer.ResolveGroups` used at mint time
  (`oauth_server.go:383-395`) rather than replaying the groups stored with
  the refresh token (`oauth_server.go:614-656`).
- IF re-resolution fails THEN THE SYSTEM SHALL fall back to the stored groups
  and SHALL NOT fail the refresh, and SHALL increment
  `oauth_refresh_regroup_failed_total`.

Observability and cut-over

- WHEN any verification completes THE SYSTEM SHALL increment
  `federation_token_verifications_total{provider,result}` with
  `result` in {`ok`, `invalid`, `unclaimed`} and observe
  `federation_verify_duration_seconds{provider}`.
- WHILE `MCTL_FEDERATION_DISABLED` is set to a kill-switch value THE SYSTEM
  SHALL use the pre-registry verification chain unchanged, in the same shape
  as `PRINCIPALS_DISABLED` (`cmd/api/main.go:206, 1420-1427`).

## Out of scope

- Any change to authorization, admin determination (`ADMIN_USERS`,
  `internal/auth/github.go:88`), or tenant resolution by GitHub login
  (`internal/gitops/reader.go:109-130, 758`). That is #377. This proposal
  only relocates the existing group resolution behind a named seam without
  changing its inputs or outputs.
- Making principal resolution fail closed — still #377; `attachPrincipal`
  keeps degrading open.
- MCP client identity / CIMD-aware MCP OAuth (#375).
- Actor versus on-behalf-of subject for agents, and delegated agent identity
  (#376).
- New identity tables or changes to `principals` / `external_identities`
  schema (`internal/principals/store.go:78-105`).
- Allowing Dex-authenticated users to link surfaces or receive gitops groups
  (a known gap; unchanged here).
- Replacing the GitHub PAT path with anything else.
- Deploying or configuring an external broker.

## Open questions

- **Should local MCP OAuth tokens carry the numeric GitHub id, or `prn_`?**
  Proposed answer: the numeric GitHub id as an additive `ghid` claim, and not
  `prn_`. Minting `prn_` would put the principal store on the OAuth callback
  path, which today degrades open, and #377 will re-resolve the principal on
  every request anyway. Recorded here for the reviewer to overrule.
- **Should groups be re-resolved on refresh?** Proposed answer: yes, default
  on, with fallback to the stored groups on resolver error so a gitops outage
  never fails a refresh. This is the one behaviour change that touches
  authorization timing rather than authorization rules; flag it for review.
- **In-process broker or external broker (Dex as the only upstream, with
  connectors)?** Proposed answer: in-process registry now. mctl-api must keep
  terminating static service tokens and its own HS256 MCP OAuth JWTs, which
  no upstream IdP can mint, and the GitHub PAT path is an opaque-token check
  Dex cannot front, so an external broker would rename the multi-verifier
  problem rather than remove it — while adding a hard runtime dependency in
  front of every request (today a Dex outage at boot only disables Dex,
  `cmd/api/main.go:97-107`). The registry does not preclude the external
  route: Dex-with-connectors becomes one provider entry plus a per-connector
  provider-name mapping. Trade-off stated in design.md.
- Whether the audience-enforcement flag day (step 5) should be a separate
  issue with its own approval, given it can refuse a production boot.
- Whether `DEX_ISSUER_URL`'s default (`https://ops.mctl.ai/api/dex`,
  `cmd/api/main.go:999`) should stay a default at all once providers are
  configured explicitly; a default issuer is a provider nobody declared.
