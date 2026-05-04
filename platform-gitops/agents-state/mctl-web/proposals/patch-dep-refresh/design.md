# Design: patch-dep-refresh

## Current state
The root `package.json` of `mctl-web` pins the following versions (see `context/architecture.md`):
- `vue`: 3.5.30
- `@vueuse/core`: 14.2.1
- `sass`: 1.98.0

All three are used exclusively in the Nuxt SSG frontend. The Cloudflare Worker (`cloudflare-worker/`) has its own `package.json` and does not depend on any of these three packages. The Kubernetes cluster and the `labs` tenant are unaffected because these are build-time dependencies that produce static assets served from Cloudflare Pages.

Available newer releases as of 2026-05-04:
- `vue` 3.5.33 (released 22 Apr 2026, patch bump from 3.5.30)
- `@vueuse/core` 14.3.0 (released 01 May 2026, minor bump; adds new composable features but does not remove or change existing ones)
- `sass` (dart-sass) 1.99.0 (released 02 Apr 2026; adds parent-selector support at document root; restricts user-defined function names that clash with `calc`/`clamp` — this is the only change that could surface a warning if any SCSS file defines such a function)

## Proposed solution
Update the three version constraints in the root `package.json` in a single commit:
- `"vue": "^3.5.33"` (or exact pin `3.5.33`)
- `"@vueuse/core": "^14.3.0"` (or exact pin `14.3.0`)
- `"sass": "^1.99.0"` (or exact pin `1.99.0`)

Regenerate the root lockfile, run `nuxt build` to confirm the prerendered output is correct, check for any sass function-name deprecation warnings, and open a single PR.

This is the simplest possible approach: no code changes, no architectural adjustments, and no new concepts introduced. The batch approach is chosen over three separate PRs to reduce reviewer fatigue while still maintaining a clear, reviewable diff.

## Alternatives

### Three separate PRs (one per package)
Each bump is independently reviewable and bisectable. The overhead is three code reviews and three CI runs for changes that are individually trivial. Rejected as disproportionate effort for patch-level updates.

### Wait for a larger upgrade cycle
Bundle these bumps with the `nuxt-minor-upgrade` or a future `vue-router-v5` migration. Rejected because it unnecessarily delays low-risk, low-effort changes and complicates the diff of a more significant upgrade.

### Use a dependency bot (Dependabot / Renovate)
Automating future patch bumps via Dependabot or Renovate would remove the need for manual proposals for patch-level work. This is a valid long-term improvement but is out of scope for this proposal. If adopted, it would make this class of proposal obsolete.

## Platform impact

### Migrations
- Root `package.json`: update three version constraints.
- Regenerate root lockfile.
- Inspect SCSS source files for any function names that match CSS built-ins (`calc`, `clamp`, `min`, `max`, etc.) — sass 1.99.0 restricts these; rename if found.

### Backward compatibility
All three updates are within stable minor or patch lines. Vue 3.5.33 and @vueuse/core 14.3.0 are additive. Sass 1.99.0 is the only one with a potentially visible behavioural change (function-name restriction), but this only emits a deprecation warning (not a build error) and only if the project defines such a function — which is unlikely given the site's scope.

### Resource impact
No change to Worker memory, container resource requests, or any Kubernetes workload. The `labs` tenant is entirely unaffected. Build artefact size is expected to remain the same or decrease marginally.

### Risks and mitigations
- **Risk:** sass 1.99.0 deprecation warning for a function named `calc` or `clamp` in project SCSS. **Mitigation:** Grep all `.scss` files for `@function calc` / `@function clamp` before finalising the PR; rename any matches.
- **Risk:** @vueuse/core 14.3.0 changes the internal behaviour of an existing composable in a way that is not documented. **Mitigation:** Run `nuxt build` and manually verify the three pages; any runtime difference will be caught by visual spot-check.
- **Risk:** Vue 3.5.33 introduces a subtle reactivity behaviour change. **Mitigation:** The three prerendered routes use standard Vue reactivity patterns; the SSG output is deterministic and can be diffed against the baseline.
