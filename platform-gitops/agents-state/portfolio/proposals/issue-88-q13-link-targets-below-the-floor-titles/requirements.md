# Q13: link hit areas, search titles, journal indexing, share-image alt

## Context

An external UX audit of https://dmitriimashkov.com/ dated 2026-09-13 measured
four mechanical defects on production 0.1.23 and against `main` at `41dc023`+.
None of them needs a copy decision from the owner, and none of them changes
wording or layout beyond two new links on the 404 page.

1. **Standalone links are below the target-size floor and the guard cannot see
   them.** `test/a11y.test.ts:22` checks `min-block-size` on six selectors only
   (`'.site-nav a'`, `'.toggle-group button'`, `'.site-footer a'`, `'.cta'`,
   `'.block > summary'`, `'.skip-link:focus'`). `src/styles/site.css` sets
   `min-block-size: 44px` on those six and nothing on the standalone links
   outside that list: the repository and Docs links on `/work/`
   (`.project-links a`, `src/components/ProjectCard.astro`), the issue and
   pull-request links in the journal meta list (`.journal-meta a`,
   `src/pages/colophon/journal/[...slug].astro`), the breadcrumb links
   (`.breadcrumb a`, `src/components/Breadcrumb.astro`), and the links inside
   the cycles and ADR tables (`.table-scroll a`,
   `src/components/CycleTable.astro`, `src/pages/colophon/index.astro`). The
   audit measured 17-20px on those. The suite is green while the links are
   half the floor.
2. **Rendered titles run past what a search result shows.** The journal route
   renders `` `${data.title.en} — Dmitrii Mashkov` `` and the ADR route
   `` `ADR-${padAdrId(entry.data.id)}: ${entry.data.title.en} — Dmitrii Mashkov` ``,
   with no length budget anywhere. The longest is 129 characters
   (`2026-09-12-symlink-safe-check-no-metrics-entry-guard.md` measures 127 in
   the committed tree; the audit measured 129 on production 0.1.23).
   `test/seo.test.ts` exercises `clampDescription` and asserts nothing about
   titles. An editorial H1 and a search-result title are different jobs; the
   page needs both.
3. **Every raw operational entry is indexable.** All 24 journal entries appear
   in `dist/sitemap-0.xml`. Most are internal build notes of 96-200 words --
   correct as a public record, wrong as an answer to a search. Nothing in
   `src/content.config.ts` can say so.
4. **The share image has no alternative text and no page carries structured
   data.** `src/layouts/Base.astro` emits `og:image` and `twitter:image` with
   no `og:image:alt` or `twitter:image:alt`, and emits no JSON-LD of any kind.

This proposal gives every standalone link a hit area the test can actually see,
gives long pages a short search title without touching their headings, lets an
entry say whether it is written for a reader or for the record, and describes
the share image.

## User stories

- AS a reader on a 360px-wide phone I WANT every standalone link -- repository
  links, breadcrumb links, journal issue and pull-request links, links inside
  the colophon tables -- to have a hit area of at least 24px SO THAT I can tap
  the one I meant instead of the one next to it.
- AS a maintainer I WANT the accessibility test to enumerate every class of
  standalone link SO THAT a link half the floor cannot ship behind a green
  suite.
- AS a person searching for this site I WANT a page's title in the result to
  read as a complete label rather than a truncated sentence SO THAT I can tell
  what the page is before I open it.
- AS the site owner I WANT an entry's `<h1>` and its `<title>` to be allowed to
  differ SO THAT an editorial heading is not forced to be a filing label.
- AS a person searching for how this platform works I WANT the six journal
  entries that answer a question to be indexed and the eighteen raw build notes
  not to be SO THAT the index carries answers rather than logs.
- AS a maintainer I WANT a `noindex` entry to stay published, linked from the
  colophon and reachable SO THAT the public record is unbroken while the index
  is not polluted.
- AS someone who sees this site shared on a social platform with images off, or
  who reads it through a screen reader, I WANT the share image described SO
  THAT the card still carries meaning.
- AS a search engine I WANT a `BreadcrumbList` on every journal and ADR page SO
  THAT the result shows where the page sits in the site.
