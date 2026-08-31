# Design: issue-212-repos-sync-proxy-sends-no-credentials-to

## Current state

`internal/api/handlers_repos.go` defines three handlers that proxy to
Backstage's `github-app-connect` plugin, all sharing one client:

```go
var backstageReposClient = &http.Client{Timeout: 15 * time.Second}
```

- `ListRepos` (line ~34): `backstageReposClient.Get(upstream)` against
  `/api/github-app-connect/repos?team=...`.
- `GetRepoInstallURL` (line ~70): `backstageReposClient.Get(upstream)`
  against `/api/github-app-connect/install-url?team=...&service=...&repo=...`.
- `SyncRepos` (line ~124, upstream call at 152-157): builds an
  `http.NewRequestWithContext(r.Context(), "POST", upstream, nil)` and calls
  `backstageReposClient.Do(upReq)` against
  `/api/github-app-connect/repos/sync?team=...&user=...`. None of the three
  ever call `req.Header.Set("Authorization", ...)`.

`SyncRepos` already does the identity part correctly: the `user` query
param is sourced only from `auth.UserFromContext(r.Context())`, never from
the JSON body (`internal/api/handlers_repos_test.go`,
`TestSyncReposIgnoresBodyUserOverridesWithAuthenticated`) — this is the
#197 fix referenced in the issue. Per-team authorization is enforced via
`user.HasTenantAccess(team)` before any of the three handlers touch the
network.

Contrast this with `internal/api/handlers_domains.go`, which proxies to
Backstage's `custom-domains` plugin and had the identical problem after
mctl-portal 951d450 removed that plugin's unauthenticated allowlist. It was
fixed with a small shared helper:

```go
var backstageDomainsClient = &http.Client{Timeout: 15 * time.Second}

func (h *Handlers) authorizeBackstage(req *http.Request) {
    if h.opts.BackstageToken != "" {
        req.Header.Set("Authorization", "Bearer "+h.opts.BackstageToken)
    }
}
```

called on every proxied request before `backstageDomainsClient.Do(req)`.
`BackstageToken` is read from `os.Getenv("BACKSTAGE_TOKEN")` in
`cmd/api/main.go` and threaded through `Config` -> `Options.BackstageToken`
(`internal/api/router.go:60`). Per the issue, that token is
`accessRestricted` in Backstage's `app-config.production.yaml` to
`plugin: custom-domains` — i.e. it is deliberately scoped and will not
authorize calls to `github-app-connect` without an explicit (mctl-portal
side) config change.

