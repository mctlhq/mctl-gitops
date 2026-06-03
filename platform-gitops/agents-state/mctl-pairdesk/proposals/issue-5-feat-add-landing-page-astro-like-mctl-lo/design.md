# Design: issue-5-feat-add-landing-page-astro-like-mctl-lo

## Current state

### Static file serving (src/server.ts)

`src/server.ts` resolves `PUBLIC_DIR` as `<repo-root>/public` and mounts it with
`express.static(PUBLIC_DIR)`. Any file in `public/` is served at its relative URL. There
is no explicit `GET /` route; instead `express.static` automatically serves
`public/index.html` when one exists.

A SPA fallback (lines 64-68) maps `/app`, `/app/*`, `/admin`, `/admin/*`, `/docs`,
`/docs/*` to `resolve(PUBLIC_DIR, 'index.html')`. This returns the React Mini App shell
for every client-side route.

The catch-all (lines 71-74) returns JSON 404 for any unmatched GET — it never fires for
`/` or `/app` as long as the SPA's `index.html` is in `public/`.

### Vite (web/) configuration

`web/vite.config.ts` sets:
- `base: '/'` — all asset URLs are absolute from the root
- `build.outDir: '../public'` — the Vite build writes directly to `<repo-root>/public/`
- `build.emptyOutDir: true` — the build wipes `public/` before writing

The comment in this file explicitly states: "PairDesk has no separate marketing landing
(unlike loyalty), so the SPA owns the /public root with base '/'."

### Dockerfile

The Dockerfile has two application build stages:
- `build-api` — compiles TypeScript to `dist/`
- `build-web` — runs `npm run build` inside `web/`, producing `public/` at `/app/public`

The runtime stage does:
```
COPY --from=build-api /app/dist ./dist
COPY --from=build-web /app/public ./public
```

### package.json scripts

```json
"build":      "npm run build:web && npm run build:api",
"build:web":  "cd web && npm install && npm run build",
"build:api":  "tsc -p tsconfig.json && cp src/db/schema.sql dist/db/schema.sql"
```

### Gitops (values.yaml)

`platform-gitops/services/labs/mctl-pairdesk/values.yaml` already contains:
```yaml
MINI_APP_URL: https://labs-mctl-pairdesk.mctl.ai/app
```
This value is already correct for the post-migration world; no gitops change is required.

### Design tokens

`web/src/pairdesk-tokens.css` defines the complete PairDesk token system
("Direction C — Trust / Banking"): deep blue accent (`#2f6bf6`), type scale, spacing,
currency identity colours (`--g-eur`, `--g-rub`, `--g-usdt`), and elevation. Tokens are
expressed as `var(--tg-*, <fallback>)` — the Telegram theme overrides apply inside the
Mini App only. The landing page runs outside Telegram, so it uses the fallback values
directly (the `--tg-*` cascade is irrelevant on a standard browser page).

---

## Proposed solution

### Overview

Add a new `landing/` Astro project at the repo root. Astro builds purely static HTML/CSS
to `public/` (the root of the Express static directory). The Vite SPA build moves its
output to `public/app/` with `base: '/app/'`. Express is adjusted in one line to point
the SPA fallback at `public/app/index.html` instead of `public/index.html`.

### 1. New `landing/` Astro project

Create `landing/` as a self-contained Node package:

```
landing/
  package.json          # { "name": "mctl-pairdesk-landing", "type": "module" }
  astro.config.mjs      # outDir: '../public', base: '/', output: 'static'
  tsconfig.json         # standard Astro TS config, extends: 'astro/tsconfigs/strict'
  src/
    pages/
      index.astro       # single page: landing HTML + inlined critical CSS
    styles/
      landing.css       # PD token subset adapted for public-web use (no --tg-* needed)
```

**`astro.config.mjs`** (key settings):
```js
import { defineConfig } from 'astro/config';
export default defineConfig({
  output: 'static',
  outDir: '../public',
  build: { assets: '_astro' },
});
```

`outDir: '../public'` means Astro writes `public/index.html` and `public/_astro/...`.
`express.static(PUBLIC_DIR)` then serves the landing at `GET /` automatically (no
explicit Express route needed) because Express's static middleware serves `index.html`
when a directory is requested.

**`landing/src/styles/landing.css`** copies the non-Telegram token variables from
`web/src/pairdesk-tokens.css` as literal values (no `var(--tg-*)` fallback chain),
plus a small set of landing-specific layout rules. This avoids a build-time dependency
on the `web/` package while keeping the visual language consistent.

**`landing/src/pages/index.astro`** contains:
- `<meta>` tags: title "PairDesk", description, Open Graph
- "What is PairDesk" section: bulletin board, not an exchange; no custody, no escrow
- "How to join" section: open the bot, send `/start`, wait for admin approval
- CTA button: Telegram deep-link `https://t.me/<bot_username>` (see Open Questions)
- No `<script>` tags; no JS framework; `<style>` or `<link>` to `landing.css`

### 2. Vite SPA config change (`web/vite.config.ts`)

```diff
-  base: '/',
+  base: '/app/',
   build: {
-    outDir: '../public',
+    outDir: '../public/app',
     emptyOutDir: true,
   },
```

All asset references in the SPA build (`/assets/...`) become `/app/assets/...`. The
`index.html` for the SPA lands at `public/app/index.html`.

The comment at the top of the file should be updated to reflect the new split:
> "Landing page at `/` (Astro, `public/`); Mini App SPA at `/app` (Vite, `public/app/`)."

### 3. Express SPA fallback change (`src/server.ts`)

One line changes — the sendFile path:

