# Tasks: issue-88-q13-link-targets-below-the-floor-titles

Order matters where noted. Every task is satisfiable by a commit; nothing here
asks for a note in the pull request description.

## A. Hit areas

- [ ] 1. Add one grouped rule block to `src/styles/site.css`, next to the
  existing "Tap targets" block (currently around line 494), covering
  `.project-links a`, `.breadcrumb a`, `.journal-meta a` and `.table-scroll a`
  with `display: inline-flex; align-items: center; min-block-size: 24px;` and a
  comment naming issue #88 and why prose links (`main a`) are excluded.
  — DoD: the four selectors each appear as an exact member of a comma-separated
  selector list on a block that declares `min-block-size: 24px`; no
  `min-width`, no fixed `height`/`block-size`, no `animation`, no `transition`
  is added anywhere in the file; `.table-scroll`'s `overflow-x: auto`,
  `:focus-visible` outline and the `@media (max-width: 599px)`
  `.table-scroll::after` block are byte-identical to `main`.

- [ ] 2. Refactor `test/a11y.test.ts`'s inline rule matcher into a named
  `minBlockSizeProblems(css, selector, floor): string[]` that returns problem
  strings instead of asserting (same shape as `entryPointProblems()` in
  `test/entry-point.test.ts`), and extend `TARGET_SELECTORS` from six to the ten
  selectors: `.site-nav a`, `.toggle-group button`, `.site-footer a`, `.cta`,
  `.block > summary`, `.skip-link:focus`, `.project-links a`, `.breadcrumb a`,
  `.journal-meta a`, `.table-scroll a`. (depends on 1)
  — DoD: ten per-selector cases, each
  `assert.deepEqual(minBlockSizeProblems(siteCss, selector, MIN_TARGET_PX), [])`;
  `MIN_TARGET_PX` stays 24; every other test in the file is unchanged and still
  passes.

- [ ] 3. Add two mutation cases to `test/a11y.test.ts`, over synthetic
  stylesheet string literals declared in the test file. (depends on 2)
  — DoD: case one feeds a synthetic stylesheet whose block for the selector
  declares `min-block-size: 20px` and asserts `minBlockSizeProblems` returns a
  non-empty list whose joined message names `20` and the selector; case two
  feeds a synthetic stylesheet whose block for the selector declares no
  `min-block-size` and asserts the returned list names the missing rule. Both
  run under `npm test`.

## B. Short search titles

- [ ] 4. Add `titleProblems(title, { warn = 65, fail = 75 } = {}): string[]` to
  `src/lib/seo.ts`, counting code points (`[...title].length`), returning `[]`
  at or below `warn`, one `warning:` problem naming the measured length and
  `warn` above `warn` up to `fail`, and one `failure:` problem naming the
  measured length and `fail` above `fail`. Keep the module zero-import except
  for `padAdrId` in task 5.
  — DoD: `titleProblems('x'.repeat(65))` is `[]`; `titleProblems('x'.repeat(66))`
  has exactly one problem containing `66` and `65`; `titleProblems('x'.repeat(75))`
  reports no failure; `titleProblems('x'.repeat(76))` reports a failure
  containing `76` and `75`.

- [ ] 5. Add `journalPageTitle(data)` and `adrPageTitle(data)` to
  `src/lib/seo.ts`, holding the two templates and the `seoTitle ?? template`
  precedence, with `padAdrId` imported from `src/lib/adr.ts` so no id format is
  retyped. (depends on 4)
  — DoD: `journalPageTitle({ title: { en: 'X' } })` returns
  `X — Dmitrii Mashkov`; `adrPageTitle({ id: 3, title: { en: 'X' } })` returns
  `ADR-0003: X — Dmitrii Mashkov`; each returns `data.seoTitle` verbatim when
  present. Em dash is U+2014 with one space either side.

- [ ] 6. Add `seoTitle: z.string().min(1).optional()` to the `journal` schema
  and to the `adr` schema in `src/content.config.ts`.
  — DoD: `npm run check` (`astro sync && astro check`) passes; an entry
  carrying `seoTitle` validates; both schemas remain `strictObject`.

- [ ] 7. Change `src/pages/colophon/journal/[...slug].astro` to
  `title={journalPageTitle(data)}` and
  `src/pages/colophon/adr/[...slug].astro` to
  `title={adrPageTitle(entry.data)}`. (depends on 5, 6)
  — DoD: no inline title template string remains in either route; the `<h1>`
  and the `<Breadcrumb currentEn … currentRu …>` props are unchanged.