`handlers_write.go`'s `notifyBackstage` also sends
`Authorization: Bearer `+h.opts.BackstageToken`, but that call hits a
different Backstage plugin API (`/api/plugin-tenant/v0/tenants`) and is
unaffected by this issue.

## Proposed solution

1. **New credential field**, mirroring `BackstageToken`:
   - `cmd/api/main.go`: `Config.BackstageGithubAppConnectToken string`,
     populated as `os.Getenv("BACKSTAGE_GITHUB_APP_CONNECT_TOKEN")`, next to
     the existing `BackstageToken` line (~line 540).
   - `internal/api/router.go`: `Options.BackstageGithubAppConnectToken
     string`, documented the same way `BackstageToken` is, next to
     `BackstageInternalURL` (~line 60-63).
   - `cmd/api/main.go` (~line 373): wire it into the `Options{}` literal
     alongside `BackstageToken`.

2. **New helper in `handlers_repos.go`**, mirroring
   `authorizeBackstage` exactly (same nil-safety, same log-free no-op when
   unset, so existing local/dev/test setups that don't configure it keep
   working unauthenticated against a permissive local Backstage):

   ```go
   func (h *Handlers) authorizeGithubAppConnect(req *http.Request) {
       if h.opts.BackstageGithubAppConnectToken != "" {
           req.Header.Set("Authorization", "Bearer "+h.opts.BackstageGithubAppConnectToken)
       }
   }
   ```

3. **Call it in all three handlers** right before the request is sent:
   - `ListRepos` / `GetRepoInstallURL`: switch from `backstageReposClient.Get(upstream)`
     to building the request explicitly (`http.NewRequestWithContext(r.Context(), http.MethodGet, upstream, nil)`),
     call `h.authorizeGithubAppConnect(upReq)`, then `backstageReposClient.Do(upReq)`.
     This is the same shape `ListDomains`/`GetDomainStatus` already use in
     `handlers_domains.go` for the same reason — `http.Client.Get` provides
     no hook to set headers.
   - `SyncRepos`: the request is already built with `http.NewRequestWithContext`;
     add one line, `h.authorizeGithubAppConnect(upReq)`, before
     `backstageReposClient.Do(upReq)`.

4. **No change to error handling or response passthrough.** All three
   handlers already forward the upstream status code and body verbatim
   (`w.WriteHeader(resp.StatusCode)`); if Backstage still 401s/403s because
   the companion mctl-portal change (granting the new token
   `plugin: github-app-connect` access, and exempting its identity from the
   `user`-param match at `plugins/github-app-connect-backend/src/router.ts:726-729`)
   hasn't landed yet, callers see that status unchanged — same failure mode
   as today, not a regression, and easy to diagnose from the response body.

5. **Tests**: add a `handlers_repos_test.go` case mirroring
   `TestDomainProxiesSendBearerToken` /
   `TestDomainProxiesOmitAuthWhenTokenUnset` from
   `handlers_domains_test.go` — table-driven over `ListRepos`,
   `GetRepoInstallURL`, `SyncRepos`, asserting the upstream request the
   fake Backstage server receives carries `Authorization: Bearer
   test-token` when the token is configured, and no `Authorization` header
   at all when it is empty.

6. **Helm / deployment**: add `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` to the
   chart's secret env wiring next to the existing `BACKSTAGE_TOKEN` entry
   in `helm/` (values + secret template), sourced from the same Vault path
   pattern the platform already uses for `BackstageToken`, once mctl-portal
   has minted the token. This proposal documents the required env var; the
   actual Vault secret provisioning and Backstage-side token minting is a
   deployment/ops action paired with the mctl-portal change, not a Go code
   change.

## Alternatives

1. **Reuse `BackstageToken` for `github-app-connect` too** (extend the
   existing token's `accessRestricted` scope in mctl-portal's
   `app-config.production.yaml` to cover both `custom-domains` and
   `github-app-connect`, and call `h.authorizeBackstage(upReq)` from the
   repos handlers instead of introducing a new field). Simpler — no new env
   var, no new Helm wiring — but widens the blast radius of a single leaked
   token to two plugins, and couples the two plugins' credential rotation.
   Rejected as the default per the issue's own framing ("different blast
   radii"), but noted in requirements.md as the fallback reviewers can pick
   with a small diff if operational simplicity is preferred over isolation.

2. **Fix only `SyncRepos`, leave `ListRepos`/`GetRepoInstallURL` as-is.**
   The issue's reproduction and title focus on sync. Rejected: all three
   routes proxy the same now-authenticated plugin and share the identical
   root cause (`backstageReposClient` sends no credential); leaving two of
   three unauthenticated would just relocate the same bug report to
   whichever route a user hits next (e.g. onboard-service's repo picker,
   which depends on `ListRepos` and `GetRepoInstallURL`).

3. **Have mctl-api mint/refresh a short-lived Backstage token itself**
   (e.g. via a Backstage service-to-service auth flow) instead of a static
   long-lived env-var token. Rejected as out of proportion for this fix:
   the platform's existing pattern for Backstage-to-mctl-api credentials is
   uniformly a static Vault-backed bearer token (`BackstageToken`,
   `ArgoCDToken`, etc.); introducing a different auth mechanism for just
   this one plugin adds complexity without a concrete driver, and doesn't
   resolve the harder identity-matching problem (Backstage still needs to
   accept *some* stable service identity as exempt from the per-user
   check).

## Platform impact

- **Backward compatibility**: when `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` is
  unset (e.g. local dev, existing test suites, any environment not yet
  carrying the new secret), behavior is byte-for-byte identical to today —
  no `Authorization` header is sent. This makes the mctl-api change safe to
  deploy independently of and before the mctl-portal companion change,
  which is important since the two live in different repos with
  independent release cadences.
- **Migrations**: none. No database or schema changes.
- **Resource impact**: negligible — one extra header set per proxied
  request, no new client, no new dependency.
- **Risks**:
  - *Sequencing risk*: deploying this mctl-api change alone does not fix
    production, since Backstage still needs to (a) accept the new token for
    `plugin: github-app-connect` and (b) exempt its identity from the
    per-user match check. Mitigation: requirements.md and tasks.md both
    flag the mctl-portal side as a hard dependency, and the proposal is
    written so mctl-api's change is a safe, inert no-op until the token is
    actually provisioned.
  - *Credential leak*: a new long-lived bearer token is another secret to
    manage. Mitigation: scope it to `plugin: github-app-connect` only (this
    proposal's chosen alternative), store via the same Vault-backed
    ExternalSecret pattern already used for `BackstageToken`, never log it
    (matches existing `authorizeBackstage` behavior, which never logs the
    token value).
  - *Silent misconfiguration*: if the token is set but Backstage rejects it
    (wrong scope, revoked, etc.), the failure mode is the same 401/403
    passthrough as today — visible to the caller and to existing
    `slog.Error("failed to proxy ... to backstage", ...)` logging on
    transport errors, though a non-2xx response with a body is currently
    not separately logged (matches existing behavior in all three handlers
    and in `handlers_domains.go`; not changed by this proposal).
