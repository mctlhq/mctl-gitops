# Design: issue-3-p1-astro-static-skeleton-nginx-image-and

## Current state

The clone of `mctlhq/portfolio` at `2bcfc6b chore: bootstrap repository wiring`
contains exactly nine tracked paths:

```
.github/dependabot.yml
.github/workflows/build.yml
.github/workflows/claude-review.yml
.github/workflows/release-please.yml
.gitignore
.release-please-manifest.json
AGENTS.md
LICENSE
README.md
release-please-config.json
```

There is no application code at all. What already exists constrains this work:

- **`.github/workflows/build.yml`** runs on `pull_request` to `main` and calls
  `docker/build-push-action@v7` with `context: .`, `push: false` and gha cache.
  It is the only build gate, and it fails today because there is no
  `Dockerfile`. It runs no `npm` step, so nothing in CI executes `astro check`.
- **`release-please-config.json`** sets `"release-type": "node"`,
  `"include-v-in-tag": false`, `"bump-minor-pre-major": true` and
  `"package-name": "portfolio"` for the `"."` package.
  **`.release-please-manifest.json`** pins `{".": "0.0.0"}`. The `node` release
  type reads and writes the version in a root `package.json` (and mirrors it
  into `package-lock.json`), so the `package.json` this proposal adds must
  start at `0.0.0` and be named `portfolio`, or release-please's first run
  after merge will not find a package to bump.
- **`.github/workflows/release-please.yml`** dispatches `release-deploy.yaml`
  in `mctlhq/mctl-gitops` with `image_name=ghcr.io/mctlhq/portfolio`,
  `team_name=labs`, `component_name=portfolio` — but only when
  `vars.MCTL_ONBOARDED == 'true'`. That variable is unset, so the first release
  after this PR merges will only tag. That is the intended sequence: image
  first, onboard second.
- **`.github/dependabot.yml`** enables the `npm`, `github-actions` and `docker`
  ecosystems on `/` with weekly Monday runs. The `docker` ecosystem is what
  keeps the pinned base-image digests fresh, which is why `AGENTS.md` requires
  tag+digest pinning rather than a floating tag.
- **`.github/workflows/claude-review.yml`** passes repository-specific
  `conventions` to the shared review workflow, including "flag ... any
  user-facing string present in only one of EN/RU" and "any client-side script
  other than the single inline preference script". Both bear on this PR: the
  404 page's "Not found" is EN-only by design at this stage, and the site must
  ship zero scripts.
- **`AGENTS.md`** sets the bootstrap boundary: humans own `README.md`,
  `AGENTS.md`, `LICENSE`, `.gitignore`, `.github/**` and the release-please
  files; **every other file** is written by the implementer from an approved
  proposal. It also fixes the constraints this design must satisfy: static
  output only, no client-side framework bundles, zero third-party browser
  requests, base images pinned by tag **and** digest, `/healthz` and `/readyz`
  returning 200 from nginx, and deployment only through mctl MCP tools.
- **`.gitignore`** already ignores `node_modules/`, `dist/`, `.astro/`,
  `.DS_Store`, `*.log`, `.env`, `.env.*` — it anticipates exactly this Astro
  layout, so no change is needed there (and it is human-owned anyway).

Two facts were established outside the clone and shape the design:

- **The reference `nginx.conf`.** `mctlhq/mctl-docs` `nginx.conf` (read via the
  GitHub API) is a single `server { listen 80; server_name _; root
  /usr/share/nginx/html; index index.html; ... }` file destined for
  `/etc/nginx/conf.d/default.conf`. Every one of its `add_header` directives
  carries the `always` flag; its `location = /healthz` / `location = /readyz`
  blocks use `access_log off; return 200 "OK\n";`. Its Dockerfile uses a
  floating `nginx:alpine`, `EXPOSE 80`, and
  `HEALTHCHECK --interval=30s --timeout=3s CMD wget --quiet --tries=1 --spider http://localhost/healthz || exit 1`.
  This proposal follows the structure and deliberately diverges on three
  points, argued below.
- **Port 80 is already a proven shape on the platform.** `mctl_list_services`
  shows `admins/mctl-docs` (`docs.mctl.ai`), `admins/mctl-web` (`mctl.ru`) and
  `admins/mctl-design` (`ui.mctl.ai`) all running `componentType:
  base-service` with `port: "80"`. `labs/portfolio` does not exist yet. So
  `EXPOSE 80` carries no onboarding risk: the base-service chart demonstrably
  accepts port 80 with the stock root-master/`nginx`-worker image.

## Proposed solution

