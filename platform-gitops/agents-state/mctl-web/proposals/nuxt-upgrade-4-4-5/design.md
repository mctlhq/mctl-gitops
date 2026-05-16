# Design: nuxt-upgrade-4-4-5

## Current state
mctl-web (`app/`) declares `nuxt` at version 4.3.1 in `app/package.json` (see `context/architecture.md`). The application uses `nuxt build` to produce a prerendered `dist/` that is served as static files via Cloudflare Pages / nginx. Three routes are prerendered: `/`, `/docs`, `/privacy`. The build is triggered by `deploy.yml` in this repository — the only service in the platform with a non-gitops deploy pipeline.

Nuxt 4.4.5 is the current latest release (2026-05-10). Intermediate releases 4.4.0–4.4.5 introduced:
- A caching layer for root resolution during SSG prerender (reduces repeated FS lookups).
- Short-circuit evaluation of `isIgnored` for relative paths (reduces unnecessary regex evaluation at build time).
- Bug fixes in Vite plugin integration, Nitro server handling, and server component hydration.

## Proposed solution
Update the `nuxt` version specifier in `app/package.json` from `4.3.1` to `^4.4.5` (or `>=4.4.5 <5.0.0`), run `npm install`, and verify the build pipeline passes end-to-end.

**Steps at implementation time:**
1. In `app/package.json`, update `"nuxt": "4.3.1"` to `"nuxt": "^4.4.5"`.
2. Run `npm install` to refresh `package-lock.json`.
3. Run `nuxt build` locally; confirm `dist/` is produced cleanly.
4. Run lint + type-check steps.
5. Commit and open a PR; CI (`deploy.yml`) must pass before merge.

No configuration changes to `nuxt.config.ts` are expected (Nuxt 4.4.x is backward-compatible with 4.3.x configuration).

## Alternatives

**Option A — Pin to exactly 4.4.4 (the previous latest).**  
4.4.4 is superseded; 4.4.5 is available and includes additional fixes. Rejected — no reason to target a stale patch.

**Option B — Upgrade to Nuxt 4.5.x or later when available.**  
A separate minor version bump warrants its own proposal and risk assessment. Rejected for this scope.

**Option C — Rely on Dependabot / Renovate to open the PR automatically.**  
Valid long-term automation, but covered under the separate `automated-dep-updates` proposal. This proposal ensures the manual upgrade is tracked and prioritised now.

## Platform impact
- **Migrations:** none — Nuxt 4.4.x is API-compatible with 4.3.x; no `nuxt.config.ts` changes required.
- **Backward compatibility:** full within the 4.x line.
- **Resource impact:** SSG build output size is expected to be identical or marginally smaller due to the build optimisations. No runtime memory or CPU change in the `admins` tenant. No impact on `labs` tenant (mctl-web is in `admins`; Worker runs on Cloudflare).
- **Risks and mitigations:** low. A minor Nuxt upgrade could surface a configuration incompatibility with a Nuxt module in use. Mitigated by running the full build + type-check in CI; the prerendered routes are verifiable via smoke tests against the built `dist/`.
