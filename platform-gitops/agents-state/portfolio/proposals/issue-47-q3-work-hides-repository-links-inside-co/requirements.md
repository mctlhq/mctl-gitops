# Q3: lift repository links and metrics out of the /work/ disclosure

## Context

On `/work/` every one of the fourteen project cards renders its repository
link, its extra links and its metrics line inside a collapsed
`<details class="block project-details">` (`src/components/ProjectCard.astro`).
A reader scanning the page sees fourteen identical `Details` summaries and not
a single repository URL, even though opening the code is the main action a
portfolio page exists to offer. The same component hand-writes a
`<details>`/`<summary>` pair that `src/components/Details.astro` already
renders, gives every summary the same accessible name (`ui.workDetailsSummary`
— `Details` / `Подробнее`), ships an empty `<ul class="project-links"></ul>`
plus `Commits —, Releases —` for the one project that has no repository
(`pfeifenpatenschaft-backend`), and looks chips up with `chip in stackChipRu`,
which walks the prototype chain.

This proposal moves `.project-links` and `.project-metrics` to card level,
gates both on real data, gives the metrics line visible separators, replaces
the hand-written disclosure with `Details.astro`, gives each summary a
distinct accessible name, removes two class names that no rule matches, fixes
the chip lookup, and anchors the chip-literal assertions in
`test/work.test.ts` so they test what they claim to test. Nothing about the
content of a card changes; only where the elements sit, when they render, and
how they read.

## User stories

- AS a visitor scanning `/work/` I WANT each project's repository link to be
  visible without opening anything SO THAT I can go to the code in one click.
- AS a screen-reader user listing the controls on `/work/` I WANT each
  disclosure to have a distinct accessible name SO THAT fourteen rows do not
  all announce as "Details".
- AS a screen-reader user reading the card of a project with no public
  repository I WANT a stated absence SO THAT I do not meet an empty list and
  two em dashes where a link and numbers should be.
- AS a reader of the metrics line I WANT the parts visually separated SO THAT
  `Commits 542` and `Releases 93` do not read as one run of prose.
- AS a maintainer of this repository I WANT one disclosure component and one
  chip-lookup path SO THAT the two `<details>` widgets and the two chip
  code paths cannot drift apart.
- AS a reviewer of `test/work.test.ts` I WANT the chip assertions anchored SO
  THAT they fail on a hard-coded chip and pass on a chip named in a comment.

## Copy (the contract)

Existing keys in `src/i18n/ui.ts`, reused unchanged:

| Key | en | ru |
| --- | --- | --- |
| `workDetailsSummary` | `Details` | `Подробнее` |
| `workMetricsLabel` | `Repository metrics` | `Метрики репозитория` |
| `statCommits` | `Commits` | `Коммиты` |
| `statReleases` | `Releases` | `Релизы` |
| `statCaptionPrefix` | `Snapshot` | `Снимок` |

One new key in `src/i18n/ui.ts`:

| Key | en | ru |
| --- | --- | --- |
| `workPrivateRepo` | `private repo` | `приватный репозиторий` |

