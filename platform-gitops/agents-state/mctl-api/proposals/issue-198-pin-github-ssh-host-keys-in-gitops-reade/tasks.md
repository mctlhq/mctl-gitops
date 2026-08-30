# Tasks: issue-198-pin-github-ssh-host-keys-in-gitops-reade

- [ ] 1. Add `internal/gitops/github_known_hosts` with GitHub's currently
      published SSH host key lines (RSA, ECDSA, ED25519 for `github.com`,
      per `https://api.github.com/meta`), plus
      `internal/gitops/known_hosts.go` with a `//go:embed github_known_hosts`
      byte slice (e.g. `githubKnownHosts`).
      DoD: file compiles into the binary; a quick `go run` smoke check
      confirms the embedded content is non-empty and matches the checked-in
      file byte-for-byte.

- [ ] 2. Add `knownHostsPath` field to `Reader` and extend `NewReader` to
      `NewReader(repoURL, branch, localPath, token, sshKeyPath, knownHostsPath string) (*Reader, error)`
      (depends on 1) — DoD: when `knownHostsPath == ""`, `NewReader`
      materializes `githubKnownHosts` to a resolved on-disk path (written
      with `0o400`, skipped if a byte-identical file already exists) and
      stores that path; when `knownHostsPath != ""`, it is stored verbatim
      with no write. `go vet`/`go build ./...` pass.

- [ ] 3. Update `refresh()`'s SSH branch to build
      `ssh -i %s -o StrictHostKeyChecking=yes -o UserKnownHostsFile=%s`
      using `r.sshKeyPath` and `r.knownHostsPath`, replacing the
      `accept-new` flag and its stale comment (depends on 2) — DoD: no
      other branch of `refresh()` (HTTPS/token, no-auth) is touched;
      `golangci-lint run` and `go vet` clean.

- [ ] 4. Wire the new parameter through `cmd/api/main.go`: add
      `GitOpsSSHKnownHostsPath string` to `config`, source it from
      `GITOPS_SSH_KNOWN_HOSTS_PATH` (empty default), pass it as the new
      trailing argument to `gitops.NewReader(...)` at main.go:79 (depends
      on 2) — DoD: `go build ./...` passes; existing env vars unaffected.

- [ ] 5. Document the new env var: add
      `# GITOPS_SSH_KNOWN_HOSTS_PATH=` (commented, with a one-line
      explanation) to `.env.example` near `GITOPS_REPO_URL`/
      `GITOPS_LOCAL_PATH` (depends on 4) — DoD: `.env.example` updated,
      no functional change.

- [ ] 6. Write the SSH auth flag regression test: assert the
      `GIT_SSH_COMMAND` string built for the SSH branch contains
      `StrictHostKeyChecking=yes` and `UserKnownHostsFile=<path>` and does
      not contain `accept-new` (depends on 3) — DoD: test fails on the old
      code (verify by temporarily reverting task 3 locally) and passes on
      the new code.

- [ ] 7. Build a minimal in-process SSH test fixture using
      `golang.org/x/crypto/ssh` (add as a direct dependency; already
      present transitively) that binds `127.0.0.1:0`, presents a fixed
      test host key pair, and completes the SSH transport handshake
      (depends on 3) — DoD: fixture is reusable from both the positive and
      negative tests below; `go.mod`/`go.sum` updated via `go mod tidy`.

- [ ] 8. Add the negative test: point `knownHostsPath` at a fixture
      containing a *different* key for the fixture server's host;
      `refresh()` must return an error whose text indicates host-key
      verification failure (`Host key verification failed` /
      `REMOTE HOST IDENTIFICATION HAS CHANGED`), and `localPath` must not
      be populated afterward (depends on 7) — DoD: test fails against the
      pre-change `accept-new` behavior and passes against the new code.

- [ ] 9. Add the positive test: point `knownHostsPath` at a fixture
      containing the fixture server's real host key; assert the clone
      progresses past host-key checking (no host-key-failure error text),
      either by fully faking `git-upload-pack` for a true end-to-end
      success or by asserting the specific absence of host-key-failure
      error classes if a full protocol fake is out of scope (depends on 7)
      — DoD: test is deterministic and does not depend on network access
      to real GitHub.

- [ ] 10. Run `go fmt ./...`, `go vet ./...`, `golangci-lint run`, and the
      full `go test ./...` (per CLAUDE.md conventions) — DoD: all green,
      including the untouched pre-existing `internal/gitops` tests
      (`TestRefreshResetsDivergedCache` and friends).

## Tests
- [ ] T1. Unit test: `GIT_SSH_COMMAND` contains
      `StrictHostKeyChecking=yes` + `UserKnownHostsFile=<path>`, never
      `accept-new` (task 6).