Eleven new files, no modifications to anything that exists: `package.json`,
`package-lock.json`, `astro.config.mjs`, `tsconfig.json`,
`src/pages/index.astro`, `src/pages/404.astro`, `public/favicon.svg`,
`public/robots.txt`, `nginx.conf`, `Dockerfile`, `.dockerignore`. Everything in
that list sits outside the human-owned set in `AGENTS.md`.

### 1. Node project (`package.json`, `package-lock.json`, `astro.config.mjs`, `tsconfig.json`)

`package.json`: `"name": "portfolio"`, `"version": "0.0.0"`, `"private": true`,
`"type": "module"`, scripts `dev` (`astro dev`), `build` (`astro build`),
`preview` (`astro preview`), `check` (`astro check`).

`dependencies` holds `astro` only, pinned as `"^5.0.0"`. The registry's current
`latest` for `astro` is **7.3.2**, so an unqualified `npm install astro` would
land on 7 and violate the issue. `^5.0.0` resolves the newest 5.x and cannot
cross into 6 or 7.

`devDependencies` holds `@astrojs/check` (`^0.9.10`) and `typescript`
(`^5.0.0`). This is the one place the design reads past the issue's literal
"dependency `astro` only": in Astro 5, `astro check` is a stub that requires
the separate `@astrojs/check` package (whose peer is `typescript ^5 || ^6`) and
prompts to install it when absent — which fails in any non-interactive run.
Acceptance criterion 6 (`npm run check` passes) is therefore unsatisfiable
without them. They are dev-only, contribute nothing to `dist/`, and the
production dependency graph stays exactly `astro`.

`package-lock.json` is committed (lockfile v3), which is what makes
`npm ci --no-audit --no-fund` legal in the builder stage and what release-please
mirrors the version bump into.

`astro.config.mjs`:

```js
import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static',
  site: 'https://dmitriimashkov.com',
  trailingSlash: 'always',
  integrations: [],
});
```

`output: 'static'` is Astro 5's default but is stated explicitly because
`AGENTS.md` treats "static output only" as an invariant that must be visible in
the config, not inferred. `trailingSlash: 'always'` matches the URL shape the
future content routes will use; with the default `build.format: 'directory'` it
means every route emits `<route>/index.html`, which the nginx `try_files`
chain resolves via `$uri/index.html`.

`tsconfig.json` is `{ "extends": "astro/tsconfigs/strict" }`. That preset
already sets `"include": [".astro/types.d.ts", "**/*"]` and `"exclude":
["dist"]`, which is precisely what `astro check` needs after `astro sync`
generates `.astro/types.d.ts`.

### 2. Pages and public assets

`src/pages/index.astro` — a complete HTML document with `<html lang="en">`,
`<meta charset="utf-8">`, `<meta name="viewport" ...>`,
`<title>Dmitrii Mashkov</title>`, `<link rel="icon" type="image/svg+xml"
href="/favicon.svg">` and a body containing exactly `<h1>Dmitrii Mashkov</h1>`.
No layout component, no `<style>`, no `<script>` — a `<style>` block would make
Astro emit `_astro/*.css`, and a `<script>` would emit `_astro/*.js` and break
acceptance criterion 1.

`src/pages/404.astro` — the same minimal document shape with
`<title>Not found</title>` and `<h1>Not found</h1>`. Astro special-cases this
route and writes `dist/404.html` at the root even under
`build.format: 'directory'`, which is what `error_page 404 /404.html` needs.

`public/favicon.svg` — a hand-written, dependency-free monogram SVG (no raster,
no external font reference; `img-src 'self' data:` covers it).
`public/robots.txt` — `User-agent: *` / `Disallow:` plus
`Sitemap: https://dmitriimashkov.com/sitemap-index.xml` **omitted** for now,
since no sitemap is generated in P1 and advertising a 404 URL would be worse
than silence.

Because the site has no CSS and no JS, `dist/` after a build is expected to be
just `index.html`, `404.html`, `favicon.svg`, `robots.txt` — with no `_astro/`
directory at all. The `location /_astro/` block is written anyway, so the
caching contract is already correct the moment the design issue introduces
stylesheets.

### 3. `nginx.conf`

One `server` block, structured like the mctl-docs file, copied to
`/etc/nginx/conf.d/default.conf`:

- `listen 80; server_name _; root /usr/share/nginx/html; index index.html;`
- Server-level: the seven headers from the issue, each with the `always` flag
  so they also apply to the 404 response (`add_header` without `always` only
  attaches to 200/201/204/206/301/302/303/304/307/308). `X-Frame-Options` is
  `DENY` here, not mctl-docs' `SAMEORIGIN`, and `X-XSS-Protection` is dropped —
  the issue's header list is authoritative and the deprecated header adds
  nothing over `frame-ancestors 'none'`.
