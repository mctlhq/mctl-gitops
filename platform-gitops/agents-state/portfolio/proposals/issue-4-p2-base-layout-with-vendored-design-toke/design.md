# Design: issue-4-p2-base-layout-with-vendored-design-toke

## Current state

The clone at `main` (`74fc1f9`) is the P1 skeleton and nothing more.

**Pages.** `src/pages/index.astro` and `src/pages/404.astro` are each a
complete standalone document — `<!doctype html>`, `<html lang="en">`, a
`<head>` with charset, viewport, `<title>` and
`<link rel="icon" type="image/svg+xml" href="/favicon.svg" />`, and a `<body>`
holding one `<h1>`. There is no `src/layouts/`, no `src/components/`, no
`src/styles/`, no `src/i18n/`, no `src/content/`, no `scripts/`. `src/` has
exactly one subdirectory, `pages/`.

**Build.** `package.json` pins `astro: ^5.0.0`, `@astrojs/check: ^0.9.10`,
`typescript: ^5.0.0`; `package-lock.json` (lockfileVersion 3) resolves
`astro@5.18.2`, `vite@6.4.3`, `typescript@5.9.3`. Scripts are `dev`, `build`,
`preview`, `check` — there is no `prebuild` and no `vendor`.
`astro.config.mjs` sets `output: 'static'`, `site: 'https://dmitriimashkov.com'`,
`trailingSlash: 'always'`, `integrations: []`. `tsconfig.json` is a single line
extending `astro/tsconfigs/strict`.

**Image and server.** `Dockerfile` is a two-stage build:
`node:24-alpine@sha256:50c8e8ca…` runs `npm ci` then `npm run build`;
`nginx:1.30-alpine@sha256:dc5069ad…` copies `nginx.conf` straight to
`/etc/nginx/conf.d/default.conf` and `dist/` to `/usr/share/nginx/html/`.
There is no build-time transformation of `nginx.conf` at all.

`nginx.conf` defines `/healthz`, `/readyz`, a `/_astro/` immutable-cache
location, and `/` with `error_page 404 /404.html`. The same six security
headers are repeated verbatim in all five blocks, including:

```
add_header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
```

