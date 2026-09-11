# P8: Production hardening, accessibility (WCAG 2.2 AA) and SEO

## Context

The site is feature complete: home, work, approach and colophon render, the
colophon generates a page per public journal entry and per public ADR, the
build ships zero JavaScript (`scripts/check-dist.mjs`), and `nginx.conf`
already sends six security headers with a CSP whose `script-src` carries the
build-time SHA-256 of the single inline script (`scripts/csp-hash.mjs`,
`Dockerfile`). What is missing is everything a release needs that is not a
page: machine-readable discovery metadata (sitemap, `robots.txt` pointer,
per-page description, canonical, Open Graph and Twitter card), two further
isolation headers (`Cross-Origin-Opener-Policy`,
`Cross-Origin-Resource-Policy`), and a written, committed record that the
accessibility and header work was actually done rather than asserted.

The issue also folds in a maintainability defect deferred from the P1 review
(#12): the six `add_header` lines are repeated verbatim in the server block and
in all four `location` blocks of `nginx.conf`, because a `location`-level
`add_header` discards the inherited set. Thirty near-identical lines with the
CSP — the one directive this cycle has to change — written out six times is the
exact shape of a configuration that drifts. This cycle is already editing the
CSP, so it is the cheapest moment to define the header set once.

Two constraints shape the whole proposal. First, the implementer has no
browser: a Lighthouse run, a HAR capture and a "no violation in the console"
observation cannot be acceptance criteria, so each is restated as a mechanical
proxy the build can prove plus a named reviewer step (AGENTS.md, "Issue
contract"). Second, `scripts/check-dist.mjs` currently rejects any `<link>`
whose `href` is an absolute URL; a `<link rel="canonical">` is exactly that, so
that check has to be narrowed in the same commit or the build fails.

## User stories

- AS a search engine I WANT a sitemap, a per-page description and a canonical
  URL SO THAT I can index every public page of the site once and correctly.
- AS a reader who shares a link in a chat client I WANT Open Graph and Twitter
  card metadata SO THAT the link renders as a titled card rather than a bare
  URL.
- AS a keyboard-only or screen-reader user I WANT every disclosure, link and
  button operable and visibly focused in both themes and both languages SO
  THAT I can use the whole site without a mouse.
- AS a reader who lands on a wrong URL I WANT a bilingual 404 page with a link
  home SO THAT I am not stranded.
- AS the site operator I WANT the browser isolated from cross-origin openers
  and embedders SO THAT the page cannot be used as a cross-origin side channel.
- AS the next implementer I WANT the security header set defined exactly once
  SO THAT changing the CSP is one edit and cannot leave a `location` block
  behind.
- AS a reviewer I WANT the hardening outcome and the WCAG pass recorded in
  committed files SO THAT the claim is auditable after the pull request is
  merged.

## Acceptance criteria (EARS)

### Sitemap and robots

- WHEN `npm run build` runs THE SYSTEM SHALL emit `dist/sitemap-index.xml` and
  the sitemap file(s) it references, produced by the `@astrojs/sitemap`
  integration configured in `astro.config.mjs`.
- WHEN `scripts/check-dist.mjs` runs after the build THE SYSTEM SHALL verify
  that the set of `<loc>` URLs across every sitemap referenced by
  `dist/sitemap-index.xml` is exactly: `<site>/`, `<site>/work/`,
  `<site>/approach/`, `<site>/colophon/`, one `<site>/colophon/journal/<id>/`
  per public journal entry in `src/content/journal/`, and one
  `<site>/colophon/adr/<id>/` per public ADR entry in `src/content/adr/`, and
  exit non-zero naming the difference otherwise.
- WHILE an entry in `src/content/journal/` or `src/content/adr/` carries
  `visibility: private` THE SYSTEM SHALL keep its id out of every sitemap file.
- IF a URL for `/404`, `/404.html` or any `/dev/` route would appear in a
  sitemap THEN THE SYSTEM SHALL exclude it.
- WHEN `@astrojs/sitemap` is added THE SYSTEM SHALL declare it in
  `devDependencies` of `package.json` (it runs only during `astro build`) and
  the lockfile SHALL be regenerated with `npm install --package-lock-only`.
- WHEN a crawler fetches `/robots.txt` THE SYSTEM SHALL serve a file that keeps
  the existing `User-agent: *` / `Disallow:` pair and adds the line
  `Sitemap: https://dmitriimashkov.com/sitemap-index.xml`.

### Per-page metadata

- WHEN any page renders through `src/layouts/Base.astro` THE SYSTEM SHALL emit
  in `<head>`: `<meta name="description">` with the page's English
  description, `<meta property="og:type">`, `og:site_name`, `og:title`,
  `og:description`, `og:url`, `og:image`, `og:locale`,
  `<meta name="twitter:card" content="summary_large_image">`,
  `twitter:title`, `twitter:description` and `twitter:image`.
- WHEN a page other than the 404 page renders THE SYSTEM SHALL emit
  `<link rel="canonical">` whose `href` is the page's absolute URL, built from
  the `site` value in `astro.config.mjs` and the page path, ending in a
  trailing slash (`trailingSlash: 'always'`).
- WHILE the 404 page renders THE SYSTEM SHALL emit
  `<meta name="robots" content="noindex">` and SHALL NOT emit a canonical link.
- WHEN `src/layouts/Base.astro` is compiled THE SYSTEM SHALL require
  `description: string` in its `Props` interface, so a page that forgets one
  fails `npm run check`.
- THE SYSTEM SHALL use exactly these English descriptions, character for
  character:
  - `/` — `Platform engineering with AI on proven open source. Dmitrii Mashkov builds and runs an internal developer platform where agents ship and humans hold the gates.`
  - `/work/` — `Platform services and products built through the DevLoop, each with its stack, its repository and the snapshot metrics behind it.`
  - `/approach/` — `The DevLoop in detail: an issue becomes a reviewed proposal, an agent pull request, an automated review gate, a release and a deployment.`
  - `/colophon/` — `How this site is built and deployed: the DevLoop cycle table with lead times and manual interventions, and the architecture decision records.`
  - `/404` — `This page does not exist. Return to the home page of dmitriimashkov.com.`
- WHEN a journal entry page renders THE SYSTEM SHALL derive its description
  from that entry's `decided.en`, clamped to at most 160 characters at a word
  boundary with a single trailing `…` when clamped.
- WHEN an ADR page renders THE SYSTEM SHALL derive its description from the
  template `Architecture decision record ADR-<NNNN> for the portfolio site: <title.en>. Status: <status label EN>, <date>.`,
  clamped the same way.
- WHEN the build completes THE SYSTEM SHALL have written `public/og.svg`: a
  text-only SVG card, `viewBox="0 0 1200 630"`, containing no `<image>`
  element, no `data:` URI, no `xlink:href` and no raster file extension, and
  carrying exactly this copy: `Dmitrii Mashkov` /
  `Platform engineering with AI on proven open source` / `dmitriimashkov.com`.
- WHEN `scripts/check-dist.mjs` inspects `dist/**/*.html` THE SYSTEM SHALL
  exempt `<link>` elements whose `rel` is `canonical` or `alternate` from the
  absolute-URL subresource check, and SHALL keep rejecting an absolute URL on
  every other `<link>`, `<script>`, `<img>` and `<source>`.

### 404 page

- WHEN nginx cannot resolve a path under `location /` THE SYSTEM SHALL return
  the built `/404.html` with HTTP status 404 and all eight response headers.
- WHILE the 404 page renders THE SYSTEM SHALL show the English and Russian
  title, body and home link already defined as `ui.notFoundTitle`,
  `ui.notFoundBody` and `ui.notFoundHome` in `src/i18n/ui.ts`, with the Russian
  half carrying `lang="ru"` (via `src/i18n/Lang.astro`), and the home link
  pointing at `/`.

### nginx: header set defined once

- WHEN `nginx.conf` is read THE SYSTEM SHALL contain no `add_header` directive
  for any of the eight security headers; each SHALL be defined exactly once, in
  a new repository-root file `security-headers.conf`.
- WHEN the server block and each of the four `location` blocks in `nginx.conf`
  are read THE SYSTEM SHALL show exactly one
  `include /etc/nginx/security-headers.conf;` in each.
- WHEN `grep -c "add_header Content-Security-Policy" nginx.conf security-headers.conf`
  is run THE SYSTEM SHALL report `1` in total (0 in `nginx.conf`,
  1 in `security-headers.conf`). This is the proposal's restatement of the
  issue's `grep -c ... nginx.conf is 1`; see Open questions, item 1.
- WHEN `security-headers.conf` is read THE SYSTEM SHALL contain exactly one
  `add_header` line for each of: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`,
  `Permissions-Policy: geolocation=(), microphone=(), camera=()`,
  `Strict-Transport-Security: max-age=31536000; includeSubDomains`,
  `Content-Security-Policy` (carrying the `__SCRIPT_SRC_HASHES__` placeholder),
  `Cross-Origin-Opener-Policy: same-origin` and
  `Cross-Origin-Resource-Policy: same-origin`, each with the `always` flag.
- WHILE the CSP is served THE SYSTEM SHALL keep
  `default-src 'self'; script-src 'self' <hashes>; style-src 'self'; font-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`
  and SHALL name no external origin and no `'unsafe-inline'` in any directive.
- WHEN the image is built THE SYSTEM SHALL substitute the build-time hashes
  into `security-headers.conf` (not `nginx.conf`), assert the rendered file
  contains `sha256-` and no `__SCRIPT_SRC_HASHES__`, and run `nginx -t` so an
  unresolvable `include` fails the build rather than the deployment.
- WHEN `npm test` runs THE SYSTEM SHALL execute a source-level check
  (`test/nginx.test.ts`) asserting the two preceding invariants against
  `nginx.conf` and `security-headers.conf`.
- WHEN the pull-request CI workflow runs THE SYSTEM SHALL build the image, run
  the container, and execute `scripts/check-headers.mjs <base-url>`, which
  issues `HEAD` requests to `/`, `/healthz`, the `/_astro/` stylesheet emitted
  by the build and a path that does not exist, and exits non-zero unless every
  response carries all eight headers with the expected values, the 404 response
  has status 404, and the CSP value contains `sha256-` and no `http://` or
  `https://` origin.

### Accessibility and documentation

- WHEN the change lands THE SYSTEM SHALL contain `docs/accessibility-checklist.md`
  with one row per item — keyboard operation of every `<details>`, focus
  visibility on links and buttons, contrast in both themes, `lang` correct on
  RU blocks, heading hierarchy, link purpose, SVG text alternatives, target
  size at least 24 px, no motion — each marked pass, fail or reviewer step,
  each with a note citing the file and the evidence.
- IF an item cannot pass THEN THE SYSTEM SHALL record it as a documented
  exception in the same file, naming the follow-up issue to open.
- WHEN `npm test` runs THE SYSTEM SHALL execute `scripts/check-contrast.mjs`,
  which reads the vendored tokens in `public/assets/mctl/mctl.css`, resolves
  the foreground/background pairs `site.css` actually uses
  (`--surface-fg`, `--surface-fg-muted` and `--accent` over `--surface-bg` and
  `--surface-elevated`; `--accent-fg` over `--accent`) for both `data-theme`
  values, and exits non-zero if any text pair is under 4.5:1 or the focus ring
  over either surface is under 3:1.
- WHEN `scripts/check-dist.mjs` runs THE SYSTEM SHALL additionally fail if any
  `dist/**/*.html` contains a `<style` element or a `style="` attribute, since
  `style-src 'self'` without `'unsafe-inline'` would block both at runtime.
- WHEN `npm test` runs THE SYSTEM SHALL execute a source-level check
  (`test/a11y.test.ts`) asserting that `src/styles/site.css` keeps a
  `:focus-visible` outline rule and a minimum block size of at least 24 px on
  `.site-nav a`, `.toggle-group button`, `.site-footer a`, `.cta` and
  `.block > summary`, and that `src/i18n/Lang.astro` emits `lang="ru"` on the
  Russian span.
- WHEN the change lands THE SYSTEM SHALL contain `docs/hardening-notes.md` with
  one row per header (the six existing plus COOP and CORP) stating whether it
  landed and why, a section recording that `style-src` already carries no
  `'unsafe-inline'` because `build.inlineStylesheets: 'never'` was set in
  `astro.config.mjs` in an earlier cycle, a section on the Open Graph image
  being SVG and what that costs, and an empty, labelled section for the
  reviewer's post-deployment Lighthouse mobile results.
- WHILE this cycle is open THE SYSTEM SHALL treat as reviewer steps, named as
  such in `docs/hardening-notes.md` and never as acceptance criteria: the
  Lighthouse mobile run on the four pages, the HAR capture showing same-origin
  requests only, and the browser-console check for CSP violations in both
  themes and both languages.
- WHEN the change lands THE SYSTEM SHALL add a journal entry under
  `src/content/journal/` for this cycle, per AGENTS.md.

## Out of scope

- Analytics of any kind, in any form, including self-hosted or
  first-party-only counters (ADR-0004 stands).
- The metrics generator (P8b); `src/data/metrics.json` is untouched and no
  number moves.
- Raster images: no PNG, JPEG or WebP is added, for the Open Graph card or
  anything else.
- Any external origin in the CSP, a third-party font, script, or an SRI hash
  for a cross-origin asset — there are none (ADR-0005).
- Russian-language `<meta name="description">`, `og:locale:alternate` or a
  `hreflang` pair: language is a CSS toggle over a single URL, so there is no
  second URL to point at.
- Automated browser testing (Playwright, axe-core in a headless browser) and
  any new runtime dependency shipped to the client.
- Changing `Permissions-Policy`, `X-Frame-Options`, `Referrer-Policy` or HSTS
  values; they move file but not content.
- `Cross-Origin-Embedder-Policy`: not requested by the issue, and it is the one
  isolation header that can break subresource loading.

## Open questions

1. The deferred item's check, `grep -c "add_header Content-Security-Policy" nginx.conf`
   is 1, cannot hold together with the extraction it asks for in the same
   sentence: once the header set moves into `security-headers.conf`, that
   count in `nginx.conf` is 0. This proposal reads the intent as "the CSP is
   defined exactly once" and restates the check as a total of 1 across
   `nginx.conf` and `security-headers.conf`, enforced by `test/nginx.test.ts`.
   A reviewer who wants the literal count instead should send this back and ask
   for design.md alternative 2 (server-level headers only, no `location`-level
   `add_header`, `Cache-Control` via a `map`), which keeps the CSP in
   `nginx.conf` and yields literally 1 — at the cost of not creating the
   `security-headers.conf` file the issue names.
2. The issue requires `public/og.svg`, text-only, no raster. Most social
   platforms (Facebook, LinkedIn, Slack, Telegram, X) do not rasterize SVG for
   link previews and will show no image at all. The no-raster rule wins here
   because it is explicit; the consequence is recorded in
   `docs/hardening-notes.md` rather than silently accepted. Revisit only with
   a new issue that relaxes the no-raster rule.
3. `<meta name="description">` is English only, as the issue states, while
   AGENTS.md requires every user-facing string in both languages. Treated as
   consistent: a meta description is not rendered to the reader and the toggle
   produces no second URL to carry the Russian variant. Recorded here rather
   than resolved.
4. Descriptions for journal and ADR pages are derived from existing content
   (`decided.en`, the ADR title/status/date) rather than hand-typed per entry,
   so a new journal entry never ships without one. If the reviewer wants
   hand-written descriptions, that is a schema change and a different issue.
5. The exact `@astrojs/sitemap` major that declares a peer range accepting
   `astro@^7` is left to the implementer to resolve at install time; the
   criterion is the emitted output, not a version number.
