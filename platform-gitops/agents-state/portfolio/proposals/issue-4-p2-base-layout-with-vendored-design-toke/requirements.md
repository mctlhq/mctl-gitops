# P2: Base layout with vendored design tokens and fonts, EN fallback, persisted RU/theme preference

## Context

`portfolio` today is the bare P1 skeleton: two hand-written full documents
(`src/pages/index.astro`, `src/pages/404.astro`) that each repeat their own
`<!doctype html>`, `<head>` and a single `<h1>`. There is no layout, no
stylesheet, no component directory, no `src/styles/`, no `src/i18n/`, no
`scripts/`. `astro.config.mjs` declares `output: 'static'`,
`site: 'https://dmitriimashkov.com'`, `trailingSlash: 'always'` and an empty
`integrations` array. `nginx.conf` already ships a strict CSP
(`script-src 'self'`, `style-src 'self'`, `font-src 'self'`, no
`'unsafe-inline'` anywhere) repeated verbatim in all five `location` blocks.
The site therefore renders unstyled, monolingual, and would reject any inline
script the moment one is added.

This proposal gives every page one `Base.astro` layout that carries the
`@mctlhq/css` 0.5.0 design system and its three font families as files served
from the site's own origin, renders a complete and usable English page with
JavaScript disabled, and — with JavaScript — lets a visitor switch to Russian
and between the dark and light surface, remembering both choices in
`localStorage`. This is the only client-side script the site will ever have,
so its byte budget (400 bytes) and its CSP hash are part of the contract, not
an implementation detail. It matters because every later issue (content,
journal, ADRs, metrics) renders through this layout: getting the token
plumbing, the bilingual mechanism and the CSP hash pipeline right once removes
them from the critical path of every subsequent DevLoop cycle.

## User stories

- AS a visitor with JavaScript disabled I WANT the English site to render
  completely and legibly SO THAT the page is usable without executing any code.
- AS a Russian-speaking visitor I WANT a toggle that switches every
  user-facing string to Russian and survives a reload SO THAT I do not have to
  re-select my language on every page.
- AS a visitor who prefers a light surface I WANT a theme toggle whose choice
  survives a reload SO THAT the site respects my reading preference.
- AS a privacy-conscious visitor I WANT the page to make zero requests to any
  third-party host SO THAT loading the site does not expose me to `ui.mctl.ai`,
  Google Fonts or any other origin.
- AS the site owner I WANT design tokens and fonts vendored into the repository
  with their licences SO THAT the build is reproducible offline and the OFL
  attribution obligation is met.
- AS the site owner I WANT the inline script's SHA-256 substituted into the CSP
  at image build time SO THAT `script-src` never needs `'unsafe-inline'`.
- AS a maintainer I WANT the Astro toolchain on the current major SO THAT
  security updates and Dependabot PRs land against a supported line.

## Acceptance criteria (EARS)

### Toolchain

- WHEN `npm ls astro` is run after the upgrade THE SYSTEM SHALL report a
  version in the current major line (7.x; `astro@7.3.2` is latest at the time
  of writing, `engines` `node >=22.12.0`, `npm >=9.6.5`, Vite `^8`).
- WHEN `npm run build` is run THE SYSTEM SHALL exit 0.
- WHEN `npm run check` is run THE SYSTEM SHALL exit 0 with zero errors.
- WHILE the project is on the upgraded major THE SYSTEM SHALL keep
  `@astrojs/check` and `typescript` resolvable without peer-dependency errors
  (`@astrojs/check@0.9.10` declares only `typescript: ^5 || ^6` as a peer).
- WHEN the Docker image is built THE SYSTEM SHALL use a Node base image whose
  version satisfies the new `engines.node` floor, pinned by tag and digest.
- WHEN `find dist -name '*.js'` is run after a build THE SYSTEM SHALL return no
  results.

### Vendored assets

- WHEN `npm run vendor` is run THE SYSTEM SHALL download
  `https://ui.mctl.ai/0.5.0/mctl.css`, `global.css` and `prose.css` into
  `public/assets/mctl/`.
- IF the first line of the downloaded `mctl.css` does not contain the string
  `0.5.0` THEN THE SYSTEM SHALL exit non-zero and write no file. (The current
  first line is `/* @mctlhq/css 0.5.0 — raw tokens + semantic theme layer. */`.)
- WHEN `npm run vendor` is run THE SYSTEM SHALL download `woff2` files for
  Onest weights 300, 400, 500, 600 and 700, Instrument Serif 400 normal and
  400 italic, and JetBrains Mono weights 400, 500, 600 and 700, into
  `public/assets/fonts/`.
