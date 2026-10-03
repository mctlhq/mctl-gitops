# Design: issue-10-p8-production-hardening-accessibility-wc

## Current state

**Build and layout.** `astro.config.mjs` sets `output: 'static'`,
`site: 'https://dmitriimashkov.com'`, `trailingSlash: 'always'`,
`integrations: []` and — already — `build.inlineStylesheets: 'never'`, with a
comment stating the reason: the CSP's `style-src 'self'` carries no
`'unsafe-inline'`, so no stylesheet may be inlined. Half of the issue's CSP
task is therefore already done and only needs recording.

`src/layouts/Base.astro` is 30 lines. Its `Props` interface is
`{ title: string }`. `<head>` holds the charset, the viewport, one
`is:inline` script (the language/theme bootstrap, hashed into the CSP by
`scripts/csp-hash.mjs`, capped at 400 bytes), five `<link rel="stylesheet">`
to same-origin paths under `/assets/` and `/styles/`, `<title>` and the
favicon. There is no description, no canonical, no Open Graph, no Twitter
card. All seven pages call `<Base title={...}>`:
`src/pages/index.astro`, `work.astro`, `approach.astro`, `404.astro`,
`colophon/index.astro`, `colophon/journal/[...slug].astro`,
`colophon/adr/[...slug].astro`. `src/pages/dev/[check].astro` writes its own
`<html>` and emits nothing in a production build.

**Bilingual mechanics.** `src/i18n/Lang.astro` renders
`<span class="l en">{en}</span><span class="l ru" lang="ru">{ru}</span>`;
`src/styles/site.css` hides one half per `:root[data-lang]`. Every string
lives in `src/i18n/ui.ts` as an `{ en, ru }` pair — including
`notFoundTitle`, `notFoundBody` and `notFoundHome`, which `src/pages/404.astro`
already uses, with a link to `/`. The bilingual 404 the issue asks for exists;
what it lacks is `noindex` and a description.

**Accessibility affordances already present.** `site.css` has a
`:focus-visible` outline built from `--focus-ring*` tokens; `min-block-size:
44px` on `.site-nav a`, `.toggle-group button`, `.site-footer a`, `.cta` and
`.block > summary`; `.block > summary { display: list-item }` so every
`<details>` in `src/components/Details.astro` keeps its native disclosure
triangle and native keyboard behaviour. `src/components/Nav.astro` labels the
`<nav>`; the toggles in `LangToggle.astro` / `ThemeToggle.astro` are real
`<button type="button">` with `aria-pressed` and `<noscript>` fallbacks. The
two `<svg>` diagrams in `src/components/CycleDiagram.astro` carry `role="img"`,
`aria-labelledby`, one `<title>` and one `<desc>` — `scripts/check-dist.mjs`
already enforces that. There is no `style="` attribute anywhere in `src/`
(verified by grep) and no animation.

**Serving.** `nginx.conf` is one `server` block with four `location` blocks
(`= /healthz`, `= /readyz`, `/_astro/`, `/`). The same six `add_header` lines
appear at server level and in each `location`, thirty lines in total, because a
`location`-level `add_header` (here `Cache-Control` in `/_astro/`) discards the
inherited set. `location /` has `error_page 404 /404.html`. The CSP string
carries the literal `__SCRIPT_SRC_HASHES__`; the `Dockerfile` runs
`scripts/csp-hash.mjs` over `dist/` in the builder stage, `sed`s the hashes
into `nginx.conf` while copying it to `/etc/nginx/conf.d/default.conf`, and
asserts the result contains `sha256-` and no leftover placeholder.

**Mechanical gates.** `npm test` (also `prebuild`, via
`npm run vendor && npm test`) runs `scripts/check-no-metrics.mjs` plus eleven
`node --test` files over `src/`. `scripts/check-dist.mjs` runs after
`astro build` inside the Docker builder stage and enforces the post-build
criteria of P4, P6 and P7: no `.js` under `dist/`, `class="l en"` /
`class="l ru"` parity per file, a 40 KB cap on `dist/index.html`, the approach
page's SVG rules, a page per public journal/ADR entry and none per private one,
`data-release` parity with `package.json`, and — the detail that matters most
here — a rejection of any `<link|script|img|source>` whose `href`/`src` is
absolute or protocol-relative (`ABSOLUTE_URL_RE`, `SUBRESOURCE_RE`).
`.github/workflows/build.yml` runs `npm ci` + `npm test`, then builds the image
with `push: false`; nothing currently runs the container. AGENTS.md declares
`build.yml` explicitly *not* reserved, so adding a runtime check there is
allowed.

## Proposed solution

Seven coordinated changes. Nothing in the list requires a browser.

