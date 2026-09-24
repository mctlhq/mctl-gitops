# Tasks: issue-374-feat-unified-identity-introduce-a-swappa

Four separately mergeable slices. Each slice is one pull request that can merge,
deploy and be rolled back without the others. Slices B, C and D each depend on A
being merged, but not on each other.

Mapping to the reviewed proposal's numbering, for traceability:
`A1-A9` = old tasks 1-9, `A10` = old task 12 (docs), `A11` = new (production
canary, replacing the old cut-over step 3), `B1` = old task 10, `C1` = old task
11, `D1-D2` = old task 13 split. Tests keep their old labels: `T1-T6, T9-T12` in
A, `T7` in B, `T8` in C, plus new `T13-T15`.

---

## Slice A — registry, providers, wiring, metrics (behaviour-identical, plus one stated behaviour fix)

- [ ] A1. Define the federation contract in `internal/auth/federation.go`:
      `Verified` (an `auth.Identity` plus `Claims`, with **no** field able to
      express an acting/on-behalf subject), `Provider` (`Name`, `Claims`,
      `Verify`), `tokenShape` derived from the existing `isJWT`/`jwtIssuer`
      helpers (`internal/auth/oidc.go:218-240`), and `ErrNoProvider`.
      — DoD: package compiles, `go vet` clean, doc comments state that the
      unverified `iss` peek is routing information only and that `Verified`
      cannot express delegation; no behaviour wired yet.

- [ ] A2. Implement `Registry` with routing and contract enforcement (depends
      on A1): constant-time static-secret match first, then exact normalized
      `iss` → provider lookup, then the single opaque provider; reject a
      `Verified` whose `Identity.Provider` is not the provider's declared
      namespace, whose `Subject` is empty unless
      `Identity.GitHubLoginOnly()` (`internal/auth/principal.go:69-71`), or
      whose `Kind` is not an `auth.Kind*` constant (`principal.go:46-50`).
      — DoD: `NewRegistry` refuses, each with a named error: a duplicate
      provider name; a duplicate normalized issuer; a name colliding with a
      **reserved name** `github`, `service`, `dev`, `agent`, or `dex` when the
      entry is not the Dex entry; a name colliding with a `surfaceid` surface
      name (`internal/surfaceid/store.go:50-51`); more than one opaque
      provider. `agent` is reserved for #376's `ProviderAgent = "agent"`, with
      that reason in the code comment.

- [ ] A3. Implement the static-secret providers in
      `internal/auth/provider_static.go` (depends on A1), wrapping
      `staticServiceUser`, `surfaceTokens`/`surfaceUserFor`,
      `usageWriterToken`/`usageWriterUserFor` (`oidc.go:367-452`), keeping the
      refusal rules for short, shared and duplicated tokens — **and fixing the
      service-token compare**. Add one shared helper
      `secretMatches(configured, presented string) bool` that returns false on
      an empty `configured` and otherwise
      `subtle.ConstantTimeCompare([]byte(configured), []byte(presented)) == 1`
      (`crypto/subtle` is already imported, `oidc.go:19`), and route all three
      static providers through it. This replaces the plain `==` at
      `oidc.go:448`, which is a deliberate behaviour fix (timing only, same
      accept/reject outcome), stated as such in requirements.md and design.md.
      — DoD: identical `auth.Identity` values to `User.Identity()` today
      (`principal.go:114-118`); the existing token-refusal tests in
      `internal/auth/auth_test.go` still pass; no `==`/`!=` comparison against a
      presented token remains in the static path; T13 and T14 pass.

- [ ] A4. Implement the GitHub opaque provider in
      `internal/auth/provider_github.go` (depends on A1) over
      `GitHubValidator.ValidateIdentity` (`internal/auth/github.go:66`), with a
      `GroupSource` interface whose only implementation wraps `resolveGroups`
      (`oidc.go:620-637`) verbatim.
      — DoD: groups and `*User` fields are identical to the current GitHub path
      for an admin login, a tenant-member login, and a login with neither;
      `ADMIN_USERS` (`github.go:88-95`) and `gitops.Reader` are untouched.

- [ ] A5. Implement the local MCP OAuth provider in
      `internal/auth/provider_localoauth.go` (depends on A1), declaring
      namespace `github`, registered on `OAuthServer.BaseURL`, delegating to
      `OAuthServer.ValidateJWT` (`internal/auth/oauth_server.go:677-686`).
      — DoD: returns the login-only identity today's code produces, and the
      registry accepts its cross-namespace declaration only because it is
      declared, not inferred.

