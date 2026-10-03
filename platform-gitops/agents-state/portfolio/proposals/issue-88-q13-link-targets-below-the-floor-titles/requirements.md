# Q13: link hit areas, search titles, journal indexing, share-image alt

## Context

An external UX audit of https://dmitriimashkov.com/ dated 2026-09-13 measured
four mechanical defects on production 0.1.23 and on `main` at `41dc023`+. None
of them needs a copy decision from the owner.

1. `src/styles/site.css` gives a 44px `min-block-size` to six interactive
   selectors (`.site-nav a`, `.toggle-group button`, `.site-footer a`, `.cta`,
   `.block > summary`, `.skip-link:focus`) and the guard in
   `test/a11y.test.ts:22` checks exactly those six. Four classes of standalone
   link carry no hit-area rule at all and measured 17-20px: `.project-links a`
   (the repository and Docs links on `/work/`), `.journal-meta a` (the issue
   and pull-request links on a journal entry page), `.breadcrumb a`, and the
   links inside `.table-scroll` (the cycles table and the ADR index). The suite
   is green while those links are half the 24px floor.
2. `src/pages/colophon/journal/[...slug].astro` renders
   `` `${data.title.en} — Dmitrii Mashkov` `` and
   `src/pages/colophon/adr/[...slug].astro` renders
   `` `ADR-${padAdrId(entry.data.id)}: ${entry.data.title.en} — Dmitrii Mashkov` ``,
   with no length budget anywhere. Measured against the clone, 23 rendered
   titles are longer than 65 characters and one more is exactly 65; the longest
   is 127 characters
   (`2026-09-12-symlink-safe-check-no-metrics-entry-guard.md`).
   `test/seo.test.ts` exercises `clampDescription` only and asserts nothing
   about titles. An editorial H1 and a search-result title are different jobs.
3. All 24 public journal entries reach `dist/sitemap-0.xml`, because
   `astro.config.mjs` only filters `/404` and `/dev/` and `scripts/check-dist.mjs`
   `checkSitemap()` expects exactly one sitemap URL per public journal entry.
   Most entries are internal build notes of 96-200 words: correct as a public
   record, wrong as an answer to a search. The journal schema in
   `src/content.config.ts` has no way to say so.
4. `src/layouts/Base.astro` emits `og:image` and `twitter:image` with no
   `og:image:alt` or `twitter:image:alt`, and no page carries structured data
   of any kind.

This proposal gives every standalone link a hit area the test can actually
see, gives long pages a short search title without touching their headings,
lets a journal entry say whether it is written for a reader or for the record,
and describes the share image. Nothing user-facing changes in wording or
layout beyond the 404 page's two new links.

## User stories

- AS a reader on a 360px phone I WANT every standalone link on the work,
  journal, breadcrumb and colophon-table surfaces to have a hit area of at
  least 24px SO THAT I can tap the link I meant without hitting its neighbour.
- AS the maintainer I WANT the hit-area guard in `test/a11y.test.ts` to cover
  all ten selectors and to fail when a declaration drops below the floor SO
  THAT a future stylesheet edit cannot silently take a link back under 24px.
- AS someone who finds a page of this site in a search result I WANT its title
  to fit inside the result SO THAT I can read what the page is before I click.
- AS the maintainer I WANT a build-time title-length budget SO THAT a new
  entry with a long editorial title cannot ship a truncated search title.
- AS someone searching for how this site handles CSP headers or cache
  lifetimes I WANT the six journal entries that answer a real question to be
  indexed and the eighteen raw build notes to stay out of the index SO THAT
  search results are answers and not operational noise.
- AS a reader of the colophon I WANT every journal entry, indexed or not, to
  stay published, linked and reachable SO THAT the public record is complete.
- AS someone shown the share card by a screen reader or on a slow connection I
  WANT the image to have alternative text SO THAT I know what was shared.