- [ ] 8. Write the 24 `seoTitle` values from `requirements.md` section B into
  their named content files, one `seoTitle:` frontmatter line each, character
  for character. (depends on 6)
  — DoD: all 24 named files carry their exact value; the five unlisted journal
  entries
  (`2026-09-10-add-portfolio-to-the-devloop-service-enums.md`,
  `2026-09-11-approach-page.md`,
  `2026-09-11-hero-name-in-the-reader-s-script.md`,
  `2026-09-11-home-page.md`,
  `2026-09-11-work-page.md`)
  and `src/content/adr/0006-browser-verified-security-headers.md` carry none;
  every value is 60 code points or fewer.

- [ ] 9. Add `scripts/check-dist.mjs` coverage for built titles: inside
  `checkColophonPages()`'s existing per-file loop, for a journal or ADR page,
  extract `<title>…</title>` and report a problem if its code-point length
  exceeds 75. (depends on 7)
  — DoD: the check names the file and the measured length; `node scripts/check-dist.mjs`
  exits zero after `npm run build`.

## C. Indexing

- [ ] 10. Add `src/lib/indexing.ts` exporting `INDEXING_RE`,
  `indexingFromFrontmatter(text)`, `noindexJournalIds(dir)` and
  `noindexJournalPaths(dir)` (returning `/colophon/journal/<id>/`), zero-import
  apart from `node:fs` and `node:path`, importable from `astro.config.mjs`,
  `scripts/*.mjs` and `node --test`.
  — DoD: `noindexJournalIds('./src/content/journal')` returns the sorted ids of
  every entry whose frontmatter declares `indexing: noindex`, and an empty
  array for a directory with none.

- [ ] 11. Add `indexing: z.enum(['index', 'noindex']).default('index')` to the
  `journal` schema in `src/content.config.ts`. Do not add it to `adr`.
  — DoD: `npm run check` passes; the `adr` schema is unchanged.

- [ ] 12. Write `indexing:` into all 24 journal entries: `index` on exactly the
  six named in `requirements.md` section C
  (`2026-09-11-production-cutover.md`,
  `2026-09-11-csp-hash-quoting-and-browser-verified-headers.md`,
  `2026-09-11-metrics-provenance-and-no-analytics.md`,
  `2026-09-10-base-layout-vendored-tokens-and-fonts.md`,
  `2026-09-12-content-link-contrast-and-an-offline-link-check.md`,
  `2026-09-13-journal-lifecycle-and-release-closure.md`),
  `noindex` on the other eighteen. (depends on 11)
  — DoD: every journal file has exactly one anchored `indexing:` line; the
  `index` set is exactly those six.

- [ ] 13. Add the optional `robots?: string` prop to `src/layouts/Base.astro`,
  rendering `<meta name="robots" content={robots} />` alongside the canonical
  link in the non-`noindex` branch. Leave the existing `noindex` boolean branch
  exactly as it is.
  — DoD: a page passing neither prop renders a canonical and no robots meta; a
  page passing `robots="noindex,follow"` renders both; `/404.astro`'s output is
  unchanged apart from task 19's two links.

- [ ] 14. Pass `robots={data.indexing === 'noindex' ? 'noindex,follow' : undefined}`
  from `src/pages/colophon/journal/[...slug].astro`. Leave the ADR route
  without a robots prop. (depends on 11, 13)
  — DoD: a built `noindex` journal page contains
  `<meta name="robots" content="noindex,follow">` and a
  `<link rel="canonical">`; a built `index` journal page contains neither a
  robots meta nor any other head change; every built ADR page contains no
  robots meta.

- [ ] 15. Change the sitemap `filter` in `astro.config.mjs` to also exclude
  every path returned by `noindexJournalPaths('./src/content/journal')`,
  computed once at config load. Keep the `/404` and `/dev/` exclusions and their
  comment. (depends on 10, 12)
  — DoD: no hand-typed journal path appears in `astro.config.mjs`;
  `dist/sitemap-0.xml` after `npm run build` contains the six indexed journal
  URLs and none of the eighteen.

- [ ] 16. Update `checkSitemap()` in `scripts/check-dist.mjs` to subtract the
  `noindex` ids (via `src/lib/indexing.ts`) from its expected journal URL set,
  and add a per-page robots/canonical check to `checkColophonPages()` matching
  task 14. (depends on 10, 14, 15)
  — DoD: `node scripts/check-dist.mjs` exits zero after `npm run build`; both
  directions of the sitemap comparison still fire (flipping one entry's
  `indexing` without rebuilding makes it fail).

## D. Share image alt and structured data

- [ ] 17. In `src/layouts/Base.astro`, declare the alt string once in the
  frontmatter and emit `<meta property="og:image:alt">` after `og:image` and
  `<meta name="twitter:image:alt">` after `twitter:image`, with exactly:
  `Dmitrii Mashkov — platform engineering with AI on proven open source, dmitriimashkov.com`
  — DoD: every built page carries both metas with that exact string (em dash
  U+2014, one space either side); the literal appears once in the source.

