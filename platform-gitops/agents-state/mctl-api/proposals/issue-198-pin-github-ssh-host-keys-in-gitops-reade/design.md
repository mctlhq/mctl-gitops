# Design: issue-198-pin-github-ssh-host-keys-in-gitops-reade

## Current state
`internal/gitops/reader.go` defines `Reader` (fields: `repoURL`, `branch`,
`localPath`, `token`, `sshKeyPath`, plus a mutex and `lastSync`), constructed
via `NewReader(repoURL, branch, localPath, token, sshKeyPath string)`
(reader.go:177-186). `refresh()` (reader.go:210-271) picks an auth mode:

```go
switch {
case r.sshKeyPath != "":
    // SSH auth: use key file, accept-new trusts on first connect (TOFU)
    cloneURL = r.repoURL
    sshCmd := fmt.Sprintf("ssh -i %s -o StrictHostKeyChecking=accept-new", r.sshKeyPath)
    sshEnv = []string{"GIT_SSH_COMMAND=" + sshCmd}
case r.token != "":
    // HTTPS auth: inject token into URL
    ...
}
```

`sshEnv` is passed as extra process environment to every `git` invocation
in `refresh()`: the initial `git clone --depth=1 --branch=... ` (reader.go:
238) and, on subsequent syncs, `git fetch` / `reset` / `checkout` / `clean`
via `runGit`/`gitOutput` (reader.go:245-256, 273-287). There is no
`UserKnownHostsFile` override, so with `StrictHostKeyChecking=accept-new`
OpenSSH falls back to the default `~/.ssh/known_hosts` for the process
user, trusting and persisting whatever key is presented on first contact.

`cmd/api/main.go` wires this up: `config` (main.go:445-482) holds
`GitOpsSSHKeyPath string` populated from `GITOPS_SSH_KEY_PATH`
(main.go:538), and `main()` calls
`gitops.NewReader(cfg.GitOpsRepoURL, cfg.GitOpsBranch, cfg.GitOpsLocalPath, cfg.GitOpsToken, cfg.GitOpsSSHKeyPath)`
(main.go:79). The Helm chart (`helm/templates/deployment.yaml:46-49,99-103,
113-118`, `helm/values.yaml:79-82`) optionally mounts a Secret named by
`.Values.gitopsSSHSecret` at `/etc/gitops-ssh/ssh-privatekey` and sets
`GITOPS_SSH_KEY_PATH` accordingly; there is no existing known_hosts
mounting or env var.

`internal/gitops/reader_test.go` exercises `refresh()` entirely against
local `file://`-style bare git repos (`TestRefreshResetsDivergedCache`,
reader_test.go:89-148) — `sshKeyPath` is never set in any existing test, so
the SSH code path currently has zero test coverage.

## Proposed solution
1. **Embed a pinned known_hosts file.** Add
   `internal/gitops/github_known_hosts` containing GitHub's published SSH
   host key lines for `github.com` (RSA, ECDSA, ED25519 — the three
   algorithms currently listed under `ssh_keys` at
   `https://api.github.com/meta`), in standard `known_hosts` format
   (`github.com ssh-rsa AAAA...`, one line per algorithm, `github.com` and
   any published IP entries GitHub itself recommends pinning by hostname).
   Embed it into the binary with `//go:embed github_known_hosts` so no
   extra file needs to ship in the Docker image or be mounted via
   ConfigMap/Secret — it travels with the Go binary like any other
   compiled asset. Reference file: `internal/gitops/known_hosts.go` (new).

