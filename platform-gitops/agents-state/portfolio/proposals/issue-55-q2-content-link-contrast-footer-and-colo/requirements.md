# Q2': content link contrast, footer and colophon links, plus an internal-only link check

## Context

Every `<a>` inside `<main>` that carries no class of its own is unstyled and
renders in the user-agent default. Against the dark surface
(`--mctl-surface-dark-bg: #0a0b0d`, `public/assets/mctl/mctl.css`) the default
`#0000EE` measures 2.10:1 and the visited `#551A8B` measures 1.79:1, where WCAG
2.2 AA 1.4.3 requires 4.5:1. The affected links are the Contact block on `/`
(`src/pages/index.astro`), both tables on `/colophon/`
(`src/pages/colophon/index.astro` and `src/components/CycleTable.astro`), the
meta block and the "Back to the colophon" link on
`src/pages/colophon/journal/[...slug].astro` and
`src/pages/colophon/adr/[...slug].astro`, and "Back to home" on
`src/pages/404.astro`. Alongside the contrast defect, the footer renders
`Release: 0.1.11` with a colon and no link to the release tag, its "Source on
GitHub" label points at the organisation rather than this repository, and the
two identifiers in the colophon's "Build and deploy chain" list
(`github.com/mctlhq/portfolio`, `ghcr.io/mctlhq/portfolio`) are plain text.

This supersedes issue #46, whose pull request (#54) closed unmerged. The single
requirement that broke that cycle — proving link health by checking that every
link returns HTTP 200 — is removed here. Roughly 60 sequential unauthenticated
requests per pull request from shared GitHub Actions egress addresses makes a
429 or a 403 secondary rate limit a routine outcome unrelated to the diff:
forgiving the failure lets the gate pass without checking, and not forgiving it
makes CI flake. Both branches are wrong in one direction, which is the signal
that the requirement, not the implementation, was wrong. This proposal replaces
it with an **internal-only** link check that issues no network request at all
and resolves every internal `href` against the built `dist/` tree.

This proposal introduces **no new user-facing string**. Every string it touches
already exists in `src/i18n/ui.ts` and is reproduced character for character in
the acceptance criteria below; the changes are colour, punctuation, `href`
targets and anchor wrapping only.

## User stories

- AS a reader with low vision I WANT links in the page body to meet the WCAG
  2.2 AA 4.5:1 contrast minimum in both themes, unvisited and visited SO THAT I
  can find and read them without straining.
- AS a returning reader I WANT a visited call-to-action and a visited project
  link to keep highlighting on hover SO THAT the page does not appear inert once
  I have been to those pages.
- AS a reader printing the colophon I WANT content links legible on paper SO
  THAT a printed copy carries the same information as the screen.
- AS a reader of the footer I WANT the release number to link to its GitHub tag
  and "Source on GitHub" to point at this repository SO THAT I can go from the
  version I am looking at to the code that produced it in one click.
- AS a reader of the colophon I WANT the repository and image identifiers to be
  links SO THAT I can reach the source and the published image directly.
- AS a maintainer I WANT a merge gate that proves no internal link in the built
  site is broken, without depending on anyone else's uptime SO THAT the gate
  fails only on defects this repository introduced.

## Acceptance criteria (EARS)

### Part 1 — content link contrast

- WHEN `src/styles/site.css` is built THE SYSTEM SHALL colour every `<a>` inside
  `<main>` with `var(--accent)` through a `main a` rule, resolving to `#e25a3c`
  in the dark theme and `#b83d28` in the light theme.
- WHILE a content link is in the `:visited` state THE SYSTEM SHALL render it in
  the same `var(--accent)`, so `#551A8B` is never used.
- WHEN a content link is hovered THE SYSTEM SHALL render it in
  `var(--accent-highlight)` (`#ff8a6a` dark, `#9a3220` light).
- WHILE `@media print` is active THE SYSTEM SHALL override `--accent` to the
  light-theme `#b83d28` so content links measure at least 4.5:1 (measured:
  5.62:1) against the forced white background, instead of the 3.64:1 the
  dark-theme value gives.
