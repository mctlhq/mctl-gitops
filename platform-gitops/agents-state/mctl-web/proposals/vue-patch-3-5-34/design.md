# Design: vue-patch-3-5-34

## Current state
mctl-web (`app/`) is a Nuxt 4.3.1 application (see `context/architecture.md`) that declares `vue` as a peer dependency managed by Nuxt. The pinned Vue version in use is 3.5.30. Nuxt resolves `vue` transitively; the effective version is whatever Nuxt's own `package.json` resolves to at install time. As of Nuxt 4.3.1, the resolved Vue is 3.5.30.

The DOM leak, ref-wrapper inference regression, and suspense fixes introduced between 3.5.30 and 3.5.34 are relevant to client-side hydration of the prerendered routes served by Nuxt.

## Proposed solution
Pin `vue` explicitly to `^3.5.34` (or `>=3.5.34 <3.6.0`) in `app/package.json`. This overrides any transitive resolution that might lock to an older patch and guarantees the fix set is applied.

**Steps at implementation time:**
1. In `app/package.json`, update the `vue` version specifier to `^3.5.34`.
2. Run `npm install` (or the project's preferred lock-file manager) to update `package-lock.json`.
3. Run `nuxt build` to verify no breaking changes.
4. Run the existing lint + type-check steps.

Because this is a semver patch bump within the 3.5.x line, no API surface changes or migration steps are required.

## Alternatives

**Option A — Rely on Nuxt's transitive resolution (no explicit pin).**  
Simpler, but does not guarantee the fix arrives promptly; Nuxt 4.3.1 may continue resolving 3.5.30. Rejected in favour of an explicit pin for determinism.

**Option B — Upgrade Nuxt to 4.4.5 first, which transitively pulls Vue ≥ 3.5.34.**  
Valid, but couples two independent changes. Either proposal can be done independently; the Vue pin is lower-risk and faster. Rejected as sole strategy — both upgrades should be tracked separately.

**Option C — Wait for Nuxt's next minor to upgrade Vue automatically.**  
No clear timeline; leaves the DOM leak unpatched in the interim. Rejected.

## Platform impact
- **Migrations:** none — patch bump, no API changes.
- **Backward compatibility:** fully maintained within Vue 3.5.x.
- **Resource impact:** no change to runtime memory or CPU; Vue bundle size is negligibly different between patch versions. No impact on `labs` tenant (mctl-web runs in `admins`; Worker runs on Cloudflare).
- **Risks and mitigations:** low. The risk of a semver-compatible patch introducing a regression is minimal. Mitigated by running the full build + type-check in CI before merging.
