# Design: issue-47-q3-work-hides-repository-links-inside-co

## Current state

### `src/components/ProjectCard.astro`

One `<article class="project">` per project, built from the `en` and `ru`
entries of the `projects` content collection. Its template today is:

```
<article class="project" id={en.data.slug}>
  <h3 class="project-name">…</h3>
  <p class="project-summary"><Lang …/></p>
  <ul class="chips"> … one <li class="chip"> per stack chip … </ul>
  <details class="block project-details">
    <summary><Lang en={ui.workDetailsSummary.en} ru={ui.workDetailsSummary.ru} /></summary>
    <div class="l en"><BodyEn /></div>
    <div class="l ru" lang="ru"><BodyRu /></div>
    <ul class="project-links"> … </ul>
    <p class="project-metrics"> … </p>
  </details>
</article>
```

Four defects live in this block:

- The repository link and every extra link are inside the collapsed
  `<details>`, as is the metrics line.
- The `<details>`/`<summary>` pair duplicates `src/components/Details.astro`,
  which renders exactly `<details class="block" open={open}><summary><Lang …
  /></summary><slot /></details>` and is already used six times across
  `src/pages/index.astro` and `src/pages/approach.astro`.
- Both `<ul class="project-links">` children are conditional
  (`{en.data.repo && …}` and `{links.map(…)}`), but the `<ul>` itself is
  unconditional, so `pfeifenpatenschaft-backend` — the only project whose
  content files carry neither `repo:` nor `links:`
  (`src/content/projects/pfeifenpatenschaft-backend.{en,ru}.md`, asserted by
  `test/projects.test.ts`) — ships `<ul class="project-links"></ul>`. Its
  metrics line renders through `repoMetrics(metrics, undefined)`, which
  `src/lib/metrics.ts` documents as returning an all-null `MetricRepo`, so
  `formatStat(null)` produces the `EM_DASH` twice.
- The frontmatter guard uses `chip in stackChipRu` and the template uses
  `stackChipRu[chip] ?? chip`. `stackChipRu` is a plain object literal
  (`src/i18n/ui.ts`), so both expressions see `Object.prototype`: a chip named
  `constructor` passes the guard and renders `stackChipRu['constructor']` —
  a function — into the `.l.ru` span.

### `src/styles/site.css`

`.block ul { margin: 0; padding-inline-start: var(--mctl-space-5) }` and
`.block p { margin-block-end: var(--mctl-space-2) }` are descendant selectors
with specificity (0,1,1); `.project-links` and `.project-metrics` are (0,1,0).
While the two elements sit inside the `<details class="block">`, the
`.block ul` rule wins on `margin` and `padding-inline-start`, so three of the
four declarations on `.project-links` are dead and `.project-metrics`'s
`margin: 0` is overridden on the block-end side. Nothing in the file matches
`project-details` (`ProjectCard.astro`) or `work-group`
(`src/pages/work.astro`); both class names are inert. There is no
visually-hidden utility anywhere in `src/styles/site.css` or in the vendored
`public/assets/mctl/*.css`.

### Gates this change has to stay inside

- `npm test` = `check-no-metrics.mjs` + `check-contrast.mjs` + twenty test
  files, and it runs from `prebuild`, i.e. **before** `astro build`. No
  source-level test can read `dist/`.
- `scripts/check-no-metrics.mjs` fails on any `\b[0-9]{2,}\b` in
  `src/pages`, `src/components`, `src/layouts` that no RULES classifier or
  ALLOW entry covers.
- `test/projects.test.ts` asserts the `ProjectCard.astro` template (everything
  after the frontmatter fence) contains no digit at all once `<h1>`–`<h6>` tag
  names are stripped, and that commits/releases render only through
  `formatStat(repoStats.…)`.
- `test/a11y.test.ts` asserts `min-block-size >= 24px` on `.block > summary`
  and that `site.css` declares no `animation`/`transition` anywhere.
- `test/link-cascade.test.ts` resolves the `main a` / `.cta` /
  `.project-links a` colour families over the real `site.css` and asserts a
  fixed colour table; it also fails loudly on an unrecognised
  `.project-links a…` selector shape.