Two consequences matter for this issue. First, `script-src 'self'` with no
hash means the inline preference script is **blocked today** — the hash
pipeline is not an optimisation, it is what makes the feature work at all.
Second, `style-src 'self'` carries **no** `'unsafe-inline'`, so any `<style>`
element Astro inlines into the built HTML is also blocked. The issue's
out-of-scope note ("removing `'unsafe-inline'` from `style-src` … tracked in
P8") is written as if it were present; it is not. This proposal therefore has
to keep Astro from emitting inline styles rather than relax the header.

**Conventions.** `AGENTS.md` is the binding contract: static output only, no
framework bundles, one inline `<head>` script of at most 400 bytes wrapped in
`try/catch` with its SHA-256 in the CSP, English usable with JavaScript
disabled, Russian as a CSS-driven `.l.en` / `.l.ru` toggle, zero third-party
browser requests, `@mctlhq/css` 0.5.0 and the three OFL families vendored with
their licences, no analytics or cookies, base images pinned by tag and digest.
Human hands may touch only `README.md`, `AGENTS.md`, `LICENSE`, `.gitignore`,
`.github/**` and the release-please files; every file this proposal creates is
implementer territory. `.github/workflows/build.yml` builds the Docker image on
every PR without pushing, so a broken `Dockerfile` fails the PR.

**Upstream facts verified against the live sources.**
`https://ui.mctl.ai/0.5.0/mctl.css` returns 200, 19,084 bytes, first line
`/* @mctlhq/css 0.5.0 — raw tokens + semantic theme layer. */` (so a
first-line `0.5.0` check is well-founded). `global.css` is 739 bytes and
`prose.css` 2,579 bytes — 22,402 bytes together, 4,781 gzipped. `mctl.css`
declares `--mctl-typography-font-family-display: 'Onest', …`, `-mono:
'JetBrains Mono', …`, `-editorial: 'Instrument Serif', …` and a semantic layer
keyed on `:root` (dark default) and `[data-theme='light']`, plus `data-accent`
variants. It contains **no** `@font-face` rules — supplying them is entirely
this proposal's job. `global.css` styles only `box-sizing` and `body`, and
`prose.css` is scoped under `.mctl-prose`.

The three families are all OFL-1.1 and all published as `@fontsource`
packages: `@fontsource/onest@5.3.0` (subsets `latin`, `latin-ext`,
`cyrillic`, `cyrillic-ext`, `math`, `symbols`, `vietnamese`; weights 100–900,
normal only), `@fontsource/instrument-serif@5.3.0` (subsets `latin`,
`latin-ext` only; weight 400; normal and italic),
`@fontsource/jetbrains-mono@5.3.1` (subsets including `cyrillic` and
`cyrillic-ext`). Each package ships a top-level `LICENSE` and a `files/`
directory of per-subset `woff2`. Google's `css2` endpoint serves the same
faces split the same way, with `unicode-range` per subset.

`astro@7.3.2` is the current release (majors: 5.18.2, 6.4.8, 7.3.2). Its
`engines` are `node >=22.12.0`, `npm >=9.6.5`; it depends on `vite ^8.0.13`
and declares `@astrojs/markdown-remark ^7.3.0` as a *peer* rather than a
direct dependency. `@astrojs/check@0.9.10` is still the latest and peers only
on `typescript ^5 || ^6`, so it does not block the jump.

The `mctlhq/mctl-docs` `Dockerfile` is the pattern the issue points at: the
builder runs the build and then a hash script; the runtime stage copies
`nginx.conf` to `/tmp`, `sed`s `__SCRIPT_SRC_HASHES__`, then
`grep -q "sha256-"` and `! grep -q "__SCRIPT_SRC_HASHES__"` as build-failing
assertions before deleting the temporaries.

## Proposed solution

### 1. Toolchain upgrade (must land first, as its own commit)

Bump `astro` to `^7.0.0`, regenerate `package-lock.json`, and work through the
official 5 → 6 and 6 → 7 upgrade guides in order. Known hard constraints from
the published package metadata: Node floor rises to `>=22.12.0` (the pinned
`node:24-alpine` already satisfies it, so the `Dockerfile` base needs no
change on that count), Vite moves to 8 (this repo has no Vite plugins or
`vite` config block, so the blast radius is the lockfile), and
`@astrojs/markdown-remark` becomes a peer — irrelevant until the journal/ADR
issue introduces Markdown, but the implementer should add it explicitly if
`astro check` complains. `astro.config.mjs`'s four options (`output`, `site`,
`trailingSlash`, `integrations`) are all still current; `tsconfig.json`'s
`astro/tsconfigs/strict` preset is still shipped. Gate: `npm ls astro`,
`npm run build`, `npm run check`, and `find dist -name '*.js'` empty.

Doing this before any layout work means a build break is attributable to the
upgrade, not to the new components.

### 2. `scripts/vendor-assets.mjs` — vendoring with a version gate

A plain Node ESM script, no dependencies, wired as `"vendor"` in
`package.json` and invoked from `"prebuild"`.

*Design tokens.* Fetch the three URLs under `https://ui.mctl.ai/0.5.0/`. Before
writing `mctl.css`, assert that its first line contains `0.5.0`; on failure,
exit non-zero having written nothing. Write to `public/assets/mctl/`.

*Fonts.* Resolve each family from its `@fontsource` package rather than by
scraping `fonts.googleapis.com`. Two reasons: the package is a stable,
version-pinned artifact (`@fontsource/onest@5.3.0`), whereas gstatic URLs carry
an opaque revision segment (`/s/onest/v11/…`) that changes under us; and the
package ships the OFL `LICENSE` text in the same tarball, which satisfies the
attribution requirement from the same fetch instead of a second guess at where
the licence lives. Download the tarball from the npm registry, extract the
requested `files/*.woff2` for the `latin`, `latin-ext`, `cyrillic` and
`cyrillic-ext` subsets at the requested weights and styles, and copy the
package `LICENSE` to `public/assets/fonts/LICENSES/<family>.txt`. Fail loudly
if any of the three licence files is missing or empty, and if any requested
weight/subset combination resolves to nothing.