- AS a search engine crawling a journal or ADR page I WANT a `BreadcrumbList`
  that matches the visible breadcrumb SO THAT the page's place in the site is
  unambiguous.
- AS a reader who lands on a wrong URL I WANT the 404 page to offer the work
  page and a contact address SO THAT I am not left with only a link home.
- AS the maintainer I WANT the JSON-LD to cost no CSP change SO THAT
  `scripts/csp-hash.mjs` keeps reporting exactly one script hash and the
  `script-src` directive stays as it is.

## Acceptance criteria (EARS)

### A. Hit areas

- WHEN `src/styles/site.css` is read THE SYSTEM SHALL declare, for each of
  `.project-links a`, `.breadcrumb a`, `.journal-meta a` and `.table-scroll a`,
  a `min-block-size` of at least 24px together with `display: inline-flex` and
  `align-items: center`, in the same shape the existing six selectors use.
- WHILE those four rules are in force THE SYSTEM SHALL leave `main a` in prose
  untouched: no hit-area rule may apply to a link inside a paragraph of running
  text by virtue of being inside `<main>`.
- WHEN `test/a11y.test.ts` runs THE SYSTEM SHALL check all ten selectors --
  the existing `.site-nav a`, `.toggle-group button`, `.site-footer a`, `.cta`,
  `.block > summary`, `.skip-link:focus` plus the four new ones -- keeping the
  existing assertion shape: at least one rule block whose selector list
  contains the exact selector sets `min-block-size`, and every such declaration
  is at or above 24px.
- IF any of the ten `min-block-size` declarations drops below 24px THEN THE
  SYSTEM SHALL fail `test/a11y.test.ts` naming the selector and the measured
  value.
- WHEN `test/a11y.test.ts` runs THE SYSTEM SHALL prove the guard discriminates
  by running the same matcher over a synthetic stylesheet recorded in the test
  file that declares `min-block-size: 20px` for a selector, and asserting the
  matcher reports a problem for it; and over a synthetic stylesheet that
  declares no `min-block-size` at all for that selector, and asserting the
  matcher reports a problem for that too.
- WHILE the new rules are in force THE SYSTEM SHALL introduce no `min-width`,
  no fixed `height`/`block-size`, no `animation` and no `transition`, and
  SHALL leave `.table-scroll`'s `overflow-x: auto`, `tabindex="0"` focusable
  region, `:focus-visible` outline and the `@media (max-width: 599px)`
  `.table-scroll::after` scroll hint exactly as they are.

### B. Short search titles

- WHEN `src/content.config.ts` is loaded THE SYSTEM SHALL accept an optional
  `seoTitle: z.string().min(1)` on the `journal` collection schema and on the
  `adr` collection schema.
- WHILE `seoTitle` is a single Latin string THE SYSTEM SHALL NOT make it
  bilingual: it is a complete `<title>` string, one per entry, exactly as
  `AGENTS.md` already prescribes for `ui.homeTitle`.
- WHEN a journal page is rendered THE SYSTEM SHALL use `data.seoTitle` as the
  `<title>` if present, and otherwise `` `${data.title.en} — Dmitrii Mashkov` ``.
- WHEN an ADR page is rendered THE SYSTEM SHALL use `entry.data.seoTitle` as
  the `<title>` if present, and otherwise
  `` `ADR-${padAdrId(entry.data.id)}: ${entry.data.title.en} — Dmitrii Mashkov` ``.
- WHILE `seoTitle` is present on an entry THE SYSTEM SHALL leave that page's
  `<h1>` and its breadcrumb current-item text rendering `title.en` / `title.ru`
  unchanged.
- WHEN `src/lib/seo.ts` is imported THE SYSTEM SHALL export
  `titleProblems(title: string, options?: { warn?: number; fail?: number }): string[]`
  with defaults `warn = 65` and `fail = 75`, returning a list of problem
  strings.
- WHEN `titleProblems` is called with a title of exactly 65 characters THE
  SYSTEM SHALL return an empty list.
