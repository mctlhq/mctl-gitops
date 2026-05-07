# Tasks: vue-router-v5-migration-v3

- [ ] 1. Audit vue-router API usage in the codebase — DoD: Every file using `useRouter`, `useRoute`, `<RouterLink>`, `<NuxtLink>`, `router.push`, `router.replace`, or navigation guards is listed in the PR description. Each usage is annotated as "unchanged in v5", "deprecated", or "breaking change with mitigation".

- [ ] 2. Confirm Nuxt 4.4.x compatibility with vue-router 5.x (depends on 1) — DoD: The Nuxt 4.4.x release notes and source are checked for internal vue-router version requirements. The PR description documents whether Nuxt 4.4.x already bundles or requires vue-router 5.x, or whether an explicit override is needed.

- [ ] 3. Bump vue-router to 5.0.6 in package.json and regenerate lockfile (depends on 2) — DoD: `package.json` shows `"vue-router": "5.0.6"` (or `"^5.0.6"`). `npm install` completes without peer dependency conflicts. `package-lock.json` is committed with the updated resolution.

- [ ] 4. Resolve TypeScript and build errors (depends on 3) — DoD: `nuxt build` completes without TypeScript errors, type errors, or unresolved import errors. If any component required API changes due to vue-router v5, those changes are applied and documented in the PR description.

- [ ] 5. Deploy to Cloudflare Pages preview (depends on 4) — DoD: The preview URL serves HTTP 200 for `/`, `/docs`, and `/privacy`. Navigation between pages via `<NuxtLink>` works without console errors. Client-side routing transitions function correctly.

- [ ] 6. Validate OAuth redirect flow in preview (depends on 5) — DoD: The GitHub OAuth login flow (`/api/github/login` → GitHub → `/api/github/callback`) completes successfully in the preview environment and lands the user on the expected post-login page. No router-related errors appear in the browser console.

- [ ] 7. Merge to main and confirm production deploy (depends on 6) — DoD: `deploy.yml` completes on main. Production Cloudflare Pages serves the upgraded build. No JavaScript errors observed in the browser for 30 minutes post-deploy.

## Tests

- [ ] T1. Build smoke test — `nuxt build` exits 0 with no errors.
- [ ] T2. TypeScript check — `nuxt typecheck` (or `tsc --noEmit`) exits 0 with no route-related type errors.
- [ ] T3. Route rendering — preview URL returns HTTP 200 for `/`, `/docs`, `/privacy` via `curl -I`.
- [ ] T4. Client-side navigation — clicking `<NuxtLink>` elements between pages in the browser produces no console errors and the correct page content appears.
- [ ] T5. OAuth flow — end-to-end GitHub login in the preview environment succeeds and the post-login redirect lands on the correct page.
- [ ] T6. Form behavior — the tenant request form on the preview URL renders, validates, and submits without vue-router-related errors.

## Rollback
If the upgrade causes a regression in production:
1. Revert the `package.json` and `package-lock.json` changes via a revert commit on main.
2. Trigger `deploy.yml` on the revert commit to restore the vue-router 4.6.4 build to Cloudflare Pages.
3. No Kubernetes or ArgoCD intervention required — the service is statically served via Cloudflare Pages.
4. Open a follow-up issue documenting the regression, referencing the exact vue-router v5 changelog entry responsible, before reattempting the migration.

Note: this proposal should be applied after `nuxt-minor-upgrade-v2` is merged and stable in production, to keep the dependency surface of each change minimal.
