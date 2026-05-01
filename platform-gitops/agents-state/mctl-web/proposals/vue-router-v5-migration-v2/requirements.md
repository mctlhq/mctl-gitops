# vue-router v5 Migration: Execution Phase

## Context
mctl-web currently uses vue-router 4.6.4. As of the 2026-05-01 reporting cycle, vue-router v4.x has ceased receiving new releases; all future security patches and bug fixes are being directed exclusively to v5. The latest stable release is v5.0.6 (released April 22, 2026), which merges `unplugin-vue-router` into core and declares no breaking changes relative to v4 for projects that do not use `unplugin-vue-router` — which includes mctl-web.

The earlier proposal `vue-router-v5-migration` established the compatibility audit phase (Phase 1). This proposal (`vue-router-v5-migration-v2`) covers the execution phase (Phase 2): the actual version bump, any API adjustments, and enabling typed routes. The delta is small — mctl-web has only three static routes (`/`, `/docs`, `/privacy`), no dynamic segments, and no named views — making this a low-risk, high-value migration. Remaining on v4 accumulates technical debt and, if a security fix lands only in v5, would trigger a forced high-urgency migration.

## User stories
- AS a platform engineer I WANT vue-router upgraded to v5.0.6 SO THAT the service is on a supported release line that will receive future security patches.
- AS a developer I WANT typed route names and params enabled via vue-router v5's integrated `unplugin-vue-router` SO THAT route mismatches are caught at compile time rather than at runtime.
- AS a platform operator I WANT the migration completed with zero downtime and no change to prerendered routes SO THAT end users experience no disruption.

## Acceptance criteria (EARS)
- WHEN `npm install` is run with `vue-router` set to `5.0.6` THE SYSTEM SHALL resolve all peer dependencies without conflicts.
- WHEN `nuxt build` is executed on the upgraded branch THE SYSTEM SHALL complete with exit code 0 and no new errors or warnings related to the router.
- WHEN a user navigates to `/`, `/docs`, or `/privacy` THE SYSTEM SHALL render the correct prerendered page with no `[Vue Router warn]` messages in the browser console.
- WHEN typed routes are enabled via `experimental.typedPages: true` in `nuxt.config.ts` THE SYSTEM SHALL produce a TypeScript compilation (`tsc --noEmit`) that exits 0.
- IF Nuxt 4.4.x declares a peer-dependency range that excludes vue-router v5 THEN THE SYSTEM SHALL NOT proceed with the version bump until Nuxt compatibility is confirmed; the finding SHALL be documented and this proposal deferred.
- WHILE the Cloudflare Worker deployment is live THE SYSTEM SHALL continue to serve all `/api/*` routes without interruption regardless of the vue-router upgrade (the Worker is independent of vue-router).
- WHEN the migration PR is merged THE SYSTEM SHALL include an ADR entry (`context/decisions/`) recording the vue-router v5 adoption decision.

## Out of scope
- Introducing new routes or changing the URL structure of existing pages.
- Migrating to a different router library.
- Changes to the Cloudflare Worker routing configuration (`cloudflare-worker/wrangler.toml`).
- Upgrading Vue core (3.5.30) beyond what Nuxt 4.4.x requires as a peer dependency.
- Adopting experimental vue-router v5 features beyond typed routes (e.g., view transitions API changes).