- [ ] 18. Narrow `INLINE_SCRIPT_RE` in `src/lib/csp.ts` so a
  `<script type="application/ld+json">` element is not captured, and add three
  cases to `test/csp.test.ts`: `extractInlineScripts` skips a `ld+json` body,
  still captures the executable inline script when both are present, and
  `staleHashProblems` returns `[]` for a fixture carrying both. (do before 20)
  — DoD: `npm test` passes; every existing `test/csp.test.ts` case still passes
  unmodified; `scripts/csp-hash.mjs` and `scripts/check-headers.mjs` are not
  edited.

- [ ] 19. Add `breadcrumbJsonLd(site, items)` to `src/lib/seo.ts` returning a
  `BreadcrumbList` with `position` 1..n, `name` and absolute-URL `item`.
  — DoD: called with three items it returns
  `@context: 'https://schema.org'`, `@type: 'BreadcrumbList'` and three
  `ListItem` entries; a unit case in `test/title.test.ts` (or `test/seo.test.ts`)
  asserts the shape.

- [ ] 20. Add the optional `jsonLd` prop to `src/layouts/Base.astro`, rendering
  exactly one `<script type="application/ld+json" set:html={JSON.stringify(jsonLd).replace(/</g, '\\u003c')} />`
  when given and nothing when not; pass a three-item `BreadcrumbList` from the
  journal and ADR routes, built from the same `currentEn` variable already
  handed to `<Breadcrumb>` and from `ui.navHome.en` / `ui.navColophon.en`.
  (depends on 18, 19)
  — DoD: built journal and ADR pages carry exactly one `application/ld+json`
  block; no other page carries one; `node scripts/csp-hash.mjs` prints exactly
  one `'sha256-…'` token; no `Person`, `WebSite` or `Article` entity appears
  anywhere.

- [ ] 21. Add `checkJsonLd()` to `scripts/check-dist.mjs`, called from the
  existing journal/ADR branch of `checkColophonPages()` next to
  `checkBreadcrumb()`. (depends on 20)
  — DoD: it asserts exactly one `application/ld+json` block per page, that it
  `JSON.parse`s, `@type === 'BreadcrumbList'`, three items at positions 1,2,3,
  and that the three `name` values equal the three names read out of that same
  page's `<nav class="breadcrumb">` English spans; `node scripts/check-dist.mjs`
  exits zero.

## E. The 404 page

- [ ] 22. Add `notFoundWork: { en: 'See the work', ru: 'Посмотреть работы' }`
  and `notFoundContact: { en: 'Get in touch', ru: 'Написать' }` to
  `src/i18n/ui.ts`, next to `notFoundHome`.
  — DoD: `test/ui.test.ts`'s existing every-key test passes; a new exact-value
  case asserts both keys character for character in both languages.

- [ ] 23. Add two paragraphs to `src/pages/404.astro` below the existing home
  link: `<a href="/work/">` with `notFoundWork` and
  `<a href="mailto:hello@dmitriimashkov.com">` with `notFoundContact`, both
  through `<Lang en ru />`. (depends on 22)
  — DoD: `/404.html` carries both hrefs and all four strings; it still carries
  `<meta name="robots" content="noindex">`; its `class="l en"` and
  `class="l ru"` counts remain equal; `node scripts/check-links.mjs` reports
  the `mailto:` as skipped, not failed.

- [ ] 24. Add a `/404.html` check to `scripts/check-dist.mjs` covering both new
  hrefs, both EN strings and the surviving robots meta. (depends on 23)
  — DoD: `node scripts/check-dist.mjs` exits zero and fails if either link is
  removed.

## F. Suite, journal and gates

- [ ] 25. Add `test/title.test.ts` and `test/indexing.test.ts` to the
  enumerated `test` script in `package.json`. (depends on 26, 27)
  — DoD: both files appear in the `node --test` argument list; `npm test` runs
  them.

- [ ] 26. Write `test/title.test.ts`: the four `titleProblems` behaviours from
  task 4; a scan of `src/content/journal/*.md` and `src/content/adr/*.md` that
  extracts `title.en`, `seoTitle` and (ADR) `id` with anchored regexes, feeds
  them through `journalPageTitle` / `adrPageTitle` — the same functions the
  routes call — and asserts no computed title exceeds 75 code points; and an
  assertion that every entry whose computed title exceeds 65 carries a
  `seoTitle`. (depends on 5, 8)
  — DoD: no hand-typed list of titles appears in the file; the test fails if a
  `seoTitle` is deleted from a long entry.

