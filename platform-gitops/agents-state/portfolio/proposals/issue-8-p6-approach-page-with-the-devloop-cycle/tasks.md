# Tasks: issue-8-p6-approach-page-with-the-devloop-cycle

- [ ] 1. Add the page's strings to `src/i18n/ui.ts`. Declare the module-level
  consts `RUN_ITEMS_EN`, `RUN_ITEMS_RU` (the nine existing `detailsRunItems`
  entries, moved out unchanged) and `STACK_EXTRA`
  (`Claude Agent SDK`, `release-please`, `Astro`, `nginx`); rebuild
  `detailsRunItems` from the first two; add `detailsStackItems` as
  `[...RUN_ITEMS_*, ...STACK_EXTRA]`. Add `approachPageTitle`,
  `approachIntro`, `cycleNodes` (ten entries per language), `cycleTitle`,
  `cycleDesc`, `detailsGatesSummary`, `detailsGatesItems` (four per language),
  `detailsNumbersSummary`, `statDevloopProposals`, `statReleasesCount`,
  `detailsStackSummary`. Copy is character-exact from the Copy section of
  `requirements.md`. Do not touch `statReleases` or `statServices`.
  — DoD: `npm test` passes (`test/ui.test.ts` accepts every new entry);
  `npm run check` is clean; the home page's rendered `What I run` list is
  byte-identical to before.

- [ ] 2. Create `src/components/CycleDiagram.astro` (depends on 1). Two sibling
  top-level `<svg>` roots, `cycle-wide` (`viewBox="0 0 740 300"`, five nodes
  left-to-right on the top row, five right-to-left on the bottom row, a
  connector down the right margin and a return connector up the left margin
  back to `Issue`) and `cycle-narrow` (`viewBox="0 0 320 700"`, one column of
  ten nodes with the return path in the left gutter). Each root carries
  `role="img"`, `aria-labelledby="cycle-<variant>-title cycle-<variant>-desc"`,
  a `viewBox`, and no `width`/`height` attribute. Each contains exactly one
  `<title id="cycle-<variant>-title">` and one `<desc id="cycle-<variant>-desc">`
  holding the `EN / RU` joined strings from `ui.cycleTitle` / `ui.cycleDesc`.
  Each node is a `<g class="cycle-node">` (or `cycle-node is-gate` for
  `Approve` and `Review gate`) with one `<rect>` and the pair
  `<text class="l en">` / `<text class="l ru" lang="ru">`, labels read from
  `ui.cycleNodes`. Arrowheads are a `<marker>` in each variant's own `<defs>`
  with a variant-suffixed id. No nested `<svg>`, no `style` attribute, no
  colour literal, no `--font-editorial`, no import of `metrics.json`.
  — DoD: the component renders in `astro dev` at both breakpoints; every id in
  the document is unique; the file contains no `#`-colour, `rgb(`, `hsl(`,
  `<image`, `data:` or `xlink:href`.

- [ ] 3. Add the diagram CSS to `src/styles/site.css` (depends on 2), as one
  commented block after the work-page rules: `.cycle`, `.cycle-svg`
  (`display:block; width:100%; height:auto; color: var(--surface-fg)`),
  narrow-first variant toggle with `.cycle-wide { display: none }` and a
  `@media (min-width: 600px)` block that flips it, `.cycle-node rect`
  (`fill: var(--surface-elevated); stroke: var(--surface-line-strong)`),
  `.cycle-node.is-gate rect` (`stroke: var(--accent); stroke-width: 2;
  stroke-dasharray: 5 4`), `.cycle-node text` (`fill: currentColor;
  font-family: var(--font-display)`; 14px narrow, 13px at the wide breakpoint)
  and `.cycle-edges path` (`fill: none; stroke: currentColor`). No `<style>`
  element anywhere. — DoD: `npm run vendor` regenerates
  `public/styles/site.css` with the same block, and that file is committed;
  no rule uses a colour literal.

- [ ] 4. Create `src/pages/approach.astro` (depends on 1, 2, 3). `<Base
  title={ui.approachPageTitle.en}>`, `<h1>` from `ui.navApproach`, intro
  paragraph from `ui.approachIntro`, `<figure class="cycle"><CycleDiagram /></figure>`,
  then three `<Details>` blocks in order: `Gates` (two `<ul class="l en">` /
  `<ul class="l ru" lang="ru">` over `ui.detailsGatesItems`), `Numbers`
  (`<div class="stats">` with three `<Stat>` — `devloop_proposals`, `services`,
  `releases` — and the `.stat-caption` line built from `ui.statCaptionPrefix`
  and `snapshotDate(metrics.generated_at)`), `Proven open source` (two `<ul>`
  over `ui.detailsStackItems`). — DoD: `/approach/` builds; the template region
  contains no digit once `<h1>`…`<h6>` tag names are stripped; all three stats
  render the em dash against the current placeholder `metrics.json`.

- [ ] 5. Point the navigation at the new route (depends on 4): in
  `src/components/Nav.astro`, change `href="/#approach"` to `href="/approach/"`.
  — DoD: no occurrence of `/#approach` remains in `src/`.