- WHEN `titleProblems` is called with a title of 66 characters THE SYSTEM
  SHALL return exactly one problem, classified as a warning, whose message
  contains the number 66 and the number 65.
- WHEN `titleProblems` is called with a title of 76 characters THE SYSTEM
  SHALL return a problem classified as a failure, whose message contains the
  number 76 and the number 75.
- WHEN the title-length test runs THE SYSTEM SHALL compute, for every journal
  and every ADR entry, the title the route actually renders -- by calling the
  same exported helper the route calls, not by reading a hand-typed list of
  titles -- and SHALL assert that no computed title exceeds 75 characters.
- WHEN the title-length test runs THE SYSTEM SHALL assert that every entry
  whose computed title exceeds 65 characters carries a `seoTitle`; that is, an
  entry may exceed the 65-character warning budget only by carrying one.
- WHEN the content files are read THE SYSTEM SHALL carry exactly these 24
  `seoTitle` values, character for character, each on the named file and on no
  other:

| file | `seoTitle` |
|---|---|
| `src/content/journal/2026-09-12-symlink-safe-check-no-metrics-entry-guard.md` | `Symlink-safe entry guards in npm test — Dmitrii Mashkov` |
| `src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md` | `Journal entries closed by their release — Dmitrii Mashkov` |
| `src/content/journal/2026-09-13-journal-tests-assert-invariants-only.md` | `Journal tests assert invariants — Dmitrii Mashkov` |
| `src/content/journal/2026-09-12-q9-six-review-findings.md` | `Guards that could pass unchecked — Dmitrii Mashkov` |
| `src/content/journal/2026-09-12-backfilling-five-omitted-journal-entries.md` | `Backfilling five omitted journal entries — Dmitrii Mashkov` |
| `src/content/journal/2026-09-11-production-cutover.md` | `Production cutover and rollback drill — Dmitrii Mashkov` |
| `src/content/journal/2026-09-12-share-image-font-preload-cache-lifetime.md` | `Share image, fonts and cache lifetime — Dmitrii Mashkov` |
| `src/content/journal/2026-09-12-content-link-contrast-and-an-offline-link-check.md` | `Link contrast and an offline link check — Dmitrii Mashkov` |
| `src/content/journal/2026-09-12-navigation-state-and-accessibility-affordances.md` | `Navigation state and missing affordances — Dmitrii Mashkov` |
| `src/content/journal/2026-09-11-p8-production-hardening-accessibility-wc.md` | `Hardening, accessibility and SEO — Dmitrii Mashkov` |
| `src/content/journal/2026-09-12-colophon-tables-and-computed-lead-time.md` | `Colophon tables and computed lead time — Dmitrii Mashkov` |
| `src/content/journal/2026-09-10-astro-static-skeleton-and-nginx-image.md` | `Astro static skeleton and nginx image — Dmitrii Mashkov` |
| `src/content/journal/2026-09-12-q7-polish-wave-findings.md` | `Fourteen findings from the polish wave — Dmitrii Mashkov` |
| `src/content/journal/2026-09-10-register-portfolio-as-a-devloop-service.md` | `Registering portfolio as a DevLoop service — Dmitrii Mashkov` |
| `src/content/journal/2026-09-11-csp-hash-quoting-and-browser-verified-headers.md` | `CSP hash quoting, headers verified live — Dmitrii Mashkov` |
| `src/content/journal/2026-09-11-content-collections.md` | `Content collections for projects and ADRs — Dmitrii Mashkov` |
| `src/content/journal/2026-09-10-base-layout-vendored-tokens-and-fonts.md` | `Base layout with vendored tokens and fonts — Dmitrii Mashkov` |
| `src/content/journal/2026-09-11-metrics-provenance-and-no-analytics.md` | `Metrics provenance and no analytics — Dmitrii Mashkov` |
| `src/content/journal/2026-09-12-repository-links-out-of-the-disclosure.md` | `Repository links out of the disclosure — Dmitrii Mashkov` |
| `src/content/adr/0003-custom-domain-via-mctl-registry.md` | `ADR-0003: Custom domain and DNS-01 cert — Dmitrii Mashkov` |
| `src/content/adr/0005-self-contained-runtime-assets.md` | `ADR-0005: Self-contained runtime assets — Dmitrii Mashkov` |
| `src/content/adr/0001-bootstrap-boundary.md` | `ADR-0001: Bootstrap boundary — Dmitrii Mashkov` |
| `src/content/adr/0004-no-analytics.md` | `ADR-0004: No analytics, no cookies — Dmitrii Mashkov` |
| `src/content/adr/0002-static-astro-no-client-bundles.md` | `ADR-0002: Static Astro, no client bundles — Dmitrii Mashkov` |

  The em dash in every value above is U+2014 surrounded by one space on each
  side, exactly as the existing route templates already emit.

