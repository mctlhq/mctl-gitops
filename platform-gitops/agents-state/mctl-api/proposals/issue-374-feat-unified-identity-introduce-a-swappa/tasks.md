# Tasks: issue-374-feat-unified-identity-introduce-a-swappa

- [ ] 1. Define the federation contract in `internal/auth/federation.go`:
      `Verified` (an `auth.Identity` plus `Claims`, with **no** field able to
      express an acting/on-behalf subject), `Provider` (`Name`, `Claims`,
      `Verify`), `tokenShape` derived from the existing `isJWT`/`jwtIssuer`
      helpers (`internal/auth/oidc.go:218-240`), and `ErrNoProvider`.
      — DoD: package compiles, `go vet` clean, doc comments state that the
      unverified `iss` peek is routing information only and that `Verified`
      cannot express delegation; no behaviour wired yet.

- [ ] 2. Implement `Registry` with routing and contract enforcement (depends
      on 1): constant-time static-secret match first, then exact normalized
      `iss` → provider lookup, then the single opaque provider; reject a
      `Verified` whose `Identity.Provider` is not the provider's declared
      namespace, whose `Subject` is empty unless
      `Identity.GitHubLoginOnly()` (`internal/auth/principal.go:69`), or
      whose `Kind` is not an `auth.Kind*` constant.
      — DoD: `NewRegistry` refuses duplicate names, duplicate issuers, a name
      colliding with `github`/`service`/`dev`/a `surfaceid` surface name, and
      more than one opaque provider, each with a named error.

- [ ] 3. Implement the static-secret providers in
      `internal/auth/provider_static.go` (depends on 1), wrapping
      `staticServiceUser`, `surfaceTokens`/`surfaceUserFor`,
      `usageWriterToken`/`usageWriterUserFor` (`oidc.go:367-452`) unchanged,
      including the refusal rules for short, shared and duplicated tokens.
      — DoD: identical `auth.Identity` values to `User.Identity()` today
      (`principal.go:114-118`); the existing token-refusal tests in
      `internal/auth/auth_test.go` still pass against the provider.

- [ ] 4. Implement the GitHub opaque provider in
      `internal/auth/provider_github.go` (depends on 1) over
      `GitHubValidator.ValidateIdentity` (`internal/auth/github.go:66`),
      with a `GroupSource` interface whose only implementation wraps
      `resolveGroups` (`oidc.go:620-637`) verbatim.
      — DoD: groups and `*User` fields are byte-identical to the current
      GitHub path for an admin login, a tenant-member login, and a login with
      neither; `ADMIN_USERS` and `gitops.Reader` are untouched.

- [ ] 5. Implement the local MCP OAuth provider in
      `internal/auth/provider_localoauth.go` (depends on 1), declaring
      namespace `github`, registered on `OAuthServer.BaseURL`, delegating to
      `OAuthServer.ValidateJWT` (`internal/auth/oauth_server.go:677-686`).
      — DoD: returns the login-only identity today's code produces, and the
      registry accepts its cross-namespace declaration only because it is
      declared, not inferred.

- [ ] 6. Implement the generic OIDC provider in
      `internal/auth/provider_oidc.go` (depends on 1): configured issuer
      (exact match), required non-empty audience list, configurable
      `subject_claim`, ordered `display_claims` reproducing
      `DexVerifier.Verify`'s `preferred_username` → `email` → `sub` fallback
      (`oidc.go:206-212`), and `groups_claim`.
      — DoD: a Dex-shaped token yields exactly the `*User` `DexVerifier`
      yields today, including `dexIssuer`/`dexSubject`, so
      `external_identities` rows with `provider='dex'` resolve unchanged.

- [ ] 7. Add configuration in `internal/auth/federation_config.go` and
      `cmd/api/main.go` (depends on 2, 6): parse `MCTL_OIDC_PROVIDERS` in
      `loadConfig` (`cmd/api/main.go:912+`), validate it in
      `config.validate` (`main.go:1224-1257`) in the same style as
      `OAUTH_PREREGISTERED_CLIENTS`, and add the legacy shim that synthesizes
      one provider from `DEX_ISSUER_URL`/`DEX_CLIENT_ID` while counting
      `federation_audience_check_skipped_total` when `DEX_CLIENT_ID` is empty.
      — DoD: a malformed value, an entry with no `audiences`, a duplicate
      name or a duplicate issuer each refuse boot with a message naming the
      offending entry; an unset `MCTL_OIDC_PROVIDERS` reproduces today's
      single-Dex configuration.