- AS a reader who lands on a missing URL I WANT a link to the work and a way to
  get in touch SO THAT the 404 is a fork in the road rather than a dead end.

## Acceptance criteria (EARS)

### A. Hit areas

- WHEN `src/styles/site.css` is read THE SYSTEM SHALL declare a
  `min-block-size` of at least `24px`, together with `display: inline-flex` and
  `align-items: center`, for each of `.project-links a`, `.breadcrumb a`,
  `.journal-meta a` and `.table-scroll a`, in the same grouped-rule shape the
  existing six selectors already use.
- WHILE those four rules are in force THE SYSTEM SHALL leave `main a` -- a link
  inside a sentence of prose -- untouched: this change covers standalone links
  only, and no rule may turn an inline sentence link into a block.
- WHEN `test/a11y.test.ts` runs THE SYSTEM SHALL check all ten selectors --
  `.site-nav a`, `.toggle-group button`, `.site-footer a`, `.cta`,
  `.block > summary`, `.skip-link:focus`, `.project-links a`, `.breadcrumb a`,
  `.journal-meta a` and `.table-scroll a` -- keeping the existing assertion
  shape: at least one rule block whose comma-separated selector list contains
  the exact selector sets `min-block-size`, and every such declaration is at or
  above the 24px floor.
- IF any of the ten selectors declares a `min-block-size` below `24px` THEN THE
  SYSTEM SHALL fail `test/a11y.test.ts`, and the test file SHALL itself contain
  a recorded mutation -- the same matcher run over a synthetic stylesheet whose
  declaration is below the floor, asserted to report a problem -- so the guard
  is proven to discriminate rather than merely to pass.
- WHILE the four new rules are in force THE SYSTEM SHALL introduce no
  `min-width`, no fixed `height`/`block-size`, and no change to
  `.table-scroll`'s focusable region (`role="region"`, `tabindex="0"`,
  `:focus-visible` outline) or to its `@media (max-width: 599px)`
  `.table-scroll::after` scroll hint.
- WHILE the four new rules are in force THE SYSTEM SHALL declare no
  `animation` or `transition` anywhere in `src/styles/site.css`, so the
  existing assertion in `test/a11y.test.ts` continues to hold.

### B. Short search titles

- WHEN `src/content.config.ts` is loaded THE SYSTEM SHALL accept an optional
  `seoTitle: z.string().min(1)` on the `journal` schema and on the `adr`
  schema. It is a complete `<title>` string, Latin, one per entry, not
  bilingual -- a browser tab is a filing label, exactly as `AGENTS.md` already
  says of `homeTitle`.
- WHEN a journal or ADR entry carries `seoTitle` THE SYSTEM SHALL render that
  string as the page `<title>` (and therefore as `og:title` and
  `twitter:title`, which `Base.astro` derives from the same `title` prop).
- IF an entry carries no `seoTitle` THEN THE SYSTEM SHALL render the current
  template unchanged: `` `${data.title.en} — Dmitrii Mashkov` `` for a journal
  entry, `` `ADR-${padAdrId(entry.data.id)}: ${entry.data.title.en} — Dmitrii Mashkov` ``
  for an ADR.
- WHILE `seoTitle` is present THE SYSTEM SHALL leave the page's `<h1>` and its
  breadcrumb current-item unchanged: the journal `<h1>` keeps its
  `title.en`/`title.ru` `<Lang>` pair, the ADR `<h1>` keeps
  `ADR-{padAdrId(id)}: ` plus its `title.en`/`title.ru` pair, and the
  breadcrumb keeps `currentEn`/`currentRu` exactly as today.
- WHEN `src/lib/seo.ts` is imported THE SYSTEM SHALL export
  `titleProblems(title, { warn = 65, fail = 75 })` returning a list of problem
  strings.
- WHEN `titleProblems` is given a title of exactly 65 characters THE SYSTEM
  SHALL return an empty list.
- WHEN `titleProblems` is given a title of 66 characters THE SYSTEM SHALL
  return exactly one problem, a warning whose message names the actual length.
- WHEN `titleProblems` is given a title of 76 characters THE SYSTEM SHALL
  return a failure-level problem.
