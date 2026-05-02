# Upgrade Wrangler to 4.87.0 for Module-Fallback V2 and Router Refactor

## Context
mctl-web's Cloudflare Worker is deployed via `wrangler` through a self-contained `deploy.yml`
GitHub Actions workflow — the only service with this exception from the centralised mctl-gitops
pipeline (see `context/architecture.md`). The Worker handles all `/api/*` traffic: GitHub OAuth
callbacks, tenant provisioning via Backstage, contact form submissions with Telegram and Resend
notifications.

Wrangler 4.87.0 was released on 2026-04-30 and introduces two notable changes: V2 protocol
support for the module fallback service (activated when the `new_module_registry` compatibility
flag is set) and a refactored router-worker that supports gradual rollout gating. The existing
wrangler proposals (`wrangler-cve-0933`, `wrangler-upgrade-security`, `wrangler-full-upgrade`,
`wrangler-ci-injection-audit`) all target CVE-2026-0933 security remediation; none addresses
this functional release. Keeping the deploy tool current reduces supply-chain version drift and
ensures the Worker is deployed with the latest routing and module-resolution semantics.

## User stories
- AS a platform engineer I WANT wrangler upgraded to 4.87.0 SO THAT the Worker is deployed using
  the most current module-resolution and router semantics available in the Cloudflare toolchain.
- AS a developer I WANT a current wrangler version in `cloudflare-worker/package.json` SO THAT
  local `wrangler dev` and CI `wrangler deploy` execute on the same toolchain version.
- AS an on-call engineer I WANT the deploy pipeline to remain stable after the upgrade SO THAT
  no `/api/*` endpoint experiences a regression in routing or module loading behaviour.

## Acceptance criteria (EARS)
- WHEN `wrangler deploy` is executed in the `cloudflare-worker/` directory THE SYSTEM SHALL
  invoke wrangler version 4.87.0 or newer, confirmed by `wrangler --version` output in CI logs.
- WHEN the Worker is deployed with wrangler 4.87.0 THE SYSTEM SHALL serve all four `/api/*`
  endpoints (`/api/github/login`, `/api/github/callback`, `/api/submit`, `/api/contact`) with
  the same response behaviour as under the previous wrangler version.
- WHILE the Worker is running after the upgrade THE SYSTEM SHALL enforce all existing rate
  limits unchanged: 5/5 min on `/api/submit`, 3/5 min on `/api/contact`, 10/min on
  `/api/github/login`.
- IF `wrangler dev` is run locally after the upgrade THE SYSTEM SHALL start without errors and
  serve all Worker routes.
- WHEN the upgraded `package.json` and `package-lock.json` are committed THE SYSTEM SHALL be
  the only change in the changeset (no unrelated dependency bumps).
- WHEN the GitHub Actions `deploy.yml` workflow runs THE SYSTEM SHALL complete successfully with
  no wrangler deprecation warnings that were not present in the prior version.

## Out of scope
- Enabling the `new_module_registry` compatibility flag (requires separate testing and approval).
- Changes to Worker business logic, secret management, or external integrations.
- Auditing the `deploy.yml` pipeline for CVE-2026-0933 injection risk — covered by
  `wrangler-ci-injection-audit`.
- Upgrading the workerd runtime binary — covered by `workerd-runtime-upgrade`.
- Changes to the Nuxt 4 frontend or any Kubernetes tenant manifests.
