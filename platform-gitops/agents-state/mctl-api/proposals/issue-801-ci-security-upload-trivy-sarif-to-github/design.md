# Design: issue-801-ci-security-upload-trivy-sarif-to-github

## Current state
- `.github/workflows/security.yml` triggers on `pull_request` to `main` and `schedule: "17 4 * * 1"`; workflow-level `permissions: contents: read`; no job-level permissions.
- Job `govulncheck`: installs `govulncheck@v1.7.0`, fail-closed. Not touched by this proposal.
- Job `trivy` (`timeout-minutes: 15`): `actions/checkout@v7`, then step "Trivy filesystem scan" using `aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25 # v0.36.0` with `scan-type: fs`, `scan-ref: .`, `severity: CRITICAL`, `exit-code: "1"`, `ignore-unfixed: true`, `version: v0.69.3`. Default format is `table`; no SARIF, no upload.
- Pinning convention in this repo: third-party actions are pinned by full SHA with a `# vX.Y.Z` comment (trivy-action, `actions/create-github-app-token` in `portal-allowlist-dispatch.yml`, `appleboy/telegram-action` in `release-please.yml`); first-party `actions/*` use major tags in `security.yml`. A pinned scanner is justified in-file by the govulncheck comment ("an unpinned scanner release could turn every PR red").
- No `.trivyignore` exists in the repo root.

Deployed state checked:
- Not applicable to runtime: this change is CI-only and alters no deployed configuration. `$MCTL_GITOPS_ROOT/services/*/` was listed; no deployed-state assertion is made from it. No mctl MCP tool was called because nothing about tenants, hostnames or env vars is asserted.
- Repository visibility / GitHub Advanced Security status: could not be observed from this run (no GitHub API access). Recorded under Open questions in requirements.md.

## Proposed solution
Edit only `.github/workflows/security.yml`.

1. Triggers: add `push: branches: [main]` and `workflow_dispatch:` so the default branch is scanned on every merge (alerts open and close promptly) and can be scanned on demand to verify the Done-when criterion. `pull_request` and `schedule` stay.
2. Job `trivy` gets job-level permissions (job-level permissions replace, not merge with, the workflow-level block, so `contents: read` must be restated):
   ```yaml
   permissions:
     contents: read
     security-events: write
   ```
3. Steps, in order:
   - `actions/checkout@v7` (unchanged).
   - NEW "Trivy filesystem scan (SARIF)": same trivy-action SHA, `scan-type: fs`, `scan-ref: .`, `format: sarif`, `output: trivy-results.sarif`, `severity: CRITICAL,HIGH`, `limit-severities-for-sarif: true` (without it trivy-action emits all severities into SARIF regardless of `severity`), `ignore-unfixed: true`, `exit-code: "0"`, `version: v0.69.3`. Placed before the gate so the gate failing cannot skip it, and it never fails the job on findings.
   - "Trivy filesystem scan" gate: unchanged, byte-for-byte. It may set `skip-setup-trivy`/cache implicitly via the action's own cache; no input is added to it.
   - NEW "Upload Trivy SARIF to Code Scanning": `github/codeql-action/upload-sarif@<sha> # v3.x` (implementer resolves the current release SHA), `with: sarif_file: trivy-results.sarif, category: trivy-fs`, guarded by
     `if: always() && hashFiles('trivy-results.sarif') != '' && (github.event_name != 'pull_request' || (github.event.pull_request.head.repo.full_name == github.repository && github.actor != 'dependabot[bot]'))`.
     `always()` keeps it running after a gate failure; the `hashFiles` guard avoids a confusing second error if SARIF generation itself crashed; the fork/Dependabot guard avoids a 403 on read-only tokens turning the job red for a reason unrelated to findings.
4. Job outcome: gate fail -> upload still runs -> job remains failed (an `always()` step does not reset job status). Gate pass -> upload runs -> job green.

The tool name in Code Scanning is `Trivy` (from the SARIF `tool.driver.name`); `category: trivy-fs` separates this analysis from any future image scan. Locations come from Trivy's SARIF (`go.mod`/`go.sum` path and line), and commit SHA from the upload's default `ref`/`sha`.

## Alternatives
- Single invocation with `format: sarif` plus `exit-code: "1"`: one scan, but it changes the gate step's inputs and output (no table in logs), and couples report severity to gate severity. Rejected: the issue requires the gate unchanged.
- Run the SARIF scan after the gate with `if: always()`: works, but leaves the report dependent on step-ordering conditions; putting it first with `exit-code: "0"` is simpler and equally correct.
- Upload SARIF from a separate job via artifact: cleaner permission isolation, but adds artifact plumbing and a second runner for a single file; job-scoped `security-events: write` already limits blast radius. Rejected as unnecessary complexity.
- Rely on schedule only (no `push: main`): smallest diff, but main alerts lag up to 7 days. Kept as fallback if reviewers object to the extra trigger.

## Platform impact
- Migrations / compatibility: none; CI-only. No Go, Helm, or MCP tool-count change.
- Resource impact: one extra Trivy fs scan per run (DB already cached by the first invocation; seconds to low minutes); extra runs on every push to `main`. Well within `timeout-minutes: 15`.
- Risks and mitigations:
  - Code Scanning not enabled (private repo without GHAS): upload fails and turns the job red. Mitigation: verify visibility/GHAS before merge; open question recorded.
  - HIGH findings create alerts that do not gate: intended triage signal; narrow to `CRITICAL` if noisy.
  - Unpinned upload action could change behaviour: pinned by SHA per repo convention.
  - PR-ref uploads create PR-scoped analyses; default-branch alerts come only from `push`/`schedule`/`workflow_dispatch` on `main`.
