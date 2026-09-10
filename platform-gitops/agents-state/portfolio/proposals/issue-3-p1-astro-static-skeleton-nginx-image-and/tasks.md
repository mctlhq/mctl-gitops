# Tasks: issue-3-p1-astro-static-skeleton-nginx-image-and

All work happens on a single branch,
`feat/agents-issue-3-p1-astro-static-skeleton-nginx-image-and`, and lands as one
PR. No file listed as human-owned in `AGENTS.md` (`README.md`, `AGENTS.md`,
`LICENSE`, `.gitignore`, `.github/**`, `release-please-config.json`,
`.release-please-manifest.json`) is created, edited or deleted.

- [ ] 1. Create the Node project skeleton: `package.json` with
      `"name": "portfolio"`, `"version": "0.0.0"`, `"private": true`,
      `"type": "module"`, scripts `dev`/`build`/`preview`/`check` mapped to
      `astro dev`/`astro build`/`astro preview`/`astro check`,
      `dependencies: { "astro": "^5.0.0" }` and
      `devDependencies: { "@astrojs/check": "^0.9.10", "typescript": "^5.0.0" }`.
      Run `npm install` once to generate `package-lock.json` (lockfile v3) and
      commit it.
      — DoD: `npm ci --no-audit --no-fund` on a clean checkout exits `0`;
      `node -p "require('./package.json').version"` prints `0.0.0`, matching the
      `"."` entry of `.release-please-manifest.json`;
      `npm ls astro` reports a `5.x` resolution, not `6.x` or `7.x`.

- [ ] 2. Add `astro.config.mjs` with `output: 'static'`,
      `site: 'https://dmitriimashkov.com'`, `trailingSlash: 'always'`,
      `integrations: []`, and `tsconfig.json` extending
      `astro/tsconfigs/strict` (depends on 1).
      — DoD: `npx astro sync` exits `0` and generates `.astro/types.d.ts`; the
      config file imports only `defineConfig` from `astro/config`.

- [ ] 3. Add `src/pages/index.astro`: a full HTML document with
      `<html lang="en">`, `<meta charset="utf-8">`, a viewport meta,
      `<title>Dmitrii Mashkov</title>`,
      `<link rel="icon" type="image/svg+xml" href="/favicon.svg">` and a body
      containing `<h1>Dmitrii Mashkov</h1>`. No `<style>`, no `<script>`, no
      layout component, no framework import (depends on 2).
      — DoD: `grep -c '<script' src/pages/index.astro` is `0`;
      `grep -c '<style' src/pages/index.astro` is `0`; the file contains the
      exact string `<h1>Dmitrii Mashkov</h1>`.

- [ ] 4. Add `src/pages/404.astro` with the same minimal document shape,
      `<title>Not found</title>` and `<h1>Not found</h1>`; no styles, no
      scripts (depends on 2).
      — DoD: after `npm run build`, `dist/404.html` exists at the root of
      `dist/` and contains `Not found`.

- [ ] 5. Add `public/favicon.svg` (hand-written monogram SVG, no external
      references, no embedded raster) and `public/robots.txt` allowing all
      crawlers (`User-agent: *` + empty `Disallow:`), with no `Sitemap:` line
      since P1 generates no sitemap (depends on 2).
      — DoD: `dist/favicon.svg` and `dist/robots.txt` are present after a
      build; `grep -Ei 'https?://' public/favicon.svg` returns nothing except
      the SVG namespace declaration.

- [ ] 6. Add `nginx.conf` as a single `server` block for
      `/etc/nginx/conf.d/default.conf`, modelled on `mctlhq/mctl-docs`
      `nginx.conf`: `listen 80`, `server_name _`,
      `root /usr/share/nginx/html`, `index index.html`; server-level security
      headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
      `Referrer-Policy: strict-origin-when-cross-origin`,
      `Permissions-Policy: geolocation=(), microphone=(), camera=()`,
      `Strict-Transport-Security: max-age=31536000; includeSubDomains`,
      `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`),
      each with the `always` flag; `location = /healthz` and
      `location = /readyz` with `access_log off`, `default_type text/plain` and
      `return 200 "OK\n"`; `location /_astro/` with `expires 1y` and
      `Cache-Control: public, immutable`; `location /` with
      `try_files $uri $uri/index.html $uri.html =404` and
      `error_page 404 /404.html`. Repeat the full security-header set verbatim
      inside **every** `location` block, because a `location`-level
      `add_header` discards the server-level set. Do not carry over mctl-docs'
      deprecated `X-XSS-Protection`, and use `default_type text/plain` rather
      than `add_header Content-Type text/plain` so the health responses carry
      exactly one `Content-Type`.
      — DoD: each of the six security headers appears once per `location` block
      plus once at server level; `nginx -t` passes against the built image (T4).

- [ ] 7. Resolve the current multi-arch manifest digests for `node:24-alpine`
      and `nginx:1.30-alpine` from Docker Hub (e.g.
      `docker buildx imagetools inspect node:24-alpine`). Do not reuse the
      digest quoted in `requirements.md` open question 4 — it was read during
      investigation and will have moved.
      — DoD: two `sha256:` values recorded for use in tasks 8 and 12.

