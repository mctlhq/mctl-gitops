# Tasks — nuxt-444-formdata-fix

## Checklist

- [ ] 1. Bump nuxt in package.json — Edit `package.json` to change the nuxt
  version specifier from `4.3.1` (or `^4.3.1`) to `^4.4.4`. Commit the
  change on a feature branch `fix/nuxt-444-formdata-fix`.
  DoD: `package.json` contains `"nuxt": "^4.4.4"` and the change is the
  only diff in that file.

- [ ] 2. Regenerate lockfile (depends on 1) — Run `npm ci` (or `npm install`
  followed by a clean `npm ci` to validate the lockfile) in the project
  root. Commit the updated `package-lock.json`.
  DoD: `npm ci` exits 0 with no peer-dependency warnings related to nuxt;
  `package-lock.json` reflects nuxt 4.4.4 as the resolved version.

- [ ] 3. Verify build (depends on 2) — Run `nuxt build` locally and confirm
  the `dist/` directory is produced, all three prerendered routes (`/`,
  `/docs`, `/privacy`) appear in the output, and no build errors or
  deprecation warnings are emitted.
  DoD: `nuxt build` exits 0; `dist/` contains `index.html`, `docs/index.html`,
  `privacy/index.html`.

- [ ] 4. Run unit tests (depends on 2) — Execute the existing unit test suite
  (`npm test` or equivalent). No new failures may be introduced.
  DoD: all tests pass; test report shows 0 new failures compared to the
  baseline on `main`.

- [ ] 5. Run end-to-end tests against local build (depends on 3, 4) — Start
  the built site locally (`npx serve dist/` or `nuxt preview`) and execute
  the Playwright/Cypress suite, including the tenant sign-up form scenario.
  DoD: all E2E tests pass; the sign-up form scenario sends exactly one POST
  to `/api/submit` (verified via network intercept or mock) with no duplicate
  requests on retry simulation.

- [ ] 6. Deploy to staging (depends on 5) — Push the branch, trigger the
  `deploy.yml` workflow against the staging Cloudflare Pages + Worker
  environment, and perform a manual smoke test of the sign-up form end-to-end
  (Backstage call, Telegram notification, Resend email).
  DoD: staging smoke test passes; Telegram receives exactly one notification
  per form submission; Resend logs exactly one email dispatch; Backstage shows
  one provisioning workflow triggered.

- [ ] 7. Merge to main and deploy to production (depends on 6) — Open a PR,
  obtain approval, merge, and confirm the production deployment completes via
  `deploy.yml`.
  DoD: production site reports Nuxt version 4.4.4 in the build manifest;
  monitoring shows no error-rate spike in the 30 minutes following deploy.

## Tests

- T1. Unit: `useFetch` deduplication key test — assert that two successive
  `useFetch` calls with identical `FormData` bodies produce the same cache key
  (test against the Nuxt composable directly or via a vitest mock of the
  deduplication utility).

- T2. E2E: sign-up form happy path — submit the tenant sign-up form with valid
  data; assert the UI shows the success state; assert the network log contains
  exactly one POST to `/api/submit`.

- T3. E2E: retry simulation — intercept the first POST to `/api/submit` and
  return a 503; assert the client retries; assert only one provisioning request
  reaches the Worker after the retry succeeds (no duplicate).

- T4. Prerender smoke — load `/`, `/docs`, `/privacy` in a browser with
  simulated slow network; assert all three pages hydrate without a full reload
  or flash-of-unhydrated-content.

- T5. Build regression — run `nuxt build` in CI on every PR targeting `main`;
  fail the build gate if `nuxt build` exits non-zero or if the prerendered
  output is missing any of the three expected routes.

## Rollback plan

1. Revert the `package.json` and `package-lock.json` commits on `main` to
   restore nuxt 4.3.1.
2. Push the revert commit; the `deploy.yml` workflow will automatically
   redeploy the previous build to Cloudflare Pages and the Worker.
3. Verify the production site is serving the reverted build by checking the
   Nuxt build manifest version.
4. If the automatic redeploy does not trigger, manually re-run the last
   successful `deploy.yml` run against the pre-bump commit SHA from the
   GitHub Actions UI.
5. No database migrations or Cloudflare Worker secrets changes are involved;
   rollback is purely a code revert and redeploy.
