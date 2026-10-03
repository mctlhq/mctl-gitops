# Tasks: issue-9-p7-colophon-page-journal-and-adr-routes

- [ ] 1. Add `src/lib/content.ts`: an import-free module exporting `isPublic`
      and `publicEntries` over `{ data: { visibility } }`, with a header comment
      in the style of `src/lib/journal.ts` explaining why it imports nothing.
      — DoD: `node --test test/content.test.ts` passes; the module has no
      `import` statement.

- [ ] 2. Extend `src/lib/journal.ts` with `cycleTimestamp`, `byNewestFirst`,
      `isoDate`, `isoStamp`, `formatLeadTime`, `totalInterventions` and
      `githubRef` exactly as specified in `design.md` section 1, keeping the
      module's import list empty (define a module-private `const EM_DASH = '—'`
      with a comment pointing at the same rule `src/lib/metrics.ts` documents).
      (depends on nothing) — DoD: existing `test/journal.test.ts` still passes
      unchanged; new cases in it cover every added function.

- [ ] 3. Extend `src/lib/adr.ts` with a `byAdrId` comparator (ascending `id`)
      and a `padAdrId(id: number): string` returning the four-digit form.
      — DoD: `node --test test/adr.test.ts` passes with new cases for both.

- [ ] 4. Add every string listed in `design.md` section 6 to `src/i18n/ui.ts`,
      verbatim, character for character, keeping the existing file's grouping
      and comment style. Do not modify `navColophon` or `footerColophonLabel`.
      — DoD: `test/ui.test.ts` passes; `npm run check` reports no type error.

- [ ] 5. Add `src/components/CycleTable.astro` per `design.md` section 2: eight
      columns, one `<tr data-cycle-row>` per entry, title cell linking to
      `/colophon/journal/${entry.id}/`, em dash for absent `pr`, `release` and
      `null` lead time, `interventionCount` rendered even when `0`. Wrap the
      table in the keyboard-reachable scroll region with the concatenated
      bilingual `aria-label`. (depends on 2, 4) — DoD: the component contains no
      hard-coded row, no numeric literal and no `var(--font-editorial)`.

- [ ] 6. Add `src/pages/colophon/index.astro` per `design.md` section 3: intro,
      `Build and deploy chain` bullets, `Cycles` section with `<CycleTable>` and
      the two computed totals carrying `data-cycle-count` and
      `data-intervention-count`, `Decisions` section with the ADR index table.
      (depends on 1, 2, 3, 4, 5) — DoD: `npm run build` emits
      `dist/colophon/index.html` containing eight `data-cycle-row` occurrences
      and the two totals; neither total appears as a literal in `src/`.

- [ ] 7. Add `src/pages/colophon/journal/[...slug].astro` per `design.md`
      section 4, with `getStaticPaths` over `publicEntries(await
      getCollection('journal'))`. (depends on 1, 2, 4) — DoD: `npm run build`
      emits one `dist/colophon/journal/<id>/index.html` per public entry and
      none for a private one; each page renders its interventions verbatim under
      the bilingual note, inside a `lang="en"` container.

- [ ] 8. Add `src/pages/colophon/adr/[...slug].astro` per `design.md` section 5,
      rendering the body through `render(entry)` inside `<div class="mctl-prose">`.
      (depends on 1, 3, 4) — DoD: `npm run build` emits
      `dist/colophon/adr/0001-bootstrap-boundary/index.html`,
      `.../0002-static-astro-no-client-bundles/index.html` and
      `.../0005-self-contained-runtime-assets/index.html`; no `class="lede"` and
      no `var(--font-editorial)` in the page.

- [ ] 9. Add the Colophon link to `src/components/Nav.astro` using the existing
      `ui.navColophon`. (depends on 6) — DoD: every page's nav links
      `/colophon/`; `.l.en` / `.l.ru` counts stay equal.

- [ ] 10. Add the Colophon link to `src/components/Footer.astro` using the
      existing `ui.footerColophonLabel`, and replace the stale comment about the
      release source with the statement that `package.json`'s `version` (bumped
      by release-please) is the source. Leave
      `<span data-release>{pkg.version}</span>` unchanged. (depends on 6)
      — DoD: the footer renders the current `package.json` version and a
      `/colophon/` link; no version literal appears in the component.

- [ ] 11. Add table, scroll-region and colophon layout rules to
      `src/styles/site.css` (`.cycles`, `.table-scroll`, `.adr-index`,
      `.cycle-totals`, `.interventions`), narrow-first, using design tokens
      only, `font-variant-numeric: tabular-nums` on numeric columns, and
      `var(--font-display)` for every translated string. (depends on 5, 6)
      — DoD: no literal colour and no `--font-editorial` in the added rules; the
      page is readable at 360px with the table scrolling horizontally.

- [ ] 12. Create `src/content/journal/2026-09-11-content-collections.md` with
      the frontmatter block given verbatim in `design.md` section 7.
      — DoD: `npm run check` passes (the entry validates against the `journal`
      schema); the file has an empty body, like every existing journal entry.

- [ ] 13. Backfill `pr`, `release`, `merged_at` and `released_at` into
      `src/content/journal/2026-09-11-home-page.md` and
      `src/content/journal/2026-09-11-approach-page.md` with the exact values in
      `design.md` section 7, in the documented key order, every timestamp
      single-quoted. — DoD: `npm run check` passes; `git diff` shows only added
      lines in those two files.

