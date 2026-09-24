# Design: issue-374-feat-unified-identity-introduce-a-swappa

## Current state

### One middleware, four token types, an unverified peek

`auth.Middleware` (`internal/auth/oidc.go:469-575`) is the whole
authentication boundary. Its body is a literal `if/else if` chain:

1. `staticServiceUser(token)` (`oidc.go:446-452`) — compares the bearer token
   with `MCTL_AGENT_SERVICE_TOKEN` using a plain `==` (`oidc.go:448`), yields
   `NewServiceUser()`.
2. `surfaceUserFor(surfaces, token)` (`oidc.go:430-441`) — `subtle.ConstantTimeCompare`
   against the per-surface tokens read at construction by `surfaceTokens()`
   (`oidc.go:401-426`), yields `NewSurfaceUser(name)`.
3. `usageWriterUserFor(usageWriter, token)` (`oidc.go:391-396`) —
   `subtle.ConstantTimeCompare`, yields `NewUsageWriterUser()`.
4. `isJWT(token)` (`oidc.go:218-220`, three dot-separated parts) then
   `jwtIssuer(token)` (`oidc.go:224-240`), which base64-decodes the payload
   **without verifying the signature** and reads `iss`. If it equals
   `oauth.BaseURL` the token goes to `OAuthServer.ValidateJWT`
   (`oauth_server.go:677-686`); otherwise it goes to `DexVerifier.Verify`
   (`oidc.go:190-215`), or is refused if `dex == nil`.
5. Everything else is assumed to be a GitHub token and goes to
   `GitHubValidator.ValidateIdentity` (`internal/auth/github.go:66`), then
   `resolveGroups(login, validator, resolver)` (`oidc.go:620-637`).

There is no provider interface. Adding an IdP means editing this chain.

Note the inconsistency in steps 1-3: two of the three static-secret checks are
constant-time and the third is not. `crypto/subtle` is already imported in this
file (`oidc.go:19`), so the plain `==` is an omission, not a dependency choice.

### One OIDC verifier, one issuer, optional audience

`NewDexVerifier` (`oidc.go:173-186`) constructs a single
`oidc.IDTokenVerifier` from `DEX_ISSUER_URL`. When `DEX_CLIENT_ID` is empty it
sets `cfg.SkipClientIDCheck = true` (`oidc.go:181-183`) — every audience is
accepted. Both values are read in `loadConfig` (`cmd/api/main.go:999-1000`),
with `DEX_ISSUER_URL` carrying a hard-coded default of
`https://ops.mctl.ai/api/dex`. A Dex init failure only logs a warning and
leaves `dexVerifier` nil (`cmd/api/main.go:97-107`).

`DexVerifier.Verify` takes `Groups` straight from the token claims and derives
`User.ID` from `preferred_username`, then `email`, then `sub`
(`oidc.go:206-212`). It sets the unexported `dexIssuer`/`dexSubject`, which is
what makes `User.Identity()` return `(dex, iss, sub)` at
`principal.go:121-122`.

### What happens after verification (and must not change)

Every branch converges on `attachPrincipal` (`oidc.go:565, 594-611`):
`User.Identity()` (`principal.go:109-129`) → `PrincipalResolver.ResolvePrincipal`
(`principal.go:75-77`) → `principals.Resolver.ResolvePrincipal`
(`internal/principals/resolver.go:126`) → the store. A disabled principal is
403, a revoked identity 401, anything else degrades open with
`principal_resolution_failed_total` (`resolver.go:52-57`).

The security model of `*auth.User` rests on unexported fields with a documented
rationale (`oidc.go:44-95`): `service`, `githubLogin`, `usageWriter`, `surface`,
`actingPrincipal`, `relaySurface`, `githubID`, `dexIssuer`, `dexSubject`, `dev`,
`principalID`, `viaPrincipalID`. Only constructors inside package `auth` set
them, so no caller can claim to be the service principal by naming itself
`mctl-agent`.

### The GitHub couplings this boundary must isolate

- `ADMIN_USERS` → `GitHubValidator.IsAdmin(login)` (`github.go:88-95`), reached
  only through `resolveGroups` (`oidc.go:623`) and `OAuthServer.ResolveGroups`
  (`oauth_server.go:383`).
- Tenant membership by GitHub login: `strings.EqualFold(m.UserID, login)`
  (`internal/gitops/reader.go:109-130`), reached through
  `Reader.GetTenantsForUser` (`reader.go:758`).
