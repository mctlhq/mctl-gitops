# Tasks: vue-router-v5-migration-v2

- [ ] 1. Check Nuxt 4.4.x peer-dependency range for vue-router: run `npm info nuxt@4.4.4 peerDependencies` and confirm whether `vue-router@5.0.6` falls within the declared range — DoD: result documented in the PR description as `compatible`, `incompatible` (proposal deferred), or `no range declared` (proceed with caution).

- [ ] 2. Create a feature branch; update `"vue-router"` in `package.json` to `"5.0.6"` and run `npm install` (depends on 1, only if compatible) — DoD: `package.json` shows `5.0.6`; lockfile is updated; `npm install` exits 0 with no unresolved peer-dependency conflicts.

- [ ] 3. Run `nuxt build` on the feature branch and resolve any errors (depends on 2) — DoD: `nuxt build` exits 0; no new errors or warnings referencing vue-router appear in the build output.

- [ ] 4. Add `experimental: { typedPages: true }` to `nuxt.config.ts` and run `tsc --noEmit` (depends on 3) — DoD: TypeScript compilation exits 0; auto-generated route types for `/`, `/docs`, `/privacy` are present in `.nuxt/`; no type errors.

- [ ] 5. Run a local preview (`nuxt preview` or equivalent) and smoke-test all three prerendered routes (depends on 3) — DoD: `/`, `/docs`, `/privacy` each return HTTP 200 with correct HTML content; browser console contains no `[Vue Router warn]` messages.

- [ ] 6. Audit all `useRouter()` and `useRoute()` call sites across `app/pages/` and `app/components/` for any API usage that changed in v5 (depends on 2) — DoD: all call sites reviewed; any required adjustments committed; no unresolved API incompatibilities.

- [ ] 7. Write ADR `context/decisions/0004-vue-router-v5-migration.md` documenting the decision, compatibility outcome, and any call-site changes made (depends on 3, 4, 5, 6) — DoD: ADR file merged to `context/decisions/` before the feature branch is merged to `main`.

- [ ] 8. Open a PR targeting `main`, referencing this proposal and the ADR; request review from at least one platform engineer (depends on 7) — DoD: PR is open; all CI checks (build, type-check) are green; at least one reviewer assigned.

- [ ] 9. Merge PR and confirm successful Cloudflare Pages deploy (depends on 8) — DoD: production site serves `/`, `/docs`, `/privacy` correctly; Cloudflare Pages deployment log shows `nuxt build` completed without errors.

## Tests
- [ ] T1. `nuxt build` exits 0 on the feature branch with `vue-router@5.0.6`.
- [ ] T2. All three prerendered routes (`/`, `/docs`, `/privacy`) return HTTP 200 with correct HTML in both local preview and the production deploy.
- [ ] T3. `tsc --noEmit` exits 0 with `experimental.typedPages: true` enabled.
- [ ] T4. No `[Vue Router warn]` messages appear in the browser console during navigation between all three routes.
- [ ] T5. The Cloudflare Worker `/api/*` endpoints (`/api/github/login`, `/api/contact`) continue to respond correctly after the frontend deploy (confirming the Worker is unaffected).

## Rollback
vue-router is a build-time and client-side dependency only; the Cloudflare Worker is deployed independently and is not affected.

To roll back:
1. Revert `package.json` to `"vue-router": "4.6.4"` and remove `experimental.typedPages` from `nuxt.config.ts`.
2. Run `npm install` to restore the previous lockfile state.
3. Trigger a new Cloudflare Pages deploy from the reverted commit.
4. Confirm all three prerendered routes serve correctly.

No database migrations, Worker changes, or infrastructure changes are involved, so rollback is a single-commit revert with a redeploy.