- WHEN the title test runs THE SYSTEM SHALL compute, for every journal entry
  and every ADR entry, the title the route actually renders -- through the same
  shared helper the route calls, not a hand-typed list -- and SHALL assert that
  none of them exceeds 75 characters.
- WHILE a page's rendered title exceeds 65 characters THE SYSTEM SHALL require
  that page to carry a `seoTitle`; a page may exceed 65 only by carrying one.
- WHEN the content files are read THE SYSTEM SHALL find exactly these 24
  `seoTitle` values, character for character, one on each named entry, and on
  no other entry:

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

- WHILE those 24 are the only entries carrying `seoTitle` THE SYSTEM SHALL
  leave every other entry on its generated title. The five unlisted journal
  entries (`2026-09-11-hero-name-in-the-reader-s-script.md` 61 chars,
  `2026-09-10-add-portfolio-to-the-devloop-service-enums.md` 60,
  `2026-09-11-work-page.md` 48, `2026-09-11-approach-page.md` 31,
  `2026-09-11-home-page.md` 27) and the unlisted ADR
  (`0006-browser-verified-security-headers.md` 61) each already render at or
  below 65.
- WHEN this cycle's own new journal entry is written THE SYSTEM SHALL give it a
  `title.en` of at most 47 characters, so its generated title (`title.en` plus
  the 18-character suffix `" — Dmitrii Mashkov"`) is at or below 65 and it
  needs no `seoTitle` of its own -- no entry outside the 24 above may gain one.

### C. Indexing

- WHEN `src/content.config.ts` is loaded THE SYSTEM SHALL accept
  `indexing: z.enum(['index', 'noindex']).default('index')` on the `journal`
  schema only.
- WHILE the `adr` schema is unchanged in this respect THE SYSTEM SHALL give
  ADRs no `indexing` field: the six decision records are each substantive and
  all stay indexed.
- WHEN the journal content files are read THE SYSTEM SHALL find an explicit
  `indexing:` key in the frontmatter of every journal entry, with exactly these
  values:

| file | `indexing` |
|---|---|
| `2026-09-10-add-portfolio-to-the-devloop-service-enums.md` | `noindex` |
| `2026-09-10-astro-static-skeleton-and-nginx-image.md` | `noindex` |
| `2026-09-10-base-layout-vendored-tokens-and-fonts.md` | `index` |
| `2026-09-10-register-portfolio-as-a-devloop-service.md` | `noindex` |
| `2026-09-11-approach-page.md` | `noindex` |
| `2026-09-11-content-collections.md` | `noindex` |
| `2026-09-11-csp-hash-quoting-and-browser-verified-headers.md` | `index` |
| `2026-09-11-hero-name-in-the-reader-s-script.md` | `noindex` |
| `2026-09-11-home-page.md` | `noindex` |
| `2026-09-11-metrics-provenance-and-no-analytics.md` | `index` |
| `2026-09-11-p8-production-hardening-accessibility-wc.md` | `noindex` |
| `2026-09-11-production-cutover.md` | `index` |
| `2026-09-11-work-page.md` | `noindex` |
| `2026-09-12-backfilling-five-omitted-journal-entries.md` | `noindex` |
| `2026-09-12-colophon-tables-and-computed-lead-time.md` | `noindex` |
| `2026-09-12-content-link-contrast-and-an-offline-link-check.md` | `index` |
| `2026-09-12-navigation-state-and-accessibility-affordances.md` | `noindex` |
| `2026-09-12-q7-polish-wave-findings.md` | `noindex` |
| `2026-09-12-q9-six-review-findings.md` | `noindex` |
| `2026-09-12-repository-links-out-of-the-disclosure.md` | `noindex` |
| `2026-09-12-share-image-font-preload-cache-lifetime.md` | `noindex` |
| `2026-09-12-symlink-safe-check-no-metrics-entry-guard.md` | `noindex` |
| `2026-09-13-journal-lifecycle-and-release-closure.md` | `index` |
| `2026-09-13-journal-tests-assert-invariants-only.md` | `noindex` |

  That is six `index` and eighteen `noindex` across the 24 entries committed
  today. This cycle's own new entry is a build note and carries
  `indexing: noindex`, making nineteen `noindex` in the tree the implementer
  commits.