- [ ] 6. Extend `scripts/check-dist.mjs` with a `checkApproachPage()` pass
  (depends on 4), in the file's existing problem-string style, covering
  `dist/approach/index.html`: at least two `<svg` roots; summed
  `<svg>…</svg>` byte length under 12288; no `<image`, `data:`, `xlink:href`
  or raster file extension in any slice; no `#rrggbb`, `rgb(` or `hsl(` in any
  slice; every slice has `role="img"`, an `aria-labelledby` whose id tokens all
  resolve to a `<title>`/`<desc>` `id` inside the same slice, and exactly one
  `<title` and one `<desc`; every slice has a `viewBox` and no root
  `width=`/`height=`; per-slice `class="l en"` and `class="l ru"` counts are
  equal; the narrow slice's `viewBox` width is at most 360. Keep the existing
  whole-`dist/` checks and the 40 KB cap on `dist/index.html` untouched, and
  extend the success line to report the measured SVG byte total.
  — DoD: `npm run build && node scripts/check-dist.mjs` exits 0 and prints the
  SVG byte total; deliberately breaking any one condition makes it exit 1 with
  a message naming that condition.

- [ ] 7. Add `test/approach.test.ts` and register it in the `test` script of
  `package.json` (depends on 4, 5), after `test/work.test.ts`. — DoD:
  `npm test` runs eight files and passes.

- [ ] 8. Add the journal entry
  `src/content/journal/2026-09-11-approach-page.md` (depends on 4) with exactly
  the frontmatter given in `requirements.md`, including
  `issue_opened_at: '2026-09-10T22:48:15Z'` and the approval timestamp.
  — DoD: `npm run check` passes the `journal` collection's `strictObject`
  schema; the entry is `visibility: public` and names no credential, internal
  hostname or third party.

- [ ] 9. Full local gate (depends on 1-8): `npm run check`, `npm test`,
  `npm run build`, `node scripts/check-dist.mjs`, `docker build .`.
  — DoD: all five succeed on a clean checkout; the commit is a conventional
  `feat:` with no `!` and no `BREAKING CHANGE`.

## Tests

- [ ] T1. `approach.astro` imports `../data/metrics.json`, has exactly three
  `<Stat` tags, and every `value=` expression matches `/^metrics\.sources\./`
  (mirrors `test/home.test.ts`).
- [ ] T2. The template region of `approach.astro` (everything after the
  frontmatter fence), with `<h1>`…`<h6>` tag names stripped, contains no digit.
- [ ] T3. `CycleDiagram.astro` does not reference `data/metrics.json` and
  contains no `<Stat`.
- [ ] T4. Neither `approach.astro` nor `CycleDiagram.astro` references
  `--font-editorial`, and neither contains `tabindex`.
- [ ] T5. `CycleDiagram.astro` contains no colour literal (`#` hex, `rgb(`,
  `hsl(`), no `style=` attribute, no `<image`, no `data:`, no `xlink:href`.
- [ ] T6. `CycleDiagram.astro` contains exactly two `role="img"` occurrences,
  two `aria-labelledby=`, two `<title`, two `<desc`, and no `width=`/`height=`
  attribute on an `<svg` tag.
- [ ] T7. `ui.cycleNodes.en` and `.ru` each have ten entries and the first
  entry of both is `Issue`; `ui.detailsGatesItems` has four per language.
- [ ] T8. `ui.detailsStackItems.en` starts with the full `ui.detailsRunItems.en`
  array and ends with `['Claude Agent SDK','release-please','Astro','nginx']`;
  same for `ru`; both sides have thirteen entries.
- [ ] T9. `Nav.astro` matches `href="/approach/"` and does not match `/#approach`.
- [ ] T10. `src/styles/site.css` contains `@media (min-width: 600px)`, a
  `.cycle-svg` rule with `width: 100%` and `height: auto`, and a
  `.cycle-node.is-gate` rule using `var(--accent)`; and
  `public/styles/site.css` is byte-identical to `src/styles/site.css`.
- [ ] T11. Post-build (`scripts/check-dist.mjs`): every assertion listed in
  task 6 against `dist/approach/index.html`.
- [ ] T12. Post-build: the existing whole-file `class="l en"` / `class="l ru"`
  parity check passes for `dist/approach/index.html` (criterion 5) and no `.js`
  file appears under `dist/`.

### Reviewer steps (human, not gated by CI)

- [ ] R1. `/approach/` at a 360 px viewport, dark and light: diagram readable,
  no horizontal scroll.
- [ ] R2. Contrast tool on the rendered node labels and gate strokes in both
  themes; expect about 15.9:1 and 15.2:1 for text, 5.4:1 and 4.8:1 for the
  accent stroke.
- [ ] R3. Screen-reader confirmation of the diagram's name and description —
  recorded in `docs/accessibility-checklist.md` in P8, not this cycle.

## Rollback

Every change is additive except one line in `src/components/Nav.astro` and the
`test` script line in `package.json`, so rollback is a revert of the single
merge commit: `git revert -m 1 <merge-sha>`, opened as a pull request like any
other change (`main` takes merge commits only and has no administrator bypass).
That removes `src/pages/approach.astro`, `src/components/CycleDiagram.astro`,
`test/approach.test.ts`, the journal entry, the `site.css` block and its
vendored copy, the `check-dist.mjs` pass, and restores the `/#approach` nav
href. Nothing outside the repository is touched: no migration, no gitops
values, no secret, no DNS record. If the page is already deployed, the revert's
release tag redeploys through the normal `release-deploy` path; if a faster
step is needed, `mctl_rollback_service` back to the previous image tag restores
the site without a code change, and `/approach/` then 404s through nginx's
existing `error_page 404 /404.html`, which is the pre-P6 state.