2. **Add a `knownHostsPath` field/parameter to `Reader`.**
   Extend `NewReader` to
   `NewReader(repoURL, branch, localPath, token, sshKeyPath, knownHostsPath string) (*Reader, error)`.
   - If `knownHostsPath == ""`, `NewReader` materializes the embedded
     default into a file once (e.g.
     `filepath.Join(os.TempDir(), "mctl-api-github-known-hosts")`, written
     with `0o400` if it doesn't already exist with matching content) and
     stores that resolved path on `r.knownHostsPath`. This keeps the field
     always populated post-construction so `refresh()` never has to special
     case "no path configured."
   - If `knownHostsPath != ""` (test or explicit override), it is used
     verbatim — this is the seam
     `internal/gitops/reader_test.go` uses to point at a fixture file
     containing a deliberately wrong key.
   - Resolving/writing the embedded default at construction time (not
     per-refresh) keeps `refresh()` a pure "run git with these already-known
     args" function and avoids repeated disk writes on every periodic sync.

3. **Change the SSH command construction in `refresh()`** from:
   ```go
   sshCmd := fmt.Sprintf("ssh -i %s -o StrictHostKeyChecking=accept-new", r.sshKeyPath)
   ```
   to:
   ```go
   sshCmd := fmt.Sprintf(
       "ssh -i %s -o StrictHostKeyChecking=yes -o UserKnownHostsFile=%s",
       r.sshKeyPath, r.knownHostsPath,
   )
   ```
   `git clone`/`fetch` will now hard-fail (non-zero exit, output captured
   via `CombinedOutput()`) if the presented host key is not in
   `knownHostsPath`, and that failure already propagates correctly through
   the existing `fmt.Errorf("git clone failed: %w\n%s", err, ...)` /
   `"git fetch failed: %w"` wrapping — no error-handling changes needed
   there.

4. **Wire the new parameter through `cmd/api/main.go`.**
   - Add `GitOpsSSHKnownHostsPath string` to `config` (main.go:451 area),
     sourced from a new `GITOPS_SSH_KNOWN_HOSTS_PATH` env var via
     `os.Getenv` (empty by default, meaning "use the shipped default" —
     mirrors how `GitOpsSSHKeyPath` itself defaults to empty).
   - Update the `gitops.NewReader(...)` call (main.go:79) to pass it
     through.
   - Add `GITOPS_SSH_KNOWN_HOSTS_PATH=` (commented, empty) to
     `.env.example` alongside the existing `GITOPS_REPO_URL`/
     `GITOPS_LOCAL_PATH` entries for discoverability.

5. **Tests** (`internal/gitops/reader_test.go`):
   - A **positive** in-process test: spin up a minimal SSH server (using
     `golang.org/x/crypto/ssh`, added as a direct test-time dependency —
     already present transitively per `go.sum`) bound to `127.0.0.1:0`
     that presents a known, fixed host key pair, and serves `git-upload-pack`
     for a tiny bare repo (or, more simply, only needs to complete the SSH
     transport-layer key exchange since `StrictHostKeyChecking` is enforced
     before user auth / channel work — the test can let the subsequent git
     protocol fail and only assert on the *class* of error, i.e. no
     "host key verification failed" / `REMOTE HOST IDENTIFICATION HAS
     CHANGED` message, or assert success end-to-end if a full fake
     `git-upload-pack` responder is implemented). Point `r.knownHostsPath`
     at a fixture file containing that server's real host key: clone must
     get past host-key checking (any subsequent failure must not be a
     host-key failure).
   - A **negative** test: same fake SSH server, but `knownHostsPath` points
     at a fixture containing a *different* key for the same host
     (`127.0.0.1`/test hostname). `refresh()` must return an error, and the
     error text (from `CombinedOutput()`) must indicate host-key
     verification failure (OpenSSH emits `Host key verification failed` /
     `REMOTE HOST IDENTIFICATION HAS CHANGED`) rather than any other
     failure mode. Assert `localPath` was not populated (no partial clone
     left behind), matching the "SHALL NOT write any repository data"
     requirement.
   - A **flag-composition** test: assert the `GIT_SSH_COMMAND` string built
     by `refresh()` contains `StrictHostKeyChecking=yes` and
     `UserKnownHostsFile=<path>` and does **not** contain `accept-new`
     (cheap regression guard against the flag silently reverting, doesn't
     need a live SSH server).
   - Keep the existing `TestRefreshResetsDivergedCache` and friends
     untouched — they exercise the non-SSH path and must keep passing
     unmodified.

## Alternatives
1. **Fetch `https://api.github.com/meta` at startup/runtime and build
   known_hosts dynamically.** Rejected as the primary mechanism: it
   reintroduces a first-contact trust problem one layer up (now trusting
   whatever `api.github.com` TLS/HTTP response is received at boot,
   dependent on the pod's network path and CA trust store being intact),
   adds a hard runtime dependency on internet egress at startup for a
   control-plane process that otherwise only needs to reach GitHub for the
   gitops clone itself, and doesn't match the issue's explicit ask to "ship
   a pinned known_hosts." A periodic drift-check job against the same
   endpoint remains a reasonable *follow-up* (see Open questions in
   requirements.md), but should not replace the static pinned file for the
   actual host-key check.

2. **Set `GIT_SSH_COMMAND`'s known_hosts path directly from an env var in
   `main.go`, with no embedded default (operator must always supply a
   file).** Rejected: this would make `GITOPS_SSH_KEY_PATH` deployments
   that don't also set a new env var fail closed with a missing-file error
   at every clone, a behavior change bigger than the issue asks for and a
   likely production outage for any existing SSH-based deployment on
   upgrade. Embedding a sane default (GitHub's own keys) and only
   overriding via env var for tests/exceptional cases is safer and matches
   the "make the path configurable for tests" phrasing (tests need to
   override it; production shouldn't need to).

3. **Ship the known_hosts file as a plain file in the Docker image
   (`COPY` in `Dockerfile`) instead of `go:embed`.** Considered because it
   avoids adding a `//go:embed` directive, but rejected: it adds another
   file path that must survive the multi-stage Docker build and be kept in
   sync with `internal/gitops/`, whereas `go:embed` keeps the pinned data
   version-controlled next to the code that consumes it, requires zero
   Dockerfile changes, and works identically for anyone running the binary
   outside the container (e.g. local dev, `go run`).

## Platform impact
- **Migrations:** none — no schema/data migration; purely an SSH-transport
  flag change plus a new embedded asset.
- **Backward compatibility:**
  - HTTPS/token-based gitops deployments (`GitOpsToken` set, no SSH key):
    fully unaffected, this change only touches the `r.sshKeyPath != ""`
    branch of `refresh()`.
  - Existing SSH-based deployments: behavior changes from "trust whatever
    key GitHub presents on first contact, cache it" to "trust only the
    shipped GitHub host keys." Since the target is always `github.com`
    (per `GitOpsRepoURL` defaulting to
    `https://github.com/mctlhq/mctl-gitops.git` / its SSH equivalent) and
    GitHub's host keys are stable, well-published values, this should be
    transparent in the common case. Risk: if a deployment's `GitOpsRepoURL`
    actually points at a different SSH host (e.g. a GitHub Enterprise
    instance, or a mirror) rather than `github.com`, the pinned file would
    not contain that host's key and the clone would start failing closed.
    Mitigation: `knownHostsPath` is fully overridable via
    `GITOPS_SSH_KNOWN_HOSTS_PATH`, so any non-github.com deployment can
    supply its own known_hosts file; this should be called out in the
    rollout/README notes for the SSH auth option.
  - `NewReader`'s signature changes (new trailing parameter) — this is an
    internal package (`internal/gitops`), so the only call site is
    `cmd/api/main.go:79`, which this proposal updates in the same change;
    no external consumers exist.
- **Resource impact:** negligible — one small embedded file (a few hundred
  bytes) and one extra file write at startup when the SSH path is used;
  no additional network calls, no additional running processes.
- **Risks + mitigations:**
  - *Risk:* GitHub rotates its SSH host keys and the pinned file goes
    stale, breaking all SSH-based gitops clones simultaneously.
    *Mitigation:* documented as an Open Question / follow-up (periodic
    drift check); in the meantime, `GITOPS_SSH_KNOWN_HOSTS_PATH` /
    `GITOPS_SSH_KEY_PATH` deployments can fall back to the HTTPS+token auth
    path (`GitOpsToken`) as an operational escape hatch, which this change
    does not touch.
  - *Risk:* a bug in the new file-materialization logic could accidentally
    widen permissions or write to an unexpected path. Mitigation: write
    with `0o400`, write only once (skip if a byte-identical file already
    exists at the resolved path) inside `NewReader` under the same pattern
    already used elsewhere in this file for `//nolint:gosec` trusted-path
    reads, and cover with a unit test asserting the file's permissions and
    content.