- WHEN the indexing split is tested THE SYSTEM SHALL read the collection and
  assert that the set of `index` ids is exactly the six named above and that
  every other journal entry is `noindex` -- never a hard-coded total that a
  future cycle must edit.
- WHEN a `noindex` journal page is built THE SYSTEM SHALL emit
  `<meta name="robots" content="noindex,follow">` -- follow, not none: the
  links out of it stay useful -- and SHALL still emit its
  `<link rel="canonical">`, since the page is still the canonical copy of
  itself.
- WHEN an `index` journal page is built THE SYSTEM SHALL emit no robots meta at
  all and SHALL be byte-identical to today's output in every other respect.
- WHILE an entry is `noindex` THE SYSTEM SHALL keep it published: its page is
  still generated, still linked from `/colophon/`, still reachable, and still
  counted in the colophon's cycle table and totals. It leaves the index only.
- WHEN `astro.config.mjs` builds the sitemap THE SYSTEM SHALL exclude the
  `noindex` journal pages alongside `/404` and `/dev/`, deriving the excluded
  set from the journal collection at build time rather than from a hand-typed
  path list -- the defect class `test/entry-point.test.ts` already exists to
  prevent.
- WHEN `dist/sitemap-0.xml` is checked THE SYSTEM SHALL contain the six indexed
  journal pages and no `noindex` one, with the expectation derived from the
  collection.

### D. Share image and structured data

- WHEN any page is built THE SYSTEM SHALL emit `og:image:alt` and
  `twitter:image:alt` in English, on every page, with exactly this text,
  because the image itself is English and Latin:

  `Dmitrii Mashkov — platform engineering with AI on proven open source, dmitriimashkov.com`

- WHEN `src/layouts/Base.astro` is given an optional `jsonLd` prop THE SYSTEM
  SHALL render exactly one `<script type="application/ld+json">` element
  carrying it, and WHEN the prop is absent THE SYSTEM SHALL render nothing.
- WHEN a journal or ADR page is built THE SYSTEM SHALL carry exactly one
  `BreadcrumbList` JSON-LD block with three items -- Home (`/`), Colophon
  (`/colophon/`) and the current page -- whose names are built from the same
  values `src/components/Breadcrumb.astro` renders, so the visible breadcrumb
  and the structured data cannot drift.
- WHILE this cycle is in scope THE SYSTEM SHALL emit no `Person`, `WebSite` or
  `Article` entity: those carry owner facts this cycle does not have.
- WHEN `scripts/csp-hash.mjs` runs over the built output THE SYSTEM SHALL still
  print exactly one `'sha256-...'` token: `application/ld+json` is a data
  block, not script, and CSP `script-src` does not apply to it.
- WHEN the CSP test runs THE SYSTEM SHALL assert that the built journal and ADR
  pages contain the JSON-LD block and that the count of hash tokens
  `scriptSrcTokens` yields for the built output is unchanged at one.
- IF a `<script>` element carries a non-JavaScript `type` (a data block such as
  `application/ld+json`) THEN THE SYSTEM SHALL exclude it from
  `extractInlineScripts` in `src/lib/csp.ts`, so neither `scripts/csp-hash.mjs`
  nor `scripts/check-headers.mjs` treats it as an inline script needing a hash.
- WHILE the security headers are unchanged THE SYSTEM SHALL require no edit to
  `security-headers.conf` or `nginx.conf` for the JSON-LD.

### E. The 404 page

- WHEN `/404.html` is built THE SYSTEM SHALL carry, below the existing home
  link, two further links using new `ui` keys with exactly this copy:

| key | EN | RU | href |
|---|---|---|---|
| `notFoundWork` | `See the work` | `Посмотреть работы` | `/work/` |
| `notFoundContact` | `Get in touch` | `Написать` | `mailto:hello@dmitriimashkov.com` |

  `mailto:hello@dmitriimashkov.com` is the address the home page's contact
  block already uses (`src/pages/index.astro:58`).
- WHILE the two links are added THE SYSTEM SHALL keep `/404.html` `noindex`
  (the existing `noindex` prop on `Base.astro`) and bilingual, with each new
  link rendered through `<Lang>` so the `class="l en"` / `class="l ru"` parity
  `scripts/check-dist.mjs` enforces still holds.