### 1. Sitemap (`astro.config.mjs`, `package.json`, `public/robots.txt`)

Add `@astrojs/sitemap` to `devDependencies` — it runs inside `astro build` and
ships nothing to the client — and register it in `integrations` with a
`filter` that drops any URL whose path starts with `/404` or `/dev/`. The
integration reuses the existing `site` and `trailingSlash: 'always'`, so the
emitted `<loc>` values match the real page URLs exactly. Regenerate the
lockfile with `npm install --package-lock-only` (AGENTS.md: a plain
`npm install` prunes the other platforms' optional native bindings and breaks
`npm ci` in the Dockerfile).

Append `Sitemap: https://dmitriimashkov.com/sitemap-index.xml` to
`public/robots.txt`. The sitemap files land at the site root and are served by
the existing `location /` with `try_files $uri ...`, so they inherit the
header set with no nginx change.

The issue's criterion 5 says "`sitemap-index.xml` lists the four pages and
every public journal and ADR page". A sitemap *index* lists child sitemaps, not
pages, so the check is written against the closure: read
`dist/sitemap-index.xml`, follow each `<loc>` to a local sitemap file, union
their `<loc>` values, and compare that set to the expected set. Implemented as
`checkSitemap()` in `scripts/check-dist.mjs`, which already computes public and
private journal/ADR ids via `idsByVisibility()` — reusing it keeps the expected
set derived from content rather than typed. The `site` origin is parsed out of
`astro.config.mjs` so the config stays the single source of truth.

### 2. Head metadata (`src/layouts/Base.astro`, `src/lib/seo.ts`, all pages)

Widen `Props` to `{ title: string; description: string; noindex?: boolean }`.
`description` is required, so `npm run check` (`astro check`) fails on a page
that omits it. Compute the canonical URL in the frontmatter as
`new URL(Astro.url.pathname, Astro.site)` and emit, in order: description,
canonical (unless `noindex`), `og:type`/`og:site_name`/`og:title`/
`og:description`/`og:url`/`og:image`/`og:locale`, then `twitter:card`
(`summary_large_image`), `twitter:title`, `twitter:description`,
`twitter:image`. `og:image` and `twitter:image` are
`new URL('/og.svg', Astro.site)` — absolute, as the OG spec requires, and safe
for `check-dist` because `SUBRESOURCE_RE` matches only `link|script|img|source`,
not `meta`.

The four static pages pass the literal strings fixed in requirements.md;
`404.astro` passes its description plus `noindex`. The two dynamic routes
derive theirs through a new `src/lib/seo.ts` exporting
`clampDescription(text, max = 160)` (trim at a word boundary, append `…` only
when it actually truncated) — journal pages clamp `entry.data.decided.en`, ADR
pages clamp a fixed template over `padAdrId(id)`, `title.en`, the English
status label and `date`. Deriving rather than hand-typing means a future
journal entry cannot ship without a description; `src/lib/` is where the other
pure helpers already live (`journal.ts`, `adr.ts`, `metrics.ts`, `content.ts`).

`public/og.svg` is a 1200x630 text-only SVG with three `<text>` elements,
literal hex colours (it is a standalone file with no access to the site's
custom properties — `public/favicon.svg` sets the same precedent) and a generic
font stack. It is never fetched by the page itself, so it costs no request and
does not affect the HAR criterion.

**`check-dist.mjs` must be narrowed in the same commit.** `SUBRESOURCE_RE`
currently flags `<link rel="canonical" href="https://…">` as a third-party
subresource. Change the loop to parse the `rel` attribute and skip `canonical`
and `alternate`, keeping the rejection for every other `<link>` (stylesheet,
icon, preload, manifest) and for `script`/`img`/`source`. Without this the
build fails on the very metadata this issue adds.

Also extend `check-dist.mjs` with a `<style`-element and `style="`-attribute
rejection across `dist/**/*.html`. That is the buildable proxy for the issue's
"no CSP violation in the console": with `style-src 'self'` and no
`'unsafe-inline'`, either construct is a guaranteed violation, and neither can
reach `dist/` unnoticed once the check exists.

### 3. Eight headers defined once (`security-headers.conf`, `nginx.conf`, `Dockerfile`)

Create `security-headers.conf` at the repository root holding the eight
`add_header ... always` lines (the six existing, plus
`Cross-Origin-Opener-Policy: same-origin` and
`Cross-Origin-Resource-Policy: same-origin`), with the CSP keeping its
`__SCRIPT_SRC_HASHES__` placeholder. `nginx.conf` keeps its structure and
replaces each of its five header blocks with a single
`include /etc/nginx/security-headers.conf;`. The `/_astro/` block keeps its own
`add_header Cache-Control` next to the include — having any `add_header` at
that level is precisely why the include is needed there.

