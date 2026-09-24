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

This is the second revision, after the review of proposal
`issue-374-feat-unified-identity-introduce-a-swappa`. Four items came out of
that review and are now first-class requirements rather than implied: the
timing-unsafe service-token compare is fixed as a stated behaviour fix
(`oidc.go:448`); the audience cut-over is a production canary in *audit mode*
because mctl-api has no staging deployment; `agent` is a reserved provider
name, since #376 introduces `ProviderAgent = "agent"`; and the work is cut
into four separately mergeable slices.

## User stories

- AS a platform operator I WANT to add or replace an OIDC identity provider
  by writing one configuration entry SO THAT swapping Dex for another IdP is
  a deployment change, not a code change to the auth middleware.
- AS a platform operator I WANT every OIDC provider to have an explicitly
  configured issuer and audience SO THAT a token minted for another relying
  party cannot be replayed against mctl-api.
- AS a platform operator with no staging environment I WANT audience
  validation to run in audit mode first, counting what it *would* refuse SO
  THAT I can prove enforcement is safe in production before it can lock
  anyone out.
- AS a security reviewer I WANT the federation boundary to be incapable of
  expressing "service principal S speaks as subject X" SO THAT adding a
  provider can never turn mctl-agent into a generic impersonation relay.
- AS a security reviewer I WANT every static-secret comparison on the
  authentication path to be constant-time SO THAT the service token is not
  the one secret in the middleware that leaks its prefix through timing.
- AS a platform engineer I WANT every existing token type (GitHub PAT, local
  OAuth JWT, Dex JWT, static service tokens) to keep working byte-identically
  through the new boundary SO THAT the cut-over is observable and reversible.
- AS a platform engineer I WANT local MCP OAuth access tokens to carry the
  numeric GitHub user id SO THAT principal resolution for those callers stops
  depending on a live GitHub lookup (`internal/principals/resolver.go:186-204`).
- AS a tenant member I WANT my group membership to be re-resolved when my
  access token is refreshed SO THAT a gitops membership change takes effect
  within an access-token lifetime instead of a refresh-token lifetime.
- AS a reviewer of this change I WANT each behaviour change to arrive in its
  own pull request SO THAT the behaviour-identical refactor can merge without
  waiting on the decisions that are not behaviour-identical.

## Acceptance criteria (EARS)

### Registry and routing

- WHEN the API starts THE SYSTEM SHALL build a federation registry of
  verification providers from configuration, each with a unique provider
  name and, for token-issuer providers, a unique normalized issuer URL.
- IF two configured providers declare the same provider name, or the same
  normalized issuer URL, THEN THE SYSTEM SHALL refuse to start with a
  configuration error naming both entries.
- IF a configured provider name collides with a reserved name — `github`,
  `service`, `dev`, `agent`, or `dex` when the entry is not the Dex entry
  itself — THEN THE SYSTEM SHALL refuse to start. `agent` is reserved because
  #376 introduces `auth.ProviderAgent = "agent"` for delegated agent
  identity, and a federation provider must never mint `(agent, ...)`
  identities.
- IF a configured provider name collides with a surface name registered in
  `internal/surfaceid` (`SurfaceTelegram`, `SurfacePortal`,
  `internal/surfaceid/store.go:50-51`) THEN THE SYSTEM SHALL refuse to start,
  because its `external_identities` rows would collide with identities
  mirrored from surface links (`docs/principals.md`).
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
- IF more than one opaque-token provider is registered THEN THE SYSTEM SHALL
  refuse to start, because an opaque token carries nothing to route on.

### Verification contract

- WHEN a provider verifies a token successfully THE SYSTEM SHALL receive a
  verified result carrying an `auth.Identity` (`Provider`, `Issuer`,
  `Subject`, `Display`, `Kind`) and provider-native claims, and nothing else.
- IF a provider returns a verified result whose `Identity.Provider` is not
  that provider's own declared namespace THEN THE SYSTEM SHALL reject the
  request with 401, log a provider-contract violation, and increment
  `federation_provider_contract_violations_total{provider}`.
- IF a provider returns a verified result with an empty `Subject` (except the
  GitHub login-only case already modelled by `auth.Identity.GitHubLoginOnly`,
  `internal/auth/principal.go:69-71`) THEN THE SYSTEM SHALL reject the
  request with 401.
