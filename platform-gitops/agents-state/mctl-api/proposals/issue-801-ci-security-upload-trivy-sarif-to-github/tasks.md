# Tasks: issue-801-ci-security-upload-trivy-sarif-to-github

- [ ] 1. Add `push: branches: [main]` and `workflow_dispatch:` to `on:` in `.github/workflows/security.yml` — DoD: existing `pull_request` and `schedule` triggers unchanged; YAML parses.
- [ ] 2. Add job-level `permissions: { contents: read, security-events: write }` to job `trivy` only — DoD: workflow-level `permissions` and `govulncheck` untouched.
- [ ] 3. Insert step "Trivy filesystem scan (SARIF)" before the gate, using the same trivy-action SHA, `format: sarif`, `output: trivy-results.sarif`, `severity: CRITICAL,HIGH`, `limit-severities-for-sarif: true`, `ignore-unfixed: true`, `exit-code: "0"`, `version: v0.69.3` (depends on 2) — DoD: step never fails on findings.
- [ ] 4. Leave step "Trivy filesystem scan" byte-for-byte unchanged — DoD: `git diff` shows no modified lines in that step.
- [ ] 5. Add step "Upload Trivy SARIF to Code Scanning" with `github/codeql-action/upload-sarif` pinned to a resolved release commit SHA (`# vX.Y.Z` comment), `sarif_file: trivy-results.sarif`, `category: trivy-fs`, and the `always() && hashFiles(...) && non-fork/non-Dependabot` guard from design.md (depends on 3) — DoD: actionlint passes; SHA verified against the codeql-action release tag.
- [ ] 6. Confirm Code Scanning is available for mctlhq/mctl-api (public repo or GHAS enabled) before merge — DoD: noted in the PR description.

## Tests
- [ ] T1. `actionlint .github/workflows/security.yml` (or equivalent YAML/schema validation) passes.
- [ ] T2. PR run (same-repo branch): `trivy` job green on a clean tree; SARIF upload step succeeds; PR analysis appears under category `trivy-fs`.
- [ ] T3. Fail-closed proof: on a throwaway branch, add a dependency with a known fixable CRITICAL CVE (e.g. pin an old vulnerable module version in `go.mod`); the gate step fails, the upload step still runs and succeeds, the job ends failed, and the SARIF contains that finding. Close the branch without merging; link the run in the PR.
- [ ] T4. After merge, run `workflow_dispatch` (or wait for the push run) on `main`: Security -> Code scanning shows tool `Trivy`, category `trivy-fs`, with file path, line and commit SHA (or a "no alerts" analysis if the tree is clean).
- [ ] T5. Verify the upload step is skipped (not failed) on a fork or Dependabot PR, by inspecting a run or reasoning from the `if:` expression.

## Rollback
Revert the PR. That removes the SARIF step, upload step, job permissions and new triggers, restoring the gate-only workflow. Existing `trivy-fs` alerts can be left (they stop updating) or the analysis deleted from Security -> Code scanning -> tool settings. The gate was never modified, so enforcement is unaffected by rollback.
