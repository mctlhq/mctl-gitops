# Tasks: issue-88-q13-link-targets-below-the-floor-titles

Ordered so each slice is independently runnable. `npm test` runs before
`astro build` (`prebuild` is `npm run vendor && npm test`), so anything that
inspects built markup belongs in `scripts/check-dist.mjs`, not in a test file.

## A. Hit areas

- [ ] 1. Add one grouped rule to `src/styles/site.css`, beside the existing
      `.site-nav a, .toggle-group button, .site-footer a` tap-target block:
      `.project-links a, .breadcrumb a, .journal-meta a, .table-scroll a`
      with `display: inline-flex; align-items: center; flex-wrap: wrap;
      min-block-size: 24px;` and a comment in the file's existing voice
      explaining that these are standalone links, that 24px is the WCAG 2.2
      target-size minimum, and that `main a` in prose is deliberately
      untouched.
      — DoD: the four selectors each appear in a rule block declaring
      `min-block-size: 24px`; no `min-width`, no fixed `height`/`block-size`,
      no `animation`, no `transition`, and no edit to `.table-scroll`,
      `.table-scroll:focus-visible` or the
      `@media (max-width: 599px) .table-scroll::after` hint.

- [ ] 2. In `test/a11y.test.ts`, extend `TARGET_SELECTORS` to all ten:
      `.site-nav a`, `.toggle-group button`, `.site-footer a`, `.cta`,
      `.block > summary`, `.skip-link:focus`, `.project-links a`,
      `.breadcrumb a`, `.journal-meta a`, `.table-scroll a`. Refactor the
      per-selector assertion body into two local pure functions,
      `declaredMinBlockSizes(css, selector)` and
      `minBlockSizeProblems(css, selector, floor)`, keeping the existing
      matching shape (comma-split, whitespace-normalised selector list must
      `include` the exact selector; at least one such block declares
      `min-block-size`; every such declaration is `>= 24`). (depends on 1)
      — DoD: ten passing per-selector tests; the assertion logic exists once,
      not ten times.

- [ ] 3. Record the mutation proof in `test/a11y.test.ts`: run
      `minBlockSizeProblems` over a synthetic stylesheet declaring
      `.breadcrumb a { min-block-size: 16px; }` and assert it reports a
      problem naming 16, and over a stylesheet with no rule for the selector
      and assert it reports the "no rule found" problem. (depends on 2)
      — DoD: both synthetic cases pass; no file outside the test is modified;
      the test file itself documents what was mutated and what failed.

## B. Short search titles

- [ ] 4. In `src/lib/seo.ts` (keeping its zero-import property — no
      `astro:content`, no `zod`), add `SITE_TITLE_SUFFIX = ' — Dmitrii Mashkov'`,
      `titleProblems(title, { warn = 65, fail = 75 } = {})`,
      `journalPageTitle(entry)` and `adrPageTitle(entry, paddedId)` with the
      signatures in `design.md`.
      — DoD: `titleProblems` returns `[]` at 65, one warning naming the length
      at 66, and a failure at 76; `journalPageTitle`/`adrPageTitle` return
      `seoTitle` when present and the current template when absent.

- [ ] 5. Add `seoTitle: z.string().min(1).optional()` to `journalSchema` and to
      the `adr` schema in `src/content.config.ts` (both are `strictObject`, so
      this is required before any content file may carry the key).
      — DoD: `npx astro sync` succeeds; an entry with `seoTitle: ""` is
      rejected.

- [ ] 6. Switch both routes to the helpers:
      `src/pages/colophon/journal/[...slug].astro` uses
      `journalPageTitle(data)`, `src/pages/colophon/adr/[...slug].astro` uses
      `adrPageTitle(entry.data, padAdrId(entry.data.id))`. (depends on 4)
      — DoD: no template literal composing a title remains in either route;
      `<h1>` and `<Breadcrumb currentEn/currentRu>` are byte-identical to
      before on both routes.

