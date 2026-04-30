# Workerd Runtime Upgrade to v1.20260430.1

## Context
The mctl-web Cloudflare Worker (in `cloudflare-worker/`) handles all `/api/*` traffic for the platform: GitHub OAuth flows (`/api/github/login`, `/api/github/callback`), tenant provisioning via Backstage (`/api/submit`), and contact form submissions with Telegram and Resend notifications (`/api/contact`). The Worker runs on the workerd runtime engine, currently pinned at v1.20260426.1.

workerd v1.20260430.1 was released on 2026-04-30 and contains a critical memory-safety fix: a use-after-free defect triggered when closures capture `this`. This class of defect can produce unpredictable behavior or silent data corruption in addition to outright crashes, making it particularly dangerous for the OAuth callback path and tenant provisioning logic. The same release also upgrades the Node.js compatibility layer to v22, introduces sidecar container state persistence improvements, delivers richer fetch error diagnostics surfaced in `wrangler tail`, and improves reporting for scheduled functions. This proposal covers the runtime binary upgrade; the related but distinct `workerd-clearweak-migration` proposal handles the ClearWeak V8 API deprecation at user-code level.

## User stories
- AS a platform engineer I WANT the Cloudflare Worker runtime to be upgraded to workerd v1.20260430.1 SO THAT the use-after-free memory-safety defect is eliminated and the Worker's stability guarantees are restored.
- AS an on-call engineer I WANT richer fetch error messages surfaced in `wrangler tail` SO THAT I can diagnose failures in external integrations (Backstage, GitHub OAuth, Resend, Telegram) faster during incidents.
- AS a developer I WANT the Worker to run on the Node.js v22 compatibility layer SO THAT Worker code has access to the latest Node.js API surface available in the Cloudflare runtime.
- AS a tenant admin I WANT the `/api/submit` and `/api/contact` endpoints to remain reliable SO THAT tenant provisioning requests and contact form submissions are never silently dropped due to a runtime memory defect.

## Acceptance criteria (EARS)
- WHEN the deploy pipeline runs `wrangler deploy` after this upgrade THE SYSTEM SHALL target a workerd version of v1.20260430.1 or later, confirmed by the Cloudflare deployment log or `wrangler versions list` output.
- WHEN the Worker processes a request on any `/api/*` route THE SYSTEM SHALL not crash or produce an undefined-behavior response due to the use-after-free defect fixed in v1.20260430.1.
- WHEN `wrangler tail` is invoked against the production Worker THE SYSTEM SHALL surface richer fetch error messages (including error type and cause) compared to the output produced under v1.20260426.1.
- WHILE the Worker is running under the upgraded runtime THE SYSTEM SHALL enforce all existing rate limits unchanged: 5 requests per 5 minutes on `/api/submit`, 3 requests per 5 minutes on `/api/contact`, and 10 requests per minute on `/api/github/login`.
- WHEN `wrangler dev` is run locally against `cloudflare-worker/` after the upgrade THE SYSTEM SHALL start without errors and serve all four `/api/*` endpoints using the v1.20260430.1 runtime.
- IF the wrangler version in `cloudflare-worker/package.json` does not pull in workerd v1.20260430.1 automatically THEN THE SYSTEM SHALL include an explicit `workerd` pin in `wrangler.toml` or `package.json` that resolves to v1.20260430.1.
- WHEN the GitHub Actions deploy workflow completes THE SYSTEM SHALL report a successful Cloudflare deployment with no runtime-version mismatch warnings.

## Out of scope
- Changes to the ClearWeak V8 API deprecation at user-code level — covered by `workerd-clearweak-migration`.
- Upgrading wrangler CLI beyond what is required to pull in workerd v1.20260430.1 — covered by `wrangler-full-upgrade`.
- Changes to the Nuxt 4 frontend build, SCSS stylesheets, or static site generation.
- Modifications to Kubernetes manifests for the `admins` or `labs` tenants.
- Changes to Worker business logic, secret rotation, or external integration configuration (GitHub OAuth App, Backstage, Telegram, Resend).
- Python `.pth` file processing enhancements and scheduled-function reporting improvements shipped in v1.20260430.1 — these are runtime-level improvements with no required action in this Worker.