The file is installed at `/etc/nginx/security-headers.conf`, deliberately **not**
under `/etc/nginx/conf.d/`: the stock `nginx.conf` in the `nginx:alpine` image
does `include /etc/nginx/conf.d/*.conf;` inside `http`, which would load the
snippet a second time at http level. `Dockerfile` therefore copies both files,
runs the existing `sed` over `security-headers.conf` instead of `nginx.conf`
(the placeholder moved), keeps the two `grep` assertions against the rendered
snippet, and adds `nginx -t` so an unresolvable include fails the image build
rather than the deployment.

Two committed checks replace the unreachable ones:

- `test/nginx.test.ts` (source level, in `npm test`): zero `add_header` for any
  of the eight headers in `nginx.conf`; exactly one per header in
  `security-headers.conf`; exactly one `include .../security-headers.conf;` at
  server level and in each of the four `location` blocks; the CSP contains
  `__SCRIPT_SRC_HASHES__`, no `'unsafe-inline'` and no `http://`/`https://`
  origin.
- `scripts/check-headers.mjs <base-url>` (runtime), called from a new step in
  `.github/workflows/build.yml` that builds the image with `load: true`, runs
  it on a published port, waits for `/healthz`, then `HEAD`s `/`, `/healthz`,
  the `/_astro/` stylesheet discovered from the home page's markup, and a
  deliberately missing path — asserting all eight headers on each, status 404
  on the last, and `sha256-` present in the CSP. This is the mechanical form of
  the issue's `curl -sI` criterion and of the deferred item's "every response
  still carries all six headers".

### 4. 404 page (`src/pages/404.astro`)

Add the description and `noindex` props. The bilingual copy and the home link
already satisfy the rest, and `error_page 404 /404.html` in `location /`
already serves it with the (now included) header set.

### 5. Accessibility pass (`docs/accessibility-checklist.md`, two checks)

The checklist is a committed table, one row per item from the issue, each
marked pass / fail / reviewer step with a note naming the file and the
evidence. Three items get machine backing so the document is not the only
artifact:

- **Contrast**: `scripts/check-contrast.mjs`, added to `npm test`, parses the
  literal hex tokens in `public/assets/mctl/mctl.css`
  (`--mctl-surface-dark-*`, `--mctl-surface-light-*`, the terracotta accent
  ramp), resolves the pairs `site.css` actually uses for both `data-theme`
  values, and computes the WCAG 2.x relative-luminance ratio. Under 4.5:1 for
  body text or 3:1 for the focus ring fails the build. A number, not an
  opinion, and it runs without a browser.
- **Target size and focus**: `test/a11y.test.ts` asserts the `:focus-visible`
  rule and the `min-block-size` declarations in `src/styles/site.css`, and that
  `src/i18n/Lang.astro` still emits `lang="ru"` on the Russian span (WCAG
  3.1.2, Language of Parts).
- **Keyboard `<details>`, headings, link purpose, SVG alternatives, motion**:
  argued in the checklist from source — native `<details>`/`<summary>` with no
  JavaScript interception, one `<h1>` per page with `<h2>` sections, link text
  from `ui.ts` rather than "click here", `role="img"` + `<title>`/`<desc>` on
  both diagrams (already enforced by `check-dist.mjs`), and no CSS animation or
  transition anywhere in `site.css`.

The screen-reader sweep, the visual focus confirmation and the Lighthouse run
stay reviewer steps, named as such in the checklist.

### 6. Hardening notes (`docs/hardening-notes.md`)

A per-header table (header, landed yes/no, why), a section stating that
`style-src` already had no `'unsafe-inline'` because
`build.inlineStylesheets: 'never'` was set in an earlier cycle and that the
only inline `<script>` is covered by its SHA-256 rather than a keyword, a
section on the SVG Open Graph card's limited platform support, and a labelled,
empty section headed for the reviewer's post-deployment Lighthouse mobile
numbers on the four pages. `docs/` is a new directory; it ships in the repo, not
in the image (`.dockerignore` aside, nothing under `docs/` is copied into
`dist/`).

### 7. Journal entry

One entry under `src/content/journal/` for this cycle, per AGENTS.md, with the
five timestamps and `interventions`. `scripts/check-dist.mjs` and the colophon
pages pick it up automatically, and the new sitemap check expects its URL —
which is exactly the coupling that proves the sitemap is generated.

## Alternatives

**A1. Hand-maintain the repeated header blocks and only add COOP/CORP.**
Smallest diff: eight lines appended in five places, forty lines total, and the
CSP still written six times. Rejected — it is the defect #12 deferred, and this
cycle edits the CSP anyway, so the next edit would face the same drift risk
with two more headers to keep in sync.

