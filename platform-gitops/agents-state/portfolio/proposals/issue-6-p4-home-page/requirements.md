# P4: Home page

## Context

`src/pages/index.astro` is still the placeholder written in P2: an `<h1>` with
`ui.homeTitle`, one lede paragraph, and two empty `<section>` shells with the
ids `work` and `approach` that `src/components/Nav.astro` anchors to. Issue #6
replaces it with the real landing page: the name, a one-sentence bilingual
thesis, a sub-line, four headline numbers read from a dated metrics snapshot,
two calls to action, and three collapsible blocks (`What I run`, `How I work`,
`Contact`).

This is the first page on the site that shows numbers, and `AGENTS.md` is
explicit that "every number shown on the site comes from
`src/data/metrics.json`, which carries `generated_at` and a per-source
`collected_at` and `method`. Numbers are never typed into templates or
content." That file does not exist yet — its generator is P8b. So this issue
introduces the file as a *placeholder with null values*, plus the two
components that consume it, so that the page's shape, its bilingual parity and
its performance budget can be proved now and the real numbers can arrive later
as a data-only change. The page must also honour the constraints the earlier
cycles already fixed in code: static output with no client bundles (ADR-0002),
zero third-party browser requests (ADR-0005), a CSS-driven `.l.en` / `.l.ru`
bilingual switch, and one inline preference script whose 400-byte budget
`scripts/csp-hash.mjs` enforces at image build time.

## User stories

- AS a hiring manager or prospective client landing on `dmitriimashkov.com`
  I WANT the thesis, the headline numbers and a way into the work within one
  screen SO THAT I can decide in seconds whether to keep reading.
- AS a Russian-speaking reader I WANT every sentence on the page in Russian
  SO THAT I never hit a half-translated page after using the language toggle.
- AS a reader on a 360 px phone on a slow connection I WANT text to paint
  immediately and tap targets large enough to hit SO THAT the page is usable
  before anything else has loaded.
- AS a reader who prints the page or saves it as PDF I WANT the collapsible
  blocks to print expanded and in readable ink SO THAT the printed page carries
  the same content as the screen.
- AS the site owner I WANT the four headline numbers to come from a dated
  snapshot file SO THAT no figure on the site can be a claim I typed by hand.
- AS a reviewer of the implementer's pull request I WANT bilingual parity, page
  weight and the absence of JavaScript checked mechanically SO THAT the gate
  does not depend on me counting spans.

## Acceptance criteria (EARS)

### Page content and copy

- WHEN `src/pages/index.astro` renders THE SYSTEM SHALL emit, in order: the
  hero name `Dmitrii Mashkov`, the thesis, the sub-line, four stat tiles with
  their caption, two calls to action, and three `<details>` blocks
  (`What I run`, `How I work`, `Contact`).
- WHEN the hero name is emitted THE SYSTEM SHALL emit the string
  `Dmitrii Mashkov` once, unpaired (no `.l` class), because it is identical in
  both languages.
- WHEN any user-facing string that differs between languages is emitted THE
  SYSTEM SHALL emit it as an `.l en` / `.l ru` pair, with the Russian element
  also carrying `lang="ru"`, exactly as `src/i18n/Lang.astro` does today.
- WHEN a user-facing string is emitted THE SYSTEM SHALL take it from
  `src/i18n/ui.ts`, never from a literal typed into `src/pages/index.astro`.
- WHEN the thesis, sub-line, stat labels, CTA labels, `<summary>` texts and
  `<details>` bodies are emitted THE SYSTEM SHALL use the EN and RU strings from
  issue #6 verbatim, character for character, including proper nouns
  (`k3s`, `Hetzner`, `OpenTofu`, `ArgoCD`, `Argo Workflows`, `Argo Rollouts`,
  `HashiCorp Vault`, `External Secrets`, `CloudNativePG`, `VictoriaMetrics`,
  `Grafana`, `Loki`, `Traefik`, `cert-manager`, `Temporal`, `Backstage`,
  `Cloudflare`).
- WHEN the two calls to action are emitted THE SYSTEM SHALL link
  `See the work` / `Смотреть работы` to `/work/` and
  `How this site is built` / `Как сделан этот сайт` to `/colophon/`, with the
  trailing slash that `astro.config.mjs` (`trailingSlash: 'always'`) requires.
