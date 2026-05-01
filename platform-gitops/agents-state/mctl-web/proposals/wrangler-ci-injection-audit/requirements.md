# Wrangler CI/CD Pipeline Audit for CVE-2026-0933 Injection Risk

## Context
CVE-2026-0933 (CVSS 7.7, High) disclosed that the `--commit-hash` parameter of `wrangler pages deploy` is passed to a shell without sanitization in affected versions (>= 4.0.0 < 4.59.1). Although mctl-web currently runs wrangler 4.87.0 — above the patched threshold — the vulnerability's root pattern (unsanitized external input flowing into a shell-executed CLI argument) warrants a proactive audit of the pipeline that constructs the `--commit-hash` value.

mctl-web holds an exceptional position among platform services: its `deploy.yml` lives in this repository rather than in mctl-gitops, and it executes wrangler directly from a GitHub Actions runner. The commit hash passed to wrangler is sourced from the GitHub Actions context (e.g., `${{ github.sha }}` or `${{ github.event.pull_request.head.sha }}`). If a fork-based pull request or a workflow-dispatch event can influence this value with attacker-controlled content, the CI runner could be used as a pivot point even on a patched wrangler version. A formal audit eliminates this uncertainty and produces verifiable evidence that the pipeline is hardened.

## User stories
- AS a platform security engineer I WANT the deploy pipeline audited for untrusted input paths into `--commit-hash` SO THAT I can confirm the CI runner is not exploitable via a pull-request-triggered injection attack.
- AS a developer I WANT clear documentation of how the commit hash is sourced in `deploy.yml` SO THAT future modifications to the pipeline do not accidentally reintroduce the injection pattern.
- AS a platform operator I WANT the audit findings captured in a signed-off checklist SO THAT the security team can close the CVE-2026-0933 tracking ticket with documented evidence.

## Acceptance criteria (EARS)
- WHEN the audit is complete THE SYSTEM SHALL have a documented record confirming that the `--commit-hash` value in `deploy.yml` is sourced exclusively from `github.sha` (the merge commit SHA, controlled by GitHub) or an equally trusted context variable, and never from user-supplied PR metadata.
- WHEN `deploy.yml` is triggered by a pull-request event from a fork THE SYSTEM SHALL NOT grant write permissions or secrets access to the workflow that constructs the `--commit-hash` argument.
- IF the audit identifies any path where a pull-request author can influence the value passed to `--commit-hash` THEN THE SYSTEM SHALL apply a mitigation (sanitization, allowlist check, or workflow permission scope reduction) before the finding is closed.
- WHILE the deployment pipeline runs THE SYSTEM SHALL pass `--commit-hash` only as a literal SHA-1/SHA-256 hex string, rejecting any value that does not match the pattern `[0-9a-f]{40}` (or `[0-9a-f]{64}` for SHA-256).
- WHEN the hardened `deploy.yml` is merged THE SYSTEM SHALL include an inline comment referencing CVE-2026-0933 and the audit date so future maintainers understand the constraint.

## Out of scope
- Upgrading wrangler beyond 4.87.0 (covered by the `wrangler-cve-0933` proposal, which already tracks version bumps).
- Auditing other GitHub Actions workflows outside `deploy.yml`.
- Changes to the Cloudflare Worker runtime logic (`cloudflare-worker/`).
- Auditing third-party GitHub Actions used in other mctl services.
- Replacing GitHub Actions with a different CI system.
