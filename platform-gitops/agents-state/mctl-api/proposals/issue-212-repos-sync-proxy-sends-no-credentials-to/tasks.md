# Tasks: issue-212-repos-sync-proxy-sends-no-credentials-to

- [ ] 1. Add `BackstageGithubAppConnectToken` config plumbing — DoD:
  `cmd/api/main.go` `Config` struct gets a `BackstageGithubAppConnectToken
  string` field populated from `os.Getenv("BACKSTAGE_GITHUB_APP_CONNECT_TOKEN")`
  next to the existing `BackstageToken` line; `internal/api/router.go`
  `Options` gets a matching `BackstageGithubAppConnectToken string` field
  with a doc comment analogous to `BackstageToken`'s; `cmd/api/main.go`
  wires `Config.BackstageGithubAppConnectToken` into the `Options{}`
  literal passed to the router. `go build ./...` succeeds.

- [ ] 2. Add `authorizeGithubAppConnect` helper (depends on 1) — DoD: new
  unexported method on `*Handlers` in `internal/api/handlers_repos.go`,
  structurally identical to `authorizeBackstage` in `handlers_domains.go`
  (sets `Authorization: Bearer <token>` only when
  `h.opts.BackstageGithubAppConnectToken != ""`; no-op otherwise; never
  logs the token value).

- [ ] 3. Wire the helper into `SyncRepos` (depends on 2) — DoD: in
  `internal/api/handlers_repos.go`, call
  `h.authorizeGithubAppConnect(upReq)` after building `upReq` and before
  `backstageReposClient.Do(upReq)` (current lines ~148-154). No other
  behavior of `SyncRepos` changes — the `user` query param still comes only
  from `auth.UserFromContext`, per-team `HasTenantAccess` check unchanged.

- [ ] 4. Wire the helper into `ListRepos` (depends on 2) — DoD: in
  `internal/api/handlers_repos.go`, replace
  `backstageReposClient.Get(upstream)` with an explicit
  `http.NewRequestWithContext(r.Context(), http.MethodGet, upstream, nil)`
  + `h.authorizeGithubAppConnect(upReq)` + `backstageReposClient.Do(upReq)`,
  preserving existing error handling (`slog.Error` + 502 on transport
  error) and response passthrough.

- [ ] 5. Wire the helper into `GetRepoInstallURL` (depends on 2) — DoD:
  same transformation as task 4, applied to `GetRepoInstallURL`'s upstream
  call.

- [ ] 6. Add Helm/env wiring for the new secret (depends on 1) — DoD:
  `helm/` chart's deployment/secret templates and values reference
  `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` alongside the existing
  `BACKSTAGE_TOKEN` entry, following the same Vault-backed ExternalSecret
  pattern already used for `BackstageToken`. Chart lints clean
  (`helm lint` / whatever the repo's existing chart CI check is).

- [ ] 7. Update docs/README references to `BACKSTAGE_TOKEN` env var list, if
  any, to mention the new `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` — DoD: grep
  for `BACKSTAGE_TOKEN` in `*.md` under the repo root and update any env
  var inventory found; skip if none exists.

## Tests

- [ ] T1. Table-driven test in `internal/api/handlers_repos_test.go`,
  modeled on `TestDomainProxiesSendBearerToken` in
  `handlers_domains_test.go`: for each of `ListRepos`, `GetRepoInstallURL`,
  `SyncRepos`, spin up a fake Backstage server (reuse/extend
  `captureBackstage`), configure
  `Options{BackstageGithubAppConnectToken: "test-token", ...}`, invoke the
  handler, and assert the captured upstream request's `Authorization`
  header equals `Bearer test-token`.
- [ ] T2. Companion test asserting that when
  `BackstageGithubAppConnectToken` is empty (zero-value `Options`), the
  captured upstream request for all three handlers has no `Authorization`
  header set at all (not `Bearer ` with an empty suffix) — mirrors the
  "unset token must not produce a malformed header" test already present
  for the domains proxy.
- [ ] T3. Re-run the existing `TestSyncRepos*` suite in
  `handlers_repos_test.go` unmodified and confirm all five still pass —
  proves the credential change does not alter the identity-attribution
  behavior from #197 (user always from `auth.UserFromContext`, 401 on nil
  user, 403 on cross-tenant, 400 on missing team).
- [ ] T4. `go vet ./...` and `golangci-lint run` clean, per this repo's
  `CLAUDE.md` conventions.

## Rollback

The change is additive and gated entirely by whether
`BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` is set:

- If the deployed mctl-api build misbehaves, roll back the image tag via
  the platform's standard service rollback (`mctl_rollback_service` /
  previous Helm release) — no data or schema changes to unwind.
- If only the token itself is the problem (e.g. wrong scope, Backstage
  rejects it), unset `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` via
  `update-config` without rolling back the image; `authorizeGithubAppConnect`
  degrades to today's no-header behavior, restoring the exact pre-change
  (broken-but-known) 401 state rather than introducing a new failure mode.
- No feature flag is needed beyond the token's presence/absence, since the
  helper's no-op branch already serves that purpose.