- [ ] 8. Add the two-stage `Dockerfile` (depends on 1, 6, 7). Stage 1
      `FROM node:24-alpine@sha256:<digest> AS builder`: `WORKDIR /app`,
      `COPY package.json package-lock.json ./`,
      `RUN npm ci --no-audit --no-fund`, `COPY . .`, `RUN npm run build`.
      Stage 2 `FROM nginx:1.30-alpine@sha256:<digest>`:
      `COPY nginx.conf /etc/nginx/conf.d/default.conf`,
      `COPY --from=builder /app/dist/ /usr/share/nginx/html/`, `EXPOSE 80`,
      `HEALTHCHECK --interval=30s --timeout=3s CMD wget -q --spider http://127.0.0.1/healthz || exit 1`,
      `CMD ["nginx", "-g", "daemon off;"]`. Use `127.0.0.1`, not `localhost`,
      because `listen 80` binds IPv4 only.
      — DoD: both `FROM` lines carry tag **and** `@sha256:` digest as
      `AGENTS.md` requires; no `RUN` in stage 2 other than none at all.

- [ ] 9. Add `.dockerignore` with `node_modules`, `dist`, `.git`, `.astro`
      (depends on 8).
      — DoD: `docker build` transfers a context under ~1 MB from a checkout
      that has a populated `node_modules/` and `dist/`.

- [ ] 10. Run the full local verification sweep (T1-T8 below) and capture every
      command with its output (depends on 3, 4, 5, 8, 9).
      — DoD: all eight tests pass; transcript saved for the PR description.

- [ ] 11. Open the PR with a conventional-commit title
      (`feat: add Astro static skeleton, nginx image and health endpoints`).
      — DoD: the PR targets `main`, the `build` workflow passes (this is the
      first PR in the repository where it can), and the Claude review gate
      returns.

- [ ] 12. Write the PR description (depends on 7, 10, 11): both base image tags
      and both resolved digests; the T1-T8 transcript; three explicit
      call-outs — (a) `@astrojs/check` and `typescript` are devDependencies
      required by acceptance criterion 6 and the production dependency graph is
      still `astro` alone; (b) the 404 page's "Not found" is EN-only because
      i18n is a separate issue, so the repository convention in
      `.github/workflows/claude-review.yml` is knowingly deferred, not
      overlooked; (c) `astro` is pinned `^5.0.0` while npm `latest` is 7.3.2,
      so a Dependabot major-bump PR is expected on the next Monday run and
      should be triaged as an upgrade decision, not merged reflexively.
      — DoD: acceptance criterion 5 satisfied; a reviewer can verify every
      acceptance criterion from the PR body without running anything.

## Tests

All are manual/local: `.github/workflows/build.yml` runs only the docker build
and is not modified by this proposal.

- [ ] T1. `npm ci --no-audit --no-fund && npm run build` exits `0` with no Astro
      or Vite warning about this project's own configuration or sources.
      Transitive npm deprecation notices, if any, are recorded in the PR body
      rather than treated as failures (requirements open question 3).
- [ ] T2. `find dist -name '*.js'` prints nothing, and `ls dist` shows
      `index.html`, `404.html`, `favicon.svg` and `robots.txt`.
- [ ] T3. `npm run check` exits `0` with `0 errors, 0 warnings, 0 hints`.
- [ ] T4. `docker build -t portfolio .` succeeds, and
      `docker run --rm portfolio nginx -t` reports the configuration valid.
- [ ] T5. With `docker run --rm -d -p 8080:80 --name portfolio-t portfolio`:
      `curl -si localhost:8080/healthz` and `curl -si localhost:8080/readyz`
      each return `200`, body exactly `OK`, exactly one
      `Content-Type: text/plain` header, and the six security headers.
- [ ] T6. `curl -si localhost:8080/` returns `200`, the body contains
      `<h1>Dmitrii Mashkov</h1>` and a non-empty `<title>`, and the response
      carries `Content-Security-Policy`, `Strict-Transport-Security`,
      `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and
      `Permissions-Policy`.
- [ ] T7. `curl -si localhost:8080/does-not-exist` returns `404` and serves the
      404 page body (`Not found`).
- [ ] T8. After the first health interval,
      `docker inspect --format '{{.State.Health.Status}}' portfolio-t` prints
      `healthy`. Tear down with `docker rm -f portfolio-t`.

## Rollback

Nothing in this proposal is deployed, so rollback is entirely repository-level.

- **Before merge:** close the PR and delete the branch. The repository returns
  to `2bcfc6b` with no residue; the `build` gate goes back to failing for want
  of a `Dockerfile`, which is the pre-existing state.
- **After merge, before the first release:** `git revert` the merge commit on a
  new branch and merge that revert PR. All eleven files are additions, so the
  revert is mechanical and touches nothing human-owned. Note that release-please
  will already have opened a release PR against the merged state — close it
  before merging the revert, or the manifest and `package.json` will disagree.
- **After the first release tag:** the tag is immutable and is not deleted. Fix
  forward with a follow-up PR; release-please's next run cuts a new version.
  Because `vars.MCTL_ONBOARDED` is unset, no release-deploy dispatch fires and
  nothing reaches the cluster, so no `mctl_rollback_service` is needed.
- **After onboarding (out of scope here, but for completeness):** roll back with
  `mctl_rollback_service(team_name=labs, component_name=portfolio,
  target_tag=<previous>)`. There is no previous tag at this point, so the only
  true rollback would be `mctl_retire_service` — which is why onboarding is
  deliberately a separate, later step.