- `scripts/check-dist.mjs` (post-build, run in CI via `npm run build` plus the
  workflow's own steps) requires equal `class="l en"` / `class="l ru"` counts
  in every `dist/**/*.html` and no `.js` under `dist/`.
- `scripts/check-links.mjs` (post-build, `.github/workflows/build.yml`)
  resolves every internal href against `dist/` and lists every skipped
  off-origin href. `docs/link-check.md` records why it makes no network
  request.
- `src/styles/site.css` is copied to the gitignored
  `public/styles/site.css` by `npm run vendor` on every `prebuild`; nothing
  under `public/styles/` is committed.

## Proposed solution

### 1. Card structure

`ProjectCard.astro` renders, in order: `<h3 class="project-name">`,
`<p class="project-summary">`, `<ul class="chips">`, then the links/metrics
group, then `<Details …>` carrying only `<BodyEn />` / `<BodyRu />`:

```
<article class="project" id={en.data.slug}>
  <h3 class="project-name">…</h3>
  <p class="project-summary">…</p>
  <ul class="chips">…stack chips…</ul>

  {hasLinks && <ul class="project-links"> … </ul>}
  {en.data.repo && <p class="project-metrics"> … </p>}
  {!en.data.repo && (
    <ul class="chips">
      <li class="chip"><Lang en={ui.workPrivateRepo.en} ru={ui.workPrivateRepo.ru} /></li>
    </ul>
  )}

  <Details
    summaryEn={ui.workDetailsSummary.en}
    summaryRu={ui.workDetailsSummary.ru}
    suffixEn={en.data.name}
    suffixRu={ru.data.name}
  >
    <div class="l en"><BodyEn /></div>
    <div class="l ru" lang="ru"><BodyRu /></div>
  </Details>
</article>
```

with `const hasLinks = Boolean(en.data.repo) || links.length > 0;` in the
frontmatter. Gating on `hasLinks` rather than on `repo` alone keeps the `<ul>`
for a hypothetical future project that has extra links but no public
repository; gating the metrics line on `en.data.repo` alone is what criterion
4 of the issue asks for, and matches `repoMetrics`, which can only resolve a
`per_repo` key from a repository URL.

The private-repo chip reuses the existing `.chips` / `.chip` pair as a second
one-item list rather than inventing a new element: `.chip` sets padding, a
border, a pill radius and a muted colour but no `display`, so it only sizes to
its content inside the `display: flex` `.chips` container. This adds no CSS
and keeps the chip visually identical to the stack chips beside it. It is a
separate list, not a fifteenth stack chip, because it states a fact about the
repository rather than naming a technology.

### 2. The `.block` conflict disappears; nothing becomes redundant

Once `.project-links` and `.project-metrics` are children of
`<article class="project">`, no `.block` ancestor exists, `.block ul` and
`.block p` stop matching them, and the elements' own rules become the only
author rules. They are then all load-bearing against the UA defaults
(`ul { margin-block: 1em; padding-inline-start: 40px; list-style: disc }`,
`p { margin-block: 1em }`), so **no declaration is removed**:
`.project-links { list-style: none; margin: 0 0 var(--mctl-space-2);
padding: 0 }` and `.project-metrics { … margin: 0 }` stay exactly as they are.
No `!important` is added anywhere.

"Verify rather than assume" is discharged mechanically, not by inspection: a
miniature cascade resolver in `test/work.test.ts`, modelled on the one already
in `test/link-cascade.test.ts`, parses the real `src/styles/site.css`, seeds
the UA `ul` defaults, applies every top-level rule whose selector matches an
element with `class="project-links"` whose ancestor chain is
`article.project` (and separately, as a control, one whose ancestor chain
includes `details.block`), and asserts the resolved `padding-inline-start` is
`0` in the first case. The structural half — that the element really has no
`.block` ancestor — is asserted against the `ProjectCard.astro` template by
index comparison: both elements appear before the `<Details` opening tag and
neither appears between `<Details` and `</Details>`.

### 3. Metrics line

```
<p class="project-metrics">
  <Lang en={ui.workMetricsLabel.en} ru={ui.workMetricsLabel.ru} /> ·
  <Lang en={ui.statCommits.en} ru={ui.statCommits.ru} /> <span data-stat>{formatStat(repoStats.commits)}</span> ·
  <Lang en={ui.statReleases.en} ru={ui.statReleases.ru} /> <span data-stat>{formatStat(repoStats.releases)}</span> ·
  <Lang en={`${ui.statCaptionPrefix.en} ${snapshot}`} ru={`${ui.statCaptionPrefix.ru} ${snapshot}`} />
</p>
```

The separator is the literal `·` character (U+00B7) in the template — never
`&#183;`, whose digits would trip `check-no-metrics.mjs` and the no-digit
assertion in `test/projects.test.ts`. `data-stat` moves onto each number span
individually, matching `src/components/Stat.astro`, which marks the value and
not the label. Every number still comes from `formatStat(repoStats.…)` and the
date from `snapshotDate(metrics.generated_at)`, so `test/projects.test.ts`'s
existing `formatStat(repoStats.commits)` / `formatStat(repoStats.releases)`
assertions keep passing unchanged.

Bilingual parity is preserved because each translated part is one `<Lang>`
(one `class="l en"` and one `class="l ru"`), and the separators are
language-neutral punctuation outside any `<Lang>`. When a card has no
repository the whole `<p>` disappears in both languages at once, so
`check-dist.mjs`'s per-file count stays balanced.

### 4. `Details.astro` gains two optional suffix props

```
interface Props {
  summaryEn: string;
  summaryRu: string;
  open?: boolean;
  suffixEn?: string;
  suffixRu?: string;
}
```

```
<details class="block" open={open}>
  <summary><Lang en={summaryEn} ru={summaryRu} />{suffixEn && suffixRu && (
    <span class="visually-hidden">, <Lang en={suffixEn} ru={suffixRu} /></span>
  )}</summary>
  <slot />
</details>
```

Both props are optional and default to `undefined`, so the six existing call
sites in `index.astro` and `approach.astro` are untouched and keep rendering
exactly the markup they render today. The component is extended, not forked,
as the issue requires. A bilingual pair is used rather than a single string
because `checkProjectParity` in `src/content.config.ts` deliberately allows
`name` to differ between a slug's `.en.md` and `.ru.md`; passing both also
keeps the `class="l en"` / `class="l ru"` counts equal.

New utility in `src/styles/site.css`:

```
/* Text for assistive technology only: present in the accessibility tree
 * (so a <summary> can carry a distinct accessible name) but not painted.
 * display:none or visibility:hidden would remove it from the tree, which
 * is the whole point of the class. */
.visually-hidden {
  position: absolute;
  inline-size: 1px;
  block-size: 1px;
  margin: -1px;
  padding: 0;
  border: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
```

No `animation`/`transition` (so `test/a11y.test.ts` stays green) and no colour
declaration (so `scripts/check-contrast.mjs` gains no pair). The accessible
name of each summary becomes `Details, mctl-api` / `Подробнее, mctl-api`,
because the inactive language half is `display: none` (the `:root[data-lang]`
rules at the top of `site.css`) and display-none text is excluded from name
computation, while `.visually-hidden` text is not. Fourteen distinct project
names give fourteen distinct names.

### 5. Chip lookup moves into `src/i18n/ui.ts` as two pure functions

```
export function chipRu(chip: string): string {
  return Object.hasOwn(stackChipRu, chip) ? stackChipRu[chip] : chip;
}
export function chipIsKnown(chip: string): boolean {
  return Object.hasOwn(stackChipRu, chip) || stackChipUntranslated.has(chip);
}
```

`ProjectCard.astro` calls `chipIsKnown(chip)` in its build-time guard (keeping
the existing error message verbatim) and `chipRu(chip)` in the template. Two
call sites become one implementation, and — unlike a source-level grep for
`Object.hasOwn` — a test can call `chipRu('constructor')` and assert it
returns the string `'constructor'`. These are plain function exports, not
`ui` keys, so `test/ui.test.ts`'s "every `ui` entry is an `{en, ru}` pair"
loop is unaffected, exactly as `stackChipRu` and `stackChipUntranslated`
already are.

### 6. Two dead class names: both dropped

- `project-details` disappears with the hand-written `<details>`;
  `Details.astro` writes its own `class="block"` and accepts no class prop.
- `work-group` is removed from both `<section>` elements in
  `src/pages/work.astro`. The two sections need no box of their own: `.project`
  already draws the separating `border-top`, and the `<h2>` inside each
  section carries the group heading. Giving the class rules would mean
  inventing spacing the design does not ask for.

The choice and its reason go into the final commit message (issue criterion 7,
AGENTS.md permits a commit-message requirement; a pull-request-body
requirement would not be satisfiable by the implementer).

### 7. Anchored chip-literal assertions in `test/work.test.ts`

The current assertion builds `new RegExp(escaped)` and asserts the literal
appears nowhere in the file — so it also fires on a comment, and it says
nothing about the literal being *hard-coded* as opposed to merely mentioned.
Replaced by:

- `stripComments(source)` — removes `<!-- … -->`, `/* … */` and `// …` — so a
  chip named in a comment cannot fail the test;
- an anchored pattern `(?:'|"|\`|>)\s*<escaped>\s*(?:'|"|\`|<)`, which matches
  a chip appearing as a quoted string literal or as element text and nothing
  else;
- two control assertions proving the anchor means what it claims: a synthetic
  source whose only occurrence is inside a comment passes, and a synthetic
  source containing `stack: ["TypeScript"]` fails.

### Files changed

| File | Why |
| --- | --- |
| `src/components/ProjectCard.astro` | items 1, 3, 4, 5, 6, 7, 8 |
| `src/pages/work.astro` | item 7 (`work-group`) |
| `src/styles/site.css` | `.visually-hidden`; verification that nothing else changes |
| `test/work.test.ts` | items 2, 5, 6, 8, 9 coverage |
| `src/components/Details.astro` | item 6 (the prop the issue authorises) |
| `src/i18n/ui.ts` | `workPrivateRepo` copy, `chipRu` / `chipIsKnown` |

## Alternatives

1. **Raise specificity on `.project-links` (e.g. `.block .project-links`, or
   `!important`) and leave the markup where it is.** Rejected: the issue
   forbids `!important` explicitly, and either variant fixes the CSS symptom
   while leaving the actual defect — the links being invisible until a reader
   opens a disclosure — completely untouched.

2. **Keep the hand-written `<details>` in `ProjectCard.astro` and add the
   visually hidden span there.** Rejected: it leaves two disclosure
   implementations that must be kept in step by convention, which is exactly
   what issue #31 item 4 complained about. `Details.astro` already takes a
   slot and needs one additive, optional prop pair to serve both call sites.

3. **Render the private-repo state as prose (`<p class="project-metrics">
   private repo</p>`) instead of a chip.** Rejected: the issue asks for a
   chip, and reusing `.chips`/`.chip` costs no new CSS while keeping the
   absence visually parallel to the stack chips a reader is already scanning.
   A `<p>` would also need its own rule to avoid the UA `1em` block margin.

4. **Prove the fourteen distinct accessible names and the zero computed
   padding in `scripts/check-dist.mjs` against the built HTML.** Rejected for
   this cycle: `check-dist.mjs` is outside the issue's file list, and the
   composition of a source-level structural assertion plus the cascade
   resolver gives the same guarantee inside `npm test`, where it fails a
   pull request before a build even runs. Worth revisiting if a later cycle
   touches `check-dist.mjs` anyway.

5. **Add a network link checker for criterion 8.** Rejected: see
   `docs/link-check.md`. Issue #46 / PR #54 closed unmerged over precisely
   this, and issue #55 replaced it with the internal-only checker. The
   criterion is met by pasting `scripts/check-links.mjs` output into the final
   commit message.

## Platform impact

- **Migrations / data:** none. No content file, no `src/data/metrics.json`
  entry and no schema in `src/content.config.ts` changes.
- **Backward compatibility:** the six existing `<Details>` call sites render
  byte-identically (both new props are optional). `#<slug>` anchors on
  `/work/` still resolve — `id={en.data.slug}` stays on the `<article>`.
- **Resource impact:** `dist/work/index.html` grows by roughly fourteen hidden
  spans and thirteen separator runs, on the order of a kilobyte. Only
  `dist/index.html` has a byte cap (40 KB in `check-dist.mjs`) and it is not
  touched. Still zero JavaScript.
- **Risk: the `.l.en` / `.l.ru` parity check fails.** Mitigation: every new
  translated string goes through `<Lang>`; separators and the `, ` before the
  hidden name are language-neutral punctuation. `check-dist.mjs` catches any
  slip post-build in CI.
- **Risk: a numeric HTML entity for the middle dot trips
  `check-no-metrics.mjs`.** Mitigation: the literal `·` character is mandated
  in requirements.md and asserted by a `test/work.test.ts` case that the
  template contains no `&#`-style entity.
- **Risk: `test/link-cascade.test.ts` fires on a changed
  `.project-links a…` selector.** Mitigation: this change adds no selector in
  that family and removes none; the colour table is untouched.
- **Risk: `.visually-hidden` written with `display: none` or
  `visibility: hidden` would silently defeat item 6.** Mitigation: a
  `test/work.test.ts` assertion that the `.visually-hidden` rule declares
  neither, and does declare a clipping property.
- **Rollback:** one revert commit; the change is confined to six source files
  with no state, no build artifact and no deployment coupling beyond the next
  image build.
