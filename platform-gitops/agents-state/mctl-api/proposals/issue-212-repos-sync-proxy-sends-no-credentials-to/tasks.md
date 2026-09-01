# Tasks: issue-212-repos-sync-proxy-sends-no-credentials-to

## Approval decisions — read before starting

1. **This PR does not fix production and must not claim to.** It is step 1
   of 3. Sync stays broken until (a) mctl-portal grants a token
   `plugin: github-app-connect` access and resolves the per-user identity
   check at `router.ts:726-729`, and (b) the token is provisioned in Vault
   and wired into the deployment. Use **`Refs #212`** in the PR body, never
   `Closes #212` — a closing keyword here would mark a P1 production
   breakage resolved while `mctl_sync_repos` still returns 401. #212 closes
   only when a real sync succeeds against production.
2. **File the mctl-portal companion issue before opening this PR**, and cite
   its number in the description. It carries the token grant, the identity
   exemption, and the Vault path. Without it this change is an inert edit
   that reads as a fix, which is the specific way this issue gets forgotten
   in the "done" column.
3. **Task 6 (Helm/env wiring) is dropped from this PR** — see task 6 below.
4. The **second-token** choice (a dedicated
   `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` rather than widening
   `BACKSTAGE_TOKEN`) is **confirmed**. Smaller blast radius and
   independent rotation are worth one extra env var, and the two plugins
   already rotate on different schedules.

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

- [ ] 6. **DROPPED from this PR — do not do this here.** Wiring
  `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` into the chart before the Vault key
  exists points an ExternalSecret at a missing path, and a failing
  ExternalSecret does not fail politely — it can block the whole release
  from syncing, taking unrelated changes down with it. Config goes to
  GitOps **after** the secret exists, not with the code that reads it. The
  correct order is: mint the token in Backstage → write it to Vault → one
  gitops PR adding the env var → deploy. Until then the Go code reads an
  unset env var and sends no header, which is byte-for-byte today's
  behavior. — DoD: no chart/values change in this PR; the required env var
  name and its Vault path are stated in the PR description and in the
  companion mctl-portal issue so whoever provisions it does not have to
  re-derive them.

- [ ] 6a. **Make the unset-token case visible at startup** (depends on 1) —
  log one `slog.Warn` at router construction when
  `BackstageGithubAppConnectToken` is empty, naming the env var and the
  three routes that will proxy without a credential. — DoD: exactly one
  line at startup, not one per request; the token value is never logged.
  Rationale: the design's own risk list names "silent misconfiguration" and
  then leaves it silent — the no-op branch is deliberately quiet, so a
  missing token is indistinguishable from a working one until a user hits a
  401. One startup line converts that into something greppable in
  `mctl_get_service_logs`, and it is also the signal that tells us when
  step 3 of the rollout has actually landed.

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
- [ ] T5. (task 6a) Construct the router with an empty
  `BackstageGithubAppConnectToken` against a capturing logger and assert the
  startup warn fires exactly once and does not contain any token value;
  construct it with a token set and assert it does not fire.

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
