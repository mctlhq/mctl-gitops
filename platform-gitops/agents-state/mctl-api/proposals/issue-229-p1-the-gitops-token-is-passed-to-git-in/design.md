# Design: issue-229-p1-the-gitops-token-is-passed-to-git-in

## Current state

All references are to `internal/gitops/reader.go` unless noted.

- `Reader.refresh()` (line ~359) takes `r.mu`, resolves the credential once per
  refresh into `r.token` (`ghtoken.Resolve(r.tokenSource)`), and selects a mode:
  - SSH (`r.sshKeyPath != ""`): `cloneURL = r.repoURL`, and
    `sshEnv = GIT_SSH_COMMAND=...` from `buildSSHCommand`.
  - HTTPS token (`r.token != ""`): `u.User = url.UserPassword("x-access-token", r.token)`
    and `cloneURL = u.String()`. **The token is now inside a string that becomes argv.**
  - Otherwise: an anonymous `r.repoURL`.
- Clone: `exec.CommandContext(ctx, "git", "clone", "--depth=1", "--branch="+r.branch,
  "--single-branch", cloneURL, r.localPath)` with
  `ctx = context.WithTimeout(context.Background(), gitCommandTimeout)`.
- Fetch: `r.runGit(sshEnv, "fetch", "--depth=1", cloneURL, r.branch)`. That goes
  through `gitOutput`, which also builds its context from `context.Background()` with
  `gitCommandTimeout` (2 min) and `cmd.WaitDelay = gitWaitDelay` (5 s).
- A deferred `remote set-url origin r.repoURL` scrubs the userinfo that `git clone`
  persists into `.git/config`, on every return path. It is pinned by
  `TestRefresh_CloneDoesNotPersistTheCredential`,
  `TestRefresh_StripsACredentialLeftByAnEarlierCrash` and
  `TestRefresh_ScrubsEvenWhenTheFetchFails` in `reader_test.go`.
