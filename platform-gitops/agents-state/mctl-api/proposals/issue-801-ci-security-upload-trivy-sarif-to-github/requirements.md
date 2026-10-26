# Upload Trivy filesystem-scan SARIF to GitHub Code Scanning (category trivy-fs)

## Context
`.github/workflows/security.yml` job `trivy` runs `aquasecurity/trivy-action` (v0.36.0, Trivy v0.69.3) as a fail-closed CRITICAL gate (`severity: CRITICAL`, `exit-code: "1"`, `ignore-unfixed: true`) but writes only a table to the log. GitHub Code Scanning therefore never receives Trivy results and no `code_scanning_alert` webhook fires for them. That blocks prerequisite P2 of mctlhq/mctl-gitops#2103 (SecurityFinding v1 slice 3, contract mctlhq/mctl-api#774), which consumes those webhooks.

This proposal adds a SARIF-producing Trivy invocation and a `github/codeql-action/upload-sarif` step (category `trivy-fs`) that runs even when the gate fails, grants only the `trivy` job `security-events: write`, and leaves the existing gate step byte-for-byte unchanged.

## User stories
- AS the mctl-gitops SecurityFinding pipeline I WANT Trivy findings for mctl-api to appear as Code Scanning alerts (tool `Trivy`) SO THAT `code_scanning_alert` webhooks fire and can be turned into SecurityFindings.
- AS a maintainer I WANT the CRITICAL Trivy gate to keep failing the job exactly as today SO THAT adding reporting never weakens enforcement.
- AS a reviewer I WANT Trivy results visible in the Security tab with path, line and commit SHA SO THAT I can triage without reading CI logs.

## Acceptance criteria (EARS)
- WHEN the `trivy` job runs THE SYSTEM SHALL produce a SARIF file `trivy-results.sarif` from a Trivy `fs` scan of `.` with severities `CRITICAL,HIGH`, `ignore-unfixed: true`, `limit-severities-for-sarif: true`, and `exit-code: "0"`.
- WHEN the SARIF file exists THE SYSTEM SHALL upload it with `github/codeql-action/upload-sarif` (pinned to a commit SHA) using `category: trivy-fs`.
- IF the CRITICAL gate step fails the job THEN THE SYSTEM SHALL still run the upload step (`if: always()` semantics) and the job SHALL still end failed.
- WHILE the change is in place THE SYSTEM SHALL keep the gate step "Trivy filesystem scan" identical in inputs (`scan-type: fs`, `scan-ref: .`, `severity: CRITICAL`, `exit-code: "1"`, `ignore-unfixed: true`, `version: v0.69.3`) and its pass/fail outcome.
- WHILE the change is in place THE SYSTEM SHALL grant `security-events: write` only to the `trivy` job, keep `contents: read` for it, and keep the workflow-level `permissions: contents: read` and the `govulncheck` job permissions unchanged.
- IF the run is a pull request from a fork or from Dependabot (read-only `GITHUB_TOKEN`) THEN THE SYSTEM SHALL skip the upload step rather than fail the job on a permission error.
- WHEN a commit is pushed to `main` (or the weekly schedule / a manual dispatch runs on `main`) THE SYSTEM SHALL run the security workflow so Code Scanning alerts for the default branch reflect `main` and close when a finding is fixed.
- IF a CRITICAL fixable vulnerability is present THEN THE SYSTEM SHALL fail the `trivy` job AND upload the SARIF containing that finding.

## Out of scope
- Changing the gate's severity, `ignore-unfixed`, Trivy version, or trivy-action version.
- SARIF upload for `govulncheck`, container image scans, or Trivy misconfig/secret scanners beyond what `scan-type: fs` already emits.
- Any change to the Go code, Helm chart or the mctl-gitops webhook consumer.
- Branch-protection or Code Scanning merge-protection rules.

## Open questions
- Severity set for the upload: the issue leaves it open; this proposal uses `CRITICAL,HIGH` (useful triage signal, bounded noise). Reviewer may narrow to `CRITICAL` to match the gate 1:1.
- Code Scanning availability: SARIF upload requires the repo to be public or have GitHub Advanced Security / Code Security. This run could not verify the repo's visibility or GHAS status.
- Whether adding `push: branches: [main]` and `workflow_dispatch` triggers is acceptable (it also runs `govulncheck` on every merge). Without it, `main` is scanned only by the weekly cron (Monday 04:17 UTC), which would satisfy "a scan on main" but delay alerts and alert closure by up to a week.
- The exact commit SHA for `github/codeql-action/upload-sarif` (v3 or current major) must be resolved by the implementer at implementation time; it is not in the clone.
