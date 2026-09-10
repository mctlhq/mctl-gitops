# P1: Astro static skeleton, nginx image and health endpoints

## Context

`mctlhq/portfolio` is today a wiring-only repository: `AGENTS.md`, `README.md`,
`LICENSE`, `.gitignore`, `release-please-config.json`,
`.release-please-manifest.json` and `.github/**` (a `build` PR gate that runs
`docker/build-push-action` against `context: .`, a `release-please` workflow, a
`claude-review` workflow and `dependabot.yml` with npm, github-actions and
docker ecosystems). There is no `Dockerfile`, so the PR build gate cannot
currently succeed, and there is no `package.json`, so release-please's `node`
release type has nothing to version. The single commit in history is
`2bcfc6b chore: bootstrap repository wiring`.

This proposal turns that skeleton into a deployable static site: an Astro 5
project producing a single placeholder page plus a 404 page, built into a
two-stage image whose runtime stage is nginx serving `/healthz` and `/readyz`.
It unblocks everything downstream — the PR docker gate starts passing, the
first release-please tag becomes meaningful, and the operator can run
`mctl_deploy_service action=onboard` for tenant `labs`, service `portfolio`,
port 80 (the same shape `admins/mctl-docs`, `admins/mctl-web` and
`admins/mctl-design` already run on the platform). No content, no design, no
i18n: those are separate issues.

## User stories

- AS the mctl platform I WANT a `Dockerfile` at the repository root that builds
  a self-contained nginx image SO THAT the existing `build` PR gate and the
  centralized `release-deploy` dispatch can build `ghcr.io/mctlhq/portfolio`.
- AS a Kubernetes probe I WANT `/healthz` and `/readyz` to answer `200 OK` in
  plain text without polluting the access log SO THAT the base-service chart
  can mark the pod live and ready.
- AS a visitor I WANT the site to render with JavaScript disabled SO THAT the
  page is usable on any browser, matching the `AGENTS.md` site constraints.
- AS a security reviewer I WANT every response to carry a self-only CSP and the
  standard hardening headers SO THAT the site makes zero third-party browser
  requests and cannot be framed.
- AS release-please I WANT a root `package.json` at version `0.0.0` matching
  `.release-please-manifest.json` SO THAT the `node` release type can bump the
  version and open a release PR.
- AS Dependabot I WANT the base images pinned by tag **and** digest SO THAT the
  weekly `docker` ecosystem update can propose digest bumps.

## Acceptance criteria (EARS)

### Build and project shape

- WHEN `npm ci --no-audit --no-fund` is run at the repository root THE SYSTEM
  SHALL install from a committed `package-lock.json` that is consistent with
  `package.json` and SHALL exit `0`.
- WHEN `npm run build` is run THE SYSTEM SHALL exit `0` and SHALL emit no
  Astro or Vite warning attributable to this repository's own configuration.
- WHEN `npm run build` completes THE SYSTEM SHALL have produced `dist/index.html`
  and `dist/404.html`.
- WHEN `find dist -name '*.js'` is run after a build THE SYSTEM SHALL produce
  empty output.
- WHEN `npm run check` (`astro check`) is run THE SYSTEM SHALL exit `0` with
  zero errors, zero warnings and zero hints.
- WHILE the project has no UI framework integration THE SYSTEM SHALL declare
  `astro` as its only runtime dependency, with `@astrojs/check` and
  `typescript` present as devDependencies solely so that `astro check` runs
  non-interactively.
- WHILE `astro.config.mjs` is in effect THE SYSTEM SHALL use
  `output: 'static'`, `site: 'https://dmitriimashkov.com'`,
  `trailingSlash: 'always'` and an empty `integrations` list.
- WHILE `package.json` is at the repository root THE SYSTEM SHALL declare
  `"name": "portfolio"` and `"version": "0.0.0"` so that the `node` release
  type in `release-please-config.json` and the `"."` entry of
  `.release-please-manifest.json` stay consistent.
- WHILE the pinned major is Astro 5 THE SYSTEM SHALL express the dependency as
  a range that cannot resolve to Astro 6 or 7 (`"astro": "^5.0.0"`).

### Image

- WHEN `docker build -t portfolio .` is run from a clean checkout THE SYSTEM
  SHALL succeed.
- WHILE the `Dockerfile` is being built THE SYSTEM SHALL use a builder stage
  based on `node:24-alpine@sha256:<digest>` and a runtime stage based on
  `nginx:1.30-alpine@sha256:<digest>`, each pinned by tag **and** digest as
  required by `AGENTS.md`.
- WHEN the builder stage runs THE SYSTEM SHALL copy `package.json` and
  `package-lock.json` first, run `npm ci --no-audit --no-fund`, then copy the
  remaining sources and run `npm run build`.
- WHEN the runtime stage is assembled THE SYSTEM SHALL copy `nginx.conf` to
  `/etc/nginx/conf.d/default.conf`, copy `/app/dist/` to
  `/usr/share/nginx/html/`, `EXPOSE 80`, declare
  `HEALTHCHECK --interval=30s --timeout=3s CMD wget -q --spider http://127.0.0.1/healthz || exit 1`
  and set `CMD ["nginx", "-g", "daemon off;"]`.
- WHILE `.dockerignore` is present THE SYSTEM SHALL exclude `node_modules`,
  `dist`, `.git` and `.astro` from the build context.
- WHEN a container has been running past its start period THE SYSTEM SHALL
  report `Health.Status == "healthy"` under `docker inspect`.

### Serving

- WHEN `GET /healthz` is requested THE SYSTEM SHALL return `200` with body
  `OK\n` and `Content-Type: text/plain`, and SHALL NOT write an access log
  entry.