*`fonts.css`.* Generate it, do not hand-write it. One `@font-face` per
extracted file, with `font-display: swap`, `src: url('/assets/fonts/<file>')
format('woff2')`, and the `unicode-range` for that subset taken from the
package's own per-subset CSS. Emitting `unicode-range` is what keeps the
Cyrillic files off the wire for an English-only reader — without it the
browser would fetch every face.

*Reproducibility.* Everything under `public/assets/` is committed. `prebuild`
runs the script but treats a network failure as fatal only when the expected
files are absent or fail their version check; with the committed tree present
and correct, an offline `npm run build` (and therefore an offline Docker
build) succeeds. The script exists to refresh deliberately, not to be a build
dependency.

*Idempotence.* Re-running must produce a byte-identical tree, so `git status`
is the regression test: if a refresh changes nothing, it changes nothing.

### 3. The bilingual and theming mechanism

`src/i18n/ui.ts` exports a typed dictionary
`export const ui = { navHome: { en: 'Home', ru: 'Главная' }, … } as const`
covering the four nav labels, the toggle labels and the footer strings, with a
`type UiKey = keyof typeof ui` so `astro check` catches a typo in a key.

`src/i18n/Lang.astro` takes `en` and `ru` props and renders
`<span class="l en">{en}</span><span class="l ru" lang="ru">{ru}</span>`. The
`lang="ru"` on the Russian span is what lets a screen reader switch voice, and
it is why the component exists at all rather than two inline spans.

`src/styles/site.css` carries the switch:

```
:root[data-lang="en"] .l.ru { display: none }
:root[data-lang="ru"] .l.en { display: none }
```

plus the analogous pair for the theme toggle group (`.t.dark` / `.t.light`
keyed on `:root[data-theme]`), a `:root:not([data-theme])`
`prefers-color-scheme: light` fallback, and the layout rules: a
`--content-max` max width, `padding-inline` of at least 16 px at every
viewport, `overflow-x: hidden` avoided in favour of not overflowing in the
first place (long mono strings get `overflow-wrap: anywhere`), and a visible
`:focus-visible` ring using the design system's `--focus-ring`.

### 4. `src/layouts/Base.astro`

```
<html lang="en" data-lang="en" data-theme="dark">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <script is:inline>…</script>
    <link rel="stylesheet" href="/assets/mctl/mctl.css" />
    <link rel="stylesheet" href="/assets/mctl/global.css" />
    <link rel="stylesheet" href="/assets/mctl/prose.css" />
    <link rel="stylesheet" href="/assets/fonts/fonts.css" />
    <link rel="stylesheet" href="/styles/site.css" />
    <title>{title}</title>
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
  </head>
  <body> <Nav /> <slot /> <Footer /> </body>
</html>
```

Three deliberate choices here.

**`is:inline` is mandatory.** Without it, Astro processes the script, hoists
it, and emits a file under `_astro/` — which breaks "no `.js` in `dist/`", the
400-byte measurement, *and* the CSP hash, since the hash would then be of
nothing. `is:inline` leaves the element untouched in the output.

**Stylesheets are plain `<link>`s to `public/`, not `import`s.** Astro's
default `build.inlineStylesheets: 'auto'` inlines any bundled stylesheet under
~4 kB into a `<style>` element in `<head>` — which the existing
`style-src 'self'` header would block, and the issue puts fixing `style-src`
out of scope. Astro also chooses where to inject links for imported styles,
which would fight the "script before the stylesheets" requirement. Serving
`site.css` from `public/styles/site.css` and referencing it by URL removes
both problems: the head order is exactly as authored, nothing is inlined, and
the file is byte-stable. The issue names `src/styles/site.css` as the authored
path, so the source of truth stays there and `scripts/vendor-assets.mjs`
copies it to `public/styles/site.css` on `prebuild` (with
`public/styles/site.css` gitignored to avoid two copies drifting). Belt and
braces: set `build: { inlineStylesheets: 'never' }` in `astro.config.mjs` so
that any future component-scoped `<style>` becomes a `_astro/*.css` link the
current CSP already allows, instead of an inline block that silently fails.