Separator between metrics parts: the literal character ` · ` — one space,
U+00B7 MIDDLE DOT, one space. It is written as the character itself, never as
`&middot;` and never as a numeric entity such as `&#183;` (a numeric entity
would put digits into a template and fail both
`node scripts/check-no-metrics.mjs` and the "no digit in the ProjectCard
template" assertion in `test/projects.test.ts`).

Rendered metrics line, with the numbers and the date coming from
`src/data/metrics.json` through `formatStat(...)` and `snapshotDate(...)`:

- en: `Repository metrics · Commits 542 · Releases 93 · Snapshot 2026-09-11`
- ru: `Метрики репозитория · Коммиты 542 · Релизы 93 · Снимок 2026-09-11`

Accessible name appended to each `<summary>`, inside a visually hidden span,
as the literal `, ` followed by the project's `name` for that language:

- en: `Details, mctl-api`
- ru: `Подробнее, mctl-api`

## Acceptance criteria (EARS)

1. WHEN `/work/` is built THE SYSTEM SHALL render each card's
   `<ul class="project-links">` and `<p class="project-metrics">` as children
   of `<article class="project">`, positioned after `<ul class="chips">` and
   before the disclosure element, never inside it.
2. WHEN a project's `en.data.repo` is set THE SYSTEM SHALL render its
   repository link inside `.project-links` with no reader interaction.
3. IF a project has neither `repo` nor a non-empty `links` array THEN THE
   SYSTEM SHALL render no `<ul class="project-links">` element at all.
4. IF a project's `en.data.repo` is absent THEN THE SYSTEM SHALL render no
   `<p class="project-metrics">` element at all.
5. IF a project's `en.data.repo` is absent THEN THE SYSTEM SHALL render, in
   the position the links and metrics would have occupied, exactly one chip
   reading `private repo` / `приватный репозиторий`.
6. WHEN the metrics line renders THE SYSTEM SHALL emit the label, the commits
   part, the releases part and the snapshot part as discrete parts separated
   by ` · `, with every number produced by `formatStat(...)` over the result
   of `repoMetrics(...)` and the date by `snapshotDate(metrics.generated_at)`.
7. WHILE `src/components/ProjectCard.astro` exists THE SYSTEM SHALL contain no
   hand-written `<details>` or `<summary>` element in it; the disclosure SHALL
   be rendered by `src/components/Details.astro`.
8. WHEN a card's disclosure renders THE SYSTEM SHALL give its `<summary>` an
   accessible name that is `ui.workDetailsSummary` for the active language
   followed by `, ` and that project's `name`, contributed by a span that is
   visually hidden but present in the accessibility tree (not `display: none`
   and not `visibility: hidden`).
9. WHILE the fourteen project slugs are what `test/projects.test.ts` lists THE
   SYSTEM SHALL yield fourteen distinct summary accessible names.
10. WHEN `ProjectCard` resolves a stack chip's Russian text THE SYSTEM SHALL
    use `Object.hasOwn(stackChipRu, chip)`, so a chip named `constructor`,
    `toString`, `__proto__` or `valueOf` resolves to the chip string itself
    and never to an inherited `Object.prototype` member.
11. IF a chip is present in neither `stackChipRu` (own property) nor
    `stackChipUntranslated` THEN THE SYSTEM SHALL keep failing the build with
    the existing `ProjectCard (<slug>): stack chip "<chip>" has no Russian
    translation …` error.
12. WHILE `src/styles/site.css` exists THE SYSTEM SHALL contain no `!important`
    added by this change, and THE SYSTEM SHALL resolve `padding-inline-start`
    on a `.project-links` element that has no `.block` ancestor to `0`.
13. WHILE `src/styles/site.css` exists THE SYSTEM SHALL contain a rule for
    every class name emitted by `src/components/ProjectCard.astro` and
    `src/pages/work.astro`, or those class names SHALL be removed from the
    markup — specifically `project-details` and `work-group`.
14. WHEN the chip-literal assertions in `test/work.test.ts` run THE SYSTEM
    SHALL fail on a chip literal appearing as a quoted string or as element
    text in `work.astro` or `ProjectCard.astro`, and SHALL pass when the same
    literal appears only inside a comment.
15. WHEN `npm test` runs THE SYSTEM SHALL be green, including
    `node scripts/check-no-metrics.mjs`, `node scripts/check-contrast.mjs`,
    `test/projects.test.ts` (no digit in the ProjectCard template),
    `test/a11y.test.ts` (no `animation`/`transition` in `site.css`,
    `min-block-size` on `.block > summary`) and `test/link-cascade.test.ts`,
    with no existing assertion weakened or deleted.
16. WHEN `npm run build` runs THE SYSTEM SHALL succeed, and
    `node scripts/check-dist.mjs` SHALL report equal `class="l en"` and
    `class="l ru"` counts for `dist/work/index.html` and no `.js` file under
    `dist/`.
17. WHEN the final commit of this cycle is written THE SYSTEM SHALL carry, in
    its message, the verbatim output of `node scripts/check-links.mjs` run
    against the `dist/` tree of that commit, and a sentence naming which of
    `project-details` / `work-group` was dropped or given rules, and why.

## Out of scope

- CSP hash quoting and the header guards (separate cycle, may already have
  landed).
- Content link colour and contrast (settled by issue #55; the
  `.project-links a` cascade pins in `src/styles/site.css` and their
  `test/link-cascade.test.ts` resolver stay exactly as they are).
- Colophon tables, timestamps, lead time.
- Navigation state, skip-link, `role="group"`, toggle spacing, which blocks
  open by default (`Details.astro`'s `open` prop keeps defaulting to `false`).
- `og:image`, font preload, `Cache-Control`, the DevLoop diagram, the hero
  name wrap.
- Issue #31 item 7 (`0.5.0` typed into `mctl-design` content).
- Any network-fetching link checker. `docs/link-check.md` records that issue
  #46 / PR #54 closed unmerged over exactly that requirement and that issue
  #55 replaced it with the internal-only `scripts/check-links.mjs`;
  reintroducing outbound HTTP checks would re-create the flake that decision
  removed. Criterion 17 is therefore met with the existing
  `scripts/check-links.mjs`, which resolves every internal href on `/work/`
  against `dist/` and lists every off-origin href it skipped.
- Adding a journal entry or a row in `docs/accessibility-checklist.md`. The
  issue's file list names four files and no journal entry exists for the
  preceding cycle (#55) either; see Open questions.

## Open questions

- **The exact metrics wording.** The issue's example line reads
  `Commits 542 · Releases 93 · snapshot 2026-09-11` — without the
  `Repository metrics` label and with a lowercase `snapshot` — while the same
  paragraph says "the label and the snapshot date translated in both
  languages". Resolved by keeping both existing keys unchanged
  (`workMetricsLabel`, `statCaptionPrefix` = `Snapshot` / `Снимок`) and
  separating all four parts with ` · `, so no new translation is invented and
  the wording stays consistent with the home page's `Snapshot <date>` caption.
  The exact rendered strings are fixed in the Copy section above.
- **HTTP 200 on every link (issue criterion 8).** Answered above under Out of
  scope: satisfied by `scripts/check-links.mjs` output pasted into the final
  commit message, not by a new network checker. A reviewer who disagrees
  should say so before approval, because the alternative reopens a question
  this repository has already closed twice.
- **Proving fourteen distinct accessible names (issue criterion 5).**
  `npm test` runs before `astro build` (`prebuild` is
  `npm run vendor && npm test`), so no source-level test can read the built
  markup. Proved compositionally in `test/work.test.ts`: the fourteen
  `name:` values in `src/content/projects/*.en.md` are distinct, and
  `ProjectCard.astro` passes each project's `name` into the `Details` suffix
  props which `Details.astro` renders inside the visually hidden span.
- **Journal entry.** AGENTS.md asks for one journal entry per DevLoop cycle,
  but the issue's file list omits it and `src/content/journal/` carries no
  entry for the previous cycle either. This proposal follows the issue's file
  list. If the reviewer wants the entry, it is one added file and no change
  to anything else here.
- **Files beyond the issue's list.** Items 5, 6 and 3/4 cannot be implemented
  inside the four named files alone: `src/components/Details.astro` needs the
  suffix props (the issue explicitly allows this — "if `Details.astro` needs a
  prop for this, add one") and `src/i18n/ui.ts` needs the `workPrivateRepo`
  key and the chip-lookup helpers. Both are additive.