- `location = /healthz` and `location = /readyz`: `access_log off;`
  `default_type text/plain;` `return 200 "OK\n";` plus a verbatim repeat of the
  seven security headers.
  **`default_type`, not `add_header Content-Type`** — this is a deliberate fix
  to the mctl-docs pattern. With `return 200 "..."`, nginx takes the response
  content type from `default_type`, which the stock `/etc/nginx/nginx.conf`
  sets to `application/octet-stream`; `add_header Content-Type text/plain`
  appends a *second* `Content-Type` header instead of replacing the first, so
  the response ends up with both. `default_type text/plain;` yields a single,
  correct `Content-Type: text/plain`.
- `location /_astro/`: `expires 1y;`
  `add_header Cache-Control "public, immutable" always;`
  `try_files $uri =404;` plus the repeated security headers.
- `location /`: `try_files $uri $uri/index.html $uri.html =404;`
  `error_page 404 /404.html;` and the repeated security headers.

The repetition is not stylistic. nginx's `add_header` inheritance is
all-or-nothing per level: a `location` that declares even one `add_header`
discards every `add_header` inherited from `server`. `location /_astro/` adds
`Cache-Control`, and the health locations add nothing but must still be covered
for defence in depth, so the full set is restated in each. The issue calls this
out explicitly and the implementation follows it literally. A single shared
snippet `include`d in each location would be tidier but requires writing a
second file into `/etc/nginx/`, adding a moving part for no behavioural gain at
this size — revisit when the location count grows.

`error_page 404 /404.html` re-enters `location /`, where `try_files` finds
`/usr/share/nginx/html/404.html`; nginx preserves the original `404` status
because the `error_page` directive has no `=` override. That is what makes
acceptance criterion 3's `curl -si localhost:8080/does-not-exist` return 404
with the 404 page's body.

### 4. `Dockerfile` and `.dockerignore`

```dockerfile
FROM node:24-alpine@sha256:<resolved> AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.30-alpine@sha256:<resolved>
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist/ /usr/share/nginx/html/
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -q --spider http://127.0.0.1/healthz || exit 1
CMD ["nginx", "-g", "daemon off;"]
```

Both digests are resolved from Docker Hub at implementation time and written
into the PR description alongside their tags (acceptance criterion 5).
`nginx:1.30-alpine` was confirmed to exist during investigation (manifest-list
digest `sha256:dc5069ad14f19660b141b21236140b91656bf89bbc3e2417c70ae650cd66104c`
at that moment); it will very likely have moved by implementation time, so the
implementer must re-resolve rather than copy that value.

`127.0.0.1` rather than mctl-docs' `localhost`: `listen 80` binds IPv4 only,
and a musl resolver that hands back `::1` first would make the health check
fail against a healthy server. BusyBox `wget` is present in `nginx:alpine`, so
no extra package is installed. No `--start-period` is set, matching the issue;
nginx binds its listener before the first probe fires 30s in, and the default
three retries give ample margin — `docker inspect` reaching `healthy` is
acceptance criterion 4.

`.dockerignore` lists `node_modules`, `dist`, `.git`, `.astro`. Excluding
`dist` matters twice over: it keeps a stale local build from shadowing the
builder's output, and it keeps the gha-cached context small in `build.yml`.

### Ordering and verification

The whole change is one PR on `feat/agents-issue-3-p1-astro-static-skeleton-nginx-image-and`.
Verification is local and manual because CI only runs the docker build:
`npm ci && npm run build && npm run check && find dist -name '*.js'`, then
`docker build`, `docker run -p 8080:80`, four `curl -si` probes, and
`docker inspect --format '{{.State.Health.Status}}'` after the first interval.
Every command and its output goes into the PR description.

## Alternatives

1. **Serve from `nginx-unprivileged` on port 8080 instead of `nginx:1.30-alpine`
   on 80.** Attractive if the cluster enforced `runAsNonRoot`. Dropped on
   evidence: `mctl_list_services` shows `admins/mctl-docs`, `admins/mctl-web`
   and `admins/mctl-design` already running `base-service` on `port: "80"` with
   the stock image, so the constraint does not exist here — and the issue
   specifies `nginx:1.30-alpine` and `EXPOSE 80` outright. Deviating would also
   break the mctl-docs modelling the issue asks for. Worth revisiting only if a
   platform-wide non-root policy lands.

