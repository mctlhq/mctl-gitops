# Keep the GitOps token out of git's argv and bind git to the refresh loop's context

## Context

`internal/gitops/reader.go` (`Reader.refresh`) authenticates HTTPS clones of the
GitOps repo by putting the GitHub token in the URL as userinfo
(`url.UserPassword("x-access-token", r.token)`) and passing that URL as an argument to
`git clone` and `git fetch`. On Linux, `/proc/<pid>/cmdline` can be read by any process
in the PID namespace, and `ps`, auditd, eBPF agents and APM collectors record it. That
exposes a live GitHub App installation token for the length of every clone and fetch,
and a fetch runs on every refresh tick (60s for the main reader, 5 min for the roadmap
reader in `cmd/api/main.go`). The fix moves the token out of argv: git gets it from a
credential helper that reads it from the child process's environment
(`/proc/<pid>/environ` can only be read by the same uid or root).

The issue also points out that `RefreshLoop` does not pass its `context.Context` to
`refresh()`. The clone now uses `exec.CommandContext` and bounds each command with
`gitCommandTimeout` (2 min). But each command's context still comes from
`context.Background()`, so cancelling the loop (on shutdown) does not stop a running
git command. A hung remote holds `r.mu` and keeps the goroutine running for up to 2
minutes after `ctx.Done()`. Both problems are in the same file and the same call
sites, so this proposal fixes them together.

## User stories

- AS a platform operator I WANT the GitOps credential never to appear in any process's
  command line SO THAT process listings and process-audit pipelines cannot capture it.
- AS a platform operator I WANT the gitops refresh loop to stop its git subprocesses
  as soon as the server shuts down SO THAT shutdown does not hang on a slow remote
  and does not leak goroutines.
- AS a maintainer I WANT the existing token redactor and the scrub of
  `remote.origin.url` to stay SO THAT other output paths and checkouts left by older
  versions are still covered.

## Acceptance criteria (EARS)

- WHEN `Reader.refresh` runs `git clone` or `git fetch` in HTTPS-token mode THE SYSTEM
  SHALL pass the bare `repoURL` (no userinfo) as the remote argument, and no element of
  the git process's argv SHALL contain the token in raw or percent-encoded form.
- WHEN git needs HTTPS credentials during a refresh THE SYSTEM SHALL supply username
  `x-access-token` and the token from a credential helper. The helper SHALL read the
  token from an environment variable set only on that git child process
  (`cmd.Env`), not on the mctl-api process itself.
- WHILE the credential helper is configured THE SYSTEM SHALL first clear every
  credential helper inherited from system or global git config (`credential.helper=`)
  and scope its own helper to the scheme and host of `repoURL`, so that git never sends
  the token to another host and never runs another helper.
- WHEN git calls the helper with an action other than `get` (`store`, `erase`)
  THE SYSTEM SHALL make the helper exit 0 without output.
- WHILE a refresh runs any git command THE SYSTEM SHALL set `GIT_TERMINAL_PROMPT=0`,
  so a rejected credential fails fast instead of waiting on a prompt.
- WHEN a git command that is not a network command (`reset`, `checkout`, `clean`,
  `rev-parse`, `remote set-url`) runs THE SYSTEM SHALL NOT put the token in its
  environment.
- WHEN the `ctx` passed to `RefreshLoop` is cancelled while a git command is running
  THE SYSTEM SHALL kill that command (with `WaitDelay` still the hard bound) and SHALL
  make `refresh` return within `gitWaitDelay` plus a small margin. `gitCommandTimeout`
  SHALL still cap each command when the context is not cancelled.
- WHEN `refresh` returns, including after its context is cancelled, THE SYSTEM SHALL
  still run the deferred scrub of `remote.origin.url` and the deferred `head` update,
  using a context that is detached from cancellation and has its own short timeout.
- IF a refresh fails because its context was cancelled THEN THE SYSTEM SHALL return
  from `RefreshLoop` without logging that failure at error level.
- WHILE in SSH mode (`sshKeyPath` set) THE SYSTEM SHALL keep the current behaviour:
  no token is resolved or injected, and `GIT_SSH_COMMAND` pins the host key.
- THE SYSTEM SHALL keep `redactTokenLocked` and apply it to all git output as it does
  today.

## Out of scope

- Removing or weakening `redactTokenLocked` (#223). It stays as defence in depth.
- Changing how the token is sourced or rotated (`ghtoken.Source`,
  `GITHUB_APP_TOKEN_FILE`).
- Other git or HTTP callers that use GitHub tokens outside `internal/gitops/reader.go`
  (for example `internal/releaseartifact/resolver.go`, which uses `SetBasicAuth` over
  HTTP and has no argv exposure).
- Changes to Helm or deployed configuration.

## Open questions

- Should the helper be injected with `-c` arguments (visible in argv but containing
  only the env-var reference, never the secret) or with `GIT_CONFIG_COUNT`/`KEY_n`/
  `VALUE_n` environment variables (needs git 2.31 or later)? This proposal uses `-c`,
  which works with any git version. Both keep the secret out of argv.
- The deployed git version in the runtime image (`apk add git` in the `Dockerfile`)
  was not observed directly. Version-sensitive behaviour is limited to scoped
  `credential.<url>.helper` matching and resetting the helper list with an empty value,
  both of which have been in git for many years.