**A2. Server-level headers only, no `location`-level `add_header`, with
`Cache-Control` from a `map`.** nginx inherits `add_header` from the parent
level *only* when the child level declares none, so the repetition disappears
entirely if `/_astro/` stops declaring `add_header Cache-Control`. That can be
done with an http-context `map $uri $cache_control` at the top of the file
(legal, since `conf.d/*.conf` is included inside `http`) and a single
server-level `add_header Cache-Control $cache_control always;` — nginx omits a
header whose value resolves to the empty string. This variant satisfies the
issue's literal `grep -c "add_header Content-Security-Policy" nginx.conf` = 1,
needs no new file and no `include`. Rejected as the primary because the issue
explicitly names `security-headers.conf` and an `include` per block, and
because the empty-value-omission behaviour is a subtlety a future reader has to
know to read the config correctly. It is the recommended fallback if the
reviewer insists on the literal grep (Open question 1).

**A3. Move the headers into the platform ingress instead of nginx.** The
headers would live in gitops values and the image would carry none. Rejected:
AGENTS.md forbids hand-edited gitops values and confines deployment to the mctl
MCP tools, the header set would stop being reviewable in this repository's
diff, and a local `docker run` would no longer reproduce production.

**A4. Generate the sitemap by hand from the content collections** (an
`astro:build:done` hook writing XML). No new dependency, full control.
Rejected: it re-implements URL normalisation, trailing slashes and the
index/child split that `@astrojs/sitemap` already does correctly, and it is
build-time-only code either way, so the dependency costs the client nothing.
The verification stays ours regardless — `checkSitemap()` compares the
integration's output against an independent scan of `src/content/`.

**A5. Rasterize the Open Graph card to PNG at build time** (resvg/sharp), which
is what every social platform actually renders. Rejected: the issue says
text-only, no raster, and `check-dist.mjs` plus ADR-0005 keep the repository
free of binary blobs and of an image-processing dependency. The consequence is
documented instead (Open question 2).

## Platform impact

**Migrations.** None. No data, no schema, no persisted state. The content
collection schemas in `src/content.config.ts` are untouched.

**Backward compatibility.** URLs are unchanged; no redirect is introduced. Two
new response headers are added — COOP `same-origin` and CORP `same-origin`.
Neither can break this site: it embeds no cross-origin resource, is embedded
nowhere (`frame-ancestors 'none'`, `X-Frame-Options: DENY` already), and opens
no cross-origin window. New files served: `/sitemap-index.xml`,
`/sitemap-0.xml`, `/og.svg`.

**Resource impact.** One build-time dev dependency. A handful of kilobytes of
XML and one small SVG in the image. `dist/index.html` grows by roughly 700-900
bytes of `<head>` metadata against a 40 KB cap currently unspent — the
`check-dist` cap check will confirm it. Runtime CPU and memory are unchanged;
nginx `add_header` via `include` costs nothing at request time. CI grows by one
container run plus four `HEAD` requests.

**Risks and mitigations.**

- *A wrong `include` path or a typo takes the site down at deploy time.* The
  image build now runs `nginx -t`, so a broken config fails in CI, before any
  deployment.
- *A `location` block silently loses the headers because someone adds an
  `add_header` next to the include, or forgets the include in a new block.*
  `test/nginx.test.ts` fails on a `location` block without exactly one include;
  `scripts/check-headers.mjs` fails in CI on any response missing any header.
- *The canonical link breaks the existing absolute-URL guard.* Handled
  head-on: the guard is narrowed to skip `rel="canonical"`/`rel="alternate"`
  only, in the same commit, and the `rel`-less cases stay rejected.
- *The sitemap silently omits a page or exposes a private entry.*
  `checkSitemap()` compares against an independent scan of
  `src/content/journal` and `src/content/adr` and fails on any difference in
  either direction.
- *`npm install` regenerates a linux/x64-only lockfile and breaks `npm ci` in
  the Dockerfile.* AGENTS.md's rule is restated as its own task with its own
  DoD: `npm install --package-lock-only`, then confirm the per-platform binding
  entries survived.
- *`@astrojs/sitemap` has no release compatible with `astro@^7`.* Then the
  integration is dropped and A4 (a build-time hook writing the XML) is
  implemented instead; `checkSitemap()` is unchanged either way because it
  validates output, not the producer.
- *The contrast script fails on a token pair the design system ships.* That is
  a genuine WCAG finding, not a script bug: record it in the checklist as a
  documented exception with a follow-up issue against the token set, and let
  the script's threshold list name the exempted pair explicitly rather than
  lowering the threshold.
