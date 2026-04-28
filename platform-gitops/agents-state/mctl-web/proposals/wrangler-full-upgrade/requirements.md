# Wrangler Full Upgrade to v4.86.0

## Context
The existing proposal `wrangler-cve-0933` established a minimum wrangler version of v4.59.1 to remediate CVE-2026-0933 (OS command injection, CVSS 9.9). Production wrangler is now at that floor, but 27 releases separate v4.59.1 from the current latest, v4.86.0. Those releases include resource-leak fixes in worker teardown—directly relevant to the Cloudflare Worker that handles all `/api/*` traffic—and the addition of stack traces in `wrangler tail`, which reduces mean-time-to-diagnosis during incidents.

Leaving this gap open means the service accumulates stability risk (leaked resources in worker teardown) and loses observability improvements over time. Because wrangler is a CI-only tool invoked in `deploy.yml` and `cloudflare-worker/package.json`, the upgrade carries no memory or runtime impact on either the `admins` or `labs` Kubernetes tenants.

## User stories
- AS a platform engineer I WANT wrangler to be at v4.86.0 in both `deploy.yml` and `cloudflare-worker/package.json` SO THAT worker deploys benefit from resource-leak fixes and stack traces in tail logs without carrying accumulated version debt.
- AS an on-call engineer I WANT stack traces in `wrangler tail` output SO THAT I can identify the source of Worker errors faster during incidents.

## Acceptance criteria (EARS)
- WHEN the `deploy.yml` GitHub Actions workflow runs `wrangler` SO THAT the version resolves to v4.86.0 or above THE SYSTEM SHALL complete the deploy step without deprecation warnings or resource-leak errors.
- WHEN `wrangler tail` is invoked against the production Worker THE SYSTEM SHALL include JavaScript stack traces in the log output for uncaught exceptions.
- WHEN a worker teardown event occurs during `wrangler dev` or a deploy THE SYSTEM SHALL release all associated resources without leak warnings in the process output.
- WHILE the CI pipeline is running THE SYSTEM SHALL not install any wrangler version below v4.86.0 in either the Actions environment or `cloudflare-worker/`.
- IF the wrangler version in `cloudflare-worker/package.json` differs from the pinned version in `deploy.yml` THEN THE SYSTEM SHALL fail the CI lint step with a version-mismatch error.

## Out of scope
- Upgrading or modifying the Cloudflare Worker runtime (workerd) — covered by `workerd-clearweak-migration`.
- Remediating CVE-2026-0933 — already covered by `wrangler-cve-0933`.
- Changes to Worker business logic (`/api/*` endpoints).
- Any changes to Kubernetes workloads on `admins` or `labs` tenants.