- WHILE `notFoundWork` exists THE SYSTEM SHALL NOT reuse the existing
  `ctaWork` key: `ctaWork` is `{ en: 'See the work', ru: 'Смотреть работы' }`
  and the Russian side differs from `notFoundWork`'s
  `Посмотреть работы`.

### F. Cycle hygiene

- WHEN the build runs THE SYSTEM SHALL pass `npm run vendor && npm test`,
  `npm run build`, `node scripts/check-dist.mjs` and
  `node scripts/check-links.mjs`.
- WHILE any new test file exists THE SYSTEM SHALL list it in the enumerated
  `test` script in `package.json`.
- WHEN this cycle is implemented THE SYSTEM SHALL write its own journal entry
  under `src/content/journal/` with `status: in_progress`; the closure workflow
  closes the previous one as usual. No journal entry currently carries
  `status: in_progress`, so the one-cycle-at-a-time guard in
  `checkJournalCollection` is satisfied by adding exactly one.

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
- Changing `main a` (prose links inside a paragraph), or adding a hit-area
  floor to any selector beyond the four named in section A.
- Changing `public/og.svg` or `scripts/render-og.mjs`: the alt text describes
  the existing image, it does not redraw it.
- Changing `security-headers.conf`, `nginx.conf` or the CSP header value.
- Removing any journal entry from the site, from `/colophon/`, from the cycle
  table or from the totals. `noindex` affects the index, nothing else.

## Reviewer steps (not acceptance criteria)

- Measure the actual rendered rectangles of the four link classes in a browser
  at 360px and 390px, in EN and in RU.
- Confirm the cycles table still scrolls sideways and keeps its focus ring.

## Open questions

- The issue's heading for section 2 says "Twenty-four rendered titles exceed 65
  characters". Measured in the committed tree at `main`, 23 pages render a
  title strictly above 65: 18 journal entries and 5 ADRs. The 24th row in the
  `seoTitle` table, `2026-09-12-repository-links-out-of-the-disclosure.md`,
  renders at exactly 65 -- at the budget, not over it. The table is
  authoritative and the count is not: apply all 24 values as written. The entry
  at exactly 65 gains a `seoTitle` too, which is harmless and satisfies "all 24
  present, no unlisted entry gains one".
- Acceptance criterion 4 in the issue reads "exactly the six in C.11 are
  `index` and the other eighteen `noindex`". This cycle's own new journal entry
  makes it nineteen others. Proceeding with the derived form the same criterion
  demands ("a test asserts the split by reading the collection, not a literal
  count that a future cycle must edit"): the test asserts the `index` set
  equals the six named ids and that every other entry is `noindex`.
- The issue does not name this cycle's journal entry title. Since no unlisted
  entry may gain a `seoTitle`, the new entry's `title.en` must fit the 47-char
  budget. Proceeding with
  `title.en: "Q13: hit areas, titles, indexing, image alt"` (43 chars, renders
  at 61) and `title.ru: "Q13: зоны нажатия, заголовки, индексация, alt изображения"`.
  The implementer may choose different wording provided `title.en` stays at or
  below 47 characters.
- The issue asserts that JSON-LD needs no CSP change. That is true of the
  header, and false of this repository's tooling as written:
  `INLINE_SCRIPT_RE` in `src/lib/csp.ts` matches any `<script>` without a
  `src=` attribute, which includes `type="application/ld+json"`. Left alone,
  `scripts/csp-hash.mjs` would see two distinct inline bodies and fail the
  build, and `scripts/check-headers.mjs` would report a stale hash against
  production. Proceeding by narrowing `extractInlineScripts` to JavaScript
  script elements, which is what "the header needs no change" actually
  requires. See `design.md`.
- The issue's file list does not mention `scripts/check-dist.mjs`, but
  `checkSitemap()` there asserts the sitemap equals the closure of every
  *public* journal and ADR page and reports "sitemap contains unexpected URL" /
  "sitemap is missing expected URL" on any difference. Excluding the eighteen
  `noindex` pages therefore fails that gate unless the same script learns the
  `indexing` field. Proceeding by extending it; this is also where acceptance
  criteria 5, 6, 7 and 8 are proven against real built output.