**Script first, stylesheets after.** A render-blocking stylesheet parsed
before an inline script delays that script's execution, which is precisely the
flash of English-dark-then-Russian-light the issue is trying to avoid.

The script itself, verified at **341 bytes** (`wc -c` of its text content,
under the 400-byte cap):

```js
try{let d=document.documentElement,s=localStorage,A=(k,v)=>{d.dataset[k]=v;k=="lang"&&(d.lang=v)};s.lang&&A("lang",s.lang);s.theme&&A("theme",s.theme);addEventListener("click",e=>{let b=e.target.closest?.("[data-set-lang],[data-set-theme]"),k=b&&(b.dataset.setLang?"lang":"theme");k&&A(k,s[k]=b.dataset.setLang||b.dataset.setTheme)})}catch{}
```

It applies *stored* values only (never writing a default, so a first-time
visitor keeps the authored dark English render), sets `data-lang`, `lang` and
`data-theme` on the root element, and delegates clicks from the document so it
works for buttons that do not exist yet when it runs. Everything is inside one
`try`/`catch` per `AGENTS.md`. The implementer should treat the listing above
as the reference implementation and re-measure after the build, since the byte
count and the hash are both taken from `dist/`, not from the source.

### 5. Components

`src/components/Nav.astro` renders Home / Work / Approach / Colophon, each
label through `Lang`, inside a `<nav aria-label>` whose own label is also
bilingual.

`src/components/Footer.astro` renders the `https://github.com/mctlhq` link,
the `/colophon/` link (trailing slash, matching `trailingSlash: 'always'`),
and a `<span data-release>` placeholder carrying the `package.json` version,
so a later issue can change the source without touching markup.

`src/components/LangToggle.astro` and `ThemeToggle.astro` are the interesting
ones, because of the `aria-pressed` / 400-byte tension. Measured: the script
above is 341 bytes; the smallest variant that additionally synchronises
`aria-pressed` across both load and click is 446 bytes — over the cap.

The resolution is to make `aria-pressed` correct *without* script. Each toggle
renders **two** groups of buttons, one per state, and the existing CSS display
rules choose which group is visible:

```
<div class="t dark"> <button type="button" data-set-theme="dark" aria-pressed="true">Dark</button>
                     <button type="button" data-set-theme="light" aria-pressed="false">Light</button> </div>
<div class="t light"><button type="button" data-set-theme="dark" aria-pressed="false">Dark</button>
                     <button type="button" data-set-theme="light" aria-pressed="true">Light</button> </div>
```

with `:root[data-theme="dark"] .t.light { display: none }` and its mirror.
Because `display: none` removes a subtree from the accessibility tree, the
only `aria-pressed` values ever exposed are the ones that match the current
`data-theme` — including immediately after a reload that restored a stored
preference, which is exactly the case the script could not afford to handle.
The same pattern with `.l.en` / `.l.ru` covers `LangToggle`. Cost: roughly 300
bytes of duplicated HTML, trivial against the 30 KB budget. Button text labels
themselves go through `Lang`, so "Dark"/"Light" read as "Тёмная"/"Светлая"
in Russian.

### 6. CSP hash pipeline

`scripts/csp-hash.mjs` reads the built `dist/**/*.html`, extracts the text
content of every inline `<script>` element, computes
`sha256-<base64>` per unique body, and prints them space-separated on stdout.
Reading from `dist/` rather than from the `.astro` source is essential: the
hash must cover exactly the bytes the browser receives, and Astro's
`compressHTML` may alter surrounding whitespace. The script also asserts that
it found exactly one distinct inline script and that its body is at most 400
bytes, so the byte budget is enforced by the build rather than by review.

