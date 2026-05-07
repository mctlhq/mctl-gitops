# Design: nuxt-minor-upgrade-v2

## Current state
As documented in `context/architecture.md`, mctl-web uses Nuxt 4.3.1 with SSR enabled and prerendering configured for `/`, `/privacy`, and `/docs`. The build outputs a static `dist/` directory served via Cloudflare Pages. Vue 3.5.30 is the currently installed Vue core version, brought in as a peer dependency of Nuxt. The full frontend dependency tree also includes vue-router 4.6.4, vee-validate 4.15.1, yup 1.7.1, @vueuse/core 14.2.1, sass 1.98.0, and vite-svg-loader 5.1.1.

## Proposed solution
Update the `nuxt` package in `package.json` from `4.3.1` to `4.4.3`, regenerate `package-lock.json`, and validate the build. No other primary dependencies need version changes; Vue 3.5.34 will be resolved automatically as Nuxt 4.4.3 declares updated Vue peer dependencies.

The upgrade approach is intentionally narrow: only `nuxt` is bumped explicitly. If compatibility errors arise with other packages (e.g., @vueuse/core 14.2.1 or vite-svg-loader 5.1.1), those will be bumped to their current latest as a secondary step within the same PR, with changes logged in the PR description.

The rationale for upgrading rather than staying at 4.3.1:
- Two minor versions of Nuxt represent a meaningful accumulation of fixes that reduce technical risk.
- The Vue 3.5.34 patches fix reactivity edge cases relevant to form-heavy pages (tenant creation form uses vee-validate + yup).
- Staying current on Nuxt ensures access to security backports should a vulnerability be disclosed in the 4.3.x line.

## Alternatives

**Option A — Upgrade Nuxt to the latest available (4.4.x at time of implementation).**
This is effectively the same as the proposed solution if 4.4.3 is the latest 4.4.x. If a 4.4.4 or 4.4.5 exists at implementation time, the implementor should target that instead and update this proposal accordingly.

**Option B — Wait for Nuxt 4.5.x and do one larger upgrade.**
This delays the Vue 3.5.34 patches and increases the size of the eventual diff. The accumulation of skipped versions raises the probability of a hidden breaking change at upgrade time. Rejected in favor of incremental upgrades.

**Option C — Upgrade Nuxt and all frontend dependencies simultaneously.**
Bundling all dependency bumps into one PR maximizes diff size and makes regression isolation harder. A targeted Nuxt upgrade with Vue pulled in transitively keeps the PR reviewable and bisectable. Rejected.

## Platform impact
- **Migrations:** No database migrations. No changes to `wrangler.toml`, Kubernetes manifests, or ArgoCD configuration. The build output format (`dist/`) does not change.
- **Backward compatibility:** Nuxt 4.x minor releases are backward compatible by policy. The upgrade should not require changes to `nuxt.config.ts`, page components, or composables. If any Nuxt-internal API used by the codebase was deprecated in 4.4.x, it will surface as a build warning, not an error.
- **Resource impact:** The `labs` tenant is not directly affected — mctl-web runs under the `admins` tenant. The build runs in GitHub Actions, not in the Kubernetes cluster. The built static output size may change marginally but is served via Cloudflare Pages with no memory pressure on the cluster.
- **Risks and mitigations:** The primary risk is a silent regression in prerendering behavior for one of the three routes. Mitigation: run `nuxt build` and inspect the `dist/` output in CI, and deploy to a Cloudflare Pages preview URL before merging to main. A snapshot test of the prerendered HTML for each route would catch structural regressions.