- IF a provider returns a `Kind` that is not one of `auth.KindHuman`,
  `auth.KindAgent`, `auth.KindService` (`principal.go:46-50`) THEN THE SYSTEM
  SHALL reject the request with 401.
- WHILE any provider is in use THE SYSTEM SHALL construct `*auth.User` only
  inside package `auth`, so that `service`, `githubLogin`, `usageWriter`,
  `surface`, `actingPrincipal` and `relaySurface` remain unforgeable by a
  provider (the unexported-field rule documented at `oidc.go:45-95`).

### Non-impersonation

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
  `auth.NewRelayedUser` at `oidc.go:287-302`).

### Static-secret matching (behaviour fix)

- WHEN a bearer token is compared against `MCTL_AGENT_SERVICE_TOKEN` THE
  SYSTEM SHALL compare it with `crypto/subtle.ConstantTimeCompare`. Today
  `staticServiceUser` uses a plain `==` (`internal/auth/oidc.go:448`) while
  the surface and usage-writer checks already use constant time
  (`oidc.go:392, 433`). This is a deliberate behaviour fix carried by this
  proposal, not a refactor: the accept/reject outcome is unchanged, the
  timing signal is removed.
- WHILE any static-secret provider matches a token THE SYSTEM SHALL route
  every comparison through one shared constant-time helper, so a future
  static provider cannot reintroduce `==`.
- IF the configured secret is empty THEN THE SYSTEM SHALL NOT match, without
  performing a comparison against the presented token.

### Issuer and audience validation

- WHEN an OIDC provider is configured through the new provider configuration
  THE SYSTEM SHALL require a non-empty audience list, and SHALL refuse to
  start if it is empty.
- WHEN an OIDC provider verifies a JWT THE SYSTEM SHALL require the token's
  `iss` to equal that provider's configured issuer, and SHALL evaluate
  whether its `aud` contains at least one configured audience.
- WHILE an OIDC provider's `audience_enforcement` is `audit` THE SYSTEM SHALL
  accept a token whose audience does not match and SHALL increment
  `federation_audience_mismatch_total{provider}`, so that enforcement can be
  proven safe in production before it refuses anything.
- WHILE an OIDC provider's `audience_enforcement` is `enforce` THE SYSTEM
  SHALL refuse a token whose `aud` contains no configured audience.
- WHILE the legacy `DEX_ISSUER_URL`/`DEX_CLIENT_ID` configuration is still in
  use AND `DEX_CLIENT_ID` is empty THE SYSTEM SHALL keep accepting tokens
  (compatibility), SHALL increment
  `federation_audience_check_skipped_total{provider="dex"}` on every such
  verification, and SHALL log a startup warning naming the variable to set.
- IF an explicit provider entry claims the same issuer as the legacy Dex shim
  THEN THE SYSTEM SHALL use the explicit entry, SHALL NOT synthesize the
  shim, and SHALL log at boot which of the two is active. Two registrations on
  one issuer are a boot refusal, so the explicit entry supersedes the shim
  rather than running beside it.
- WHEN the legacy shim is removed (slice D) THE SYSTEM SHALL refuse to start
  with an OIDC provider that has no audience, and SHALL no longer contain the
  `SkipClientIDCheck` branch (`oidc.go:181-183`).

### Compatibility of existing token types

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
  short, shared, or duplicated tokens (`oidc.go:367-441`) — the only
  difference being the constant-time compare above.
- WHEN no `Authorization` header is present AND `AUTH_REQUIRED=false` THE
  SYSTEM SHALL produce the dev principal unchanged (`oidc.go:503`).
- WHILE verification succeeds THE SYSTEM SHALL continue to call
  `attachPrincipal` exactly as today (`oidc.go:565, 594-611`): 403 on a
  disabled principal, 401 on a refused identity, and fail-open with
  `principal_resolution_failed_total` on any other resolution failure.

### Local OAuth token contents (slice B)

- WHEN the local OAuth server issues an access token after a GitHub callback
  THE SYSTEM SHALL include the numeric GitHub user id as an additional JWT
  claim (`ghid`), obtained by calling `GitHubValidator.ValidateIdentity`
  (`internal/auth/github.go:66`) instead of `Validate` in the callback
  (`internal/api/oauth_handlers.go:251`).
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

### Refresh-time group freshness (slice C)