- WHEN the `Contact` block is emitted THE SYSTEM SHALL emit a link to
  `https://github.com/mctlhq` with the text `github.com/mctlhq` and a link to
  `mailto:hello@dmitriimashkov.com` with the text `hello@dmitriimashkov.com`,
  each emitted once and unpaired because both are identical in the two
  languages.

### Metrics data and the stat tiles

- WHEN the repository is built THE SYSTEM SHALL read every displayed number
  from `src/data/metrics.json`, whose shape is
  `{ "generated_at", "sources": { "github": { "collected_at", "method", "repos", "commits", "releases" }, "mctl": { "collected_at", "method", "services", "devloop_proposals" } } }`.
- WHILE `src/data/metrics.json` is the placeholder introduced by this proposal
  THE SYSTEM SHALL carry `null` for `generated_at`, both `collected_at` fields
  and every metric value, and the literal string `placeholder` for both
  `method` fields.
- IF a metric value is `null` THEN THE SYSTEM SHALL render an em dash
  (U+2014) in that tile instead of a number.
- IF `generated_at` is `null` THEN THE SYSTEM SHALL render the snapshot caption
  with an em dash in place of the date, as `Snapshot —` / `Снимок —`.
- IF `generated_at` is a non-null ISO 8601 timestamp THEN THE SYSTEM SHALL
  render its calendar date as `YYYY-MM-DD` in the caption, in both languages
  identically.
- WHEN the four tiles are emitted THE SYSTEM SHALL bind them to
  `sources.github.repos` (`Repositories` / `Репозитории`),
  `sources.github.commits` (`Commits` / `Коммиты`),
  `sources.github.releases` (`Releases` / `Релизы`) and
  `sources.mctl.services` (`Services in production` / `Сервисов в проде`).
- WHILE this proposal is in force THE SYSTEM SHALL contain no digit in
  `src/pages/index.astro` other than the digits in HTML heading element names
  (`h1`…`h6`), which is the mechanical form of "no metric value is typed into
  the page".
- IF `src/data/metrics.json` carries a metric value that is neither `null` nor
  a non-negative integer THEN THE SYSTEM SHALL fail `npm test`.

### Bilingual parity, budget and platform constraints

- WHEN `npm run build` has produced `dist/` THE SYSTEM SHALL contain, in every
  `dist/**/*.html`, exactly as many occurrences of the literal `class="l en"`
  as of `class="l ru"`.
- WHEN `npm run build` has produced `dist/` THE SYSTEM SHALL keep
  `dist/index.html` under 40 960 bytes (40 KB).
- WHEN `npm run build` has produced `dist/` THE SYSTEM SHALL contain no file
  with a `.js` extension anywhere under `dist/`.
- IF any of the three checks above fails THEN THE SYSTEM SHALL fail the Docker
  image build, in the same `RUN` step that already runs
  `scripts/csp-hash.mjs`, so the pull request's `build` job goes red.
- WHILE the page is served THE SYSTEM SHALL issue same-origin requests only:
  no font, stylesheet, image or script URL outside `https://dmitriimashkov.com`
  is referenced from the document.
- WHEN the document loads THE SYSTEM SHALL ship exactly one inline script — the
  existing preference script in `src/layouts/Base.astro` — and no other
  JavaScript, so `scripts/csp-hash.mjs` still finds exactly one body under
  400 bytes.
- WHEN the browser reports the largest contentful paint THE SYSTEM SHALL have
  a text node as the LCP element, which follows from the page carrying no
  image, no `background-image` and no video.

### Layout, typography and print

- WHILE the viewport is 360 px wide THE SYSTEM SHALL produce no horizontal
  scrollbar: `document.documentElement.scrollWidth` is not greater than
  `document.documentElement.clientWidth`.
- WHILE the viewport is 360 px wide THE SYSTEM SHALL render every interactive
  element on the page — nav links, the language and theme toggle buttons, both
  CTAs, every `<summary>`, and both links in the `Contact` block — at least
  44 px tall.
- WHEN text that has a Russian counterpart is styled THE SYSTEM SHALL set it in
  `var(--font-display)` (Onest), never in `var(--font-editorial)`
  (Instrument Serif), which ships no Cyrillic subset — see
  `public/assets/fonts/fonts.css`, where `Instrument Serif` has only `latin`
  and `latin-ext` faces.