- [ ] 7. Add all 24 `seoTitle` values from the table in `requirements.md` §B to
      their entries, character for character, as a top-level frontmatter
      scalar. Nineteen journal files and five ADR files. No other entry gains
      one. (depends on 5)
      — DoD: `grep -c '^seoTitle:' src/content/journal/*.md src/content/adr/*.md`
      totals 24, on exactly the 24 named files; every value matches the table
      byte for byte, including the em dash `—`.

## C. Indexing

- [ ] 8. Add `indexing: z.enum(['index', 'noindex']).default('index')` to
      `journalSchema` only, in `src/content.config.ts`. The `adr` schema gains
      no such field.
      — DoD: `npx astro sync` succeeds; an entry with `indexing: maybe` is
      rejected; the ADR schema is unchanged in this respect.

- [ ] 9. Add an explicit `indexing:` key to every journal entry per the 24-row
      table in `requirements.md` §C: `index` on
      `2026-09-10-base-layout-vendored-tokens-and-fonts.md`,
      `2026-09-11-csp-hash-quoting-and-browser-verified-headers.md`,
      `2026-09-11-metrics-provenance-and-no-analytics.md`,
      `2026-09-11-production-cutover.md`,
      `2026-09-12-content-link-contrast-and-an-offline-link-check.md`,
      `2026-09-13-journal-lifecycle-and-release-closure.md`; `noindex` on the
      other eighteen. (depends on 8)
      — DoD: every `src/content/journal/*.md` declares the key; exactly six
      say `index`.

- [ ] 10. Add a `robots?: string` prop to `src/layouts/Base.astro` and replace
      the either/or block with
      `const robotsContent = noindex ? 'noindex' : robots;` then
      `{robotsContent && <meta name="robots" content={robotsContent} />}` and
      `{!noindex && <link rel="canonical" href={canonicalUrl.href} />}`.
      — DoD: `/404.html` output is unchanged (robots meta, no canonical);
      every ordinary page's output is unchanged (canonical, no robots meta);
      the new "robots meta *and* canonical" combination is reachable only by
      passing `robots`.

- [ ] 11. In `src/pages/colophon/journal/[...slug].astro`, pass
      `robots={data.indexing === 'noindex' ? 'noindex,follow' : undefined}` to
      `Base`. The ADR route passes nothing. (depends on 8, 10)
      — DoD: a built `noindex` entry carries
      `<meta name="robots" content="noindex,follow">` and its canonical link; a
      built `index` entry carries neither a robots meta nor any other change.

- [ ] 12. Add `src/lib/indexing.ts` (zero-import) exporting `parseIndexing`,
      `noindexJournalIds(journalDir)` and `noindexJournalPaths(journalDir)` as
      described in `design.md`. (depends on 9)
      — DoD: `parseIndexing` returns `'index'` for a source with no key,
      `'noindex'` for `indexing: noindex`, and is tolerant of surrounding
      quotes and trailing whitespace; `noindexJournalPaths` returns sorted
      `/colophon/journal/<id>/` strings.

- [ ] 13. Wire the sitemap filter in `astro.config.mjs` to that derivation:
      import `noindexJournalPaths`, build the `Set` once at config load, and
      return `false` for `/404*`, `/dev/*` and any path in the set. If the
      config loader rejects the `.ts` import, inline the same
      `readdirSync` + `parseIndexing` scan in the config instead — never a
      hand-typed slug list. (depends on 12)
      — DoD: `astro.config.mjs` contains no literal `/colophon/journal/` path;
      `dist/sitemap-0.xml` after a build lists the six indexed journal pages
      and no `noindex` one.

