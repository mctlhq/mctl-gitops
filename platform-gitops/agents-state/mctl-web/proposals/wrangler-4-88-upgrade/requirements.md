# Upgrade Wrangler to 4.88.0 with Stabilized Secrets Config

## Context
mctl-web's Cloudflare Worker is deployed via `wrangler` through a self-contained `deploy.yml`
GitHub Actions workflow — the only service with this exception from the centralised mctl-gitops
pipeline (see `context/architecture.md`). The Worker handles all `/api/*` traffic: GitHub OAuth
callbacks, tenant provisioning via Backstage, contact form submissions with Telegram and Resend
notifications. Seven production secrets are bound to these endpoints (`TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `GITHUB_OAUTH_HMAC_KEY`,
`BACKSTAGE_LANDING_TOKEN`, `RESEND_API_KEY`).

Wrangler 4.88.0 was released on 2026-05-05, one version ahead of the highest existing proposal
(`wrangler-4-87-upgrade`, targeting 4.87.0). The headline change is the graduation of the
`secrets` configuration property in `wrangler.toml` from experimental to stable API. Previously,
any misconfiguration in the experimental `secrets` block could silently fail or produce unexpected
binding behaviour, creating a risk that secrets bound to `/api/*` endpoints would not be available
at runtime. With the stable API, misconfiguration is caught deterministically at deploy time.
Keeping the exact-pin strategy current — established by prior wrangler proposals — is also
required to maintain supply-chain auditability for the CI deploy tool.

## User stories
- AS a platform engineer I WANT wrangler upgraded to 4.88.0 SO THAT the stable `secrets` config
  API is in effect for all Worker deployments, reducing the risk of silent secret-binding failures.
- AS a security engineer I WANT the Worker deploy tool pinned to the latest audited version SO
  THAT the project's exact-pin auditability policy is maintained and version drift is minimised.
- AS a developer I WANT a current wrangler version in `cloudflare-worker/package.json` SO THAT
  local `wrangler dev` and CI `wrangler deploy` operate on the same, known-good toolchain version.
- AS an on-call engineer I WANT the deploy pipeline to remain stable after the upgrade SO THAT no
  `/api/*` endpoint experiences a regression in secret binding or routing behaviour.

## Acceptance criteria (EARS)

- WHEN `wrangler deploy` is executed in the `cloudflare-worker/` directory THE SYSTEM SHALL invoke
  wrangler version 4.88.0 exactly, confirmed by `wrangler --version` output in CI logs.
- WHEN the Worker is deployed with wrangler 4.88.0 THE SYSTEM SHALL bind all seven configured
  secrets (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`,
  `GITHUB_OAUTH_HMAC_KEY`, `BACKSTAGE_LANDING_TOKEN`, `RESEND_API_KEY`) and make them available
  to the Worker runtime without error.
- WHEN a misconfigured or missing entry is present in the `secrets` block of `wrangler.toml` THE
  SYSTEM SHALL surface an explicit error at `wrangler deploy` time and abort the deployment.
- WHEN the Worker is deployed with wrangler 4.88.0 THE SYSTEM SHALL serve all four `/api/*`
  endpoints (`/api/github/login`, `/api/github/callback`, `/api/submit`, `/api/contact`) with the
  same response behaviour as under the previous wrangler version.
- WHILE the Worker is running after the upgrade THE SYSTEM SHALL enforce all existing rate limits
  unchanged: 5/5 min on `/api/submit`, 3/5 min on `/api/contact`, 10/min on `/api/github/login`.
- IF `wrangler dev` is run locally after the upgrade THE SYSTEM SHALL start without errors and
  serve all Worker routes with all secrets available through the local dev binding mechanism.
- WHEN the upgraded `package.json` and `package-lock.json` are committed THE SYSTEM SHALL be the
  only change in the changeset (no unrelated dependency bumps).
- WHEN the GitHub Actions `deploy.yml` workflow runs with wrangler 4.88.0 THE SYSTEM SHALL
  complete successfully with no deprecation warnings that were not present in the prior version.

## Out of scope
- Changes to Worker business logic, secret values, or external integrations.
- Rotating or auditing the values of the seven bound secrets — covered by separate security
  proposals if needed.
- Enabling new wrangler 4.88.0 experimental flags beyond the stabilized `secrets` property.
- Migrating the deploy pipeline to mctl-gitops — an architectural decision requiring a separate ADR.
- Upgrading the workerd runtime binary — covered by `workerd-runtime-upgrade`.
- Changes to the Nuxt 4 frontend or any Kubernetes tenant manifests.
- Auditing the `deploy.yml` pipeline for CVE-2026-0933 injection risk — covered by
  `wrangler-ci-injection-audit`.
