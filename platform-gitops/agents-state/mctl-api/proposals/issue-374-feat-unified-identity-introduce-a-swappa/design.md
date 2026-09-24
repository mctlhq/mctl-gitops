# Design: issue-374-feat-unified-identity-introduce-a-swappa

## Current state

### One middleware, four token types, an unverified peek

`auth.Middleware` (`internal/auth/oidc.go:469-575`) is the whole
authentication boundary. Its body is a literal `if/else if` chain:

1. `staticServiceUser(token)` (`oidc.go:446-452`) — constant compare against
   `MCTL_AGENT_SERVICE_TOKEN`, yields `NewServiceUser()`.
2. `surfaceUserFor(surfaces, token)` (`oidc.go:430-441`) — constant compare
   against the per-surface tokens read at construction by `surfaceTokens()`
   (`oidc.go:401-426`), yields `NewSurfaceUser(name)`.
3. `usageWriterUserFor(usageWriter, token)` (`oidc.go:391-396`) — yields
   `NewUsageWriterUser()`.
4. `isJWT(token)` (`oidc.go:218`, three dot-separated parts) then
   `jwtIssuer(token)` (`oidc.go:224-240`), which base64-decodes the payload
   **without verifying the signature** and reads `iss`. If it equals
   `oauth.BaseURL` the token goes to `OAuthServer.ValidateJWT`
   (`oauth_server.go:677-686`); otherwise it goes to `DexVerifier.Verify`
   (`oidc.go:190-215`), or is refused if `dex == nil`.
5. Everything else is assumed to be a GitHub token and goes to
   `GitHubValidator.ValidateIdentity` (`internal/auth/github.go:66-85`),
   then `resolveGroups(login, validator, resolver)` (`oidc.go:620-637`).

There is no provider interface. Adding an IdP means editing this chain.

### One OIDC verifier, one issuer, optional audience

`NewDexVerifier` (`oidc.go:173-186`) constructs a single
`oidc.IDTokenVerifier` from `DEX_ISSUER_URL`. When `DEX_CLIENT_ID` is empty
it sets `cfg.SkipClientIDCheck = true` — every audience is accepted. Both
values are read in `loadConfig` (`cmd/api/main.go:999-1000`), with
`DEX_ISSUER_URL` carrying a hard-coded default of
`https://ops.mctl.ai/api/dex`. A Dex init failure only logs a warning and
leaves `dexVerifier` nil (`cmd/api/main.go:97-107`).

`DexVerifier.Verify` takes `Groups` straight from the token claims and
derives `User.ID` from `preferred_username`, then `email`, then `sub`. It
sets the unexported `dexIssuer`/`dexSubject`, which is what makes
`User.Identity()` return `(dex, iss, sub)` at `principal.go:121-122`.

### What happens after verification (and must not change)

Every branch converges on `attachPrincipal` (`oidc.go:565, 594-611`):
`User.Identity()` (`principal.go:109-129`) → `PrincipalResolver.ResolvePrincipal`
(`principal.go:75-77`) → `principals.Resolver` (`internal/principals/resolver.go:126-162`)
→ `Store.Provision` (`internal/principals/store.go:~170`). A disabled
principal is 403, a revoked identity 401, anything else degrades open with
`principal_resolution_failed_total` (`resolver.go:52-57`).

The security model of `*auth.User` rests on unexported fields with a
documented rationale (`oidc.go:45-95`): `service`, `githubLogin`,
`usageWriter`, `surface`, `actingPrincipal`, `relaySurface`, `githubID`,
`dexIssuer`, `dexSubject`, `dev`, `principalID`, `viaPrincipalID`. Only
constructors inside package `auth` set them, so no caller can claim to be the
service principal by naming itself `mctl-agent`.

### The GitHub couplings this boundary must isolate

- `ADMIN_USERS` → `GitHubValidator.IsAdmin(login)` (`github.go:88-95`),
  reached only through `resolveGroups` (`oidc.go:623`) and
  `OAuthServer.ResolveGroups` (`oauth_server.go:383-395`).
- Tenant membership by GitHub login: `Tenant.UserNamespaces(login)` with
  `strings.EqualFold(m.UserID, login)` (`internal/gitops/reader.go:109-143`),
  reached through `Reader.GetTenantsForUser` (`reader.go:758-771`).