- [ ] 14. Extend `idsByVisibility()` in `scripts/check-dist.mjs` with
      `indexedIds` and `noindexIds` (public entries split by `parseIndexing`,
      journal only), switch `checkSitemap()`'s `expectedPaths` from
      `journal.publicIds` to `journal.indexedIds`, and add
      `checkJournalRobots()` asserting per built journal page: `noindex` →
      exactly one `<meta name="robots" content="noindex,follow">` plus a
      `<link rel="canonical">`; `index` → no robots meta. Wire
      `checkJournalRobots()` into `run()` beside the other checks.
      (depends on 12)
      — DoD: `node scripts/check-dist.mjs` passes after a build;
      `checkColophonPages()` still uses `publicIds` so every entry keeps its
      page, its colophon row and its totals contribution.

## D. Share image and structured data

- [ ] 15. In `src/layouts/Base.astro`, add the constant
      `OG_IMAGE_ALT = 'Dmitrii Mashkov — platform engineering with AI on proven open source, dmitriimashkov.com'`
      and emit `<meta property="og:image:alt" content={OG_IMAGE_ALT} />`
      directly after `og:image` and
      `<meta name="twitter:image:alt" content={OG_IMAGE_ALT} />` directly after
      `twitter:image`, on every page, in English.
      — DoD: every `dist/**/*.html` carries both tags with exactly that string.

- [ ] 16. Narrow `src/lib/csp.ts`: add `isDataBlockType(type)` and make
      `extractInlineScripts` skip `<script>` elements whose `type` is a data
      block (anything not absent, empty, `module`, or a JavaScript MIME type),
      keeping `INLINE_SCRIPT_RE`'s existing `src=` exclusion and its exported
      name.
      — DoD: `extractInlineScripts` still captures the `is:inline` bootstrap
      with or without a `type`, and ignores
      `<script type="application/ld+json">`; `scripts/csp-hash.mjs` and
      `scripts/check-headers.mjs` are not edited.

- [ ] 17. Add a `jsonLd?: unknown` prop to `src/layouts/Base.astro` rendering
      exactly one
      `<script type="application/ld+json" set:html={JSON.stringify(jsonLd).replace(/</g, '\\u003c')} />`
      when given and nothing when absent. (depends on 16)
      — DoD: a page passing no `jsonLd` emits no such element; a page passing
      one emits exactly one.

- [ ] 18. Add `src/lib/jsonld.ts` (zero-import) exporting
      `breadcrumbList(items, site)` returning a schema.org `BreadcrumbList`
      with `itemListElement` positions 1..n and each `item` resolved against
      `site`.
      — DoD: pure function, no `astro:content` import, exact shape asserted by
      a unit test.

- [ ] 19. In both `[...slug].astro` routes, build the three-item `crumbs`
      array once — `{ name: ui.navHome.en, path: '/' }`,
      `{ name: ui.navColophon.en, path: '/colophon/' }`, and the current page
      (`data.title.en` for journal, `ADR-${padAdrId(entry.data.id)}` for ADR,
      `path: Astro.url.pathname`) — pass
      `jsonLd={breadcrumbList(crumbs, Astro.site)}` to `Base`, and pass
      `crumbs[2].name` as `currentEn` to `<Breadcrumb>` so the visible
      breadcrumb and the structured data read the same value.
      (depends on 17, 18)
      — DoD: the visible breadcrumb renders exactly as today in both
      languages; the JSON-LD names equal its English side; no `Person`,
      `WebSite` or `Article` entity is emitted anywhere.

- [ ] 20. Extend `scripts/check-dist.mjs`: `checkOgImageMeta()` also asserts
      `og:image:alt` and `twitter:image:alt` are present and both equal the
      exact D.12 string; a new check asserts each built journal and ADR page
      carries exactly one `<script type="application/ld+json">`, that it
      parses as JSON with `"@type": "BreadcrumbList"` and three items, and
      that the three `name` values equal the three English names parsed out of
      that page's own `<nav class="breadcrumb">`. (depends on 15, 19)
      — DoD: `node scripts/check-dist.mjs` passes after a build and fails if
      a breadcrumb name and its JSON-LD counterpart are made to disagree.