- WHEN an access token is issued through the `refresh_token` grant AND
  `OAUTH_REFRESH_REGROUP` is not `false` THE SYSTEM SHALL re-resolve groups
  with the same `OAuthServer.ResolveGroups` used at mint time
  (`oauth_server.go:383-395`) rather than replaying the groups stored with
  the refresh token (`oauth_server.go:585-656`).
- IF re-resolution fails THEN THE SYSTEM SHALL fall back to the stored groups,
  SHALL NOT fail the refresh, and SHALL increment
  `oauth_refresh_regroup_failed_total`.

### Observability and cut-over

- WHEN any verification completes THE SYSTEM SHALL increment
  `federation_token_verifications_total{provider,result}` with `result` in
  {`ok`, `invalid`, `unclaimed`} and observe
  `federation_verify_duration_seconds{provider}`.
- WHILE `MCTL_FEDERATION_DISABLED` is set to a kill-switch value THE SYSTEM
  SHALL use the pre-registry verification chain unchanged, in the same shape
  as `PRINCIPALS_DISABLED` (`cmd/api/main.go:206, 1421-1427`).
- WHILE the production canary is running THE SYSTEM SHALL expose enough to
  gate the flag day without a staging environment:
  `federation_audience_mismatch_total{provider}` must read zero and
  `federation_token_verifications_total{provider="dex",result="ok"}` must hold
  its pre-change rate before `audience_enforcement` is flipped to `enforce`.

## Out of scope

- Any change to authorization, admin determination (`ADMIN_USERS`,
  `internal/auth/github.go:88-95`), or tenant resolution by GitHub login
  (`internal/gitops/reader.go:109-130, 758`). That is #377. This proposal only
  relocates the existing group resolution behind a named seam without
  changing its inputs or outputs.
- Making principal resolution fail closed — still #377; `attachPrincipal`
  keeps degrading open.
- MCP client identity / CIMD-aware MCP OAuth (#375).
- Actor versus on-behalf-of subject for agents, and delegated agent identity
  (#376). This proposal only *reserves* the `agent` provider name for it.
- New identity tables or changes to `principals` / `external_identities`
  schema (`internal/principals/store.go:78-105`).
- Allowing Dex-authenticated users to link surfaces or receive gitops groups
  (a known gap; unchanged here).
- Replacing the GitHub PAT path with anything else.
- Deploying or configuring an external broker.
- Deleting the legacy Dex shim and enforcing audiences: that is slice D, to be
  filed as its own follow-up issue with its own approval, because it can
  refuse a production boot.

## Open questions

Kept from the reviewed proposal with their proposed answers; the owner decides
them at approval.

- **Should local MCP OAuth tokens carry the numeric GitHub id, or `prn_`?**
  Proposed answer: the numeric GitHub id as an additive `ghid` claim, and not
  `prn_`. Minting `prn_` would put the principal store on the OAuth callback
  path, which today degrades open, and #377 will re-resolve the principal on
  every request anyway.
- **Should groups be re-resolved on refresh?** Proposed answer: yes, default
  on, with fallback to the stored groups on resolver error so a gitops outage
  never fails a refresh. This is the one change that touches authorization
  *timing* rather than authorization rules, which is why it is its own slice
  (C) and can be approved or dropped independently.
- **In-process broker or external broker (Dex as the only upstream, with
  connectors)?** Proposed answer: in-process registry now. mctl-api must keep
  terminating static service tokens and its own HS256 MCP OAuth JWTs, which no
  upstream IdP can mint, and the GitHub PAT path is an opaque-token check
  against `api.github.com/user` that Dex cannot front, so an external broker
  would rename the multi-verifier problem rather than remove it — while adding
  a hard runtime dependency in front of every request (today a Dex outage at
  boot only disables Dex, `cmd/api/main.go:97-107`). The registry does not
  preclude the external route: Dex-with-connectors becomes one provider entry
  plus a per-connector provider-name mapping. Trade-off stated in design.md.
- Whether `DEX_ISSUER_URL`'s default (`https://ops.mctl.ai/api/dex`,
  `cmd/api/main.go:999`) should stay a default at all once providers are
  configured explicitly; a default issuer is a provider nobody declared.
  Proposed answer: keep the default through slice A for compatibility, drop it
  in slice D together with the shim.
- Whether the canary in audit mode should run for 7 days (proposed) or one
  full `OAUTH_REFRESH_TOKEN_TTL`. The audience question concerns Dex tokens,
  not local OAuth refresh tokens, so 7 days is proposed as sufficient.
</content>
</invoke>