- THE SYSTEM SHALL NOT apply the `.mctl-prose` class to `<main>` on any page;
  the rule `.mctl-prose a { color: var(--accent) }` at
  `public/assets/mctl/prose.css:54` exists, but the class carries a complete
  typographic system (`h1`–`h4`, `p`, `ul`, `ol`, `em`, `code`, `pre`,
  `blockquote`, lede) and would restyle every page.
- THE SYSTEM SHALL leave `.site-nav a`, `.cta`, `.site-footer a` and
  `.project-links a` visually unchanged in every state, `:visited` included.
- WHILE a `.cta` link is visited and not hovered THE SYSTEM SHALL render it in
  `var(--surface-fg)`; WHEN it is hovered, visited or not, THE SYSTEM SHALL
  render it in `var(--accent)` per the existing `.cta:hover` rule.
- WHILE a `.project-links a` link is visited, hovered, or both THE SYSTEM SHALL
  render it in `var(--surface-fg)`, which is what it renders today.
- IF a `:visited` pin is expressed as a bare `:visited` selector THEN THE SYSTEM
  SHALL be considered non-compliant: `.cta:hover` and `.cta:visited` have equal
  specificity (0,2,0) so source order decides, and `.project-links a:visited`
  (0,2,1) loses to `main a:hover` (0,1,2) at any source order. Pins SHALL use
  `:visited:not(:hover)` so they are order-independent.
- WHEN `npm test` runs THE SYSTEM SHALL execute a cascade test that resolves,
  by specificity and then source order over the rules actually present in
  `src/styles/site.css`, the winning `color` declaration for a class-less
  content link, a `.cta` and a `.project-links a` in each of the four states
  (normal, `:visited`, `:hover`, `:visited:hover`), and SHALL fail if any of
  those twelve resolutions differs from the table above.
- WHEN `scripts/check-contrast.mjs` runs THE SYSTEM SHALL additionally check the
  content-link colour in its normal, `:visited` and `:hover` states against
  `--surface-bg` and `--surface-elevated` in both themes, and against the print
  background, failing when any pair is below 4.5:1.
- IF the content-link colour is reverted to `#0000EE`, OR the `:visited`
  declaration is reverted to `#551A8B`, OR the `main a` rule is deleted
  outright THEN `scripts/check-contrast.mjs` SHALL report a problem and exit
  non-zero; WHILE the committed stylesheet is unmutated it SHALL exit zero.
- WHEN `scripts/check-contrast.mjs` or `scripts/check-links.mjs` is loaded THE
  SYSTEM SHALL decide whether to run `main()` from `import.meta.main`, and IF
  `import.meta.main` is `undefined` (a Node build older than 24.2) THEN THE
  SYSTEM SHALL print a diagnostic and exit non-zero rather than exiting zero
  having checked nothing. Comparing `import.meta.url` to `process.argv[1]`
  SHALL NOT be used: it fails open under a symlinked checkout.

### Part 2 — footer

- WHEN `src/components/Footer.astro` renders THE SYSTEM SHALL emit the release
  label, a single space, then the version — `Release 0.1.11` in English,
  `Релиз 0.1.11` in Russian — with no colon. The labels are the existing
  `ui.footerReleaseLabel`: `en: 'Release'`, `ru: 'Релиз'`.
- WHEN the footer renders THE SYSTEM SHALL wrap the version in an anchor whose
  `href` is `https://github.com/mctlhq/portfolio/releases/tag/<version>`, built
  from the same build-time `package.json` `version` value that already feeds the
  `data-release` hook. THE SYSTEM SHALL NOT contain a literal semver in the
  template. (`release-please-config.json` sets `include-v-in-tag: false` and
  `include-component-in-tag: false`, so the tag path is bare.)
- THE SYSTEM SHALL keep `data-release` as the last attribute on the element
  whose text content is the version, so the existing
  `/data-release>([^<]*)</` assertion in `scripts/check-dist.mjs` still matches.
- WHEN the footer renders THE SYSTEM SHALL point the "Source on GitHub" anchor
  at `https://github.com/mctlhq/portfolio`, leaving its label text unchanged:
  `en: 'Source on GitHub'`, `ru: 'Исходный код на GitHub'`.