- Local MCP OAuth runs only through GitHub OAuth: the callback exchanges a
  GitHub code, calls `GitHubValidator.Validate` — dropping the numeric id
  already fetched and cached by `fetchUser` (`github.go:97-129`) — and issues
  a code with the resolved groups (`internal/api/oauth_handlers.go:242-262`).
  `jwtPayload` is `{iss, sub, groups, iat, exp}` (`oauth_server.go:~700`);
  `ValidateJWT` returns `NewGitHubUser(payload.Subject, payload.Groups)`, so
  the identity is login-only and resolution goes through
  `Resolver.resolve`'s `ResolveGitHubLogin` / live `GitHubIDLookup` path
  (`internal/principals/resolver.go:186-204`).
- Surface links accept only `github:<login>` principals
  (`internal/surfaceid/store.go:206`, enforced again at
  `internal/api/handlers_surface_identity.go:207`).
- Groups in local OAuth tokens are frozen at mint: `IssueRefreshToken` stores
  them (`oauth_server.go:585-611`) and `RefreshAccessToken` replays them
  (`oauth_server.go:614-656`), so a gitops membership change can take up to
  `OAUTH_REFRESH_TOKEN_TTL` (30 days by default, `cmd/api/main.go:1001`) to
  land.

## Proposed solution

### Shape: a provider registry inside package `auth`

Add a federation boundary as new files in `internal/auth`, not a new
top-level package:

- `internal/auth/federation.go` — `Provider`, `Verified`, `Registry`,
  registry construction and invariants, metrics.
- `internal/auth/provider_static.go` — the three static-secret providers
  (service, surface, usage-writer) and the dev identity.
- `internal/auth/provider_github.go` — the opaque GitHub PAT provider.
- `internal/auth/provider_localoauth.go` — the local HS256 MCP OAuth JWT
  provider, wrapping `OAuthServer.ValidateJWT`.
- `internal/auth/provider_oidc.go` — the generic OIDC JWT provider, of which
  Dex becomes one instance.
- `internal/auth/federation_config.go` — parsing and validation of
  `MCTL_OIDC_PROVIDERS`, plus the legacy `DEX_ISSUER_URL`/`DEX_CLIENT_ID`
  shim.

It lives in package `auth` because `*auth.User`'s safety property is that its
discriminating fields are unexported and set only by constructors in this
package (`oidc.go:45-79`). A provider in another package could not set them,
so we would have to export them — which is exactly the weakening the existing
comments argue against. Providers therefore return **data**, and `auth` mints
the `*User`.

### The contract

```go
// Verified is everything a provider may assert. It has no field able to
// express "speaking for someone else"; that is the non-impersonation
// invariant of this boundary, enforced by the type, not by review.
type Verified struct {
    Identity auth.Identity // Provider, Issuer, Subject, Display, Kind
    Claims   Claims        // Groups, PreferredUsername, Email, Expiry, Raw
}

type Provider interface {
    // Name is the registry key AND the external_identities.provider value.
    Name() string
    // Claims decides routing only, from cheap unverified inspection.
    Claims(t tokenShape) bool
    // Verify proves the token and returns the identity it proves.
    Verify(ctx context.Context, raw string) (*Verified, error)
}
```

`tokenShape` is computed once per request: `opaque` vs `jwt` plus the
unverified `iss` from the existing `jwtIssuer` helper. Nothing but routing
reads it, and that is stated in the doc comment, because the current code
already relies on this peek and the risk is that a future reader mistakes it
for a trust decision.

`Registry.Verify(ctx, raw)`:

1. constant-time match against every static-secret provider (unchanged order:
   service, surface, usage-writer);
2. for a JWT, exact lookup of the normalized `iss` in an issuer→provider map
   (local OAuth server registers `oauth.BaseURL`; each OIDC provider
   registers its configured issuer);
3. otherwise the single registered opaque provider (GitHub);
4. no provider → `ErrNoProvider` → 401 and
   `federation_token_verifications_total{provider="none",result="unclaimed"}`.

There is deliberately **no** "try every provider" fallback: spraying a token
across verifiers both costs latency and makes it possible for a token to be
accepted by a provider it was never minted for.

After a provider answers, the registry enforces provider-contract invariants
before the result is used:

- `v.Identity.Provider == p.Name()` — a provider may only mint identities in
  its own namespace, so a misconfigured or hostile provider implementation
  cannot produce a `service` identity, or claim another IdP's subjects. The
  one modelled exception is the local-OAuth provider, whose declared identity
  namespace is `github` by design (it mints only for GitHub-verified logins,
  `oauth_server.go:681-684`); it declares that namespace explicitly rather
  than deriving it.