2. **Skip nginx: publish `dist/` through a static-host integration or a
   `caddy file-server` image.** Fewer lines of config and no `add_header`
   inheritance traps. Dropped because the health endpoints, the exact header
   set and the immutable-asset caching rule are all first-class acceptance
   criteria, because `AGENTS.md` pins `nginx:1.30-alpine` by name, and because
   every static service on this platform is already an nginx image — one
   serving shape is worth more than marginally simpler config.

3. **Add `RUN npm run check` to the builder stage so the PR gate enforces
   acceptance criterion 6.** Genuinely tempting: `build.yml` runs no npm job,
   so `astro check` is otherwise verified only by whoever runs it locally.
   Dropped because the issue enumerates the builder stage's steps exactly and
   because it would put type-checking (with its dev-only dependency tree) on
   the critical path of every production image build. Recorded in
   `requirements.md` open question 5; the clean fix is a separate `check` job
   in `build.yml`, which is a human-owned `.github/**` change under the
   `AGENTS.md` bootstrap boundary.

4. **Pin `astro` to the current `latest` (7.3.2) instead of `^5.0.0`.** Would
   pre-empt the Dependabot major-bump PR that `^5.0.0` guarantees within a week.
   Dropped because the issue says "Astro 5" and the investigator does not get to
   silently retarget a major version; see open question 2 for the follow-up path.

## Platform impact

**Migrations.** None. No database, no persisted state, no existing deployment.
`labs/portfolio` does not appear in `mctl_list_services`, so there is nothing
to migrate from.

**Backward compatibility.** Nothing consumes this repository yet. The one
compatibility surface is release-please: adding a root `package.json` at
`0.0.0` is exactly what `"release-type": "node"` plus
`.release-please-manifest.json` `{".": "0.0.0"}` already expect. Any other
starting version would desynchronise the manifest from the package on the first
release run. `"private": true` prevents an accidental npm publish and does not
affect release-please's node updater.

**Deployment path.** Merging this PR makes `.github/workflows/build.yml` pass
for the first time. The next release-please run tags (probably `0.1.0`, given
`bump-minor-pre-major`) and takes the "Note skipped dispatch" branch because
`vars.MCTL_ONBOARDED` is unset. The operator then runs `mctl_deploy_service
action=onboard` for `team_name=labs`, `component_name=portfolio`,
`component_type=base-service`, **`port=80`**, `dockerfile_repo=mctlhq/portfolio`
and the new tag, which yields `labs-portfolio.mctl.ai`; the custom domain
`dmitriimashkov.com` and the `MCTL_ONBOARDED=true` variable follow. All of that
is out of scope here and gated on this image existing.

**Resource impact.** Negligible. The runtime image is `nginx:1.30-alpine` plus
roughly four small files — a low-tens-of-MB image serving static bytes; the
default base-service replica sits well inside the `labs` quota. The builder
stage's `npm ci` runs only at build time and is excluded from the final image
by the two-stage split. gha layer cache in `build.yml` keeps PR builds cheap.

**Risks and mitigations.**

- *A stray `<style>` or `<script>` breaks the "no `.js` in `dist`" criterion.*
  Mitigated by keeping both pages script-free and style-free and by making
  `find dist -name '*.js'` an explicit test (T2) whose output is pasted into
  the PR.
- *`add_header` inheritance silently drops the security headers on `/_astro/`
  or the health endpoints.* Mitigated by restating the full set in every
  `location` and by asserting headers with `curl -si` on more than just `/`
  (T5, T6).
- *Digest drift between investigation and implementation.* Mitigated by
  requiring re-resolution at implementation time and recording tag+digest in
  the PR body (acceptance criterion 5); Dependabot's `docker` ecosystem keeps
  them current afterwards.
- *Dependabot opens an Astro 5 → 7 major PR within a week of merge.* Expected,
  not prevented. Flagged in the PR body so the maintainer closes it or converts
  it into a deliberate upgrade issue rather than merging it blind.
- *The Claude review gate flags the EN-only "Not found" string* against the
  repository conventions in `claude-review.yml`. Mitigated by stating in the PR
  description that i18n is a separate issue and that P1 ships EN only by
  design.
- *`astro check` is unenforced in CI*, so a later PR could regress type
  correctness unnoticed. Accepted for now; the mitigation is the follow-up CI
  job described in alternative 3.
- *`trailingSlash: 'always'` without an nginx redirect* means a future
  `/about` (no slash) would 404 rather than redirect to `/about/`. Harmless in
  P1 — the only routes are `/` and the 404 page — but the content issue must
  either add a redirect rule or rely on `try_files $uri/index.html`, which
  already serves the directory index without changing the URL.