- [ ] 14. Backfill `pr`, `release`, `merged_at`, `released_at` and the seven
      `interventions` into `src/content/journal/2026-09-11-work-page.md`,
      verbatim and in the order given in `design.md` section 7. (depends on 13
      for consistency of key order) — DoD: the file's `- what:` items are
      exactly those seven, in that order, with their `why` and `at` values
      character for character as specified.

- [ ] 15. Add `checkColophonPages()` to `scripts/check-dist.mjs` per `design.md`
      section 8 (all six assertions), called from `main()` next to
      `checkApproachPage()`, and extend the success log line with the derived
      cycle and intervention counts. (depends on 6, 7, 8, 12, 13, 14)
      — DoD: `npm run build && node scripts/check-dist.mjs` exits 0 and prints
      the derived counts; deliberately editing one total in the page source
      makes it exit non-zero.

- [ ] 16. Register the new test files (`test/content.test.ts`,
      `test/colophon.test.ts`) in the `test` script of `package.json`, which
      enumerates its files explicitly. (depends on T1, T4) — DoD: `npm test`
      runs every test file present in `test/`, and `npm run build` still runs
      them through `prebuild`.

## Tests

- [ ] T1. `test/content.test.ts`: `isPublic` and `publicEntries` keep only
      `visibility: 'public'` entries, preserve input order, return a new array,
      and return `[]` for an all-private input — the unit-level proof of the
      "private entries produce no page" criterion.
- [ ] T2. `test/journal.test.ts` (extended): `cycleTimestamp` prefers
      `deployed_at`, then `released_at`, `merged_at`, `proposal_approved_at`,
      `issue_opened_at`; `byNewestFirst` sorts a shuffled fixture newest first
      and is stable on a tie via the id tiebreak; `isoDate` and `isoStamp`
      render UTC with no fractional seconds; `formatLeadTime(null)` is the em
      dash and `formatLeadTime(0.7338…)` is `'0.7'`; `formatLeadTime(0)` is
      `'0.0'`, not the em dash; `totalInterventions` sums across entries and is
      `0` for `[]`; `githubRef` returns `'#28'` for a pull request URL and the
      input URL unchanged for a URL with no trailing number.
- [ ] T3. `test/adr.test.ts` (extended): `byAdrId` sorts ascending; `padAdrId`
      renders `1` as `'0001'` and `25` as `'0025'`.
- [ ] T4. `test/colophon.test.ts` (source-level, reading files with
      `readFileSync` in the style of `test/work.test.ts`):
      - no file under `src/content/` contains `lead_time`, `leadTime`,
        `intervention_count` or `interventionCount` (issue criterion 3);
      - `src/pages/colophon/index.astro` contains `totalInterventions(` and
        `.length` for the totals and no standalone integer literal in the totals
        markup;
      - `src/components/CycleTable.astro` maps over `entries` and contains none
        of the journal titles, issue numbers or release tags as literals;
      - every public journal file parses to the required frontmatter keys, every
        timestamp is single-quoted and matches `ISO_WITH_OFFSET`, and every
        `interventions` item has `what`, `why` and `at`;
      - the count of public journal files equals the count of
        `/^visibility:\s*public/m` matches, and the `- what:` total over those
        files is reported in the assertion message so a reviewer sees the
        derived figures without opening the page;
      - `src/components/Footer.astro` imports `../../package.json` and renders
        `pkg.version`, with no semver literal in the file;
      - none of the new `.astro` files reference `var(--font-editorial)` or
        `class="lede"` (typography constraint carried from issue #4).
- [ ] T5. Post-build gate (`node scripts/check-dist.mjs`, run by the Dockerfile
      builder stage and therefore by the `build` job of
      `.github/workflows/build.yml`): the six assertions of `design.md`
      section 8, plus the pre-existing no-`.js`, bilingual-parity and
      `dist/index.html` size rules over the new pages.

### Reviewer steps (human, not implementer criteria)

- [ ] R1. Load `/colophon/` in a browser with the network panel recording and
      export a HAR; confirm every request is same-origin. T5's absolute-URL rule
      is the mechanical half of this; the capture itself needs a human.
- [ ] R2. Tab through `/colophon/` with the keyboard: the table's scroll region
      takes focus with a visible ring and scrolls with the arrow keys, and both
      language toggles still work.
- [ ] R3. Spot-check three backfilled timestamps against
      `gh api repos/mctlhq/portfolio/pulls` and `.../releases`.

## Rollback

Every change is additive and confined to one branch. To roll back before merge,
close the pull request; nothing else is touched. To roll back after merge,
revert the merge commit: the new routes disappear, the backfilled frontmatter
keys revert with them, and the only user-visible regression is the home page's
`ctaColophon` link 404ing again, exactly as it does today. Nothing is deployed
by this cycle — the site is not onboarded yet, so `MCTL_ONBOARDED` is unset and
the release workflow only tags. If a deploy has already happened by then,
`mctl_rollback_service team_name=labs component_name=portfolio target_tag=0.1.5`
returns the running image to the pre-P7 release; no data migration or state
change needs undoing.