- Local MCP OAuth runs only through GitHub OAuth: the callback calls
  `GitHubValidator.Validate` (`internal/api/oauth_handlers.go:251`) — dropping
  the numeric id `fetchUser` has already fetched (`github.go:97-129`) — and
  issues a code with the resolved groups (`oauth_handlers.go:262`).
  `jwtPayload` is `{iss, sub, groups, iat, exp}` (`oauth_server.go:704-710`);
  `ValidateJWT` returns `NewGitHubUser(payload.Subject, payload.Groups)`, so the
  identity is login-only and resolution goes through the
  `ResolveGitHubLogin` / live `GitHubIDLookup` path (`resolver.go:186-204`).
- Surface links accept only `github:<login>` principals
  (`internal/surfaceid/store.go:206`, enforced again at
  `internal/api/handlers_surface_identity.go:207`).
- Groups in local OAuth tokens are frozen at mint: `IssueRefreshToken` stores
  them (`oauth_server.go:585-611`) and `RefreshAccessToken` replays them
  (`oauth_server.go:614-656`), so a gitops membership change can take up to
  `OAUTH_REFRESH_TOKEN_TTL` (30 days by default, `cmd/api/main.go:1001`) to
  land.

### Deployment reality that shapes the cut-over

mctl-api has **no staging deployment**: `mctl-preprod` is production, and the
chart runs `replicaCount: 1` (`helm/values.yaml:1`), so there is no
replica-level canary either. Any "try it somewhere safe first" step has to be
expressed inside the single production process. That is why audience validation
gets an audit mode below rather than a staging soak.

## Proposed solution

### Shape: a provider registry inside package `auth`

Add a federation boundary as new files in `internal/auth`, not a new top-level
package:

- `internal/auth/federation.go` — `Provider`, `Verified`, `Registry`, registry
  construction and invariants, metrics.
- `internal/auth/provider_static.go` — the three static-secret providers
  (service, surface, usage-writer), the shared constant-time match helper, and
  the dev identity.
- `internal/auth/provider_github.go` — the opaque GitHub PAT provider.
- `internal/auth/provider_localoauth.go` — the local HS256 MCP OAuth JWT
  provider, wrapping `OAuthServer.ValidateJWT`.
- `internal/auth/provider_oidc.go` — the generic OIDC JWT provider, of which
  Dex becomes one instance.
- `internal/auth/federation_config.go` — parsing and validation of
  `MCTL_OIDC_PROVIDERS`, plus the legacy `DEX_ISSUER_URL`/`DEX_CLIENT_ID` shim.

It lives in package `auth` because `*auth.User`'s safety property is that its
discriminating fields are unexported and set only by constructors in this
package (`oidc.go:44-95`). A provider in another package could not set them, so
we would have to export them — exactly the weakening the existing comments
argue against. Providers therefore return **data**, and `auth` mints the
`*User`.

### The contract