- WHEN the hero name is styled THE SYSTEM SHALL be permitted to use
  `var(--font-editorial)`, because `Dmitrii Mashkov` is Latin-only and
  identical in both languages.
- WHEN the page is printed THE SYSTEM SHALL render dark text on a white ground
  regardless of the `data-theme` attribute that `src/layouts/Base.astro`
  hardcodes to `dark`.
- WHEN the page is printed THE SYSTEM SHALL render the body of all three
  `<details>` blocks, whether or not they are open on screen.
- WHEN the page is printed THE SYSTEM SHALL omit the language toggle, the theme
  toggle and the site navigation.
- WHEN a new stylesheet rule is needed THE SYSTEM SHALL add it to
  `src/styles/site.css` rather than to a component `<style>` block, so that the
  page keeps linking exactly the five stylesheets `src/layouts/Base.astro`
  lists today and adds no `_astro/*.css` request.

## Out of scope

- Real metric values and the snapshot generator — that is P8b. This proposal
  only introduces the placeholder file and the null-safe rendering path.
- The Work, Approach and Colophon pages (P5, P6, P7). The two CTAs point at
  `/work/` and `/colophon/`, which will 404 until those cycles land.
- Changing `src/components/Nav.astro`. Its `/#work` and `/#approach` anchors
  lose their targets when the placeholder sections go; they degrade to "top of
  the home page", not to an error, and re-pointing the navigation belongs to
  the cycle that creates those pages.
- Wiring `data-release` in `src/components/Footer.astro` to a real
  git-describe source.
- Open Graph / Twitter card images, a favicon change, a sitemap, or
  `robots.txt` changes.
- Any analytics, cookie or consent mechanism — `AGENTS.md` forbids it until the
  ADR that covers metrics provenance lands.
- An ADR. Nothing here revises ADR-0001, ADR-0002 or ADR-0005; the page is an
  application of decisions already recorded.
- `astro:content` collections. The home page reads no collection; the three
  `<details>` bodies are dictionary strings, not content entries.

## Open questions

- **Is `generated_at` null in the placeholder, or the date the placeholder was
  written?** The issue says the schema carries an ISO timestamp and that values
  are null. This proposal reads "do not type any real number into this file" as
  covering the timestamp too — a hand-written `generated_at` would assert that
  a snapshot happened, and no snapshot has. It therefore sets `generated_at` to
  `null` and renders `Snapshot —` / `Снимок —`. The components handle a non-null
  timestamp on the same code path, so if the reviewer prefers a real date, only
  `src/data/metrics.json` changes — no component, no test, no copy.
- **`method` when there is no method yet.** The schema requires the field; the
  proposal writes the literal `placeholder` in both sources, so P8b's diff
  shows the real collection method replacing an obviously provisional value.
  An empty string or `null` would read the same; `placeholder` was chosen
  because it is greppable.
- **Thousands separators.** A commit count will eventually be four or five
  digits, and EN and RU group digits differently (`1,234` vs `1 234`). The tile
  renders one value shared by both languages, so this proposal renders plain
  digits with `font-variant-numeric: tabular-nums` and no grouping. If the
  reviewer wants grouping, the tile value must become an `.l` pair like every
  other language-dependent string, which is a component change, not a copy
  change.
- **Announcing a null tile to a screen reader.** An em dash is read as
  punctuation or skipped, so a tile with no value is silent. A visually hidden
  "Not yet collected" / "Ещё не собрано" would fix it, but that is copy the
  issue does not contain, and the issue says the copy is verbatim. The proposal
  therefore ships the em dash alone and flags this for the reviewer; it becomes
  moot once P8b lands real values.
- **Whether the three blocks default open or closed.** The issue says
  "collapsible", which implies closed. The proposal renders them closed, gives
  `src/components/Details.astro` an `open` prop for later use, and forces them
  visible in the print stylesheet so the printed page is complete either way.
- **`ui.homeTitle.ru`.** It is `Дмитрий Машков` today. The issue's typography
  constraint states that the name is identical in both languages, so the hero
  renders `Dmitrii Mashkov` unpaired. The `<title>` element can hold only one
  string; this proposal sets both `homeTitle.en` and `homeTitle.ru` to
  `Dmitrii Mashkov` so the dictionary does not contradict the page.