- [ ] T2. Unit test: mismatched host key fails `refresh()` closed with a
      host-key-verification error and leaves `localPath` unpopulated
      (task 8) — this is the acceptance-criteria test the issue explicitly
      asks for.
- [ ] T3. Unit test: matching/pinned host key allows the clone to proceed
      past host-key verification (task 9).
- [ ] T4. Unit test: `NewReader` with `knownHostsPath == ""` materializes
      the embedded default to disk with `0o400` permissions and expected
      content; calling it twice does not rewrite/duplicate the file
      (task 2).
- [ ] T5. Regression: existing `internal/gitops` test suite
      (`TestRefreshResetsDivergedCache`, `TestReadTenant`, etc.) continues
      to pass unmodified, confirming the non-SSH paths are untouched.

## Rollback
- The change is confined to `internal/gitops/reader.go`,
  `internal/gitops/known_hosts.go` (new), `internal/gitops/github_known_hosts`
  (new), `cmd/api/main.go`, and `.env.example` — a straightforward
  `git revert` of the merge commit fully restores the previous
  `accept-new` behavior with no data migration to undo.
- If GitHub's host keys change and the pinned file goes stale before a fix
  can be rolled out, operators have two immediate mitigations without a
  code rollback: (a) set `GITOPS_SSH_KNOWN_HOSTS_PATH` to point at an
  operator-supplied known_hosts file with the updated key, or (b) switch
  the affected deployment to HTTPS+token auth (`GitOpsToken` /
  `GITOPS_REPO_TOKEN`) as an escape hatch, since that path is entirely
  unaffected by this change.
- No database or GitOps-repo state is modified by this change, so there is
  no forward data to clean up on rollback — reverting the binary is
  sufficient.

## Operator decisions (approve, 2026-08-30)

Context the proposal could not see: **this SSH path is dead in production
today.** `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml:28`
sets `GITOPS_REPO_URL: https://github.com/mctlhq/mctl-gitops.git`, and
`GITOPS_SSH_KEY_PATH` / `gitopsSSHSecret` appear nowhere in mctl-gitops. So
`r.sshKeyPath` is empty in the live control plane and `refresh()` takes the
token branch. The fix is still worth landing — it removes a TOFU footgun
that would arm itself the moment anyone switches to SSH — but it carries no
production risk and no urgency, and nothing about it can break the running
control plane. Say this in the PR description so the reviewer does not read
the change as touching a live credential path.

Open questions, resolved:

1. **Keeping the pinned keys current → option (a), static committed file.**
   Treat updates as a normal reviewed code change. The CI drift check
   against `https://api.github.com/meta` is a good idea but is a separate
   follow-up issue, filed by the operator after this merges — not part of
   this PR.
2. **No Helm chart change.** `GITOPS_SSH_KNOWN_HOSTS_PATH` exists for tests
   and local development only; production uses the shipped default. Do not
   touch `helm/values.yaml` or `helm/templates/deployment.yaml`.
3. **Fail closed, confirmed.** If the known_hosts material is missing or
   unreadable, the SSH path returns an error. There is no fallback to
   `accept-new` under any condition — not on read failure, not on write
   failure, not on an empty file.

Implementation constraints:

4. Carry the key material with `go:embed`, and materialize it to a file
   (0600) when the SSH branch first needs one, because `ssh` requires
   `UserKnownHostsFile` to be a path. Do **not** depend on a file being
   present at a fixed path in the image — that reintroduces exactly the
   "missing file at runtime" failure mode decision 3 is closing.
5. `GIT_SSH_COMMAND` must contain `-o StrictHostKeyChecking=yes` and
   `-o UserKnownHostsFile=<path>`, and the string `accept-new` must not
   appear anywhere in the package after this change.

Test scope — read this before writing T-tasks:

6. The issue asks for "a test that a mismatched host key fails the clone."
   A faithful end-to-end version needs a live SSH server, which this test
   suite has no way to stand up (existing tests use local `file://` repos,
   which never invoke `ssh` at all). **Do not fake one, and do not write a
   test that pretends to exercise a path it does not.** The honest coverage
   is: (a) a test asserting the constructed `GIT_SSH_COMMAND` for a
   non-empty `sshKeyPath` contains `StrictHostKeyChecking=yes` and the
   configured `UserKnownHostsFile`, and never `accept-new`; (b) a test that
   the embedded material parses as `github.com` host-key lines for all
   three algorithms; (c) a test that an explicitly configured
   `knownHostsPath` is used verbatim over the default. State this deviation
   from the issue's wording in the PR description rather than leaving the
   reviewer to notice the acceptance criterion is unmet.
