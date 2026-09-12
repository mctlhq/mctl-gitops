# Tasks: issue-47-q3-work-hides-repository-links-inside-co

- [ ] 1. Add the `workPrivateRepo` copy key to `src/i18n/ui.ts`
  (`en: 'private repo'`, `ru: 'приватный репозиторий'`), placed with the other
  `work*` keys — DoD: `npm test` green, including `test/ui.test.ts`'s
  "every ui entry has a non-empty en and ru of the same kind".

- [ ] 2. Add `chipRu(chip: string): string` and `chipIsKnown(chip: string):
  boolean` to `src/i18n/ui.ts`, both using `Object.hasOwn(stackChipRu, chip)`
  (depends on nothing) — DoD: exported as plain functions next to
  `stackChipRu` / `stackChipUntranslated`, not as `ui` keys;
  `chipRu('constructor') === 'constructor'`; `chipIsKnown('constructor') ===
  false`; `chipRu('design tokens') === 'дизайн-токены'`; `npx astro check`
  clean.

- [ ] 3. Add the `.visually-hidden` utility to `src/styles/site.css`, exactly
  as specified in design.md (`position: absolute; inline-size: 1px;
  block-size: 1px; margin: -1px; padding: 0; border: 0; overflow: hidden;
  clip-path: inset(50%); white-space: nowrap;`) with the comment explaining
  why `display: none` is wrong — DoD: no `animation`/`transition` and no
  colour declaration added; `test/a11y.test.ts` and
  `node scripts/check-contrast.mjs` green.

- [ ] 4. Extend `src/components/Details.astro` with optional `suffixEn` /
  `suffixRu` props rendered as `<span class="visually-hidden">, <Lang
  en={suffixEn} ru={suffixRu} /></span>` inside the `<summary>`, after the
  existing `<Lang>` (depends on 3) — DoD: the six existing call sites in
  `src/pages/index.astro` and `src/pages/approach.astro` are not edited and
  their rendered markup is unchanged; `.block` and `open` behaviour untouched.

- [ ] 5. Rewrite the `src/components/ProjectCard.astro` template per design.md
  (depends on 1, 2, 4): `.project-links` and `.project-metrics` at card level
  after `<ul class="chips">` and before `<Details>`; `<ul class="project-links">`
  gated on `hasLinks = Boolean(en.data.repo) || links.length > 0`;
  `<p class="project-metrics">` gated on `en.data.repo`; the private-repo chip
  (`<ul class="chips"><li class="chip"><Lang …workPrivateRepo… /></li></ul>`)
  rendered when `!en.data.repo`; the hand-written `<details>`/`<summary>`
  replaced by `<Details summaryEn summaryRu suffixEn={en.data.name}
  suffixRu={ru.data.name}>` wrapping only `<BodyEn />` / `<BodyRu />`;
  `project-details` dropped; chip guard and lookup switched to `chipIsKnown` /
  `chipRu` with the existing error message kept verbatim — DoD: no `<details`
  or `<summary` string remains in the file; `test/projects.test.ts` stays
  green, including the "template contains no digit" and
  `formatStat(repoStats.…)` assertions.

- [ ] 6. Render the metrics line as four parts separated by the literal ` · `
  (U+00B7), with `data-stat` on each number span (depends on 5) — DoD: no
  `&middot;` and no `&#`-style entity in the file; `node
  scripts/check-no-metrics.mjs` green; rendered EN line reads `Repository
  metrics · Commits <n> · Releases <n> · Snapshot <date>` and RU reads
  `Метрики репозитория · Коммиты <n> · Релизы <n> · Снимок <date>`, every
  number from `formatStat(repoStats.…)` and the date from
  `snapshotDate(metrics.generated_at)`.

- [ ] 7. Remove `class="work-group"` from both `<section>` elements in
  `src/pages/work.astro`; change nothing else in that file — DoD: `work-group`
  appears nowhere in `src/`; the two `<h2>` group headings and the sort on
  `data.order` are untouched, so `test/work.test.ts`'s existing sort and
  import assertions still pass.

- [ ] 8. Verify the cascade claim rather than assume it (depends on 5): confirm
  that with `.project-links` outside `.block`, `.block ul` and `.block p` no
  longer match, that every declaration on `.project-links` and
  `.project-metrics` is still needed against the UA defaults, and that none is
  therefore removed — DoD: `src/styles/site.css` gains only
  `.visually-hidden`; no `!important` anywhere in the diff; task T2 below
  passes.

- [ ] 9. Run `npm run build` and then `node scripts/check-links.mjs`, and write
  the final commit message with its verbatim output plus one sentence stating
  that `project-details` and `work-group` were dropped (rather than given
  rules) and why (depends on 1-8, T1-T7) — DoD: the commit message contains
  the `check-links:` output lines including the skipped-href listing, and the
  class-name sentence; `npm run build` exits 0 and `node
  scripts/check-dist.mjs` reports equal `class="l en"` / `class="l ru"` counts
  and no `.js` under `dist/`.

