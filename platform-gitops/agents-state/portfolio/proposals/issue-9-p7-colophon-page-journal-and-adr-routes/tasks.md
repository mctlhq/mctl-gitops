# Tasks: issue-9-p7-colophon-page-journal-and-adr-routes

- [ ] 1. Add `src/lib/colophon.ts`, a zero-import module (no `astro:content`,
      no `zod`, no sibling import — mirror the header comment style of
      `src/lib/metrics.ts`) exporting `EM_DASH`, `cycleDate`,
      `compareCyclesNewestFirst`, `formatLeadTime`, `formatStamp`,
      `githubRefLabel`, `visibilityOf`, `publicIds` and
      `interventionsInSource`, with the exact semantics in `design.md` section
      1. — DoD: `node --test src/…`-loadable with no build step; `formatLeadTime`
      branches on `=== null` so `0` renders as `0.0`; `githubRefLabel` throws on
      an unparseable URL; only type-strippable TypeScript syntax is used (no
      `enum`, no `namespace`, no parameter properties).

- [ ] 2. Add every copy string from `requirements.md` ("Copy" section) to
      `src/i18n/ui.ts` as `{ en, ru }` pairs — the intro, the three section
      headings, `colophonChainItems` (two five-item arrays), the page title, the
      two table captions, the eight cycle-table headers, the two ADR-only
      headers, the two totals labels and the entry-page labels — plus a separate
      `adrStatusLabel` export (a `Record<status, { en, ru }>`, not a `ui` key,
      because `test/ui.test.ts` requires every `ui` value to be an `{ en, ru }`
      pair of the same kind). — DoD: strings match `requirements.md` character
      for character; `npm test` passes `test/ui.test.ts` unchanged; `npm run
      check` is clean.

- [ ] 3. Add `src/components/CycleTable.astro` (depends on 1, 2): one
      `<table class="cycle-table">` with a bilingual `<caption>`,
      `<th scope="col">` headers and one row per entry in the order given by
      `compareCyclesNewestFirst`, with the eight columns from `requirements.md`;
      lead time from `leadTimeHours` via `formatLeadTime`, interventions from
      `interventionCount`, issue and PR cells from `githubRefLabel`, em dash for
      a missing `pr` or `release`, title linking to `/colophon/journal/<id>/`. —
      DoD: no user-facing literal in the template (all copy via `ui` + `Lang`);
      no `--font-editorial`; no `tabindex`; wrapped in a container that scrolls
      horizontally on narrow viewports.

- [ ] 4. Add `src/pages/colophon/index.astro` (depends on 2, 3): `<h1>` from
      `ui.navColophon`, the intro paragraph, the "Build and deploy chain"
      bilingual `<ul>` pair from `ui.colophonChainItems`, the "Cycles" section
      with `<CycleTable>` and the two totals carrying `data-cycle-count` and
      `data-interventions-total`, and the "Decisions" section with the ADR index
      table (id, title, status, date) sorted by `data.id` ascending, each row
      linking to `/colophon/adr/<id>/` from its `ADR-NNNN` cell. Both collections
      are read with a `visibility === 'public'` filter. — DoD: `/colophon/`
      builds; the totals are computed from the collection, never typed; stripping
      `<h1>`..`<h6>` tag names from the template leaves no digit in it (the same
      mechanical proxy `test/home.test.ts` and `test/approach.test.ts` use).

- [ ] 5. Add `src/pages/colophon/journal/[...slug].astro` (depends on 1, 2):
      `getStaticPaths` over the `journal` collection filtered to
      `visibility === 'public'`, `params: { slug: entry.id }`; renders kicker,
      bilingual title and `decided`, service, issue and PR links, release, the
      five timestamps through `formatStamp`, the computed lead time, one item per
      intervention (`what`, `why`, `at`) and a back link to `/colophon/`. — DoD:
      one page per public entry at `/colophon/journal/<id>/`; an absent timestamp
      renders an em dash rather than disappearing.

- [ ] 6. Add `src/pages/colophon/adr/[...slug].astro` (depends on 2): same
      `getStaticPaths` shape over `adr`; renders `ADR-NNNN` (zero-padded from
      `data.id`), the bilingual title, the status via `adrStatusLabel`, the date,
      `supersedes` when present, the body through
      `const { Content } = await render(entry)` as `ProjectCard.astro` does, and
      a back link. — DoD: one page per public ADR at `/colophon/adr/<id>/`; the
      rendered body keeps its own `.l en` / `.l ru` pairs.

- [ ] 7. Add the colophon link to `src/components/Nav.astro` using
      `ui.navColophon`, and correct the stale comment in
      `src/components/Footer.astro` so it states that the release shown is the
      built `package.json` version maintained by release-please with no `v`
      prefix. Leave the `data-release` markup and the `import pkg` as they are. —
      DoD: every page's nav carries `href="/colophon/"`; the footer still renders
      `pkg.version` and nothing else changed in it.

- [ ] 8. Add `.cycle-table`, `.adr-table`, `.colophon-totals`, `.entry-meta` and
      `.intervention` rules to `src/styles/site.css` using `--mctl-*` tokens and
      `var(--font-display)` / `var(--font-mono)` (depends on 3-6). — DoD: no
      `--font-editorial` in any new rule; the table wrapper scrolls on narrow
      viewports; `npm run vendor` regenerates `public/styles/site.css` with the
      new rules.