- `redactTokenLocked` removes the raw and percent-encoded token from git output
  (#223). It is tested in `reader_redact_test.go` and by `TestRedactToken`.
- `RefreshLoop(ctx, interval)` (line ~320) calls `r.refresh()` without `ctx`, so
  cancelling the loop only takes effect between ticks. A running git command keeps
  `r.mu` for up to `gitCommandTimeout`. `internal/auth/oauth_server.go` (~line 1179)
  explicitly reasons about that lock being held "for up to gitCommandTimeout".
- Callers: `cmd/api/main.go` starts `gitReader.RefreshLoop(ctx, 60*time.Second)` and
  `roadmapGit.RefreshLoop(ctx, 5*time.Minute)`, with `ctx` derived from `rootCtx`, so
  it is cancelled at shutdown. The HTTPS credential comes from `gitOpsTokenSource()`
  (`GITHUB_APP_TOKEN_FILE`, then `GITOPS_REPO_TOKEN`, then `GITHUB_TOKEN`).
- Tests call `r.refresh()` directly in `reader_test.go` and `principal_snapshot_test.go`.
- The runtime image installs git with `apk add --no-cache ca-certificates git
  openssh-client` (`Dockerfile`), so `/bin/sh` is busybox ash, which is POSIX enough
  for a `!f() { ...; }; f` helper.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`: mctl-api runs
  with `replicaCount: 2`, `GITOPS_REPO_URL: https://github.com/mctlhq/mctl-gitops.git`,
  `GITOPS_BRANCH: main` and `GITOPS_LOCAL_PATH: /data/mctl-gitops`. It runs in HTTPS
  mode, so this is the code path that leaks. No `GITOPS_SSH_KEY_PATH` showed up in the
  lines grepped.
- `$MCTL_GITOPS_ROOT/services/*`: mctl-api is not a tenant service there. It is
  deployed through the bootstrap template above.
- No mctl MCP calls were made. The change does not depend on runtime state beyond the
  HTTPS mode confirmed above. The deployed git version was not observed (see Open
  questions in requirements.md).

## Proposed solution

### 1. Credential via helper and child env, not URL

Add a small, pure function so it can be unit-tested:

```go
// gitCredentialArgs returns the -c arguments that make git obtain HTTPS
// credentials from the environment variable gitTokenEnv, and the env entries to
// put on the child process. The token itself never appears in the returned args.
func gitCredentialArgs(repoURL, token string) (args []string, env []string, err error)
```

- `const gitTokenEnv = "MCTL_GITOPS_TOKEN"` (with a `//nolint:gosec` G101 note: it
  is a variable name, not a credential).
- `args`:
  - `-c credential.helper=` clears helpers inherited from system and global config.
  - `-c credential.<scheme>://<host>.helper=!f() { test "$1" = get || exit 0; echo
    username=x-access-token; echo "password=$MCTL_GITOPS_TOKEN"; }; f`, where
    scheme and host come from `url.Parse(repoURL)`. If the URL cannot be parsed,
    the function returns an error and refresh fails closed. It must not fall back to
    an unscoped helper.
  - `-c credential.useHttpPath=false` (explicit, so path-based matching cannot turn
    the helper off).
- `env`: `MCTL_GITOPS_TOKEN=<token>` and `GIT_TERMINAL_PROMPT=0`.

In `refresh()`:
- In the HTTPS case, set `cloneURL = r.repoURL` (no userinfo) and compute
  `credArgs, credEnv`. Delete the `url.UserPassword` construction.
- Clone: `git <credArgs...> clone ... r.repoURL r.localPath`, with
  `cmd.Env = append(os.Environ(), sshEnv..., credEnv...)`.
- Fetch: add a network variant of `gitOutput` (for example a `gitOpts{env, preArgs}`
  struct, or a separate `fetchEnv`/`preArgs` parameter) so that only `fetch` gets
  `credArgs`/`credEnv`. `reset`, `checkout`, `clean`, `rev-parse` and
  `remote set-url` keep the env without the token.
- Keep the deferred `remote set-url origin r.repoURL` scrub. A new clone no longer
  writes userinfo, but checkouts on the existing emptyDir from older versions still
  carry it (`TestRefresh_StripsACredentialLeftByAnEarlierCrash` stays valid).
- Keep `redactTokenLocked` unchanged and still applied in `gitOutput` and on clone
  output.

Exposure after the change: the token exists in the mctl-api process memory (as
today), in `cmd.Env` of the `git`, `git-remote-https` and helper-shell children
(`/proc/<pid>/environ`, which is mode 0400 for the owning uid), and on the helper's
stdout pipe to git. Nothing world-readable carries it.

### 2. Context propagation

- Change the signature to `refresh(ctx context.Context) error`. `RefreshLoop` passes
  its `ctx` to both the initial and the per-tick call. Before calling, it returns if
  `ctx.Err() != nil`. If `refresh` fails and `ctx.Err() != nil`, it returns (logging
  at debug or info at most), instead of logging an error.
- Change `gitOutput(ctx, ...)` and `runGit(ctx, ...)` to build their timeout as
  `context.WithTimeout(ctx, gitCommandTimeout)`. Do the same for the clone.
  `WaitDelay` is unchanged.
- The two deferred cleanups (the head `rev-parse` and the `remote set-url` scrub) use
  `cleanupCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), gitCleanupTimeout)`
  (a new constant, for example 10s). That way the scrub still runs when shutdown
  cancels a refresh mid-flight, which preserves the invariant "no credential on disk
  when refresh returns".
- Update all test call sites to `r.refresh(context.Background())` (or `t.Context()`).
- Update the comment in `internal/auth/oauth_server.go` only if its wording is no
  longer accurate. The lock is still bounded by `gitCommandTimeout` per command, so
  most likely no change is needed.

## Alternatives

1. **`http.extraHeader` with a Basic `Authorization` header, passed through
   `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_0`/`GIT_CONFIG_VALUE_0`.** This needs no shell
   and nothing in argv. Dropped as the primary option because the header is sent on
   every request, including redirects to other hosts when `http.followRedirects`
   permits. It also needs git 2.31 or later, and the base64 header value would get
   past the current redactor unless the redactor learns that form as well. The
   scoped credential helper only answers for the configured host.
2. **`GIT_ASKPASS` pointing at a script file that echoes the env var.** This works
   too, but it needs a file written to disk (permissions, a temp-file lifecycle like
   `resolveKnownHostsPathLocked`), and it is also prompted for the username unless
   the URL carries one. The inline `!` helper needs no file.
3. **Use go-git in-process instead of the git CLI.** This removes subprocesses
   entirely, but it is a large rewrite of clone, fetch, reset and clean semantics
   that the existing tests pin. That is out of proportion to a P1 leak fix.
4. **Keep the token in the URL and only shorten the exposure.** Rejected: any
   exposure of argv is still capturable by audit pipelines.

## Platform impact

- **Migrations:** none. Existing checkouts on the emptyDir keep working: fetch passes
  the bare URL explicitly, and the scrub still cleans legacy userinfo.
- **Backward compatibility:** SSH mode and anonymous mode are unchanged. The
  signature change to `refresh` is package-private.
- **Resources:** one extra short-lived `sh` process for each credential lookup per
  network git command. Negligible.
- **Risks and mitigations:**
  - *A system or global credential helper in the image intercepts the request or
    stores the token.* Mitigated by resetting with `credential.helper=` first, and by
    the helper ignoring `store`/`erase`.
  - *Shell quoting of the helper:* the helper text is a constant and never
    interpolates the token. The host in the config key comes from the operator-set
    `GITOPS_REPO_URL` (same trust level as the other args) and is validated by
    `url.Parse`.
  - *The helper is not consulted (scope mismatch), so auth silently stops working.*
    Mitigated by an integration test against a real `git http-backend` behind Basic
    auth, and by `GIT_TERMINAL_PROMPT=0`, which turns a mismatch into a fast, visible
    refresh error instead of a hang.
  - *Cancelling mid-clone leaves a partial `.git`.* This is already possible today on
    timeout. The next refresh takes the fetch path, followed by `reset --hard`. No new
    failure mode.
  - Rollout: 2 replicas update in a rolling fashion. A broken auth path would show up
    as "gitops refresh failed" logs and a stale `LastSync`, while the replica keeps
    serving its last good checkout.