- THE SYSTEM SHALL leave `.site-footer a { color: inherit }` as the colour rule
  covering the new anchor; no new footer colour rule is added.

### Part 3 — colophon

- WHEN the "Build and deploy chain" list renders THE SYSTEM SHALL link the
  substring `github.com/mctlhq/portfolio` to `https://github.com/mctlhq/portfolio`
  and the substring `ghcr.io/mctlhq/portfolio` to
  `https://github.com/mctlhq/portfolio/packages`, in both languages.
  (Measured 2026-09-11: `https://ghcr.io/mctlhq/portfolio` 404s — it is a
  registry API host, not a web page — and `.../pkgs/container/portfolio` 404s
  anonymously; `/packages` returns 200.)
- WHILE linkifying those items THE SYSTEM SHALL leave every other character
  unchanged. The four affected list items are, verbatim:
  - `Source: github.com/mctlhq/portfolio`
  - `Image: ghcr.io/mctlhq/portfolio, built by mctl-gitops from a release tag`
  - `Исходники: github.com/mctlhq/portfolio`
  - `Образ: ghcr.io/mctlhq/portfolio, собирается mctl-gitops из тега релиза`
- THE SYSTEM SHALL keep every entry of `ui` in `src/i18n/ui.ts` a plain string
  or an array of plain strings, since `test/ui.test.ts` asserts that shape; no
  markup SHALL be stored in the dictionary.

### Part 4 — internal-only link check

- WHEN `scripts/check-links.mjs` runs THE SYSTEM SHALL resolve every internal
  `href` found in `dist/**/*.html` against the built `dist/` tree, honouring
  `trailingSlash: 'always'` from `astro.config.mjs` (`/colophon/` →
  `dist/colophon/index.html`, `/` → `dist/index.html`), stripping query and
  fragment first.
- IF an internal `href` does not resolve to a file under `dist/` THEN THE SYSTEM
  SHALL fail, naming the page the link was found on, the `href`, and the file it
  expected.
- WHEN an `href` is an absolute `http(s)` URL THE SYSTEM SHALL classify it as
  internal by comparing its origin to the `site` value read from
  `astro.config.mjs`, and SHALL resolve it exactly like a root-relative one.
  Classification SHALL NOT be done by byte equality with the page's own
  canonical `href`: `src/layouts/Base.astro` emits an absolute
  `<link rel="canonical">` on every indexable page, and remark-gfm autolinks
  bare site URLs in rendered markdown, so absolute self-links are routine and
  byte equality misclassifies the same URL carrying a fragment, missing a
  trailing slash, or appearing on a `noindex` page (`src/pages/404.astro`, which
  carries no canonical at all).
- WHEN a same-origin absolute or root-relative `href` has no trailing slash and
  no file extension THE SYSTEM SHALL resolve it as `<path>/index.html`, falling
  back to `<path>`, and SHALL name both candidates in the failure message.
- WHEN an `href` is `mailto:`, another non-`http(s)` scheme, or an off-origin
  `http(s)` URL THE SYSTEM SHALL report it as **skipped**, by count and listed.
  Nothing skipped SHALL be counted as passing.
- THE SYSTEM SHALL NOT call `fetch`, open a socket, import `node:http`,
  `node:https`, `node:net` or `undici`, retry, back off, set a timeout, consult
  a status-code table, forgive a network-unreachable condition, or carry any
  soft case.
- WHEN `npm test` runs THE SYSTEM SHALL execute a test that replaces
  `globalThis.fetch` with a counting stub that throws, drives
  `scripts/check-links.mjs` over a temporary fixture tree, and fails if the stub
  was called even once; the same test SHALL assert the script source contains
  no `fetch(`, no `node:http`/`node:https`/`node:net`/`undici` import, no
  retry/backoff and no timeout.
- WHEN `npm test` runs THE SYSTEM SHALL execute tests proving
  `scripts/check-links.mjs` fails on a broken internal `href`, resolves a
  same-origin absolute `href` carrying a fragment, resolves a same-origin
  absolute `href` with no trailing slash, and lists both a `mailto:` and an
  off-origin `href` as skipped.
