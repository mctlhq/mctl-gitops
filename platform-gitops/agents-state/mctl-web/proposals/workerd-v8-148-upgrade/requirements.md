# workerd v1.20260506.1 with V8 14.8 Upgrade

## Context
workerd v1.20260506.1 was released on 2026-05-06 and ships V8 14.8, which
includes JIT compilation improvements and memory layout optimizations. These
changes reduce CPU time for JavaScript executed inside Worker handlers,
directly benefiting the `/api/*` endpoints that perform GitHub OAuth flows,
tenant provisioning calls, and contact-form submissions on mctl.ai.

The previously identified `workerd-runtime-upgrade` proposal targets
v1.20260430.1 (bundled with wrangler 4.86.0). Today's release is a full week
newer and will be bundled with wrangler 4.88.0. Upgrading wrangler to 4.88.0
implicitly delivers this workerd version; however, an explicit version pin in
`cloudflare-worker/package.json` guarantees that local `wrangler dev`
environments use the same runtime as production Cloudflare infrastructure,
eliminating environment drift. Because the Worker runs entirely on Cloudflare
infrastructure and not on the Kubernetes cluster, there is no memory or
resource impact on the `admins` or `labs` tenants.

## User stories
- AS a backend developer I WANT `wrangler dev` to use workerd v1.20260506.1
  SO THAT my local environment matches the production Worker runtime exactly.
- AS a platform engineer I WANT the `/api/*` handlers to execute faster
  SO THAT end-to-end latency for GitHub OAuth and tenant provisioning is
  reduced for users.
- AS a developer I WANT the wrangler version pinned explicitly in
  `cloudflare-worker/package.json` SO THAT CI and local dev always agree on
  the runtime version without manual intervention.

## Acceptance criteria (EARS)

- WHEN a developer runs `wrangler dev` inside `cloudflare-worker/` THE SYSTEM
  SHALL start the local server using workerd v1.20260506.1 (V8 14.8).
- WHEN the `deploy.yml` GitHub Actions workflow runs THE SYSTEM SHALL deploy
  the Worker using the wrangler version pinned in
  `cloudflare-worker/package.json` (>= 4.88.0).
- WHILE the Worker is handling any `/api/*` request THE SYSTEM SHALL continue
  to enforce existing rate limits (5/5min on `/api/submit`, 3/5min on
  `/api/contact`, 10/min on `/api/github/login`).
- WHILE the Worker is running on Cloudflare infrastructure THE SYSTEM SHALL
  produce identical API responses before and after the upgrade (no behavioural
  regression).
- IF the wrangler or workerd version in `cloudflare-worker/package.json` is
  below 4.88.0 THEN the CI pipeline SHALL fail the dependency-version check
  step and block the merge.
- IF a smoke test against the deployed Worker returns a non-2xx status on any
  monitored `/api/*` endpoint after deployment THEN the GitHub Actions workflow
  SHALL surface the failure and halt further promotion.

## Out of scope
- Changes to the Nuxt frontend build or its Kubernetes deployment.
- Changes to any other `package.json` outside `cloudflare-worker/`.
- Enabling V8 14.8-specific features (e.g., `traceFlags` on `SpanContext`)
  beyond what workerd enables by default — those require a separate proposal.
- Modifying Cloudflare Worker secrets or environment variables.
- Any changes to the `labs` Kubernetes tenant workloads.
