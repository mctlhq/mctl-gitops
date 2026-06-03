# Tasks: issue-5-feat-add-landing-page-astro-like-mctl-lo

- [ ] 1. Create `landing/` Astro project scaffold — DoD: `landing/package.json`,
  `landing/astro.config.mjs` (`output: 'static'`, `outDir: '../public'`, `base: '/'`),
  `landing/tsconfig.json` (`extends: 'astro/tsconfigs/strict'`), and
  `landing/src/pages/index.astro` (stub with `<html lang="en">` and title "PairDesk")
  all committed; `cd landing && npm ci && npm run build` exits 0 and writes
  `public/index.html`.

- [ ] 2. Author landing page content in `landing/src/pages/index.astro` (depends on 1)
  — DoD: the rendered `public/index.html` contains: (a) a brief explanation of PairDesk
  as a closed P2P bulletin board with no custody, no payments, no escrow; (b) step-by-
  step join instructions (open the bot, send `/start`, wait for admin approval);
  (c) a `<a href="https://t.me/<bot_username>">` CTA button (bot username confirmed with
  platform team before merging). No `<script>` tags in the output.

- [ ] 3. Create `landing/src/styles/landing.css` with PD token subset (depends on 1) —
  DoD: CSS file defines `--pd-bg`, `--pd-text`, `--pd-accent` (`#2f6bf6`), `--pd-text-2`,
  `--pd-hint`, `--pd-border`, `--pd-radius`, `--pd-ui` font stack, and the type scale
  variables from `web/src/pairdesk-tokens.css` as literal hex/px values (no
  `var(--tg-*)` fallbacks); `landing/src/pages/index.astro` imports the file; visual
  output matches the "Direction C — Trust / Banking" look.

- [ ] 4. Update `web/vite.config.ts` to move SPA output to `public/app/` (no
  dependencies) — DoD: `base` changed to `'/app/'`; `build.outDir` changed to
  `'../public/app'`; top-of-file comment updated; `cd web && npm run build` exits 0 and
  writes `public/app/index.html`; all `src=` and `href=` asset references in
  `public/app/index.html` begin with `/app/`.

- [ ] 5. Update `src/server.ts` SPA fallback path (depends on 4) — DoD: the `sendFile`
  call on line 65 is changed from `resolve(PUBLIC_DIR, 'index.html')` to
  `resolve(PUBLIC_DIR, 'app', 'index.html')`; the set of matched paths
  (`/app`, `/app/*`, `/admin`, `/admin/*`, `/docs`, `/docs/*`) is unchanged.

- [ ] 6. Update `Dockerfile` to add `build-landing` stage and update COPY (depends on
  1, 4) — DoD: a new `build-landing` stage installs and builds the Astro project from
  `landing/`; the runtime stage copies with three `COPY --from=` lines:
  `build-api /app/dist ./dist`,
  `build-landing /app/public ./public`,
  `build-web /app/public/app ./public/app`;
  `docker build .` exits 0 and the resulting image contains both
  `/app/public/index.html` (landing) and `/app/public/app/index.html` (SPA).

- [ ] 7. Update root `package.json` build scripts (depends on 1, 4) — DoD: a new
  `"build:landing"` script (`cd landing && npm install && npm run build`) is added; the
  `"build"` script is updated to `"npm run build:landing && npm run build:web && npm run
  build:api"`; `npm run build` from the repo root exits 0 and produces both
  `public/index.html` and `public/app/index.html`.

- [ ] 8. Update `.github/workflows/ci.yml` to add a `landing` job (depends on 1) —
  DoD: a new `landing` job (name: "landing build & type-check",
  `working-directory: landing`) runs `npm ci`, `npm run type-check`, and `npm run build`
  on `ubuntu-latest` with Node 22; job is required to pass before PR merge (update
  branch protection rules if necessary).

- [ ] 9. Verify gitops `values.yaml` requires no change (no code dependencies) — DoD:
  confirm `platform-gitops/services/labs/mctl-pairdesk/values.yaml` already contains
  `MINI_APP_URL: https://labs-mctl-pairdesk.mctl.ai/app`; document in the PR description
  that no gitops change is needed.

## Tests

- [ ] T1. `GET /` on a running instance returns HTTP 200, `Content-Type: text/html`,
  and the body contains the text "PairDesk" and a `<a href="https://t.me/` CTA.
- [ ] T2. `GET /` with `curl --head` returns `200 OK` (not a redirect).
- [ ] T3. `GET /app` returns HTTP 200 and `Content-Type: text/html`; the body is the
  React Mini App entry document (contains `<div id="root">`).
- [ ] T4. `GET /app/order-book` (a client-side SPA route) returns HTTP 200 and the same
  Mini App entry document (SPA fallback working).
- [ ] T5. `GET /api/me` without auth headers returns HTTP 401 (API routes unaffected).
- [ ] T6. `GET /healthz` returns `{"status":"ok",...}` (liveness unchanged).
- [ ] T7. Disable JavaScript in the browser and load `/` — all text content is visible
  (landing is fully static HTML; no blank screen).
- [ ] T8. The Telegram deep-link CTA in the landing renders as a visible anchor; opening
  it in a browser navigates to `https://t.me/<bot_username>`.
- [ ] T9. `docker build .` completes without error; `docker run --rm -e DATABASE_URL= -e
  AUTH_DEV_BYPASS=true -p 8099:8080 <image>` followed by `curl -s
  http://localhost:8099/` returns the landing HTML and `curl -s
  http://localhost:8099/app` returns the Mini App HTML.
- [ ] T10. CSS on the landing page uses the PairDesk blue accent (`#2f6bf6` or
  equivalent `--pd-accent`) and does not render a blank or unstyled page.

## Rollback

If the change causes a regression (broken Mini App path, asset 404s, or landing page
not serving), revert is straightforward:

1. **Immediate (runtime):** In `platform-gitops/services/labs/mctl-pairdesk/values.yaml`
   roll the `image.tag` back to the previous image digest. ArgoCD reconciles within one
   sync cycle.

2. **Code revert (if the PR was already merged):**
   - In `web/vite.config.ts`: restore `base: '/'` and `outDir: '../public'`.
   - In `src/server.ts`: restore `resolve(PUBLIC_DIR, 'index.html')` in the SPA
     fallback.
   - In `Dockerfile`: remove the `build-landing` stage; restore the original two-stage
     `COPY` lines.
   - In root `package.json`: remove `build:landing` and restore `"build"` script.
   - Delete the `landing/` directory.
   - After merge of the revert PR, push a new semver tag and update `image.tag` in
     values.yaml.

3. **MINI_APP_URL** does not need to change either way — the value
   `https://labs-mctl-pairdesk.mctl.ai/app` is already set and valid for both the
   current state and the proposed state.