`nginx.conf`'s `script-src` becomes `'self' __SCRIPT_SRC_HASHES__` in all five
`location`-level `Content-Security-Policy` headers (a global `sed` covers
them; the repeated headers are an existing nginx quirk — `add_header` does not
inherit into a block that declares its own).

`Dockerfile` follows the `mctl-docs` shape:

```
RUN npm run build && node scripts/csp-hash.mjs > /app/csp-script-src.txt
…
COPY nginx.conf /tmp/nginx.conf
COPY --from=builder /app/csp-script-src.txt /tmp/csp-script-src.txt
RUN HASHES="$(cat /tmp/csp-script-src.txt)" \
 && sed "s|__SCRIPT_SRC_HASHES__|${HASHES}|g" /tmp/nginx.conf > /etc/nginx/conf.d/default.conf \
 && grep -q "sha256-" /etc/nginx/conf.d/default.conf \
 && ! grep -q "__SCRIPT_SRC_HASHES__" /etc/nginx/conf.d/default.conf \
 && rm /tmp/nginx.conf /tmp/csp-script-src.txt
```

Note the `g` flag — `mctl-docs` has one CSP line, this repo has five.

### 7. Compression, for the 30 KB budget

The three vendored stylesheets are 22,402 bytes uncompressed. Add the
generated `fonts.css` (roughly 30 `@font-face` blocks with `unicode-range`,
on the order of 5 KB), `site.css`, the favicon and the HTML itself, and an
uncompressed `/` lands around 32–35 KB — over acceptance criterion 7. The
stock `nginx.conf` inside the image ships `#gzip  on;`, i.e. compression off,
and this repo's config never turns it on. Gzipped, the same three stylesheets
are 4,781 bytes and the whole page comfortably clears the budget with room to
spare.

So `nginx.conf` gains, in the `server` block:

```
gzip on;
gzip_comp_level 6;
gzip_min_length 256;
gzip_vary on;
gzip_types text/css text/plain application/javascript image/svg+xml application/json;
```

`text/html` is always compressed by nginx when `gzip on` and needs no entry.
`woff2` is already compressed and is deliberately excluded.

### 8. Pages

`src/pages/index.astro` and `404.astro` shrink to a `Base` element with a
`title` prop and bilingual body content, deleting the duplicated `<head>`
blocks entirely.

## Alternatives

**Install `@mctlhq/css` and the fonts as npm dependencies and let Astro bundle
them.** Fewer moving parts, and Dependabot would track versions. Dropped
because `@mctlhq/css` is not published to the registry under that name at a
version this repo can pin (the artifacts are served from `ui.mctl.ai`), and
because bundling puts the CSS under `_astro/` with a content hash, where the
"first line names version 0.5.0" acceptance criterion has nothing to point at.
Bundling small stylesheets also reintroduces the inline-`<style>` CSP problem.
Vendoring into `public/` keeps the served bytes identical to the upstream
artifact and makes the version check a one-line assertion.

**Scrape `fonts.googleapis.com/css2` for the woff2 URLs instead of using
`@fontsource` tarballs.** This is the most direct reading of "downloads the
woff2 files", and it yields the `unicode-range` values for free. Dropped as
the primary path because the gstatic URLs embed a mutable revision segment
(`/s/onest/v11/…`) so the script is not reproducible across font updates, and
because it leaves the OFL text to be fetched from a fourth, unrelated place.
Kept as a documented fallback in the script's header comment for any family
that is ever missing from `@fontsource`.

**Render Russian as a second set of pages (`/ru/…`) with Astro i18n routing.**
Proper `hreflang`, indexable Russian URLs, no duplicated DOM. Dropped because
it contradicts `AGENTS.md` ("Russian is a CSS-driven toggle (`.l.en` /
`.l.ru` pairs)"), doubles the page count for every later content issue, and
would need either a server redirect or a script that navigates — neither of
which fits a 400-byte budget or a no-JS baseline.