- [ ] 27. Write `test/indexing.test.ts`: every journal entry declares an
  explicit `indexing` value; every value is `index` or `noindex`; the two sets
  partition the collection with no overlap and no remainder; the `index` set is
  non-empty; `noindexJournalPaths()` returns exactly one
  `/colophon/journal/<id>/` per `noindex` entry. (depends on 10, 12)
  — DoD: no literal count of six or eighteen appears in the file; the test
  fails if an entry's `indexing` line is deleted.

- [ ] 28. Add this cycle's journal entry,
  `src/content/journal/2026-09-13-<slug>.md`, with `status: in_progress`,
  `service: portfolio`, the issue URL, `proposal_slug:
  issue-88-q13-link-targets-below-the-floor-titles`, `visibility: public`,
  bilingual `title` and `decided`, `issue_opened_at`, and `indexing` like every
  other entry. Do not close the previous entry; the closure workflow does that.
  (depends on 11)
  — DoD: `checkJournalCollection` still sees at most one `in_progress` entry;
  `npm run check` passes; `scripts/check-dist.mjs`'s cycle count and row count
  agree with the file count.

- [ ] 29. Run the full gate chain and fix what it reports. (depends on all)
  — DoD: `npm run vendor && npm test` passes; `npm run build` succeeds;
  `node scripts/check-dist.mjs` exits zero; `node scripts/check-links.mjs`
  exits zero; `node scripts/csp-hash.mjs` prints exactly one token;
  `git diff --exit-code -- public/assets src/data/assets.json` is clean.

## Tests

- [ ] T1. `test/a11y.test.ts` — ten per-selector `min-block-size >= 24px` cases
  plus the two recorded mutation cases (20px, and no declaration at all).
- [ ] T2. `test/title.test.ts` — `titleProblems` at 65/66/75/76; every journal
  and ADR page's route-computed title at or below 75; any title over 65 carries
  a `seoTitle`.
- [ ] T3. `test/indexing.test.ts` — explicit value on every journal entry, valid
  enum, clean partition, non-empty `index` set, one excluded sitemap path per
  `noindex` entry, no literal counts.
- [ ] T4. `test/csp.test.ts` — `extractInlineScripts` skips
  `application/ld+json` and still captures the executable inline script;
  `staleHashProblems` returns `[]` for a mixed fixture; all existing cases
  unchanged.
- [ ] T5. `test/ui.test.ts` — `notFoundWork` and `notFoundContact` carry their
  exact EN and RU values.
- [ ] T6. `scripts/check-dist.mjs` (post-build) — built `<title>` at or below 75
  on every journal and ADR page; robots meta and canonical match each journal
  entry's `indexing`; sitemap equals the derived expected set in both
  directions; `og:image:alt` and `twitter:image:alt` carry the exact string on
  every page; exactly one `BreadcrumbList` JSON-LD per journal/ADR page whose
  three names equal the visible breadcrumb's; `/404.html` carries both new
  links and stays `noindex`.
- [ ] T7. `scripts/csp-hash.mjs` (post-build) — still prints exactly one
  `'sha256-…'` token, proving the JSON-LD needed no CSP change.
- [ ] T8. `scripts/check-links.mjs` (post-build) — zero broken internal links;
  the new `mailto:` href reported as skipped by count and by name.

## Rollback

Every change is additive and confined to one repository with no runtime state,
so `git revert` of the merge commit restores the previous behaviour completely:
the sitemap regains its eighteen URLs on the next build, the robots metas and
JSON-LD blocks disappear, the four link classes return to their unstyled hit
areas and `test/a11y.test.ts` returns to six selectors.

If only one slice misbehaves, each is independently revertable:

- **Hit areas** — delete the new `site.css` rule block and revert
  `TARGET_SELECTORS` to the original six. No other file depends on it.
- **Titles** — revert the two routes to their inline template strings and drop
  `seoTitle` from both schemas; the frontmatter lines then fail `strictObject`
  validation, so remove them in the same revert. `titleProblems` can stay
  harmlessly.
- **Indexing** — revert the `astro.config.mjs` filter and the
  `checkSitemap()`/`checkColophonPages()` edits in `scripts/check-dist.mjs`
  together; they must move as a pair or the post-build gate fails. The
  `indexing` frontmatter and the schema field can remain, inert.
- **JSON-LD** — drop the `jsonLd` prop from `Base.astro` and the two route call
  sites. `src/lib/csp.ts`'s narrowed regex is safe to keep (it only ever
  affected `ld+json` blocks, of which there would then be none) and should be
  kept so the next attempt starts from a proven base.
- **404 links** — delete the two paragraphs and the two `ui` keys.

If a deployed release needs reverting rather than the source, use
`mctl_rollback_service` with the previous image tag; the site is static, so no
data migration is involved.
