# Design: workerd-runtime-upgrade

## Current state
As documented in `context/architecture.md`, the Cloudflare Worker lives in `cloudflare-worker/` and is deployed via Wrangler through a GitHub Actions workflow (`deploy.yml`) that lives in the mctl-web repository — an explicit exception to the centralised mctl-gitops build system. The Worker handles all `/api/*` routes:

- `/api/github/login` and `/api/github/callback` — GitHub OAuth with HMAC state validation
- `/api/submit` — tenant provisioning request, forwarded to Backstage with a shared HMAC token
- `/api/contact` — contact form, dispatches to Telegram Bot and Resend

Wrangler controls which workerd binary runs locally (`wrangler dev`) and in production (via the Cloudflare deployment pipeline). The workerd version in use is determined by the wrangler version — wrangler bundles a specific workerd release as a dependency. The current production workerd is v1.20260426.1, bundled with or near wrangler@4.86.0 (already targeted by the `wrangler-full-upgrade` proposal).

workerd v1.20260430.1 fixes a use-after-free defect triggered by closures that capture `this`. The Worker's OAuth callback and Backstage integration code is typical async JavaScript using closures, making the Worker code potentially susceptible to this class of defect. The release also upgrades the Node.js compatibility layer from v20 to v22 and delivers improved fetch error diagnostics.

## Proposed solution
The runtime version is controlled by the `workerd` peer dependency resolved through wrangler. The upgrade path follows these steps:

**Step 1 — Verify automatic resolution via wrangler.**
Inspect whether `wrangler@4.86.0` (the version targeted by `wrangler-full-upgrade`) already resolves to workerd v1.20260430.1 via its `package.json` `peerDependencies` or `optionalDependencies`. Run `npm ls workerd` inside `cloudflare-worker/` after installing `wrangler@4.86.0` to confirm the resolved version.

**Step 2 — Pin if automatic resolution falls short.**
If the resolved workerd version is below v1.20260430.1, add an explicit pin in one of two ways (in order of preference):

- `cloudflare-worker/package.json`: add `"workerd": "1.20260430.1"` as a direct devDependency so that `npm install` inside the directory always resolves to the target version.
- `wrangler.toml`: set `compatibility_date = "2026-04-30"` to signal the Cloudflare platform to run the Worker on a runtime that includes the fixes from that date; this does not pin the exact binary version but ensures the compatibility tier matches.

Using the `package.json` pin is preferred for local reproducibility; the `compatibility_date` in `wrangler.toml` should be set to `2026-04-30` regardless, as it governs which platform APIs the Worker may use.

**Step 3 — Update `compatibility_date` in `wrangler.toml`.**
Set `compatibility_date = "2026-04-30"`. This is a low-risk change: compatibility dates only unlock new behaviours; they never remove existing ones for running Workers unless explicitly listed as a breaking compatibility flag.

**Step 4 — Validate with `wrangler dev` and a staging deploy.**
Run `wrangler dev` locally and smoke-test all four `/api/*` endpoints. Deploy to a staging Worker slot (or the same Worker with a temporary name) and run `wrangler tail` to confirm richer fetch error messaging and the absence of runtime errors.

**Step 5 — Promote to production.**
Push the version bump via the standard `deploy.yml` GitHub Actions pipeline. No configuration changes to secrets, routes, or rate-limit bindings are required.

No changes to Worker business logic, Nuxt frontend, or Kubernetes manifests are needed.

## Alternatives

### Option A: Rely solely on upgrading wrangler (no explicit workerd pin)
Upgrade wrangler to 4.86.0 (as per `wrangler-full-upgrade`) and assume that the bundled workerd version is sufficient. This is simpler but does not guarantee that wrangler@4.86.0 bundles workerd v1.20260430.1 specifically — wrangler release timelines and workerd release timelines are independent. Rejected as the primary approach because the use-after-free fix is a safety concern that warrants explicit verification and pinning.

### Option B: Pin workerd via `wrangler.toml` `compatibility_date` only
Set `compatibility_date = "2026-04-30"` in `wrangler.toml` without a direct `workerd` package pin. This signals the target runtime tier to Cloudflare but does not guarantee local `wrangler dev` uses the same binary. Rejected as the sole mechanism because it creates a divergence between local development (where the wrangler-bundled workerd is used) and the production deployment. Accepted as a complement to the `package.json` pin.

### Option C: Wait for the next wrangler release to bundle the fixed workerd automatically
Defer the upgrade until a future wrangler release that demonstrably includes workerd v1.20260430.1 as its bundled runtime. Rejected because the use-after-free defect is present in the production Worker now and the fix is available today; deferral extends the window of exposure on the `/api/*` endpoints that handle OAuth and tenant provisioning.

## Platform impact

### Migrations
- `wrangler.toml` `compatibility_date` updated to `2026-04-30` — a non-breaking Cloudflare configuration change.
- `cloudflare-worker/package.json` may gain a `"workerd": "1.20260430.1"` devDependency entry; `package-lock.json` will be updated accordingly.
- No database migrations, no secret rotations, no Worker route changes.

### Backward compatibility
The Worker's public API surface (`/api/*` endpoints, request/response contracts, rate limits) is entirely unchanged. workerd v1.20260430.1 introduces no new compatibility flags that would alter existing request-handling behavior. The Node.js v22 compatibility layer is a superset of v20; no Worker code needs to change to remain compatible.

### Resource impact
The Worker runs on Cloudflare's infrastructure, not on any Kubernetes tenant. There is zero CPU or memory impact on the `admins` Kubernetes tenant and zero impact on the `labs` tenant. The `labs` tenant is noted to be close to its memory ceiling; this proposal does not touch any Kubernetes workload and therefore carries no `labs` memory risk.

### Risks and mitigations
- **Risk:** wrangler@4.86.0 does not bundle workerd v1.20260430.1; the use-after-free defect remains in production after the wrangler upgrade alone.
  **Mitigation:** Step 1 explicitly verifies the resolved workerd version; an explicit `package.json` pin is added if necessary (Step 2).
- **Risk:** The Node.js v22 compatibility layer introduces a behavioral difference in a Node.js-compat API used by the Worker.
  **Mitigation:** Smoke-testing all four `/api/*` endpoints in `wrangler dev` (Task 3) and a staging deploy (Task 4) will surface any behavioral regressions before production.
- **Risk:** The `compatibility_date` bump to `2026-04-30` enables a new Cloudflare platform behavior that changes Worker semantics.
  **Mitigation:** Cloudflare's compatibility flags list for 2026-04-30 should be reviewed against the Worker's code paths. If a flag is found to be risky, it can be explicitly disabled via `compatibility_flags = ["disable_<flag>"]` in `wrangler.toml` without blocking the date bump.
- **Risk:** Cloudflare's production runtime does not update to workerd v1.20260430.1 immediately after deploy.
  **Mitigation:** `wrangler versions list` and the Cloudflare dashboard Worker settings page both show the active runtime version; verification is included as a post-deploy acceptance check (Task 5).