- `v.Identity.Subject != ""` unless `v.Identity.GitHubLoginOnly()`
  (`principal.go:69-71`).
- `v.Identity.Kind` is one of the three `auth.Kind*` constants, matching what
  `principals.validIdentity` already requires (`store.go:~155`).

`Middleware` then maps `*Verified` to a `*User` through one unexported
function, `userFromVerified`, which is the only new place a `*User` is built
and which sets the unexported discriminators from the provider's declared
kind and name — never from token claims.

### Non-impersonation, by construction

Constraint 4 of the issue is enforced three ways:

1. `Verified` carries no acting/on-behalf field. `actingPrincipal`,
   `relaySurface` and `viaPrincipalID` are set only by `NewRelayedUser`
   (`oidc.go:287-302`), which is unreachable from the registry.
2. The static providers return a compiled-in subject (`ServiceUserID`,
   `SurfacePrincipalPrefix+name`, `UsageWriterUserID`); there is no path from
   a token body to a service subject.
3. The provider-namespace invariant means no JWT provider can return
   `Provider: auth.ProviderService`.

The two existing on-behalf paths stay untouched: the
`mctl-agents-approve` `approver` input gated on `IsService()`
(`internal/api/handlers_write.go:155-196`) and the surface relay
(`handlers_surface_identity.go:176-239`), which keeps calling
`auth.AttachPrincipal` itself.

### Configuration and swappability

New variable `MCTL_OIDC_PROVIDERS`, a JSON array parsed in `loadConfig` and
validated in `config.validate` (`cmd/api/main.go:1224-1257`), alongside the
existing `OAUTH_PREREGISTERED_CLIENTS` precedent, which already refuses boot
on a malformed value:

```json
[
  {
    "name": "dex",
    "issuer": "https://ops.mctl.ai/api/dex",
    "audiences": ["mctl-api"],
    "subject_claim": "sub",
    "display_claims": ["preferred_username", "email", "sub"],
    "groups_claim": "groups",
    "kind": "human"
  }
]
```

`display_claims` reproduces `DexVerifier.Verify`'s existing fallback order
(`oidc.go:206-212`) as configuration rather than code, which is the concrete
meaning of "swappable": a second IdP that puts the username somewhere else
needs a config entry, not a code change. `audiences` is **required** for any
entry in this variable — the `SkipClientIDCheck` branch (`oidc.go:181-183`)
is not reachable from it.

Registry invariants refused at boot:

- duplicate provider name;
- duplicate normalized issuer (two providers claiming one `iss` would make
  routing order-dependent);
- a provider name colliding with `github`, `service`, `dev`, or a registered
  surface name — `docs/principals.md` already forbids a surface named after
  an auth provider, and this is the same rule from the other side, because
  both write into one `external_identities.provider` namespace
  (`internal/principals/store.go:86-101`);
- more than one opaque-token provider.

Replacing Dex is then: change the entry's `issuer`/`audiences`, keep `name`
(existing `external_identities` rows with `provider='dex'` keep resolving),
or add a second entry under a new name and migrate users by linking.

### Isolating the GitHub couplings without changing them

The GitHub provider is constructed with a `GroupSource` interface:

```go
type GroupSource interface{ GroupsFor(ctx context.Context, login string) []string }
```