- [ ] A6. Implement the generic OIDC provider in
      `internal/auth/provider_oidc.go` (depends on A1): configured issuer
      (exact match), required non-empty audience list, an
      `audience_enforcement` mode of `audit` or `enforce`, configurable
      `subject_claim`, ordered `display_claims` reproducing
      `DexVerifier.Verify`'s `preferred_username` → `email` → `sub` fallback
      (`oidc.go:206-212`), and `groups_claim`.
      — DoD: a Dex-shaped token yields exactly the `*User` `DexVerifier` yields
      today, including `dexIssuer`/`dexSubject`, so `external_identities` rows
      with `provider='dex'` resolve unchanged; in `audit` mode a wrong `aud` is
      accepted and counted, in `enforce` mode it is refused.

- [ ] A7. Add configuration in `internal/auth/federation_config.go` and
      `cmd/api/main.go` (depends on A2, A6): parse `MCTL_OIDC_PROVIDERS` in
      `loadConfig` (`cmd/api/main.go:932+`), validate it in `config.validate`
      (`main.go:1233-1249`) in the same style as `OAUTH_PREREGISTERED_CLIENTS`
      (`main.go:1297-1329`), and add the legacy shim that synthesizes one
      provider from `DEX_ISSUER_URL`/`DEX_CLIENT_ID` while counting
      `federation_audience_check_skipped_total` when `DEX_CLIENT_ID` is empty.
      The shim is synthesized only when no explicit entry claims the Dex
      issuer; boot logs which of the two is active.
      — DoD: a malformed value, an entry with no `audiences`, an invalid
      `audience_enforcement`, a duplicate name or a duplicate issuer each
      refuse boot with a message naming the offending entry; an unset
      `MCTL_OIDC_PROVIDERS` reproduces today's single-Dex configuration exactly.

- [ ] A8. Wire the registry into `auth.Middleware` (depends on A2-A7): replace
      the `if/else if` chain (`oidc.go:518-563`) with `Registry.Verify` plus one
      unexported `userFromVerified`, leaving the health-check skip
      (`oidc.go:481-484`), the `Bearer` parsing (`oidc.go:512-516`), the
      dev-mode branch (`oidc.go:498-510`), the `attachPrincipal` call
      (`oidc.go:565`) and the `WWW-Authenticate` behaviour (`oidc.go:650-659`)
      exactly as they are. Gate on `MCTL_FEDERATION_DISABLED` (shape of
      `killSwitchOn`, `main.go:1421-1427`) with the old chain retained until
      slice D.
      — DoD: `go test ./...` green with no change to
      `internal/auth/auth_test.go` assertions; `*User` construction happens in
      exactly one new place.

- [ ] A9. Add federation metrics (depends on A8) following the
      `prometheus.NewCounter` + `init()` pattern of
      `internal/principals/resolver.go:52-57`:
      `federation_token_verifications_total{provider,result}`,
      `federation_verify_duration_seconds{provider}`,
      `federation_audience_check_skipped_total{provider}`,
      `federation_audience_mismatch_total{provider}`,
      `federation_provider_contract_violations_total{provider}`.
      — DoD: all five appear on `/metrics`; an unrouted token increments
      `result="unclaimed"`; the two audience counters are distinct — skipped
      means no decision was computed, mismatch means a decision was computed,
      came out negative, and the token was accepted anyway.

- [ ] A10. Document the boundary (depends on A8, A9): a new
      `docs/federation.md` covering the provider contract, the registry
      invariants and reserved names (including why `agent` is reserved), the
      `MCTL_OIDC_PROVIDERS` schema with `audience_enforcement`, the
      non-impersonation rule, the constant-time static-secret rule, and the
      cut-over order; cross-reference it from `docs/principals.md` and add the
      new env vars to `README.md` and `helm/values.yaml` under `.Values.env`
      (no chart template change needed).
      — DoD: an operator can add a second IdP from the doc alone; the doc states
      explicitly that authorization and tenant resolution are unchanged and
      owned by #377, and that the audience flag day is a separate issue.

- [ ] A11. Production canary in audit mode (depends on A10; operational, not
      code). mctl-api has no staging deployment (`mctl-preprod` is production)
      and `replicaCount: 1` (`helm/values.yaml:1`), so this runs in production:
      set `MCTL_OIDC_PROVIDERS` to an explicit Dex entry with real `audiences`
      and `"audience_enforcement": "audit"`. The shim is not synthesized for
      that issuer; it stays in the tree as the rollback path.
      — DoD: after at least 7 days,
      `federation_audience_mismatch_total{provider="dex"} == 0` and
      `federation_token_verifications_total{provider="dex",result="ok"}` holds
      its pre-change rate. A non-zero mismatch counter is a finding, not a
      failure: it names a client minting an audience we did not configure, and
      blocks slice D until that client is reconciled. Rollback: unset
      `MCTL_OIDC_PROVIDERS`, the shim returns.

---

## Slice B — numeric GitHub id in local OAuth JWTs (depends on slice A)