- WHEN a pull request runs `.github/workflows/build.yml` THE SYSTEM SHALL build
  the site and then run `scripts/check-links.mjs` against the produced `dist/`,
  failing the job on any unresolved internal href.
- THE SYSTEM SHALL document in `docs/link-check.md` what the check proves and
  what it deliberately does not, and SHALL NOT record a dated table of
  third-party URL statuses — a snapshot of someone else's uptime is not evidence
  about this repository.

### Whole-site invariants

- WHILE the change is in place THE SYSTEM SHALL keep the count of
  `class="l en"` equal to the count of `class="l ru"` in every
  `dist/**/*.html`, and SHALL emit no `.js` file under `dist/`, both already
  enforced by `scripts/check-dist.mjs`.
- WHEN `npm test`, `npm run build` and `node scripts/check-dist.mjs` run THE
  SYSTEM SHALL exit zero on all three.
- THE SYSTEM SHALL add every new test file to the explicit file list in the
  `test` script of `package.json`, which names each file rather than globbing.

## Out of scope

- Any external link checking, now or as a scheduled job. If wanted later it is
  monitoring with its own issue.
- `/work/` beyond pinning `.project-links a` so the new rules cannot alter it —
  issue #47.
- Colophon tables, timestamps, lead time — issue #48.
- Navigation state, skip-link, `role="group"`, `<summary>` headings, toggle
  spacing, default-open blocks — issue #49.
- `og:image`, font preload, `Cache-Control`, the DevLoop diagram, hero name wrap
  — issue #50.
- The five P3s on `src/lib/csp.ts` — issue #52.
- Re-running Lighthouse to confirm `/colophon/` leaves 96: a reviewer step, it
  needs a browser.
- Journal entries for this wave: deferred to a single closing cycle, since the
  schema needs cycle timestamps the implementer cannot know.
- Changing `src/i18n/ui.ts` string content, adding any new user-facing copy, or
  translating anything.
- Re-pinning the `node:24-alpine` base image digest in the `Dockerfile`.

## Open questions

- **Node floor.** `import.meta.main` requires Node >= 24.2. CI pins
  `node-version: 24` (`.github/workflows/build.yml`) and the Docker builder is
  `node:24-alpine` pinned by digest, both of which should satisfy it, but the
  digest cannot be resolved offline to confirm the exact minor. The fail-closed
  guard specified above turns an older engine into a loud non-zero exit rather
  than a silent pass; if the Docker build fails on that diagnostic, the fix is
  re-pinning the base image (out of scope here), never weakening the guard. A
  side effect: a contributor on Node 22 will now see `npm test` refuse to run
  `check-contrast.mjs`. Proceeding: correctness of the gate outranks local
  convenience, and the guard is what the issue asks for.
- **Scope of the href set.** The issue says "every internal `href`". This
  proposal reads `href` from `<a>` elements and from
  `<link rel="canonical">`, and leaves subresource URLs (`<link rel=stylesheet>`,
  `<script>`, `<img>`) to the existing absolute-URL check in
  `scripts/check-dist.mjs`. Proceeding with that reading; it is the superset
  that matters for readers.
- **Fragment-only hrefs.** No `href="#..."` exists in the site today (the
  skip-link is issue #49). The check treats a fragment-only href as resolving to
  the current document and does not verify that the fragment matches an element
  `id`; `docs/link-check.md` records this as a deliberate non-claim.
- **`.mctl-prose` link hover.** `main a:hover` (0,1,2) does not reach ADR prose
  links: `.mctl-prose a:hover` at `public/assets/mctl/prose.css:60` is (0,2,1)
  and wins. No pin is needed and none is added.
- **Nav and footer pins.** `Nav` and `Footer` render outside `<main>` in
  `src/layouts/Base.astro`, so `main a` cannot reach `.site-nav a` or
  `.site-footer a` at all. Rather than add dead CSS pins, this proposal asserts
  that structural fact in a test. If a future layout moves either inside
  `<main>`, that test fails first.
