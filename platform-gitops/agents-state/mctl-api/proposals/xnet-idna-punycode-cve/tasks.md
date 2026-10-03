# Tasks: xnet-idna-punycode-cve

- [ ] 1. Run `go list -m all` / `go mod graph` against mctl-api's `go.mod`/`go.sum` to
      determine whether `golang.org/x/net` is resolved in the build, at what version, and via
      which direct dependency (`client-go`, `go-oidc/v3`, `chi/v5`, or other). — DoD: a
      recorded module-graph excerpt (committed to the proposal or PR description) showing the
      resolved `x/net` version and its import path, with an explicit yes/no on whether it
      falls inside CVE-2026-39821's affected range (< v0.55.0).
- [ ] 2. If Task 1 confirms exposure, decide the remediation path (toolchain bump to Go
      1.26.6+ vs. direct `golang.org/x/net` bump to v0.55.0+) based on which is unblocked
      first, cross-checking status of the go-upgrade toolchain proposal (depends on 1) — DoD:
      a one-paragraph decision recorded in the PR description naming the chosen path and why.
- [ ] 3. If Task 1 finds no exposure (dependency absent or already patched), close this
      proposal as "not applicable" with the Task 1 evidence attached, and skip Tasks 4-6
      (depends on 1) — DoD: proposal status updated to reflect closure, no code change made.
- [ ] 4. Apply the chosen remediation (toolchain bump or direct `go get
      golang.org/x/net@v0.55.0`, or later) and run `go mod tidy` (depends on 2) — DoD:
      `go.mod`/`go.sum` updated, `go build ./...` succeeds with no compile errors.
- [ ] 5. Run `govulncheck ./...` against the patched build and attach output to the PR
      (depends on 4) — DoD: zero findings for CVE-2026-39821.
- [ ] 6. Run the full existing test suite, including auth-flow tests for all three bearer
      types (GitHub PAT, Dex JWT, OAuth JWT) (depends on 4) — DoD: all tests pass with no
      modification to test logic.

## Tests
- [ ] T1. Module-graph confirmation check (Task 1) — automated `go list -m all | grep
      golang.org/x/net` in CI, output attached to the PR.
- [ ] T2. `govulncheck ./...` — zero findings for CVE-2026-39821 post-patch.
- [ ] T3. Existing OIDC/JWKS integration test (Dex JWT verification against
      `ops.mctl.me/api/dex/keys`) — passes unchanged post-patch.
- [ ] T4. Existing integration tests for GitHub PAT auth, Vault secret fetch, ArgoCD status
      calls, Backstage catalog calls, and Argo Workflows submit/inspect — all pass unchanged.
- [ ] T5. Full regression suite (`go test ./...`) — no new failures attributable to the
      dependency/toolchain bump.

## Rollback
If the patch (toolchain bump or direct `x/net` bump) causes a regression after deployment:
revert the `go.mod`/`go.sum` change (and Dockerfile base-image tag, if the toolchain path was
used) in a follow-up commit, and redeploy the prior image via ArgoCD's standard rollback (sync
to the previous Git revision). Because this is a pure dependency-version change with no data
migration, rollback is a plain revert-and-redeploy with no additional cleanup required. If
Task 1 confirmed real exposure, document the rollback as temporary and re-open the proposal
rather than closing it, so the CVE remains tracked until a working patch lands.