## E. The 404 page

- [ ] 21. Add two keys to `src/i18n/ui.ts` beside `notFoundHome`:
      `notFoundWork: { en: 'See the work', ru: 'Посмотреть работы' }` and
      `notFoundContact: { en: 'Get in touch', ru: 'Написать' }`. Do not reuse
      or modify `ctaWork` (`{ en: 'See the work', ru: 'Смотреть работы' }`).
      — DoD: `test/ui.test.ts` passes; `ctaWork` is byte-identical to before.

- [ ] 22. In `src/pages/404.astro`, add two paragraphs below the existing home
      link: `<a href="/work/">` with the `notFoundWork` `<Lang>` pair, and
      `<a href="mailto:hello@dmitriimashkov.com">` with the `notFoundContact`
      pair. Keep `noindex` on `Base`. (depends on 21)
      — DoD: `/404.html` carries both links with the exact EN and RU copy,
      stays `noindex`, and keeps equal counts of `class="l en"` and
      `class="l ru"`.

## F. Cycle hygiene

- [ ] 23. Write this cycle's journal entry at
      `src/content/journal/2026-09-13-<slug>.md` with `service: portfolio`,
      the issue URL `https://github.com/mctlhq/portfolio/issues/88`,
      `proposal_slug: issue-88-q13-link-targets-below-the-floor-titles`,
      `status: in_progress`, `visibility: public`, `indexing: noindex`, no
      `seoTitle`, a bilingual `title` whose `en` side is at most 47 characters
      (suggested: `Q13: hit areas, titles, indexing, image alt` /
      `Q13: зоны нажатия, заголовки, индексация, alt изображения`), a bilingual
      `decided`, `issue_opened_at`, and `interventions: []` unless one
      occurred. (depends on 9)
      — DoD: exactly one entry in the collection has `status: in_progress`;
      `checkJournalCollection` passes; its generated title measures at or
      below 65 characters.

- [ ] 24. Append every new test file to the enumerated `node --test` list in
      `package.json`'s `test` script.
      — DoD: `npm test` runs every new file; no test file exists that the
      script does not name.

## Tests

- [ ] T1. `test/a11y.test.ts` — ten selectors pass at the 24px floor, and the
      recorded mutation (a synthetic `.breadcrumb a { min-block-size: 16px; }`
      stylesheet, and one with no rule at all) is reported as a problem by the
      same matcher the real assertions use.
- [ ] T2. `test/seo.test.ts` — `titleProblems` returns `[]` at exactly 65, one
      warning naming the length at 66, and a failure at 76; the existing
      `clampDescription` cases are unchanged. Also cover
      `journalPageTitle`/`adrPageTitle` returning `seoTitle` when present and
      the current template when absent.
- [ ] T3. `test/title-budget.test.ts` (new) — reads the frontmatter of every
      `src/content/journal/*.md` and `src/content/adr/*.md`, computes each
      page's title through `journalPageTitle`/`adrPageTitle` (the same helpers
      the routes call, never a hand-typed list), and asserts: no title exceeds
      75 characters; every title above 65 comes from a `seoTitle`; the 24
      `seoTitle` values match the `requirements.md` §B table character for
      character on exactly those 24 files; no other entry carries one.
- [ ] T4. `test/indexing.test.ts` (new) — reads the journal collection from
      disk and asserts: every entry declares `indexing`; the set of `index`
      ids equals exactly the six named in `requirements.md` §C; every other
      entry is `noindex` (a derived comparison, not a literal total). Also
      covers `parseIndexing` on a source with no key (`'index'`), with
      `indexing: noindex`, and with quoted/whitespaced values, and asserts
      `astro.config.mjs` contains no literal `/colophon/journal/` path.