- [ ] B1. Carry the numeric GitHub id into local OAuth tokens: switch
      `internal/api/oauth_handlers.go:251` from `GitHubValidator.Validate` to
      `ValidateIdentity` (`internal/auth/github.go:66`), thread the id through
      `IssueCode` (`oauth_server.go:523`) and `IssueJWT`
      (`oauth_server.go:568-583`) as an optional `ghid` claim on `jwtPayload`
      (`oauth_server.go:704-710`), teach the local-OAuth provider to use it, and
      add `oauth_jwt_without_github_id_total`. Update `docs/federation.md`.
      — DoD: a token minted after the change resolves via
      `(github, <numeric id>)` with no `GitHubIDLookup` call
      (`internal/principals/resolver.go:186-204`); a token minted before it
      still resolves through the login-only path; `sub` is still the login; T7
      passes.

---

## Slice C — groups re-resolved on refresh (depends on slice A)

- [ ] C1. Re-resolve groups on refresh: in `RefreshAccessToken`
      (`oauth_server.go:614-656`) call `ResolveGroups`
      (`oauth_server.go:383-395`) instead of replaying the groups stored by
      `IssueRefreshToken` (`oauth_server.go:585-611`), behind
      `OAUTH_REFRESH_REGROUP` (default on), falling back to the stored groups on
      error and counting `oauth_refresh_regroup_failed_total`. Update
      `docs/federation.md`.
      — DoD: a login removed from a gitops tenant loses that group on the next
      refresh; a `TenantResolver` error leaves the refresh successful with the
      stored groups; `OAUTH_REFRESH_REGROUP=false` restores replay; T8 passes.
      This is the only slice that changes authorization *timing*, so it is
      approved or dropped on its own.

---

## Slice D — audience flag day and shim removal (own follow-up issue)

File this as a separate GitHub issue before starting; it is the only step that
can refuse a production boot, so it gets its own approval.

- [ ] D1. Flip the Dex provider entry to `"audience_enforcement": "enforce"`,
      gated on A11's metrics reading clean.
      — DoD: a Dex token with a wrong `aud` is refused with 401; Dex logins
      still work; `federation_audience_mismatch_total` stays zero. Rollback: set
      the entry back to `audit`, one values change.

- [ ] D2. Remove the legacy path (depends on D1): delete the
      `DEX_ISSUER_URL`/`DEX_CLIENT_ID` shim, `NewDexVerifier`'s
      `SkipClientIDCheck` branch (`oidc.go:181-183`), the `DEX_ISSUER_URL`
      default (`cmd/api/main.go:999`), the retained pre-registry chain and
      `MCTL_FEDERATION_DISABLED`. A provider with no audience now refuses boot.
      — DoD: `go test ./...` green after deleting the pre-registry
      characterization baselines; the boot refusal is covered by T15; its own
      revertible PR.

---

## Tests

Slice A:

- [ ] T1. Characterization tests, in package `auth` so unexported fields are
      visible: for each of GitHub token, local OAuth JWT, Dex JWT, service
      token, each surface token, usage-writer token and dev mode, assert the
      `*User` produced through the registry is field-for-field equal to the one
      the pre-registry chain produces (`ID`, `Groups`, `service`, `githubLogin`,
      `usageWriter`, `surface`, `githubID`, `dexIssuer`, `dexSubject`, `dev`).
- [ ] T2. `User.Identity()` equivalence: for the same seven cases, the resulting
      `auth.Identity` matches the table in `docs/principals.md`.
- [ ] T3. Registry construction refuses: duplicate provider name; duplicate
      normalized issuer; a provider named `github`, `service`, `dev`, `agent`,
      `telegram` or `portal`; two opaque providers; an OIDC entry with an empty
      `audiences` list; an invalid `audience_enforcement` value. The `agent`
      case has a comment naming #376 so it is not "cleaned up" later.
- [ ] T4. Non-impersonation: a fake provider returning
      `Identity.Provider = auth.ProviderService` is refused and increments
      `federation_provider_contract_violations_total`; a token whose claims
      include `act`/`on_behalf_of`/`sub_for` produces a `*User` with empty
      `ActingPrincipal()` and no `RelaySurface()`.
- [ ] T5. Routing: a JWT whose unverified `iss` matches no provider is 401
      `unclaimed` and no verifier is invoked (assert via a counting fake); a JWT
      whose unverified `iss` claims provider A but is signed by provider B's key
      is refused, not re-routed.
- [ ] T6. Audience: in `enforce` mode a token with a wrong `aud` is refused; in
      `audit` mode the same token is accepted and increments
      `federation_audience_mismatch_total`; the legacy shim with an empty
      `DEX_CLIENT_ID` accepts it and increments
      `federation_audience_check_skipped_total` without touching the mismatch
      counter.