- WHILE these 24 values are in place THE SYSTEM SHALL leave the remaining five
  journal entries
  (`2026-09-10-add-portfolio-to-the-devloop-service-enums.md`,
  `2026-09-11-approach-page.md`,
  `2026-09-11-hero-name-in-the-reader-s-script.md`,
  `2026-09-11-home-page.md`,
  `2026-09-11-work-page.md`)
  and the remaining ADR
  (`0006-browser-verified-security-headers.md`)
  without a `seoTitle`; each already renders at or below 65 characters.

### C. Indexing

- WHEN `src/content.config.ts` is loaded THE SYSTEM SHALL accept
  `indexing: z.enum(['index', 'noindex']).default('index')` on the `journal`
  collection schema, and SHALL NOT add such a field to the `adr` schema: the
  six decision records are each substantive and all stay indexed.
- WHEN the journal content files are read THE SYSTEM SHALL find an explicit
  `indexing:` line in every one of the 24 entries.
- WHEN the journal content files are read THE SYSTEM SHALL find exactly these
  six entries carrying `indexing: index`:
  - `src/content/journal/2026-09-11-production-cutover.md`
  - `src/content/journal/2026-09-11-csp-hash-quoting-and-browser-verified-headers.md`
  - `src/content/journal/2026-09-11-metrics-provenance-and-no-analytics.md`
  - `src/content/journal/2026-09-10-base-layout-vendored-tokens-and-fonts.md`
  - `src/content/journal/2026-09-12-content-link-contrast-and-an-offline-link-check.md`
  - `src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`
- WHEN the journal content files are read THE SYSTEM SHALL find every other
  journal entry carrying `indexing: noindex`.
- WHEN the indexing test runs THE SYSTEM SHALL assert the split by reading the
  collection -- every entry declares an explicit value, every value is one of
  the two, the `index` set and the `noindex` set partition the collection with
  no overlap and no remainder, and the `index` set is non-empty -- and SHALL
  NOT assert a literal count that a future cycle would have to edit.
- WHEN a journal page whose entry is `noindex` is built THE SYSTEM SHALL emit
  `<meta name="robots" content="noindex,follow">` -- `follow`, not `none`, so
  the links out of the page stay useful -- and SHALL still emit its
  `<link rel="canonical">`, because the page remains the canonical copy of
  itself.
- WHEN a journal page whose entry is `index` is built THE SYSTEM SHALL emit no
  `robots` meta at all and SHALL be byte-identical in its head to what it is
  today apart from the additions in section D.
- WHILE an entry is `noindex` THE SYSTEM SHALL keep it published, linked from
  `/colophon/` and reachable at its own URL; only its sitemap entry and its
  index eligibility change.
- WHEN `npm run build` completes THE SYSTEM SHALL produce a
  `dist/sitemap-0.xml` containing one URL for each of the six `index` journal
  entries and for no `noindex` entry, alongside the existing `/`, `/work/`,
  `/approach/`, `/colophon/` and the six ADR pages.