whose only implementation wraps today's `resolveGroups(login, validator,
resolver)` verbatim (`oidc.go:620-637`). `ADMIN_USERS` and
`gitops.Reader.GetTenantsForUser` stay exactly where they are and return
exactly what they return today — a characterization test locks the output
for both the admin and non-admin case. #377 replaces the implementation
behind `GroupSource` with a principal-keyed one without touching any
provider. Nothing about admin determination or tenant membership changes in
this proposal.

### Local OAuth tokens carry the numeric GitHub id

`internal/api/oauth_handlers.go:250` calls `o.GitHubValidator.Validate`,
which throws away the numeric id that `fetchUser` has already fetched and
cached (`github.go:66-85`). Switch that one call to `ValidateIdentity`,
thread the id through `IssueCode` → the authorization code entry →
`IssueJWT`, and add an optional `ghid` claim to `jwtPayload`.

This is additive and backward compatible: `verifyJWT` unmarshals into the
struct, so an old token simply has `ghid == 0`. The local-OAuth provider then
returns `(github, <ghid>, display=<login>)` when present and the existing
login-only identity otherwise, counting
`oauth_jwt_without_github_id_total`. The benefit is concrete: the login-only
path in `principals.Resolver.resolve` (`resolver.go:186-204`) can call out to
GitHub (`GitHubIDLookup`) on the authentication path, and with `ghid` it does
not. `sub` stays the login, because tenant membership still matches on the
login (`reader.go:109-143`) and moving that is #377. `prn_` is deliberately
not minted into the token: it would put the principal store on the OAuth
callback path, which today is allowed to degrade open.

### Groups re-resolved on refresh

`RefreshAccessToken` (`oauth_server.go:614-656`) replays groups stored with
the refresh token, for up to `RefreshTokenTTL` (30 days). Re-resolve with the
same `ResolveGroups` (`oauth_server.go:383-395`), same inputs, same rules —
only later in time — behind `OAUTH_REFRESH_REGROUP` (default on). On resolver
error, fall back to the stored groups and count
`oauth_refresh_regroup_failed_total`; a gitops outage must never fail a
refresh. This is the one change with an authorization-timing effect, so it is
flagged in requirements.md as an open question rather than buried.

### Observability and cut-over

Metrics, following the existing `prometheus.NewCounter` + `init()`
registration pattern (`internal/principals/resolver.go:52-57`,
`internal/events/relay.go:92-97`):

- `federation_token_verifications_total{provider,result}` — `ok`, `invalid`,
  `unclaimed`;
- `federation_verify_duration_seconds{provider}`;
- `federation_audience_check_skipped_total{provider}` — the legacy Dex shim;
- `federation_provider_contract_violations_total{provider}` — should be
  permanently zero; non-zero means a provider returned an identity outside
  its namespace;
- `oauth_jwt_without_github_id_total`;
- `oauth_refresh_regroup_failed_total`.

Cut-over order:

1. Ship the registry, populated from today's env vars only. Behaviour is
   identical; `federation_token_verifications_total{result="ok"}` per provider
   should match pre-change traffic shape and
   `principal_resolution_failed_total` must not rise.
2. Ship `ghid` in newly minted local OAuth JWTs; watch
   `oauth_jwt_without_github_id_total` fall towards zero over one
   `OAUTH_REFRESH_TOKEN_TTL`.
3. Enable `MCTL_OIDC_PROVIDERS` in a staging deployment with explicit
   `audiences`; confirm `federation_audience_check_skipped_total` is zero and
   Dex logins still work.
4. Set `DEX_CLIENT_ID` (or move to `MCTL_OIDC_PROVIDERS`) in production;
   require `federation_audience_check_skipped_total == 0` for 7 days.
5. Remove the legacy shim so a missing audience refuses boot. Separate PR, so
   it can be reverted on its own.

`MCTL_FEDERATION_DISABLED` (same shape as `PRINCIPALS_DISABLED`,
`cmd/api/main.go:206, 1420-1427`) restores the pre-registry chain for one
release. The old chain stays in the tree, exercised by the existing tests in
`internal/auth/auth_test.go`, until step 5.

## Alternatives

**A new top-level `internal/federation` package.** Cleaner layering on paper,
and the option to unit-test providers without importing `auth`. Dropped
because `*auth.User`'s discriminators (`service`, `githubLogin`, `surface`,
`usageWriter`, `actingPrincipal`) are unexported precisely so that only
`auth` can set them (`oidc.go:45-79`), and `auth.Identity` lives in `auth`
too (`principal.go:54-63`). A separate package means exporting those fields
or duplicating the type across a translation layer — trading a real security
property for a package boundary. The providers are already isolated files
with narrow constructor-injected dependencies, which gets most of the
testability without the cost. If the package ever needs to be split, the
`Provider` interface is the seam to split on.

**External broker: Dex as the only upstream, with connectors.** One JWKS,
one issuer, connector management outside mctl-api, and genuinely one code
path for human identity. Dropped as the *now* answer for four reasons taken
from this codebase: mctl-api must keep terminating static service tokens
(`oidc.go:446-452`) and its own HS256 MCP OAuth JWTs (`oauth_server.go:677`),
neither of which any upstream can mint, so the multi-verifier problem is
renamed rather than removed; the GitHub PAT path is an opaque-token check
against `api.github.com/user` (`github.go:98`) that Dex cannot front; a
broker in front of every request is a new SPOF where today a Dex failure at
boot only disables Dex (`cmd/api/main.go:100-107`); and every existing
`external_identities` row keyed on the current Dex `iss`
(`store.go:99`, `UNIQUE(provider, issuer, subject)`) would need its issuer
migrated. The registry does not preclude it: moving to a broker later is one
provider entry plus, if connectors should stay distinguishable, a mapping
from a connector claim to a provider name. Recorded so the choice is
revisitable, not foreclosed.

**Keep the `iss` peek, just add a second `DexVerifier` behind
`DEX_ISSUER_URL_2`.** Smallest diff by far. Dropped because it gives no
contract: the second verifier still hard-codes Dex's claim names and its
audience-skip behaviour, `SkipClientIDCheck` survives, nothing enforces
unique issuers, and the GitHub couplings stay inline in the middleware where
#377 has to unpick them. It satisfies "a second IdP" while satisfying none of
"swappable", "audience validated per provider", or "shaped so #377 can switch
to principal ids".

**Verify against every provider until one succeeds.** Removes the need for a
routing rule at all. Dropped: it turns a misconfigured issuer into a silent
cross-acceptance, costs a full verification per registered provider on every
failed request (a cheap DoS amplifier), and makes which provider "wins"
depend on map iteration order, which would then decide which
`external_identities` row a caller resolves to.

## Platform impact

**Migrations.** None. No schema change to `principals` or
`external_identities` (`internal/principals/store.go:78-105`), no new tables,
no backfill. `external_identities.provider` values are unchanged for every
existing caller — that is the point of keeping `name: "dex"` for the legacy
entry and declaring the local-OAuth provider's namespace as `github`.

**Backward compatibility.** All four existing token types keep working
unchanged through step 4, locked by characterization tests that compare the
resulting `*auth.User` field by field against the pre-registry chain. The one
intentional divergence, audience enforcement, is staged behind a metric that
must read zero first. The `ghid` JWT claim is additive; old tokens keep
resolving through the login-only path they use today.

**Resource impact.** One extra map lookup and one interface dispatch per
request. Each OIDC provider holds its own `oidc.IDTokenVerifier` with its own
JWKS cache, so N providers means N background key-set fetches — bounded by
configuration and expected to stay at one or two. No new database
connections; no new outbound calls on the hot path. Step 2 (`ghid`) *removes*
a potential outbound GitHub call from the authentication path for local OAuth
callers.

**Risks and mitigations.**

- *A refactor of the auth path silently changes who authenticates.* Mitigated
  by characterization tests per token type asserting the full `*User`
  (including the unexported discriminators, tested from inside package
  `auth`, as `auth_test.go` already does), plus `MCTL_FEDERATION_DISABLED`
  and keeping the old chain in the tree for one release.
- *Audience enforcement locks out production.* Mitigated by not enforcing it
  in this change: the legacy shim keeps accepting, counts every skip, and
  enforcement lands in a separate PR only after the counter reads zero for
  7 days.
- *Re-resolving groups on refresh drops someone's access unexpectedly.* That
  is the intended correction of stale membership, but the blast radius is
  real: mitigated by `OAUTH_REFRESH_REGROUP` (settable to `false`), by
  falling back to stored groups on resolver error, and by
  `oauth_refresh_regroup_failed_total`.
- *A future provider implementation asserts an identity outside its
  namespace.* Mitigated by the registry-enforced invariant plus
  `federation_provider_contract_violations_total`, and by a test that a
  deliberately misbehaving fake provider returning
  `Provider: auth.ProviderService` is refused.
- *Two providers configured on one issuer make routing ambiguous.* Refused at
  boot, in `config.validate`, in the same place and style as
  `OAUTH_PREREGISTERED_CLIENTS` (`cmd/api/main.go:1237-1249`).
- *`ghid` threading touches the OAuth code and refresh-token storage.*
  Mitigated by keeping the claim optional everywhere and never making a
  missing `ghid` an error — the existing login-only resolution stays as the
  fallback.

**Deployment.** No Helm chart change: env comes from the free-form
`.Values.env` map (`helm/templates/deployment.yaml:39-43`), so
`MCTL_OIDC_PROVIDERS`, `MCTL_FEDERATION_DISABLED` and `OAUTH_REFRESH_REGROUP`
are values-file additions only. `DEX_CLIENT_ID` should be set in the same
change that enables step 4.