- [ ] T9. Principal path unchanged: disabled principal still 403, revoked
      identity still 401, store outage still degrades open with
      `principal_resolution_failed_total`, for every provider
      (`internal/auth/principal_test.go`, `internal/principals/resolver_test.go`
      extended, not rewritten).
- [ ] T10. Surface relay unaffected:
      `internal/api/handlers_surface_identity.go:176-239` still produces a
      relayed `*User` with `ActingPrincipal()` and `ViaPrincipalID()` set and
      `admins` stripped (`auth.NewRelayedUser`, `oidc.go:287-302`), and a
      surface principal still cannot reach a non-relay route.
- [ ] T11. Kill switch: with `MCTL_FEDERATION_DISABLED` set, every T1 case takes
      the pre-registry chain and produces the same `*User`.
- [ ] T12. E2E (`e2e/`): a Dex-shaped login, a GitHub PAT call and an MCP OAuth
      flow all succeed against a server built with the registry.
- [ ] T13. Constant-time compare, behaviour: table test over `secretMatches`
      with an empty configured secret (no match, no comparison against the
      presented token), an equal secret, a same-length secret differing in the
      first byte, a same-length secret differing in the last byte, and a
      different-length secret. Asserts the accept/reject outcome is identical to
      the pre-change `staticServiceUser` for every case.
- [ ] T14. Constant-time compare, pinned in source: a test that reads
      `internal/auth/provider_static.go` (and the remaining static path in
      `oidc.go`) and asserts it references `subtle.ConstantTimeCompare` and
      contains no `==`/`!=` comparison against the presented token. Precedent
      for source-scanning tests in this repo:
      `TestMainWiresEveryStoreIntoReadiness` (`cmd/api/main_test.go:461-462`)
      and `TestPortalAllowlist_CoversEveryRegisteredTool`
      (`internal/mcp/portal_allowlist_test.go:119-120`). This exists because a
      behavioural test cannot observe timing, so nothing else would stop a
      future edit reverting to `==` — the failure mode the review called out.

Slice B:

- [ ] T7. `ghid`: a JWT with `ghid` yields `(github, <id>, display=login)` and no
      `GitHubIDLookup` call; a JWT without it yields the login-only identity and
      increments `oauth_jwt_without_github_id_total`; `sub` remains the login in
      both.

Slice C:

- [ ] T8. Refresh regroup: groups change after a gitops membership change; a
      `TenantResolver` error leaves the refresh successful with stored groups and
      increments `oauth_refresh_regroup_failed_total`;
      `OAUTH_REFRESH_REGROUP=false` restores replay behaviour.

Slice D:

- [ ] T15. Flag day: an OIDC provider entry with no `audiences` refuses boot
      (`config.validate`); a Dex token with a wrong `aud` is refused with 401;
      the `SkipClientIDCheck` branch no longer exists in the tree (source pin,
      same style as T14).

---

## Rollback

Per slice, independently, in the order the slices shipped.

- **Slice A (registry + constant-time fix).** Set
  `MCTL_FEDERATION_DISABLED=true` and restart; the pre-registry `if/else if`
  chain in `auth.Middleware` runs unchanged. No data was written differently, no
  schema changed, so no cleanup follows. This escape hatch exists until D2. Note
  that the kill switch also restores the plain `==` service-token compare, since
  it restores the old chain wholesale — acceptable for a short-lived revert, and
  a reason not to leave the kill switch enabled.
- **Slice A11 (canary).** Unset `MCTL_OIDC_PROVIDERS`; the legacy Dex shim is
  synthesized again from `DEX_ISSUER_URL`/`DEX_CLIENT_ID`. One values change, no
  code revert, no restart ordering concern.
- **Slice B (`ghid`).** Revert the `oauth_handlers.go`/`oauth_server.go` commit.
  Tokens already minted with `ghid` keep validating, because the claim is
  additive and old code unmarshals into a struct that ignores it
  (`oauth_server.go:741`); affected callers fall back to the login-only
  resolution path they used before, which was never removed.
- **Slice C (refresh regroup).** Set `OAUTH_REFRESH_REGROUP=false`; the next
  refresh replays the stored groups again. No code revert needed.
- **Slice D1 (enforce).** Set `audience_enforcement` back to `audit`. One values
  change.
- **Slice D2 (shim removed).** Revert that single PR. It is deliberately the
  last and smallest change precisely so that a production boot refusal over a
  missing audience can be undone without reverting the registry.
- **Full revert.** Revert the branch. Nothing in this proposal migrates data,
  changes `principals`/`external_identities` schema
  (`internal/principals/store.go:78-105`), alters
  `external_identities.provider` values, or writes new rows in a new shape, so a
  revert leaves no residue beyond local OAuth tokens carrying an unread `ghid`
  claim until they expire.
</content>
