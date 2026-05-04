# Design: nuxt-minor-upgrade

## Current state
`mctl-web` uses Nuxt 4.3.1 declared in `package.json` (root, not inside `cloudflare-worker/`). The build mode is SSG: `nuxt build` prerenderers three routes (`/`, `/docs`, `/privacy`) and emits static files into `dist/`. Vue 3.5.30, vue-router 4.6.4, vee-validate 4.15.1, yup 1.7.1, @vueuse/core 14.2.1, sass 1.98.0, and vite-svg-loader 5.1.1 are the peer dependencies. There are no Nuxt modules beyond the standard Nuxt 4 built-ins. See `context/architecture.md` for the full stack.

## Proposed solution
Update the `nuxt` version constraint in the root `package.json` to `^4.4.4` (or the exact pin `4.4.4`), regenerate the lockfile, and verify the build. No code changes to pages, composables, or configuration are anticipated because the 4.3.x → 4.4.x transition is a minor version bump within a stable major line.

The upgrade workflow:
1. Update `nuxt` in `package.json`.
2. Run `npm install` to regenerate the lockfile.
3. Run `nuxt build` locally and verify `dist/` contains the three prerendered routes with correct content.
4. Run the project's smoke tests (if any exist) or perform a manual spot-check of each route.
5. Open a PR with the lockfile diff and build output evidence.

Nuxt 4.4.4 was published on 29 April 2026. The 4.4.3 tag was released immediately before it and superseded in the same session; 4.4.4 is the canonical release. No API-breaking changes are declared in the 4.4.x changelog for the APIs used by this project.

## Alternatives

### Stay on 4.3.1 indefinitely
The site is functional today on 4.3.1 and there is no known security CVE in Nuxt itself that demands an immediate upgrade. Deferring is a valid option for zero-disruption operations. Rejected because upgrade debt compounds; a one-minor-version gap now is a much smaller risk than a multi-minor gap in six months.

### Upgrade to the latest possible Nuxt 4.x at the time of the PR
Targeting `latest` rather than `^4.4.4` would keep the project maximally current but introduces non-determinism — the resolved version depends on the date the lockfile is regenerated. Rejected in favour of pinning to the known-tested 4.4.4.

### Upgrade Nuxt together with vue-router to 5.x
Vue Router 5.0.6 was released on 22 April 2026 as a major version bump from the currently pinned 4.6.4. Bundling a major router upgrade with a Nuxt minor bump multiplies risk and effort. Rejected; the router upgrade is a separate, higher-effort proposal.

## Platform impact

### Migrations
- Root `package.json`: bump `nuxt` to `^4.4.4`.
- Regenerate root lockfile (`package-lock.json` or `pnpm-lock.yaml`).
- No schema, database, or infrastructure changes required.

### Backward compatibility
Nuxt 4.4.x is a minor release of the 4.x line. The composable API, `nuxt.config.ts` options, and prerender configuration are backward-compatible. If any deprecated API produces a build warning, it must be addressed in the same PR.

### Resource impact
Nuxt 4.4.x is expected to produce similar or smaller prerendered output than 4.3.1. There is no change to Worker memory or the Kubernetes cluster. The frontend is served as static files from Cloudflare Pages. No impact on `labs` tenant memory.

### Risks and mitigations
- **Risk:** An undocumented breaking change in 4.4.x breaks a page component. **Mitigation:** Run `nuxt build` locally and inspect the three prerendered routes before pushing. CI must pass a build step.
- **Risk:** A transitive dependency introduced by 4.4.4 carries a new CVE. **Mitigation:** Run `npm audit` against the updated lockfile; no new High/Critical findings are acceptable before merge.
- **Risk:** `vite-svg-loader` or another Vite plugin is incompatible with the Vite version bundled in Nuxt 4.4.4. **Mitigation:** Check the Nuxt 4.4.4 release notes for Vite version changes; test SVG imports during local build verification.