- WHILE the site is bilingual THE SYSTEM SHALL vendor, for every family and
  weight that offers it, at least the `latin` and `cyrillic` subsets, so that
  Russian text is rendered by the vendored family and not by a system fallback.
- WHEN `npm run vendor` is run THE SYSTEM SHALL write the SIL Open Font Licence
  text for each of the three families into `public/assets/fonts/LICENSES/`,
  one file per family, and SHALL exit non-zero if any of the three is missing
  or empty.
- WHEN `npm run vendor` is run THE SYSTEM SHALL write
  `public/assets/fonts/fonts.css` containing one `@font-face` rule per vendored
  file, each with `font-display: swap`, the correct `font-family`,
  `font-weight`, `font-style`, a `format('woff2')` source under
  `/assets/fonts/`, and the `unicode-range` matching that file's subset.
- WHILE the repository is checked out THE SYSTEM SHALL contain the vendored CSS,
  font and licence files committed, so that `npm run build` succeeds with no
  network access.
- WHEN `npm run build` is invoked THE SYSTEM SHALL run the vendor step from
  `prebuild` and SHALL NOT fail the build when the network is unavailable but
  the vendored files are already present and pass their version check.

### Layout, i18n and theming

- WHEN any page is served THE SYSTEM SHALL render a single `<html>` element
  with `lang="en"`, `data-lang="en"` and `data-theme="dark"` as authored.
- WHEN any page is served THE SYSTEM SHALL include in `<head>`, in this order:
  the charset meta, the viewport meta, exactly one inline `<script>`, then the
  stylesheet links for `/assets/mctl/mctl.css`, `/assets/mctl/global.css`,
  `/assets/mctl/prose.css`, `/assets/fonts/fonts.css` and the site stylesheet,
  plus `<title>` from a layout prop and `<link rel="icon">` to
  `/favicon.svg`.
- WHILE JavaScript is disabled THE SYSTEM SHALL render `/` in English only,
  styled with the `@mctlhq/css` tokens and the three vendored families, with
  working navigation and footer links.
- WHILE `:root` carries `data-lang="en"` THE SYSTEM SHALL hide every element
  matching `.l.ru`.
- WHILE `:root` carries `data-lang="ru"` THE SYSTEM SHALL hide every element
  matching `.l.en`.
- WHEN a visitor with JavaScript enabled activates the RU control THE SYSTEM
  SHALL set `data-lang="ru"` and `lang="ru"` on `document.documentElement` and
  store `ru` under the `localStorage` key `lang`.
- WHEN a visitor with JavaScript enabled activates a theme control THE SYSTEM
  SHALL set the corresponding `data-theme` value on
  `document.documentElement` and store it under the `localStorage` key `theme`.
- WHEN a page loads and `localStorage.lang` or `localStorage.theme` holds a
  value THE SYSTEM SHALL apply that value to `document.documentElement` before
  the stylesheets are fetched, so that the first paint already shows the stored
  language and surface.
- IF `localStorage` access throws (private mode, disabled storage) THEN THE
  SYSTEM SHALL swallow the error inside `try { … } catch {}` and continue
  rendering the authored English dark default.
- WHILE a toggle group is displayed THE SYSTEM SHALL expose its controls as
  `<button type="button">` elements with visible text labels and an
  `aria-pressed` value that truthfully reflects the current language or theme,
  including immediately after a reload that restored a stored preference.
- WHEN the rendered HTML of any page is inspected THE SYSTEM SHALL contain
  exactly one `<script>` element, inline, whose text content is at most 400
  bytes as measured by `wc -c`.
- WHEN the navigation is rendered THE SYSTEM SHALL present Home, Work, Approach
  and Colophon, each through the `Lang` component with both an English and a
  Russian string.
- WHEN the footer is rendered THE SYSTEM SHALL present a link to
  `https://github.com/mctlhq`, a link to `/colophon/`, and a placeholder slot
  for the release tag.
- WHEN `/` and `/404.html` are built THE SYSTEM SHALL render both through
  `Base.astro` rather than through their own hand-written documents.

### Security and budget

- WHEN the image is built THE SYSTEM SHALL compute the SHA-256 of the inline
  script from the built `dist/` output and substitute it for
  `__SCRIPT_SRC_HASHES__` in `nginx.conf`.
- IF the substituted nginx configuration still contains
  `__SCRIPT_SRC_HASHES__`, or contains no `sha256-` token, THEN THE SYSTEM
  SHALL fail the image build.
- WHILE the site is served THE SYSTEM SHALL send a `Content-Security-Policy`
  header whose `script-src` is `'self'` plus one or more `sha256-` tokens and
  which does not contain `'unsafe-inline'` in `script-src`.
- WHEN `/` is loaded in Chrome THE SYSTEM SHALL produce no CSP violation in the
  console.