- [ ] 8. Wire the registry into `auth.Middleware` (depends on 2-7): replace
      the `if/else if` chain (`oidc.go:518-563`) with
      `Registry.Verify` plus one unexported `userFromVerified`, leaving the
      health-check skip, the `Bearer` parsing, the dev-mode branch
      (`oidc.go:498-510`), the `attachPrincipal` call (`oidc.go:565`) and the
      `WWW-Authenticate` behaviour (`oidc.go:650-659`) exactly as they are.
      Gate on `MCTL_FEDERATION_DISABLED` (shape of `killSwitchOn`,
      `main.go:1420-1427`) with the old chain retained for one release.
      — DoD: `go test ./...` green with no change to
      `internal/auth/auth_test.go` assertions; `*User` construction happens
      in exactly one new place.

- [ ] 9. Add federation metrics (depends on 8) following the
      `prometheus.NewCounter` + `init()` pattern of
      `internal/principals/resolver.go:52-57`:
      `federation_token_verifications_total{provider,result}`,
      `federation_verify_duration_seconds{provider}`,
      `federation_audience_check_skipped_total{provider}`,
      `federation_provider_contract_violations_total{provider}`.
      — DoD: all four appear on `/metrics`; an unrouted token increments
      `result="unclaimed"`.

- [ ] 10. Carry the numeric GitHub id into local OAuth tokens (depends on 5):
      switch `internal/api/oauth_handlers.go:250` from
      `GitHubValidator.Validate` to `ValidateIdentity`, thread the id through
      `IssueCode` (`oauth_server.go:523`) and `IssueJWT`
      (`oauth_server.go:568`) as an optional `ghid` claim on `jwtPayload`,
      and add `oauth_jwt_without_github_id_total`.
      — DoD: a token minted after the change resolves via
      `(github, <numeric id>)` with no `GitHubIDLookup` call
      (`internal/principals/resolver.go:197`); a token minted before it still
      resolves through the login-only path; `sub` is still the login.

- [ ] 11. Re-resolve groups on refresh (depends on 10): in
      `RefreshAccessToken` (`oauth_server.go:614-656`) call
      `ResolveGroups` (`oauth_server.go:383`) instead of replaying stored
      groups, behind `OAUTH_REFRESH_REGROUP` (default on), falling back to the
      stored groups on error and counting
      `oauth_refresh_regroup_failed_total`.
      — DoD: a login removed from a gitops tenant loses that group on the next
      refresh; a `TenantResolver` error leaves the refresh successful with
      the stored groups.

- [ ] 12. Document the boundary (depends on 8-11): a new
      `docs/federation.md` covering the provider contract, the registry
      invariants, `MCTL_OIDC_PROVIDERS`, the non-impersonation rule and the
      cut-over order; cross-reference it from `docs/principals.md` and add
      the three new env vars to `README.md` and `helm/values.yaml` under
      `.Values.env` (no chart template change needed,
      `helm/templates/deployment.yaml:39-43`).
      — DoD: an operator can add a second IdP from the doc alone; the doc
      states explicitly that authorization and tenant resolution are
      unchanged and owned by #377.

- [ ] 13. Cut-over steps 3-5 as separate follow-up PRs (depends on 12):
      enable `MCTL_OIDC_PROVIDERS` in staging; set `DEX_CLIENT_ID` in
      production; then, after
      `federation_audience_check_skipped_total == 0` for 7 days, delete the
      legacy shim so a missing audience refuses boot, and delete the retained
      pre-registry chain and `MCTL_FEDERATION_DISABLED`.
      — DoD: each step is its own revertible PR; the final PR removes
      `NewDexVerifier`'s `SkipClientIDCheck` branch (`oidc.go:181-183`).

## Tests

- [ ] T1. Characterization tests, in package `auth` so unexported fields are
      visible: for each of GitHub token, local OAuth JWT, Dex JWT, service
      token, each surface token, usage-writer token and dev mode, assert the
      `*User` produced through the registry is field-for-field equal to the
      one the pre-registry chain produces (`ID`, `Groups`, `service`,
      `githubLogin`, `usageWriter`, `surface`, `githubID`, `dexIssuer`,
      `dexSubject`, `dev`).