- [ ] T5. `test/csp.test.ts` — `extractInlineScripts` ignores
      `<script type="application/ld+json">`; still captures a script with no
      `type`, `type=""`, `type="module"` and `type="text/javascript"`; a
      document holding both the bootstrap script and a `ld+json` block yields
      exactly one body; `isDataBlockType` discriminates in both directions;
      `scriptSrcTokens` over the committed `security-headers.conf` still
      yields exactly one hash-shaped token.
- [ ] T6. `breadcrumbList` unit coverage (in `test/seo.test.ts` or a new
      `test/jsonld.test.ts`) — three items, positions 1, 2, 3, absolute
      `item` URLs against the site origin, `@type: 'BreadcrumbList'`, and no
      `Person`/`WebSite`/`Article` key anywhere in the output.
- [ ] T7. `test/ui.test.ts` — `notFoundWork` and `notFoundContact` carry their
      exact EN and RU values; `ctaWork` still carries
      `{ en: 'See the work', ru: 'Смотреть работы' }`, proving the two were
      not conflated.
- [ ] T8. Post-build gates, all run after `npm run build`:
      `node scripts/check-dist.mjs` (robots meta and canonical per entry,
      sitemap contents derived from the collection, `og:image:alt` and
      `twitter:image:alt`, one `BreadcrumbList` per journal/ADR page with
      names matching the visible breadcrumb, the 404's two links, existing
      `class="l en"`/`class="l ru"` parity), `node scripts/csp-hash.mjs`
      (still exactly one hash token) and `node scripts/check-links.mjs`
      (`/work/` resolves, the `mailto:` is reported as skipped).
- [ ] T9. Regression sweep — `test/journal-closure.test.ts`,
      `test/journal-build.test.ts`, `test/journal-status.test.ts`,
      `test/colophon.test.ts` and `test/check-dist.test.ts` still pass with
      two extra flat frontmatter keys and the new check functions in place.
      `scripts/close-journal.mjs` is not edited.

## Rollback

Every slice is independently revertible and nothing here has state outside the
repository.

1. **Full revert.** `git revert` the merge commit. The site returns to 0.1.23
   behaviour on the next release: six-selector `TARGET_SELECTORS`, generated
   titles, all 24 journal pages in the sitemap, no image alt, no JSON-LD, a
   one-link 404. No data migration to undo — `seoTitle` and `indexing` are
   frontmatter keys that disappear with the files' previous content.
2. **Per-slice revert, if only one thing misbehaves.**
   - Hit areas: delete the one grouped CSS rule and shrink `TARGET_SELECTORS`
     back to six. Nothing else depends on it.
   - Titles: drop the `seoTitle` values (or the schema key), and both routes
     fall back to the current template automatically — the helpers are written
     so absence is the existing behaviour.
   - Indexing: set every entry to `indexing: index`. The sitemap filter then
     excludes nothing, the journal route emits no robots meta, and
     `checkSitemap()`'s expectation returns to the full public set with no code
     change.
   - JSON-LD: stop passing `jsonLd` from the two routes. The `Base.astro` prop
     renders nothing, and `csp-hash.mjs` output is unaffected either way.
   - 404: revert `src/pages/404.astro`; the two `ui` keys are inert if left.
3. **Deployed rollback.** If a defect is only visible in production, roll the
   service back to the previous image tag with `mctl_rollback_service`
   (`team_name: labs`, `component_name: portfolio`), the path already
   exercised and recorded in
   `src/content/journal/2026-09-11-production-cutover.md`. No DNS, ingress,
   certificate or `security-headers.conf` change is part of this cycle, so
   there is nothing at the edge to unwind.
4. **Search-index recovery.** If the `noindex` split proves too aggressive,
   flipping the affected entries back to `indexing: index` and releasing
   restores both the sitemap URL and the absence of the robots meta; the pages
   were never unpublished, never redirected and never removed, so no URL ever
   404s and no link ever breaks.