```go
// Verified is everything a provider may assert. It has no field able to
// express "speaking for someone else"; that is the non-impersonation
// invariant of this boundary, enforced by the type, not by review.
type Verified struct {
    Identity Identity // Provider, Issuer, Subject, Display, Kind
    Claims   Claims   // Groups, PreferredUsername, Email, Expiry, Raw
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

`tokenShape` is computed once per request: `opaque` vs `jwt` plus the unverified
`iss` from the existing `jwtIssuer` helper. Nothing but routing reads it, and
that is stated in the doc comment, because the current code already relies on
this peek and the risk is that a future reader mistakes it for a trust
decision.

`Registry.Verify(ctx, raw)`:

1. constant-time match against every static-secret provider (unchanged order:
   service, surface, usage-writer);
2. for a JWT, exact lookup of the normalized `iss` in an issuer→provider map
   (local OAuth server registers `oauth.BaseURL`; each OIDC provider registers
   its configured issuer);
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
  cannot produce a `service` (or, once #376 lands, an `agent`) identity, or
  claim another IdP's subjects. The one modelled exception is the local-OAuth
  provider, whose declared identity namespace is `github` by design (it mints
  only for GitHub-verified logins, `oauth_server.go:681-684`); it declares that
  namespace explicitly rather than deriving it.
- `v.Identity.Subject != ""` unless `v.Identity.GitHubLoginOnly()`
  (`principal.go:69-71`).
- `v.Identity.Kind` is one of the three `auth.Kind*` constants
  (`principal.go:46-50`), matching what the principal store already requires.

`Middleware` then maps `*Verified` to a `*User` through one unexported
function, `userFromVerified`, which is the only new place a `*User` is built
and which sets the unexported discriminators from the provider's declared kind
and name — never from token claims.

### One behaviour fix: the service-token compare

`staticServiceUser` compares with `token == serviceToken` (`oidc.go:448`). The
surface check (`oidc.go:433`) and the usage-writer check (`oidc.go:392`)
already use `subtle.ConstantTimeCompare`, and `crypto/subtle` is already
imported in the file (`oidc.go:19`). Wrapping the function "unchanged" would
carry a timing-unsafe compare of the platform's most privileged credential
across the refactor and, worse, a characterization test would then *lock it in*.

So this proposal makes it an explicit, stated behaviour fix, not a refactor:

- all three static-secret providers match through one helper,
  `secretMatches(configured, presented string) bool`, which returns false
  immediately on an empty `configured` and otherwise returns
  `subtle.ConstantTimeCompare([]byte(configured), []byte(presented)) == 1`;
- `staticServiceUser` (or its provider) calls that helper, so
  `MCTL_AGENT_SERVICE_TOKEN` is compared in constant time;
- the accept/reject outcome is unchanged for every input, so the
  characterization tests still apply — what changes is only the timing signal;
- the compare is pinned two ways. A behavioural table test covers empty,
  equal, same-length-differing, and different-length secrets; and a
  source-scanning test asserts that no `==`/`!=` comparison against the
  presented token survives in `provider_static.go` and that the file references
  `subtle.ConstantTimeCompare`. Source-scanning tests have precedent in this
  repo: `TestMainWiresEveryStoreIntoReadiness` reads `main.go` and asserts over
  its text (`cmd/api/main_test.go:461-462`), as does
  `TestPortalAllowlist_CoversEveryRegisteredTool`
  (`internal/mcp/portal_allowlist_test.go:119-120`). A behavioural test cannot
  observe constant-timeness, so without the source pin nothing stops a future
  edit from reverting to `==`.

This is the only intentional behaviour change in slice A, and it is called out
as such in requirements.md so it is reviewed rather than discovered.

### Non-impersonation, by construction

Constraint 4 of the issue is enforced four ways:

1. `Verified` carries no acting/on-behalf field. `actingPrincipal`,
   `relaySurface` and `viaPrincipalID` are set only by `NewRelayedUser`
   (`oidc.go:287-302`), which is unreachable from the registry.
2. The static providers return a compiled-in subject (`ServiceUserID`,
   `SurfacePrincipalPrefix+name`, `UsageWriterUserID`); there is no path from a
   token body to a service subject.
3. The provider-namespace invariant means no JWT provider can return
   `Provider: auth.ProviderService`.
4. `agent` is a reserved provider name at boot (see below), so no federation
   provider can pre-empt the `(agent, ...)` namespace that #376 introduces for
   delegated agent identity.

The two existing on-behalf paths stay untouched: the `mctl-agents-approve`
`approver` input gated on `IsService()`
(`internal/api/handlers_write.go:155-196`) and the surface relay
(`handlers_surface_identity.go:176-239`), which keeps calling
`auth.AttachPrincipal` itself.

### Configuration and swappability

New variable `MCTL_OIDC_PROVIDERS`, a JSON array parsed in `loadConfig` and
validated in `config.validate` (`cmd/api/main.go:1233-1249`), alongside the
existing `OAUTH_PREREGISTERED_CLIENTS` precedent, which already refuses boot on
a malformed value (`main.go:1309-1329`):

```json
[
  {
    "name": "dex",
    "issuer": "https://ops.mctl.ai/api/dex",
    "audiences": ["mctl-api"],
    "audience_enforcement": "audit",
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
entry in this variable — the `SkipClientIDCheck` branch (`oidc.go:181-183`) is
not reachable from it. `audience_enforcement` is `audit` or `enforce` and
exists solely to make the production canary possible; it defaults to `enforce`
for a new entry, and the canary sets it to `audit` explicitly.

Registry invariants refused at boot:

- duplicate provider name;
- duplicate normalized issuer (two providers claiming one `iss` would make
  routing order-dependent);
- a provider name colliding with a **reserved name**: `github`, `service`,
  `dev`, `agent`, or `dex` when the entry is not the Dex entry itself.
  `agent` is reserved for #376's `ProviderAgent = "agent"`, so a federation
  provider can never mint `(agent, ...)` rows;
- a provider name colliding with a registered surface name
  (`surfaceid.SurfaceTelegram`, `surfaceid.SurfacePortal`,
  `internal/surfaceid/store.go:50-51`) — `docs/principals.md` already forbids a
  surface named after an auth provider, and this is the same rule from the
  other side, because both write into one `external_identities.provider`
  namespace (`internal/principals/store.go:78-105`);
- more than one opaque-token provider.

Replacing Dex is then: change the entry's `issuer`/`audiences`, keep `name`
(existing `external_identities` rows with `provider='dex'` keep resolving), or
add a second entry under a new name and migrate users by linking.

### Isolating the GitHub couplings without changing them

The GitHub provider is constructed with a `GroupSource` interface:

```go
type GroupSource interface{ GroupsFor(ctx context.Context, login string) []string }
```

whose only implementation wraps today's `resolveGroups(login, validator,
resolver)` verbatim (`oidc.go:620-637`). `ADMIN_USERS` and
`gitops.Reader.GetTenantsForUser` stay exactly where they are and return
exactly what they return today — a characterization test locks the output for
the admin, tenant-member and neither cases. #377 replaces the implementation
behind `GroupSource` with a principal-keyed one without touching any provider.
Nothing about admin determination or tenant membership changes here.

### Local OAuth tokens carry the numeric GitHub id (slice B)

`internal/api/oauth_handlers.go:251` calls `o.GitHubValidator.Validate`, which
throws away the numeric id that `fetchUser` has already fetched and cached
(`github.go:66, 97-129`). Switch that one call to `ValidateIdentity`, thread the
id through `IssueCode` (`oauth_server.go:523`) → the authorization code entry →
`IssueJWT` (`oauth_server.go:568-583`), and add an optional `ghid` claim to
`jwtPayload` (`oauth_server.go:704-710`).

This is additive and backward compatible: `verifyJWT` unmarshals into the
struct (`oauth_server.go:741`), so an old token simply has `ghid == 0`. The
local-OAuth provider then returns `(github, <ghid>, display=<login>)` when
present and the existing login-only identity otherwise, counting
`oauth_jwt_without_github_id_total`. The benefit is concrete: the login-only
path in `principals.Resolver.resolve` (`resolver.go:186-204`) can call out to
GitHub (`GitHubIDLookup`) on the authentication path, and with `ghid` it does
not. `sub` stays the login, because tenant membership still matches on the
login (`reader.go:109-130`) and moving that is #377. `prn_` is deliberately not
minted into the token: it would put the principal store on the OAuth callback
path, which today is allowed to degrade open.

### Groups re-resolved on refresh (slice C)

`RefreshAccessToken` (`oauth_server.go:614-656`) replays groups stored with the
refresh token, for up to `RefreshTokenTTL` (30 days). Re-resolve with the same
`ResolveGroups` (`oauth_server.go:383-395`), same inputs, same rules — only
later in time — behind `OAUTH_REFRESH_REGROUP` (default on). On resolver error,
fall back to the stored groups and count `oauth_refresh_regroup_failed_total`; a
gitops outage must never fail a refresh. This is the one change with an
authorization-*timing* effect, which is why it is its own slice and its own
approval decision.

### Observability

Metrics, following the existing `prometheus.NewCounter` + `init()` registration
pattern (`internal/principals/resolver.go:52-57`):

- `federation_token_verifications_total{provider,result}` — `ok`, `invalid`,
  `unclaimed`;
- `federation_verify_duration_seconds{provider}`;
- `federation_audience_check_skipped_total{provider}` — the legacy Dex shim
  with no `DEX_CLIENT_ID`; no audience decision was even computed;
- `federation_audience_mismatch_total{provider}` — audit mode: an audience
  decision *was* computed and came out negative, and the token was accepted
  anyway. This is the canary gate;
- `federation_provider_contract_violations_total{provider}` — should be
  permanently zero; non-zero means a provider returned an identity outside its
  namespace;
- `oauth_jwt_without_github_id_total` (slice B);
- `oauth_refresh_regroup_failed_total` (slice C).

The two audience counters are deliberately distinct. "We never checked" and
"we checked, it failed, we let it through" are different operational facts, and
only the second one can gate a flag day.

### Cut-over: a production canary, not a staging soak

There is no staging deployment and `replicaCount: 1` (`helm/values.yaml:1`), so
every step below happens in production and is gated on metrics rather than on
an environment.

1. **Slice A — registry, behaviour-identical (plus the constant-time fix).**
   Populated from today's env vars only. `federation_token_verifications_total{result="ok"}`
   per provider should match the pre-change traffic shape, and
   `principal_resolution_failed_total` must not rise. Rollback:
   `MCTL_FEDERATION_DISABLED=true`.
2. **Slice B — `ghid` in newly minted local OAuth JWTs.** Watch
   `oauth_jwt_without_github_id_total` fall towards zero over one
   `OAUTH_REFRESH_TOKEN_TTL`.
3. **Slice C — regroup on refresh.** Watch `oauth_refresh_regroup_failed_total`
   and support traffic. Rollback: `OAUTH_REFRESH_REGROUP=false`.
4. **Production canary in audit mode.** Set `MCTL_OIDC_PROVIDERS` to an
   explicit Dex entry with real `audiences` and
   `"audience_enforcement": "audit"`. That entry claims the Dex issuer, so the
   legacy shim is not synthesized (two registrations on one issuer is a boot
   refusal) — "alongside the shim" means the shim code stays in the tree as the
   rollback path, reachable by unsetting one env var, not that both run at
   once. Boot logs which of the two is active. The canary is genuinely safe
   because audit mode cannot refuse a token: it only counts. Gate for at least
   7 days: `federation_audience_mismatch_total{provider="dex"} == 0` and
   `federation_token_verifications_total{provider="dex",result="ok"}` holding
   its pre-change rate. A non-zero mismatch counter is the finding this step
   exists to produce — it means some real Dex client mints tokens for an
   audience we did not configure, and the flag day would have locked those
   users out.
5. **Slice D — flag day, as its own follow-up issue.** Flip
   `audience_enforcement` to `enforce`, then delete the legacy shim, the
   `SkipClientIDCheck` branch (`oidc.go:181-183`), the retained pre-registry
   chain and `MCTL_FEDERATION_DISABLED`. This is the only step that can refuse
   a production boot, so it gets its own issue, its own approval and its own
   revertible PR.

`MCTL_FEDERATION_DISABLED` (same shape as `PRINCIPALS_DISABLED`,
`cmd/api/main.go:206, 1421-1427`) restores the pre-registry chain. The old
chain stays in the tree, exercised by the existing tests in
`internal/auth/auth_test.go`, until slice D.

## Alternatives

**A new top-level `internal/federation` package.** Cleaner layering on paper,
and the option to unit-test providers without importing `auth`. Dropped because
`*auth.User`'s discriminators (`service`, `githubLogin`, `surface`,
`usageWriter`, `actingPrincipal`) are unexported precisely so that only `auth`
can set them (`oidc.go:44-95`), and `auth.Identity` lives in `auth` too
(`principal.go:52-63`). A separate package means exporting those fields or
duplicating the type across a translation layer — trading a real security
property for a package boundary. The providers are already isolated files with
narrow constructor-injected dependencies, which gets most of the testability
without the cost. If the package ever needs splitting, `Provider` is the seam.

**External broker: Dex as the only upstream, with connectors.** One JWKS, one
issuer, connector management outside mctl-api, and genuinely one code path for
human identity. Dropped as the *now* answer for four reasons taken from this
codebase: mctl-api must keep terminating static service tokens
(`oidc.go:446-452`) and its own HS256 MCP OAuth JWTs (`oauth_server.go:677`),
neither of which any upstream can mint, so the multi-verifier problem is renamed
rather than removed; the GitHub PAT path is an opaque-token check against
`api.github.com/user` (`github.go:97-129`) that Dex cannot front; a broker in
front of every request is a new SPOF where today a Dex failure at boot only
disables Dex (`cmd/api/main.go:97-107`); and every existing
`external_identities` row keyed on the current Dex `iss`
(`store.go:78-105`, `UNIQUE(provider, issuer, subject)`) would need its issuer
migrated. The registry does not preclude it: moving to a broker later is one
provider entry plus, if connectors should stay distinguishable, a mapping from
a connector claim to a provider name. Recorded so the choice is revisitable,
not foreclosed.

**Keep the `iss` peek, just add a second `DexVerifier` behind
`DEX_ISSUER_URL_2`.** Smallest diff by far. Dropped because it gives no
contract: the second verifier still hard-codes Dex's claim names and its
audience-skip behaviour, `SkipClientIDCheck` survives, nothing enforces unique
issuers, nothing reserves the `agent` namespace, and the GitHub couplings stay
inline in the middleware where #377 has to unpick them. It satisfies "a second
IdP" while satisfying none of "swappable", "audience validated per provider",
or "shaped so #377 can switch to principal ids".

**Verify against every provider until one succeeds.** Removes the need for a
routing rule at all. Dropped: it turns a misconfigured issuer into a silent
cross-acceptance, costs a full verification per registered provider on every
failed request (a cheap DoS amplifier), and makes which provider "wins" depend
on map iteration order, which would then decide which `external_identities` row
a caller resolves to.

**Enforce audiences immediately and require `DEX_CLIENT_ID`.** One PR, no audit
mode, no dual counters. Dropped because with no staging deployment and
`replicaCount: 1` the first evidence that some client mints a different
audience would be a production outage on the login path. Audit mode buys that
evidence for the cost of one counter and one config field.

## Platform impact

**Migrations.** None. No schema change to `principals` or `external_identities`
(`internal/principals/store.go:78-105`), no new tables, no backfill.
`external_identities.provider` values are unchanged for every existing caller —
that is the point of keeping `name: "dex"` for the legacy entry and declaring
the local-OAuth provider's namespace as `github`.

**Backward compatibility.** All four existing token types keep working
unchanged through step 4, locked by characterization tests that compare the
resulting `*auth.User` field by field against the pre-registry chain. Two
intentional divergences, both stated: the service-token compare becomes
constant-time (same outcome, different timing), and audience enforcement
eventually refuses mismatched tokens — staged behind a counter that must read
zero first. The `ghid` JWT claim is additive; old tokens keep resolving through
the login-only path they use today.

**Resource impact.** One extra map lookup and one interface dispatch per
request. Each OIDC provider holds its own `oidc.IDTokenVerifier` with its own
JWKS cache, so N providers means N background key-set fetches — bounded by
configuration and expected to stay at one or two. No new database connections;
no new outbound calls on the hot path. Slice B *removes* a potential outbound
GitHub call from the authentication path for local OAuth callers.

**Risks and mitigations.**

- *A refactor of the auth path silently changes who authenticates.* Mitigated by
  characterization tests per token type asserting the full `*User` (including
  the unexported discriminators, tested from inside package `auth`, as
  `auth_test.go` already does), plus `MCTL_FEDERATION_DISABLED` and keeping the
  old chain in the tree until slice D.
- *The characterization tests lock in the timing-unsafe compare.* Mitigated by
  fixing the compare in the same slice, by the shared `secretMatches` helper,
  and by the source-scanning pin test — a behavioural test cannot see timing,
  so the pin has to read the source.
- *Audience enforcement locks out production, with no staging to catch it.*
  Mitigated by audit mode: the canary computes the audience decision and counts
  `federation_audience_mismatch_total` without refusing anything, for 7 days,
  before slice D flips to `enforce`.
- *Re-resolving groups on refresh drops someone's access unexpectedly.* That is
  the intended correction of stale membership, but the blast radius is real:
  mitigated by making it its own slice (C), by `OAUTH_REFRESH_REGROUP`
  (settable to `false`), by falling back to stored groups on resolver error,
  and by `oauth_refresh_regroup_failed_total`.
- *A future provider implementation asserts an identity outside its namespace,
  including the `agent` namespace #376 is about to claim.* Mitigated by the
  registry-enforced namespace invariant, the reserved-name boot check,
  `federation_provider_contract_violations_total`, and a test that a
  deliberately misbehaving fake provider returning `Provider:
  auth.ProviderService` is refused.
- *Two providers configured on one issuer make routing ambiguous.* Refused at
  boot, in `config.validate`, in the same place and style as
  `OAUTH_PREREGISTERED_CLIENTS` (`cmd/api/main.go:1233-1249`). The legacy shim
  yields to an explicit entry on the same issuer rather than colliding with it.
- *`ghid` threading touches the OAuth code and refresh-token storage.*
  Mitigated by keeping the claim optional everywhere and never making a missing
  `ghid` an error — the existing login-only resolution stays as the fallback.

**Deployment.** No Helm chart change: env comes from the free-form
`.Values.env` map (`helm/templates/deployment.yaml`), so `MCTL_OIDC_PROVIDERS`,
`MCTL_FEDERATION_DISABLED` and `OAUTH_REFRESH_REGROUP` are values-file
additions only. `DEX_CLIENT_ID` becomes redundant once the explicit provider
entry is in place, and is removed with the shim in slice D.
</content>
