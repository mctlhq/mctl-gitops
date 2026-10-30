# Tasks: issue-881-docs-platform-compatibility-matrix-and-o

- [ ] 1. Collect the evidence: read the #784 inventory comment (2026-10-23); read
  mctl-gitops `platform-gitops/services/labs/mctl-telegram/values.yaml` at HEAD
  and note its commit and date; run `git log -S` in mctl-gitops for
  `www.town.com`, `vscode.dev` and `MCP_CLIENT_PROFILES` to identify Town's 3
  PRs (incl. #2023, #2063) and their dates; look for any dated tg.mctl.ai
  observation for Claude, Claude Code and ChatGPT in PRs, issues or
  CHANGELOG.md — DoD: every row has either a cited link plus date or an explicit
  `not tested`.
- [ ] 2. Write `docs/platforms/compatibility.md` (depends on 1). It has a status
  legend, the rule "allowlist alone = not tested", the source path and read
  date, and a table with the exact header
  `| Host | Registration path | Allowlist entry today | Status | Evidence | Date observed |`
  and the nine rows from design.md. The Town row gives its exact progress. The
  Cloudflare portal row cites `OAUTH_DCR_REDIRECT_URIS` with placeholders,
  never the real dashboard URL. Below the table go the `antigravity.google`
  footnote and the loopback note — DoD: no `works` cell lacks a link and a
  date, and nothing contradicts `internal/config/config.go` defaults, README
  lines 13-19/151-161/279-284, or values.yaml.
- [ ] 3. Write `docs/runbooks/admitting-an-agent-platform.md` with the section
  "Admitting an agent platform". It covers: intake; the order
  `OAUTH_ALLOWED_IMPLICIT_HOSTS` -> `OAUTH_CIMD_ALLOWED_HOSTS` ->
  `MCP_CLIENT_PROFILES`; the `OAUTH_CIMD_ADVERTISE` no-DCR-fallback warning;
  verification (discovery metadata,
  `mctl_oauth_client_registrations_total`, sign-in, token, one read-only tool
  call, matrix update); rollback (including that removing a CIMD host cuts off
  refreshes); and the Town timeline split into integrator (unknown), operator
  (3 PRs, about 3 days) and waiting time. It links
  `../runbook.md#client-tool-profiles` instead of duplicating that section —
  DoD: every env var named exists in `internal/config/config.go`.
- [ ] 4. Add one link line to `docs/runbook.md` next to the canary pointer, and
  one line to README.md in the client list linking
  `docs/platforms/compatibility.md` (depends on 2, 3) — DoD: links resolve
  relative to each file, and no other README sentence changes.
- [ ] 5. Add `docs/compatibility_test.go` in package `docs` (depends on 2, 3, 4)
  — DoD: the tests in the Tests section pass, `go vet ./docs/...` is clean, and
  `go fmt` leaves no diff.
- [ ] 6. Open the PR as `docs: platform compatibility matrix and operator
  host-admission runbook (#881)`, referencing #784. The PR description lists
  any row where the matrix and the README's "Claude is the client we test
  against" are in tension — DoD: CI green, merged with a merge commit.

## Tests

- [ ] T1. `TestCompatibilityMatrixRequiredHosts`: each of the nine host names
  appears exactly once in the table.
- [ ] T2. `TestCompatibilityMatrixStatusValues`: every status is `works`,
  `works with caveats` or `not tested`.
- [ ] T3. `TestCompatibilityMatrixEvidence`: every `works` / `works with
  caveats` row has a markdown link in Evidence and a `YYYY-MM-DD` date.
- [ ] T4. `TestCompatibilityMatrixTownNotWorks`: the Town row status is not
  `works`.
- [ ] T5. `TestReadmeLinksCompatibilityMatrix`: README.md contains
  `docs/platforms/compatibility.md`.
- [ ] T6. `TestAdmissionRunbookEnvVarsExist`: every `OAUTH_*` /
  `MCP_CLIENT_PROFILES` name in the runbook appears in
  `internal/config/config.go`.
- [ ] T7. The existing `go test ./docs/...` (`TestRunbookAnchorsPresent`,
  `TestRunbookMetricNamesRegistered`, troubleshooting tests) still pass.
- [ ] T8. Negative check: temporarily set a `not tested` row to `works` with no
  link, and confirm T3 fails. Revert before committing.

## Rollback

Documentation and one test file only. Revert the merge commit
(`git revert -m 1 <merge>`). No runtime, data or gitops state depends on these
files.
