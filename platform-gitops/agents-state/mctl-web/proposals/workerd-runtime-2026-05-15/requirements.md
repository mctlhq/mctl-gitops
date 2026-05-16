# Workerd Runtime Update to v1.20260515.1

## Context
mctl-web's Cloudflare Worker (`cloudflare-worker/`) executes the `/api/*` endpoints — GitHub OAuth, tenant provisioning, contact form, and rate limiting — on Cloudflare's infrastructure using the workerd runtime. The existing proposal `workerd-v8-148-upgrade` targets v1.20260506.1 (V8 14.8). Since that proposal was written, Cloudflare released v1.20260515.1 on 2026-05-15 — nine days newer — confirmed by the `miniflare@4.20260515.0` workers-sdk release that bundles it.

Keeping the workerd pin stale creates environment drift: `wrangler dev` locally runs a different runtime snapshot than production Cloudflare infrastructure, making it harder to reproduce or rule out runtime-specific bugs. Updating the pin closes this gap without any behaviour changes or dependency on Kubernetes resources.

## User stories
- AS a developer running `wrangler dev` I WANT the local Worker runtime to match v1.20260515.1 SO THAT local testing is faithful to the production Cloudflare environment.
- AS a platform engineer I WANT the pinned workerd version in `cloudflare-worker/package.json` to track the latest dated release SO THAT environment drift is minimised between releases.

## Acceptance criteria (EARS)
- WHEN a developer runs `wrangler dev` inside `cloudflare-worker/` THE SYSTEM SHALL start using workerd v1.20260515.1 (or later if a newer dated release is available at implementation time).
- WHEN the `deploy.yml` GitHub Actions workflow runs THE SYSTEM SHALL deploy the Worker using the wrangler version that bundles workerd v1.20260515.1 or newer.
- WHILE the Worker is handling any `/api/*` request THE SYSTEM SHALL continue to enforce existing rate limits (5/5 min on `/api/submit`, 3/5 min on `/api/contact`, 10/min on `/api/github/login`).
- WHILE the Worker is running on Cloudflare infrastructure THE SYSTEM SHALL produce identical API responses before and after the pin update (no behavioural regression).
- IF a smoke test against the deployed Worker returns a non-2xx status on any `/api/*` endpoint after deployment THEN the GitHub Actions workflow SHALL surface the failure and halt further promotion.

## Out of scope
- Enabling new workerd APIs or runtime flags introduced in v1.20260515.1.
- Changes to the Nuxt frontend build or Kubernetes deployment.
- Modifying Cloudflare Worker secrets or environment variables.
- Any changes to the `labs` tenant workloads.