- WHILE the sitemap filter is in force THE SYSTEM SHALL derive the excluded
  set from the journal collection's own files at build time and SHALL NOT
  contain a hand-typed list of paths -- the defect class `test/entry-point.test.ts`
  exists to prevent.
- WHEN `node scripts/check-dist.mjs` runs THE SYSTEM SHALL compare the built
  sitemap against an expected set derived independently from
  `src/content/journal` and `src/content/adr`, honouring `indexing`, so a
  missing indexed page and a leaked `noindex` page both fail there.

### D. Share image and structured data

- WHEN any page is built THE SYSTEM SHALL emit `<meta property="og:image:alt">`
  and `<meta name="twitter:image:alt">` whose content is exactly, in English on
  every page because the image itself is English and Latin:

  `Dmitrii Mashkov — platform engineering with AI on proven open source, dmitriimashkov.com`

  The em dash is U+2014 with one space on each side.
- WHEN `src/layouts/Base.astro` receives an optional `jsonLd` prop THE SYSTEM
  SHALL render exactly one `<script type="application/ld+json">` element
  carrying its JSON serialisation, and WHEN it receives no such prop THE SYSTEM
  SHALL render no such element.
- WHEN a journal page or an ADR page is built THE SYSTEM SHALL carry exactly
  one `BreadcrumbList` JSON-LD block with three `ListItem` entries -- Home at
  `/`, Colophon at `/colophon/`, and the current page at its own URL -- whose
  three names are built from the same values `src/components/Breadcrumb.astro`
  renders for its English half, so the two cannot drift.
- WHILE the JSON-LD is in place THE SYSTEM SHALL emit no `Person`, `WebSite`
  or `Article` entity: those carry owner facts this cycle does not have.
- WHEN `node scripts/check-dist.mjs` runs THE SYSTEM SHALL assert, for every
  built journal and ADR page, that there is exactly one
  `application/ld+json` block, that it parses, that its `@type` is
  `BreadcrumbList`, and that its three item names equal the three names read
  out of that same page's rendered `<nav class="breadcrumb">` English spans.
- WHEN `scripts/csp-hash.mjs` runs over the built tree THE SYSTEM SHALL print
  exactly one `'sha256-…'` token, unchanged from today, because
  `application/ld+json` is data and not script.
- WHEN the CSP test runs THE SYSTEM SHALL assert that the inline-script
  extraction used by `scripts/csp-hash.mjs` and `scripts/check-headers.mjs`
  ignores a `<script type="application/ld+json">` body while still capturing
  the executable inline script, and that `scriptSrcTokens` for the built
  output is unchanged in count.
- WHILE the JSON-LD is in place THE SYSTEM SHALL require no change to
  `security-headers.conf`, `nginx.conf` or the `script-src` directive.

### E. The 404 page

- WHEN `/404.html` is built THE SYSTEM SHALL carry, below the existing home
  link, two new links using two new `ui` keys with exactly this copy:
  - `notFoundWork` -- EN `See the work`, RU `Посмотреть работы` -- linking to
    `/work/`
  - `notFoundContact` -- EN `Get in touch`, RU `Написать` -- linking to
    `mailto:hello@dmitriimashkov.com`, the address
    `src/pages/index.astro` already uses in its contact block
- WHILE the two links are present THE SYSTEM SHALL keep `/404.html`
  `noindex` and bilingual exactly as it is today, with the `class="l en"` /
  `class="l ru"` pairs that `scripts/check-dist.mjs` counts for parity.

### F. Suite and gates

- WHEN `npm run vendor && npm test` runs THE SYSTEM SHALL pass, and any new
  test file SHALL be listed in the enumerated `test` script in `package.json`.
- WHEN `npm run build` runs THE SYSTEM SHALL succeed.
- WHEN `node scripts/check-dist.mjs` runs against the built tree THE SYSTEM
  SHALL exit zero.