- [ ] T2. `User.Identity()` equivalence: for the same seven cases, the
      resulting `auth.Identity` matches the table in `docs/principals.md`.
- [ ] T3. Registry construction refuses: duplicate provider name; duplicate
      normalized issuer; a provider named `github`, `service`, `dev`,
      `telegram` or `portal`; two opaque providers; an OIDC entry with an
      empty `audiences` list.
- [ ] T4. Non-impersonation: a fake provider returning
      `Identity.Provider = auth.ProviderService` is refused and increments
      `federation_provider_contract_violations_total`; a token whose claims
      include `act`/`on_behalf_of`/`sub_for` produces a `*User` with empty
      `ActingPrincipal()` and no `RelaySurface()`.
- [ ] T5. Routing: a JWT whose unverified `iss` matches no provider is 401
      `unclaimed` and no verifier is invoked (assert via a counting fake);
      a JWT whose unverified `iss` claims provider A but is signed by
      provider B's key is refused, not re-routed.
- [ ] T6. Audience: a token with a wrong `aud` is refused by an
      `MCTL_OIDC_PROVIDERS`-configured provider; the legacy shim with an
      empty `DEX_CLIENT_ID` accepts it and increments
      `federation_audience_check_skipped_total`.
- [ ] T7. `ghid`: a JWT with `ghid` yields `(github, <id>, display=login)`
      and no `GitHubIDLookup` call; a JWT without it yields the login-only
      identity and increments `oauth_jwt_without_github_id_total`; `sub`
      remains the login in both.
- [ ] T8. Refresh regroup: groups change after a gitops membership change;
      a `TenantResolver` error leaves the refresh successful with stored
      groups and increments `oauth_refresh_regroup_failed_total`;
      `OAUTH_REFRESH_REGROUP=false` restores replay behaviour.
- [ ] T9. Principal path unchanged: disabled principal still 403, revoked
      identity still 401, store outage still degrades open with
      `principal_resolution_failed_total`, for every provider
      (`internal/auth/principal_test.go`, `internal/principals/resolver_test.go`
      extended, not rewritten).
- [ ] T10. Surface relay unaffected: `relaySubject`
      (`internal/api/handlers_surface_identity.go:176-239`) still produces a
      relayed `*User` with `ActingPrincipal()` and `ViaPrincipalID()` set and
      `admins` stripped, and a surface principal still cannot reach a
      non-relay route.
- [ ] T11. Kill switch: with `MCTL_FEDERATION_DISABLED` set, every T1 case
      takes the pre-registry chain and produces the same `*User`.
- [ ] T12. E2E (`e2e/`): a Dex-shaped login, a GitHub PAT call and an MCP
      OAuth flow all succeed against a server built with the registry.

## Rollback

Per-step, in the order the steps shipped.

- **Steps 8-9 (registry wired).** Set `MCTL_FEDERATION_DISABLED=true` and
  restart; the pre-registry `if/else if` chain in `auth.Middleware` runs
  unchanged. No data was written differently, no schema changed, so no
  cleanup follows. This escape hatch exists until task 13's final PR.
- **Step 10 (`ghid`).** Revert the `oauth_handlers.go`/`oauth_server.go`
  commit. Tokens already minted with `ghid` keep validating, because the
  claim is additive and old code unmarshals into a struct that ignores it;
  affected callers fall back to the login-only resolution path they used
  before, which was never removed.
- **Step 11 (refresh regroup).** Set `OAUTH_REFRESH_REGROUP=false`; the next
  refresh replays the stored groups again. No revert needed.
- **Step 13 (legacy shim removed / audience enforced).** Revert that single
  PR. It is deliberately separate from everything above precisely so that a
  production boot refusal over a missing audience can be undone without
  reverting the registry.
- **Full revert.** Revert the branch. Nothing in this proposal migrates data,
  changes `principals`/`external_identities` schema
  (`internal/principals/store.go:78-105`), alters
  `external_identities.provider` values, or writes new rows in a new shape,
  so a revert leaves no residue beyond local OAuth tokens carrying an unread
  `ghid` claim until they expire.