```diff
-  res.sendFile(resolve(PUBLIC_DIR, 'index.html'), (err) => {
+  res.sendFile(resolve(PUBLIC_DIR, 'app', 'index.html'), (err) => {
```

The set of paths handled by the fallback (`/app`, `/app/*`, `/admin`, `/admin/*`,
`/docs`, `/docs/*`) can stay as-is; they all now point to the SPA at its new location.

No new routes are needed for the landing: `express.static` serves `public/index.html`
at `GET /` automatically.

### 4. Dockerfile — new build stage

Add a `build-landing` stage before `build-web`:

```dockerfile
# ---- build landing page (Astro -> /app/public) ----
FROM node:22.11-alpine3.20 AS build-landing
WORKDIR /app/landing
COPY landing/package*.json ./
RUN npm ci
COPY landing/ ./
RUN npm run build
# Astro outDir is '../public', so output lands at /app/public/index.html
# and /app/public/_astro/...
```

Update the `build-web` stage comment: Vite outDir is now `../public/app`.

Update the runtime stage COPY commands:

```dockerfile
COPY --from=build-api     /app/dist         ./dist
COPY --from=build-landing /app/public       ./public
COPY --from=build-web     /app/public/app   ./public/app
```

The two COPY operations for `public` do not conflict: `build-landing` populates
`public/index.html` and `public/_astro/`; `build-web` populates `public/app/`.

### 5. Root package.json scripts

```diff
-  "build":      "npm run build:web && npm run build:api",
+  "build":      "npm run build:landing && npm run build:web && npm run build:api",
+  "build:landing": "cd landing && npm install && npm run build",
```

Order matters for local full-builds: Astro writes to `public/` with `emptyOutDir: true`
(wipes `public/` before writing); Vite writes to `public/app/` with `emptyOutDir: true`
(wipes only `public/app/`). Running landing first, SPA second avoids any conflict.

### 6. CI (`.github/workflows/ci.yml`)

Add a `landing` job mirroring the existing `web` job:

```yaml
landing:
  name: landing build & type-check
  runs-on: ubuntu-latest
  defaults:
    run:
      working-directory: landing
  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-node@v4
      with:
        node-version: '22'
        cache: npm
        cache-dependency-path: landing/package-lock.json
    - run: npm ci
    - run: npm run type-check
    - run: npm run build
```

The existing `docker` job already builds the full image and will exercise the new
`build-landing` stage without any changes beyond the updated Dockerfile.

---

## Alternatives

### A. Keep the SPA at `/` and serve the landing at `/landing/`

Astro `base: '/landing/'`, `outDir: '../public/landing'`. Express adds a redirect
`GET / → 301 /landing/`. The Mini App stays at `base: '/'`.

Rejected because: a landing page at `/landing/` is non-standard; the redirect adds a
round-trip for every visitor; the SPA at `/` still "answers" before the redirect fires
for any unmatched routes; and the issue explicitly requires the landing at `/` and the
Mini App at `/app`.

### B. Single Vite build with a landing page as an additional HTML entry

Vite supports `rollupOptions.input` with multiple entry HTML files. The landing would be
a plain `landing.html` inside `web/src/`.

Rejected because: the issue explicitly references Astro and the mctl-loyalty pattern;
mixing a marketing landing with the Telegram Mini App build couples concerns that are
better isolated; Astro's file-based routing, asset pipeline, and SEO primitives are
better suited to a public content page than Vite's SPA defaults.

### C. Serve the landing from a separate service or CDN origin

A standalone Astro deployment (Netlify, Cloudflare Pages, or a second Kubernetes service)
serves `/`; the Express service only handles `/api` and `/app`.

Rejected per the explicit out-of-scope statement in the issue: "No Cloudflare Worker
(unlike mctl-web) — Express serves static files directly." Adding a second service also
increases operational complexity for what is a single static HTML page.

---

## Platform impact

### Docker image size

Astro adds one `package-lock.json`-locked build stage. The static output for a
single-page landing is typically under 50 KB (HTML + CSS). The runtime image size
increases by that amount. No new runtime process is introduced.

### Backward compatibility

| Surface | Before | After | Impact |
|---|---|---|---|
| `GET /` | React Mini App SPA | Astro landing HTML | Breaking for any direct link that relied on the SPA at `/`. The bot deep-link uses `MINI_APP_URL` which already points to `/app`; no bot-initiated flow is affected. |
| `GET /app` | SPA fallback (already present in server.ts) | SPA at `public/app/index.html` | No change in observable behavior; path was already registered. |
| `GET /api/*` | Unchanged | Unchanged | None. |
| `MINI_APP_URL` env | Already set to `.../app` | Already set to `.../app` | None — gitops change was pre-applied. |

The only breaking change is `GET /` — users who bookmarked the root URL directly in a
browser will now see the landing page instead of the Mini App. The Mini App is accessed
via Telegram, which always uses `MINI_APP_URL` (already `/app`), so real users are not
affected.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Astro `emptyOutDir: true` wipes `public/app/` during a local full build if run out of order. | Document and enforce `build:landing` before `build:web` in the root `build` script. In Docker, stages are isolated so order is irrelevant. |
| SPA asset paths break after `base` change from `/` to `/app/`. | Verify by running `npm run build` in `web/` and inspecting `public/app/index.html` — all `src=` and `href=` attributes must begin with `/app/`. Run the Docker image locally and exercise the Mini App at `/app`. |
| Bot deep-link contains an incorrect username. | Confirm bot username from Vault/BotFather before publishing. See Open Question 1 in requirements.md. |
| CI cache for `landing/` is cold on first run. | Acceptable; `npm ci` with `node_modules` cache warms on subsequent runs. |