- WHEN `GET /readyz` is requested THE SYSTEM SHALL return `200` with body
  `OK\n` and `Content-Type: text/plain`, and SHALL NOT write an access log
  entry.
- WHEN `GET /` is requested THE SYSTEM SHALL return `200` with an HTML document
  containing `<h1>Dmitrii Mashkov</h1>` and a non-empty `<title>`.
- WHEN any HTML response is returned THE SYSTEM SHALL include
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy: geolocation=(), microphone=(), camera=()`,
  `Strict-Transport-Security: max-age=31536000; includeSubDomains` and
  `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`.
- IF a `location` block adds any header of its own THEN THE SYSTEM SHALL repeat
  the full security-header set inside that block, because `add_header` at
  `location` level replaces the server-level set rather than extending it.
- WHEN a request under `/_astro/` is served THE SYSTEM SHALL respond with
  `expires 1y` and `Cache-Control: public, immutable`.
- WHEN `GET /does-not-exist` is requested THE SYSTEM SHALL return status `404`
  and serve the body of `/404.html`.
- WHILE serving normal traffic THE SYSTEM SHALL resolve paths with
  `try_files $uri $uri/index.html $uri.html =404` rooted at
  `/usr/share/nginx/html`.
- WHILE the site is rendered THE SYSTEM SHALL contain no `<script>` element and
  no request to any third-party origin.

### Pull request

- WHEN the implementer opens the pull request THE SYSTEM SHALL state, in the PR
  description, both base image tags and both resolved digests
  (`node:24-alpine@sha256:...`, `nginx:1.30-alpine@sha256:...`).

## Out of scope

- Any page content beyond the `<h1>Dmitrii Mashkov</h1>` placeholder and a
  plain "Not found" 404 page.
- Any styling, CSS, design tokens (`@mctlhq/css`), fonts or vendored assets.
- Language switching (EN/RU), theme switching, and the ~400-byte inline
  preference script with its CSP SHA-256 described in `AGENTS.md`.
- Content collections, the journal (`src/content/journal/**`), ADRs
  (`src/content/adr/**`) and `src/data/metrics.json`.
- CI workflow changes: `.github/workflows/build.yml` already gates the docker
  build on every PR and is not touched. `.github/workflows/release-please.yml`,
  `.github/workflows/claude-review.yml` and `.github/dependabot.yml` are not
  touched either.
- Running `mctl_deploy_service action=onboard`, adding the `dmitriimashkov.com`
  custom domain, DNS, and setting the `MCTL_ONBOARDED` repository variable —
  all operator actions gated on this image existing first.
- Sitemap, RSS, `astro:assets` image optimization, prefetch, view transitions.

## Open questions

Recorded, not blocking. The design proceeds with the interpretation stated
after each one.

1. **"dependency `astro` only" vs. acceptance criterion 6.** `astro check` in
   Astro 5 is a thin wrapper that requires `@astrojs/check` (currently 0.9.10,
   peer `typescript ^5.0.0 || ^6.0.0`); without it the command prompts to
   install and fails non-interactively. Interpretation: `astro` is the only
   entry under `dependencies`; `@astrojs/check` and `typescript` go under
   `devDependencies`. They ship no runtime code and never reach `dist/`.
2. **Astro 5 while Astro 7.3.2 is the current `latest`.** The issue says
   "Astro 5" explicitly, so the dependency is pinned to `^5.0.0`. Consequence:
   the weekly npm Dependabot run will immediately open a major-bump PR to
   Astro 7. Interpretation: honour the issue, expect that PR, and let a human
   decide (a follow-up "upgrade to Astro 7" issue is the clean path). This
   proposal does not add an `ignore` rule to `dependabot.yml` — that file is
   human-owned wiring under the `AGENTS.md` bootstrap boundary.
3. **"succeeds with no warnings".** npm can print deprecation notices for
   transitive dependencies of `astro` that this repository does not control.
   Interpretation: the criterion binds warnings emitted by Astro/Vite about
   this project's own configuration and sources, plus `astro check` reporting
   0 warnings and 0 hints; upstream transitive deprecation notices are noted in
   the PR description rather than treated as failures.
4. **`nginx:1.30-alpine` availability.** Verified to exist on Docker Hub at
   investigation time (multi-arch manifest digest
   `sha256:dc5069ad14f19660b141b21236140b91656bf89bbc3e2417c70ae650cd66104c`).
   Interpretation: re-resolve both digests at implementation time — that
   digest will have moved — and record what was actually used in the PR body.
5. **`npm run check` is not enforced by any CI job.** `build.yml` only runs the
   docker build, and the specified `Dockerfile` does not run `astro check`.
   Interpretation: keep the `Dockerfile` exactly as the issue specifies; the
   implementer runs `npm run check` locally and records the result in the PR
   description. Wiring `check` into CI is a `.github/**` change, which the
   bootstrap boundary reserves for humans.
6. **`X-XSS-Protection`.** `mctlhq/mctl-docs` `nginx.conf` sets it; the issue's
   header list omits it. Interpretation: omit it — the header is deprecated and
   the issue's list is authoritative.
7. **`<title>` text and `<html lang>`.** The issue requires "a `<title>`"
   without giving copy. Interpretation: `<title>Dmitrii Mashkov</title>` and
   `<html lang="en">`, both proper-noun/structural rather than translatable
   copy, so the EN/RU rule in `AGENTS.md` is not yet triggered. The 404 page's
   "Not found" string is the one translatable string introduced here; it is
   accepted as EN-only because i18n is explicitly a later issue, and this must
   be called out in the PR body so the Claude review gate does not read it as
   an oversight.