- [ ] 9. Backfill the journal (independent of 1-8): create
      `src/content/journal/2026-09-11-content-collections-for-projects-journal-and-adrs.md`
      with the frontmatter given verbatim in `requirements.md` ("Copy: P3 journal
      entry"), and add the four keys listed in "Copy: backfilled timestamps" to
      `2026-09-11-home-page.md`, `2026-09-11-work-page.md` and
      `2026-09-11-approach-page.md`, keeping the key order used by the existing
      entries. Add no `interventions` and no `deployed_at`. — DoD: `npm run
      check` passes the `journal` schema; `grep -c "visibility: public"
      src/content/journal/*.md` yields 8 files; no other field of the three
      existing entries changed.

- [ ] 10. Extend `scripts/check-dist.mjs` with `checkColophonPages()` (depends
      on 1, 4, 5, 6, 9): assert `dist/colophon/index.html` exists; compare the
      directory sets under `dist/colophon/journal/` and `dist/colophon/adr/`
      against `publicIds()` over `src/content/journal/` and `src/content/adr/` in
      both directions; assert no private id appears in any `dist/` path or in
      `dist/colophon/index.html`; compare `data-cycle-count` with the number of
      public journal files and `data-interventions-total` with the summed
      `- what:` count; compare the `data-release` text in `dist/index.html` with
      `package.json`'s `version` and fail if it differs or starts with `v`. — DoD:
      every failure prints a named reason and sets a non-zero exit code, matching
      the existing style; the OK line mentions the cycle count and the release.

- [ ] 11. Add `test/colophon.test.ts` and register it in the `test` script in
      `package.json` (depends on 1, 3-6, 9). — DoD: `npm test` runs the new file;
      the whole suite is green.

- [ ] 12. Run the full local gate: `npm run check`, `npm test`, `npm run build`,
      `node scripts/check-dist.mjs`, `node scripts/csp-hash.mjs` (depends on
      1-11). — DoD: all five succeed; `find dist -name '*.js'` is empty;
      `csp-hash` still reports exactly one inline script body.

## Tests

- [ ] T1. `formatLeadTime`: `null` gives the em dash; `0` gives `0.0`;
      `0.7338888888888889` gives `0.7`; a large value keeps one decimal.
- [ ] T2. `formatStamp`: a `Date` and the equivalent ISO string give the same
      `YYYY-MM-DD HH:MMZ`; `undefined` and `null` give the em dash.
- [ ] T3. `githubRefLabel` returns `portfolio#12` for
      `https://github.com/mctlhq/portfolio/pull/12` and `mctl-api#282` for
      `https://github.com/mctlhq/mctl-api/pull/282`, and throws on a
      non-GitHub or malformed URL.
- [ ] T4. `compareCyclesNewestFirst` sorts a fixture of entries by date prefix
      descending, breaks a same-date tie by `issueOpenedAt` descending and an
      identical-timestamp tie by id descending; sorting the same array twice is
      idempotent.
- [ ] T5. `cycleDate` returns the prefix for a valid id and throws for an id with
      no `YYYY-MM-DD` prefix.
- [ ] T6. `visibilityOf` / `publicIds` / `interventionsInSource` over inline
      fixture sources: a `private` entry is excluded, a missing `visibility` line
      yields `null`, and the intervention count matches the number of `- what:`
      items.
- [ ] T7. Every file in `src/content/journal/` contains no `lead_time`,
      `lead_time_hours`, `leadTime`, `intervention_count` or `interventions_count`
      key, and every top-level frontmatter key is one the `journal` schema
      declares (the executable form of the issue's `grep -r lead_time
      src/content` criterion).
- [ ] T8. The journal directory holds 8 public entries and 10 `interventions`
      items in total, so a later hand-edit of the record moves a number that a
      test names.
- [ ] T9. Source-level assertions on the new templates, in the style of
      `test/work.test.ts`: `CycleTable.astro` derives cells from the entry
      (`leadTimeHours(`, `interventionCount(`) rather than from literals; neither
      new page nor `CycleTable.astro` mentions `--font-editorial` or `tabindex`;
      each `[...slug].astro` filters `getStaticPaths` on
      `visibility === 'public'`; `Nav.astro` carries `href="/colophon/"`;
      `Footer.astro` still imports `../../package.json`.
- [ ] T10. Post-build, `node scripts/check-dist.mjs` passes on a clean tree and
      fails with the expected message when `data-cycle-count` is tampered with
      (verify by hand once during implementation; the script itself is the
      committed evidence).

### Reviewer steps (not acceptance criteria)

- Load `/colophon/` in a browser with the network panel recording and confirm the
  HAR shows same-origin requests only, and that the page is complete with
  JavaScript disabled.
- Toggle to Russian and confirm no Cyrillic string falls back to a non-Onest
  face, particularly in the table headers and the ADR status labels.
- Confirm the P6 entry's `release: 0.1.5` still names the release that first
  contained the P6 merge commit.

## Rollback

The change is additive and self-contained. Revert the merge commit on `main`
(`git revert -m 1 <merge-sha>`): `/colophon/` returns to a dead link handled by
`src/pages/404.astro`, the journal returns to seven entries, and
`scripts/check-dist.mjs` returns to its pre-P7 checks. No schema, image,
`nginx.conf` or CSP change is involved, so nothing outside the repository has to
be undone. If only the backfill is wrong, revert the three edited entries and
delete the new P3 file; the page then shows a smaller cycle count and the
post-build check follows it automatically, because both numbers are computed. If
the site has already been deployed from a release containing this change,
`mctl_rollback_service` to the previous image tag restores the previous page set
without touching the repository.
