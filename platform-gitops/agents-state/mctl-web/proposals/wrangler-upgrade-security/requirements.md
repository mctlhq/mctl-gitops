# Upgrade Wrangler to 4.87.0 to Remediate CVE-2026-0933 and workerd UaF

## Context
mctl-web deploys its Cloudflare Worker and Pages build via `wrangler pages deploy` in a GitHub Actions pipeline (`deploy.yml`). CVE-2026-0933 (CVSS Critical) discloses an OS Command Injection vulnerability where the `--commit-hash` argument, typically sourced from `${{ github.sha }}` or a similar git context in CI, is passed unsanitised to a shell command inside wrangler. An attacker able to influence the commit SHA value (e.g., through a malicious PR in a fork-based workflow) can execute arbitrary commands in the CI runner. A separate use-after-free bug in the bundled workerd runtime (v1.20260430.1) is also patched in the same wrangler@4.87.0 release.

## User stories
- AS a platform engineer I WANT wrangler pinned to a version that is not affected by CVE-2026-0933 SO THAT the CI/CD pipeline cannot be exploited via commit-hash injection.
- AS a platform engineer I WANT the bundled workerd runtime to include the use-after-free fix SO THAT Worker execution is memory-safe.

## Acceptance criteria (EARS)
- WHEN the GitHub Actions deploy workflow runs `wrangler pages deploy` THEN the wrangler version in use SHALL be >= 4.59.1 (minimum for CVE fix) and SHOULD be 4.87.0 (current latest).
- WHEN a pull request from a fork triggers the deploy workflow THE SYSTEM SHALL NOT allow arbitrary OS command execution via the `--commit-hash` parameter.
- WHEN the Cloudflare Worker processes a request THE SYSTEM SHALL use a workerd runtime >= v1.20260430.1 that includes the use-after-free fix.
- IF the wrangler upgrade introduces any breaking change in CLI flags or Pages configuration THEN the deploy workflow SHALL be updated before merging.

## Out of scope
- Changes to the Worker source code or Nuxt application logic.
- Upgrading other Cloudflare packages (e.g. `@cloudflare/workers-types`) unless required by wrangler@4.87.0 peer deps.
- Migrating from Wrangler Pages to any other deployment mechanism.