**Synchronise `aria-pressed` from the inline script and raise the byte cap.**
The obvious implementation. Dropped because 400 bytes is fixed by both the
issue and `AGENTS.md`, and the measured cost of a correct load-plus-click
`aria-pressed` sync is 446 bytes. The duplicated-toggle-group pattern gets the
same user-visible and assistive-technology behaviour for zero script bytes.

**Cookie-based preference with server-side rendering of the chosen language.**
Zero flash, zero client script. Dropped outright: ADR-0004 forbids cookies,
and `output: 'static'` means there is no server to read them.

## Platform impact

**Migrations.** None in the data sense — the site is static with no database.
The `Dockerfile` gains a build step and a runtime-stage `RUN`, so the image
build is no longer a pure copy; `.github/workflows/build.yml` already exercises
this on every PR, so a mistake fails the PR rather than production.

**Backward compatibility.** URL surface is unchanged: `/`, `/404.html`,
`/healthz`, `/readyz`. The `/_astro/` cache location keeps working (and now
matters, since `inlineStylesheets: 'never'` may start emitting files there).
New URLs are additive under `/assets/` and `/styles/`. Nothing external
consumes this repo's output yet — `MCTL_ONBOARDED` is not set and the release
workflow only tags — so there is no deployed consumer to break.

**Resource impact.** Repository size grows by roughly 250–350 KB of committed
`woff2` plus 22 KB of CSS. The image grows by the same amount. Runtime memory
and CPU are unchanged apart from gzip, which at `gzip_comp_level 6` on a
static site of this size is negligible and is offset by roughly 25 KB less
egress per cold visit.

**Risks and mitigations.**

- *Astro 7 breaks the build in a way not covered by the upgrade guides.*
  Mitigation: land the upgrade as a separate first commit with its own green
  `npm run build` / `npm run check`, so it can be reverted independently of the
  layout work. The repo has no integrations, no Vite plugins and no Markdown
  yet, which is the smallest possible surface for a two-major jump.
- *Astro inlines a stylesheet and the existing `style-src 'self'` blocks it,
  producing an unstyled page that still passes `npm run build`.* This is the
  most likely silent failure in the whole proposal. Mitigation: set
  `build.inlineStylesheets: 'never'`, keep `site.css` in `public/`, and add an
  explicit test that greps `dist/**/*.html` for `<style` and fails if any is
  found.
- *The inline script is hoisted into `_astro/*.js` because `is:inline` was
  omitted.* Mitigation: the `find dist -name '*.js'` assertion and
  `scripts/csp-hash.mjs`'s "exactly one inline script" check both fail loudly.
- *The CSP hash does not match what is served* — for example because the
  hash was computed from source rather than from `dist/`, or because only one
  of the five CSP headers was substituted. Mitigation: compute from `dist/`,
  use a global `sed`, keep the `grep -q "sha256-"` and
  `! grep -q "__SCRIPT_SRC_HASHES__"` assertions, and verify in a browser
  console as an explicit acceptance test.
- *`ui.mctl.ai` publishes a different 0.5.0 or goes away.* Mitigation: the
  vendored files are committed, so builds never depend on it; the first-line
  version gate turns a silent content change into a failed `npm run vendor`.
- *A Cyrillic subset is missed and Russian renders in a system fallback,
  passing every automated check.* Mitigation: an explicit visual check in the
  test list, plus a vendor-script assertion that every family which offers a
  `cyrillic` subset has one vendored per weight.
- *Contrast failure in the light theme* (acceptance criterion 8). The design
  system supplies both surfaces, so the risk is in this proposal's own rules —
  muted footer text on `--surface-fg-subtle`, and the unselected toggle button.
  Mitigation: run Lighthouse in both themes, and prefer
  `--surface-fg-muted` over `--surface-fg-subtle` for anything that must be
  read.
- *Font licence obligation unmet.* Mitigation: the vendor script fails if any
  of the three `LICENSES/*.txt` is missing or empty, so the obligation cannot
  regress silently.
