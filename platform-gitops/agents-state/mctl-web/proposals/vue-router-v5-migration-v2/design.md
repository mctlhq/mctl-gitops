# Design: vue-router-v5-migration-v2

## Current state
Per `context/architecture.md`, mctl-web pins `"vue-router": "4.6.4"` alongside Nuxt 4.3.1 and Vue 3.5.30. The project has three prerendered pages (`/`, `/docs`, `/privacy`) with no dynamic route segments or nested named views. `unplugin-vue-router` is not currently used; typed routes are not enabled. As of the 2026-05-01 release cycle, vue-router v4.x received no new releases, with all activity concentrated in v5. The previous planning proposal (`vue-router-v5-migration`) established the audit framework; this proposal executes on it.

## Proposed solution
The migration is a single `package.json` version bump with two accompanying configuration changes, applied in one PR:

**1. Bump vue-router to v5.0.6.**
In `package.json`, change:
```json
"vue-router": "4.6.4"
```
to:
```json
"vue-router": "5.0.6"
```
Run `npm install` and commit the updated lockfile. Since mctl-web does not use `unplugin-vue-router` or any v4-specific API that changed in v5, no component-level code changes are expected.

**2. Verify Nuxt peer-dep compatibility before merging.**
Nuxt resolves vue-router as a peer dependency. Before the PR is opened against `main`, run `npm install --dry-run` and check for peer-dep warnings. If Nuxt 4.4.x's peer-dep range does not yet include v5, the PR is held and this proposal is deferred pending a Nuxt release; the finding is documented in the PR description.

**3. Enable typed routes.**
In `nuxt.config.ts`, add:
```typescript
experimental: {
  typedPages: true,
}
```
This activates vue-router v5's integrated typed-route generation (replacing `unplugin-vue-router`). All three route paths are simple static strings, so the generated types will be straightforward. Confirm `tsc --noEmit` exits 0.

**4. Smoke-test prerendered pages.**
Run `nuxt build` followed by a local preview and visit `/`, `/docs`, `/privacy`. Confirm correct rendering and no console warnings.

The migration is deliberately narrow. No `useRouter()` / `useRoute()` API calls are expected to change for the static-route pattern mctl-web uses. Any call-site adjustments discovered during the build are treated as blocking tasks before merge.

## Alternatives
1. **Stay on vue-router 4.6.4 indefinitely.** No engineering cost today, but the version is no longer receiving releases. A future security advisory landing only in v5 would force an emergency migration under time pressure. Rejected.
2. **Wait until Nuxt officially certifies vue-router v5 in its own release notes.** Lower risk but introduces an indefinite delay. Given that Nuxt 4.4.x's peer-dep range likely already accommodates v5 (to be verified in task 1), waiting passively is unnecessary. Rejected: the compatibility check is the first task, not a blocker to opening the proposal.
3. **Adopt unplugin-vue-router separately before upgrading to v5.** This was the migration path recommended before v5 launched. It is now obsolete: v5 ships the plugin natively. Adding unplugin-vue-router as an intermediate step creates unnecessary churn. Rejected.

## Platform impact
- **Migrations:** Single `package.json` + lockfile change and one `nuxt.config.ts` addition. No database migrations, no Worker changes, no infrastructure changes.
- **Backward compatibility:** vue-router v5 explicitly declares no breaking changes for projects not using `unplugin-vue-router`. mctl-web is in this category. Risk of call-site breakage is very low.
- **Resource impact:** vue-router v5's bundle size is comparable to v4; the three static routes produce negligible type-generation output. No impact on the `labs` tenant — this is a frontend build change only, deploying to Cloudflare Pages. `labs` memory is not affected.
- **Risks and mitigations:**
  - *Nuxt peer-dep incompatibility:* Mitigation — verify with `npm install --dry-run` before opening the PR; defer if incompatible.
  - *Typed-routes generation errors on existing route names:* Mitigation — `tsc --noEmit` is a required gate before merge; revert `typedPages` option if it blocks the migration.
  - *Cloudflare Pages deploy failure:* Mitigation — run the full `nuxt build` in CI on the feature branch; the Worker deploy (`deploy.yml`) is independent and unaffected.