- WHEN `node scripts/check-links.mjs` runs against the built tree THE SYSTEM
  SHALL exit zero, reporting the new `mailto:` href as skipped rather than as
  a failure.
- WHEN this cycle's work is committed THE SYSTEM SHALL include a new journal
  entry for it with `status: in_progress`, carrying `indexing` like every other
  entry, leaving closure of the previous entry to the existing closure
  workflow.

## Out of scope

- Compacting the mobile header. It is a layout decision that belongs with the
  navigation rework, not with this mechanical set, and it needs a browser
  measurement before and after.
- `Person` and `WebSite` structured data, the About block, hero copy, and
  anything else that states a fact about the owner. Those wait for the
  positioning cycle.
- Rewriting any journal entry into a reader-first article. Marking an entry
  `noindex` is not a judgement on its prose.
- Localized URLs, `hreflang`, and localized metadata. The one-URL model stands
  until its own decision cycle.
- Any change to `scripts/close-journal.mjs`, `.github/workflows/`, the journal
  lifecycle, or `AGENTS.md`.
- The five P3 findings still open on pull request #80.
- Any change to the visible wording or layout of any page other than the two
  new links on `/404.html`.
- Any change to the `script-src` CSP directive, `security-headers.conf` or
  `nginx.conf`.
- Measuring the rendered rectangles in a browser. That is a reviewer step (see
  below), not an acceptance criterion: the agent that must satisfy the criteria
  cannot run a browser.

## Reviewer steps (not acceptance criteria)

- Measure the actual rectangles of `.project-links a`, `.breadcrumb a`,
  `.journal-meta a` and `.table-scroll a` in a browser at 360px and 390px, in
  EN and in RU.
- Confirm the cycles table still scrolls horizontally and still shows its
  focus ring when the `.table-scroll` region is focused by keyboard.

## Open questions

- The issue states "Twenty-four rendered titles exceed 65 characters". Measured
  against the clone, 23 exceed 65 and
  `src/content/journal/2026-09-12-repository-links-out-of-the-disclosure.md`
  renders at exactly 65. That entry is nonetheless listed in the `seoTitle`
  table, so it receives its value; 24 entries gain a `seoTitle` either way and
  the acceptance criterion "no entry not listed gains one" is unaffected.
  Proceeding with the table as written.
- The issue's "files expected to change" list does not name
  `scripts/check-dist.mjs` or `src/lib/csp.ts`, but both must change for the
  acceptance criteria to hold: `checkSitemap()` in `check-dist.mjs` derives its
  expected sitemap URL set from one page per public journal entry and would
  report eighteen "sitemap is missing expected URL" problems the moment the
  filter excludes them, and `INLINE_SCRIPT_RE` in `src/lib/csp.ts` matches any
  `<script>` without a `src=` attribute, which includes
  `<script type="application/ld+json">`, so `scripts/csp-hash.mjs` would report
  two distinct inline bodies and fail. The list is "expected", not exhaustive;
  proceeding with both changes, scoped narrowly as described in `design.md`.
- The issue asks for both "a test asserts the split by reading the collection"
  and an exact six-entry list. A test that hard-codes the six ids would be the
  literal the criterion forbids. Proceeding with: the test asserts the
  structural invariants (explicit value on every entry, valid enum, clean
  partition, non-empty `index` set) while the six named entries are content in
  the files themselves, and `scripts/check-dist.mjs` proves the sitemap matches
  whatever the files say.
- `Base.astro`'s existing `noindex` boolean prop both emits
  `<meta name="robots" content="noindex">` and suppresses the canonical link.
  A `noindex` journal page needs `noindex,follow` *and* a canonical, so the
  two cases cannot share one boolean. Proceeding with a second, optional
  `robots?: string` prop that leaves the canonical in place, keeping the
  existing `noindex` boolean for `/404.html` untouched.