- WHEN `/` is recorded as a HAR in Chrome THE SYSTEM SHALL show requests to the
  page's own origin only — no `ui.mctl.ai`, no `fonts.googleapis.com`, no
  `fonts.gstatic.com`, no other host.
- WHEN `/` is loaded THE SYSTEM SHALL transfer less than 30 KB in total,
  excluding font files. (The three vendored stylesheets alone are 22,402 bytes
  uncompressed and 4,781 bytes gzipped, so this criterion requires compression
  to be enabled on the server.)
- WHEN a Lighthouse mobile accessibility audit is run against `/` THE SYSTEM
  SHALL report no colour-contrast failure in either the dark or the light
  theme.
- WHEN `/` is viewed at a 360 px viewport width THE SYSTEM SHALL produce no
  horizontal scrollbar and SHALL keep at least 16 px of page padding.

## Out of scope

- Page content: home page copy beyond what the layout demonstrates, projects,
  the journal, ADRs, `src/data/metrics.json`, and the `/colophon/` page itself
  (only the link to it is in scope).
- Any analytics, cookie, or third-party script.
- Removing `'unsafe-inline'` from `style-src` if Astro's scoped styles turn out
  to require it — tracked in P8. Note that the current `nginx.conf` has never
  carried `'unsafe-inline'` in `style-src`, so this proposal must avoid
  emitting inline `<style>` rather than relax the policy; see `design.md`.
- Content collections, RSS, sitemap, Open Graph images.
- Deploying the result (`mctl_deploy_service`) or setting `MCTL_ONBOARDED`.
- Adding accent-colour switching (`data-accent`), which the design system
  supports but the issue does not request.

## Open questions

- **`data-theme` vs the `prefers-color-scheme` fallback.** The issue requires
  `<html … data-theme="dark">` to be authored *and* a `prefers-color-scheme`
  fallback in `site.css` "for when no `data-theme` is stored". With the
  attribute always present in the served HTML, a plain media query can never
  win against the `@mctlhq/css` `[data-theme='light']` block. Proceeding with:
  keep `data-theme="dark"` authored (this is what guarantees a complete,
  styled no-JS page), scope the fallback to `:root:not([data-theme])` so it is
  a live rule for any future document that omits the attribute, and have the
  inline script apply *stored* values only — it never writes a default into
  `localStorage`, so a first-time visitor keeps the authored dark surface.
  A reviewer who instead wants the system preference to win on first visit
  should say so: that means dropping the authored `data-theme` and accepting a
  dark-only no-JS render, which conflicts with acceptance criterion 1.
- **`aria-pressed` and the 400-byte cap.** Measured on real candidate
  implementations: a script that applies stored values and delegates clicks is
  341 bytes; adding a `querySelectorAll` pass to synchronise `aria-pressed` on
  both load and click pushes the smallest working variant to 446 bytes, over
  the cap. Proceeding with the CSS-driven resolution in `design.md` (render
  both aria states in markup and let the existing display rules pick), which
  keeps `aria-pressed` truthful at zero script cost. A reviewer who prefers
  script-driven `aria-pressed` must raise the cap in `AGENTS.md` and in
  acceptance criterion 3.
- **Which font subsets to vendor.** Google's `css2` endpoint splits Onest into
  7 subsets, Instrument Serif into 2, JetBrains Mono into 6. Vendoring every
  subset for every requested weight is roughly 60 files; vendoring only
  `latin`, `latin-ext`, `cyrillic` and `cyrillic-ext` is roughly 32.
  Proceeding with `latin` + `latin-ext` + `cyrillic` + `cyrillic-ext` (and
  `latin` + `latin-ext` only for Instrument Serif, which ships no Cyrillic).
- **Instrument Serif has no Cyrillic.** Confirmed: the family offers only
  `latin` and `latin-ext`. Russian text set in the editorial face will fall
  back to Georgia/serif. Proceeding by not using the editorial face for any
  string that has a Russian counterpart in this proposal; a reviewer may want
  a documented Cyrillic editorial substitute in a later issue.
- **Compression.** The stock `nginx.conf` inside `nginx:alpine` ships
  `#gzip  on;` — compression is off. Acceptance criterion 7 is not reachable
  without enabling it. Proceeding by adding `gzip` directives to the repo's
  `nginx.conf` server block. A reviewer who considers that out of scope should
  say so, and criterion 7 must then be relaxed.
- **Release-tag placeholder in the footer.** The issue asks for a
  "placeholder for the release tag" but the value source (build arg,
  `package.json` version, git describe) is P-something later. Proceeding with a
  literal placeholder element carrying a stable hook (`data-release`) and the
  `package.json` version as its text, so a later issue can replace the source
  without touching the markup.
