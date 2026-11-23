# Tasks: issue-229-p1-the-gitops-token-is-passed-to-git-in

- [ ] 1. Add `gitTokenEnv` and a pure `gitCredentialArgs(repoURL, token)` in
  `internal/gitops/reader.go`. It returns the `-c credential.helper=` reset, a helper
  scoped to the scheme and host of `repoURL` that reads `$MCTL_GITOPS_TOKEN` and
  answers only `get`, and env `MCTL_GITOPS_TOKEN=<token>` and `GIT_TERMINAL_PROMPT=0`.
  — DoD: unit-tested. The token never appears in the returned args. An unparseable
  URL returns an error.
- [ ] 2. (depends on 1) In `Reader.refresh`, remove the `url.UserPassword` clone URL.
  Clone and fetch get the bare `r.repoURL`, plus `credArgs` before the subcommand and
  `credEnv` in `cmd.Env`. Extend `gitOutput`/`runGit` so only `fetch` gets the
  credential args and env. — DoD: no other git invocation carries the token in its
  env. The deferred `remote set-url` scrub and `redactTokenLocked` are kept unchanged.
  Comments on `refresh` and `redactTokenLocked` are updated so they no longer claim
  that the token is in the URL.
- [ ] 3. Change the signature to `refresh(ctx context.Context)`. `gitOutput(ctx, ...)`
  and `runGit(ctx, ...)` derive `context.WithTimeout(ctx, gitCommandTimeout)`, and so
  does the clone. Keep `WaitDelay`. — DoD: no `context.Background()` left in the
  git-exec paths of `reader.go`.
- [ ] 4. (depends on 3) The deferred head `rev-parse` and scrub use
  `context.WithTimeout(context.WithoutCancel(ctx), gitCleanupTimeout)` (a new
  constant, around 10s). — DoD: the scrub still runs after cancellation.
- [ ] 5. (depends on 3) `RefreshLoop` passes `ctx` and returns early if `ctx.Err()`
  is set before or after a refresh. It does not log cancellation-caused failures at
  error level. — DoD: the loop goroutine exits promptly on `ctx.Done()`.
- [ ] 6. Update every test call site (`reader_test.go`, `principal_snapshot_test.go`,
  `reader_redact_test.go`) to the new signatures. Review the `gitCommandTimeout`
  comment in `internal/auth/oauth_server.go` (~line 1179) for accuracy. — DoD:
  `go vet ./...`, `golangci-lint run` and `go test -p 1 ./internal/gitops/...` pass.

## Tests

- [ ] T1. `TestGitCredentialArgs_NoTokenInArgs`: for raw tokens and tokens with
  characters that need percent-encoding, no returned arg contains the token or its
  `url.UserPassword` encoding. The env contains `MCTL_GITOPS_TOKEN=`, and the
  helper key is scoped to `https://github.com`.
- [ ] T2. `TestRefresh_HTTPSAuthViaCredentialHelper`: an `httptest.Server` wraps
  `net/http/cgi` running `git http-backend` (`GIT_PROJECT_ROOT`,
  `GIT_HTTP_EXPORT_ALL`) behind a Basic-auth check for `x-access-token:<token>`.
  Refresh clones successfully, a second refresh (the fetch path) succeeds, and a
  reader with the wrong token fails fast without hanging. Skip if `git http-backend`
  is unavailable.
- [ ] T3. `TestRefresh_TokenNeverInGitArgv`: put a `git` shim first on `PATH`
  (`t.Setenv`) that appends `"$@"` to a log file and then execs the real git. Run
  clone and fetch against the T2 server, then assert the log contains neither the raw
  nor the encoded token, and that the env of non-network invocations does not contain
  `MCTL_GITOPS_TOKEN` (the shim also logs `env | grep MCTL_GITOPS_TOKEN` per call).
- [ ] T4. `TestRefresh_IgnoresInheritedCredentialHelper`: a `GIT_CONFIG_GLOBAL` file
  that defines a helper writing a marker file. Auth still succeeds and the marker is
  never written.
- [ ] T5. `TestRefresh_ContextCancelStopsHungGit`: an `httptest.Server` whose handler
  blocks until the request is done. Start refresh with a cancellable ctx, cancel after
  about 200ms, and assert refresh returns well under `gitCommandTimeout` (for example
  within `gitWaitDelay` plus 2s).
- [ ] T6. `TestRefreshLoop_ExitsOnCancel`: run `RefreshLoop` against the hanging
  server, cancel, and assert the goroutine returns within the same bound.
- [ ] T7. Existing `TestRefresh_CloneDoesNotPersistTheCredential`,
  `TestRefresh_StripsACredentialLeftByAnEarlierCrash`,
  `TestRefresh_ScrubsEvenWhenTheFetchFails` and the redaction tests still pass. Add an
  assertion that a scrub runs even when the refresh ctx was cancelled before the
  fetch.

## Rollback

All changes are confined to `internal/gitops/reader.go` and its tests. Revert the PR
and cut a release, or pin the previous mctl-api image in
`bootstrap/templates/mctl-platform/mctl-api.yaml`. No data or config migration is
involved. Existing checkouts on the cache emptyDir work with either version, because
both versions pass the remote URL explicitly on fetch and scrub `remote.origin.url`.
If HTTPS auth breaks after rollout, the symptom is "gitops refresh failed" errors and
a stale `LastSync`, while each replica keeps serving its last good checkout. That is
the signal to roll back.