## Tests

All in `test/work.test.ts` unless stated. No existing assertion in any file is
weakened or deleted.

- [ ] T1. Structure: in `src/components/ProjectCard.astro`, the
  `<ul class="project-links"` and `<p class="project-metrics"` occurrences
  both appear before the `<Details` opening tag and neither appears between
  `<Details` and `</Details>`; the file contains no `<details` and no
  `<summary` string, and no `project-details`.

- [ ] T2. Cascade: a miniature resolver over the real `src/styles/site.css`
  (modelled on `test/link-cascade.test.ts`'s `parseTopLevelRules` /
  `specificity`) seeded with the UA `ul` default
  (`padding-inline-start: 40px`) resolves `padding-inline-start` to `0` for an
  element with `class="project-links"` whose ancestor chain is
  `article.project`, and resolves it to `var(--mctl-space-5)` for the same
  element placed under `details.block` — so the test proves the move is what
  fixed it, not a coincidence. Also asserts `site.css` contains no
  `!important` on any `.project-` selector.

- [ ] T3. Empty-list gating: `ProjectCard.astro` gates the `<ul
  class="project-links">` on a `hasLinks`-style expression covering both
  `en.data.repo` and `links.length`, and gates `<p class="project-metrics">`
  on `en.data.repo`; `pfeifenpatenschaft-backend.{en,ru}.md` carry neither
  `repo:` nor `links:` (read from `src/content/projects/`, the same way
  `test/projects.test.ts` reads them), so those two elements cannot render for
  that slug; the private-repo branch renders `ui.workPrivateRepo` in both
  languages.

- [ ] T4. Distinct accessible names: the fourteen `name:` values in
  `src/content/projects/*.en.md` are distinct (and likewise for `*.ru.md`);
  `ProjectCard.astro` passes `en.data.name` / `ru.data.name` into the
  `<Details>` suffix props; `src/components/Details.astro` renders those props
  inside `<span class="visually-hidden">` within the `<summary>`, after the
  summary `<Lang>`.

- [ ] T5. Visually hidden, not hidden: the `.visually-hidden` rule in
  `src/styles/site.css` declares neither `display: none` nor
  `visibility: hidden`, and does declare a clipping property
  (`clip-path`) plus `position: absolute`.

- [ ] T6. Chip lookup: `chipRu('constructor') === 'constructor'`,
  `chipRu('toString') === 'toString'`, `chipRu('__proto__') === '__proto__'`,
  `chipIsKnown('constructor') === false`, `chipRu('design tokens') ===
  'дизайн-токены'`, `chipIsKnown('TypeScript') === true`; and
  `ProjectCard.astro` contains no `in stackChipRu` and no
  `stackChipRu[` indexing.

- [ ] T7. Anchored chip literals: replace the unanchored `CHIP_LITERALS` loop
  with `stripComments(source)` plus the anchored pattern
  `(?:'|"|\`|>)\s*<escaped>\s*(?:'|"|\`|<)`, asserted against both
  `work.astro` and `ProjectCard.astro`; add two control assertions — a
  synthetic source whose only occurrence of `TypeScript` is inside a `//`
  comment and inside a `<!-- -->` comment passes, and a synthetic source
  containing `stack: ["TypeScript"]` fails.

- [ ] T8. Metrics separators: `ProjectCard.astro` contains the literal `·`
  character and no `&middot;` / `&#183;` / `&#xB7;`; the four parts each go
  through `<Lang>` (so the `.l.en` / `.l.ru` counts stay equal) and the
  numbers still come from `formatStat(repoStats.commits)` and
  `formatStat(repoStats.releases)`.

- [ ] T9. Whole-suite gates (no new file): `npm test` green;
  `npm run build` green; `node scripts/check-dist.mjs` green;
  `node scripts/check-links.mjs` green.

## Rollback

The change touches six source files and creates no state, no migration and no
build artifact beyond the next image. `git revert` of the merge commit
restores the previous `/work/` markup exactly; the next `release-please`
release and `mctl_deploy_service` cycle ships it, or
`mctl_rollback_service team=<team> component_name=portfolio
target_tag=<previous tag>` restores the previously deployed image immediately
while the revert makes its way through CI. Nothing in `src/data/metrics.json`,
`src/content/**` or the content schema changes, so no content or data has to
be rolled back with it. If only the accessible-name suffix proves wrong, the
`suffixEn` / `suffixRu` props are optional: dropping the two attributes at the
`<Details>` call site in `ProjectCard.astro` reverts that item alone and
leaves the rest of the cycle in place.
