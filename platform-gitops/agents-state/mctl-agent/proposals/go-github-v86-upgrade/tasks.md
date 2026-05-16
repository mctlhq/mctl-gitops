# Tasks: go-github-v86-upgrade

- [ ] 1. Audit call sites — grep for all usages of `go-github/v68` (imports, type
  assertions, mock declarations) in the codebase. — DoD: a complete list of files and
  line numbers that must change, documented in the PR description.

- [ ] 2. Update `go.mod` and `go.sum` (depends on 1) — change
  `github.com/google/go-github/v68` to `github.com/google/go-github/v86`; run
  `go mod tidy`. — DoD: `go.mod` contains no v68 reference; `go mod verify` passes.

- [ ] 3. Migrate import paths (depends on 2) — replace every
  `"github.com/google/go-github/v68/github"` import with
  `"github.com/google/go-github/v86/github"`. — DoD: `go build ./...` succeeds with
  the updated import paths.

- [ ] 4. Migrate context-passing pattern (depends on 3) — remove `ctx` as a positional
  argument from every `client.XYZ.Method(ctx, ...)` call; initialise the client with a
  context-aware transport (`oauth2`). — DoD: `go build ./...` succeeds; no compiler
  errors from wrong method signatures.

- [ ] 5. Audit GitHub token rotation path (depends on 4) — verify that the
  `cwft-rotate-github-token` CronWorkflow's token injection mechanism still works with
  the v86 client initialisation pattern. — DoD: token rotation smoke-test passes in
  staging (rotate token, confirm next PR creation uses new token).

- [ ] 6. Update / regenerate test mocks (depends on 4) — update table-driven tests and
  mocks for the PR-creation path to match v86 method signatures. — DoD: `go test ./...`
  passes with no skipped tests; coverage on the PR-creation path is unchanged.

- [ ] 7. Close superseded proposals — add a note to `go-github-v85-upgrade`,
  `go-github-v85-migration`, `go-github-v85-authz-fix` that they are superseded by this
  proposal. — DoD: PR description links to those proposals; team acknowledges closure.

## Tests

- [ ] T1. `go build ./...` compiles cleanly against v86 imports.
- [ ] T2. `go test ./...` passes for the PR-creation package.
- [ ] T3. Integration test: create a draft PR in the `mctl-gitops` sandbox repo and verify
  title, body, and branch are correct.
- [ ] T4. Token rotation test: rotate the GitHub App installation token and confirm the
  next API call uses the new token (no 401).
- [ ] T5. Cross-host redirect test: configure the client to follow a redirect to a
  different host and assert it returns an error (CVE rejection inherited from v86).

## Rollback

Revert `go.mod`, `go.sum`, and all call-site changes to the v68 baseline and redeploy.
No schema changes; rollback is a standard ArgoCD sync to the previous commit. If the
rollback is triggered by a token-rotation failure, also verify that the v68 client still
picks up the rotated token.
