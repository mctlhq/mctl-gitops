# Design: issue-108-q18-single-icon-button-toggles-replace-t

All verbatim markup, CSS, strings, test bodies and script edits live in
`requirements.md`'s Appendices A-J. This document explains the current state,
the shape of the change and the trade-offs; it does not restate the copy.

## Current state

Read in the clone at `mctlhq/portfolio` @ `main` (version 0.1.30).

### The two components

`src/components/Nav.astro` renders

```
<div class="toggle-bar">
  <LangToggle />
  <ThemeToggle />
</div>
```

inside `<header class="site-header">`, after `<nav class="site-nav">`.

`src/components/LangToggle.astro` and `src/components/ThemeToggle.astro` are
structurally identical to each other: each emits **two**
`<div class="toggle-group … ">` wrappers — one per CSS stance (`l en` / `l ru`
for language, `t dark` / `t light` for theme) — each carrying
`role="group"` and `aria-labelledby` pointing at a single shared
`.visually-hidden` span (`#lang-toggle-label` / `#theme-toggle-label`), and
each holding **two** `<button type="button">` segments with
`data-set-lang` / `data-set-theme` and `aria-pressed="true"` on whichever
segment matches that wrapper's stance. A `<noscript><p>` follows.

So today the header contains eight `<button>` elements in the HTML, four of
which are hidden by CSS at any moment. This cycle takes that to four buttons,
two hidden.

### The stance mechanism

`src/styles/site.css` opens with the only mechanism this site has for
bilingual and theme content:

```css
:root[data-lang='en'] .l.ru { display: none; }
:root[data-lang='ru'] .l.en { display: none; }
:root[data-theme='dark'] .t.light { display: none; }
:root[data-theme='light'] .t.dark { display: none; }
```

`src/layouts/Base.astro` authors `<html lang="en" data-lang="en"
data-theme="dark">` and its single `is:inline` `<head>` script (SHA-pinned in
the CSP) applies `localStorage` values before paint and registers one
delegated `click` listener on `[data-set-lang],[data-set-theme]`. Nothing
re-renders. That is exactly why an accessible name must go through
`aria-labelledby` -> `.visually-hidden` span -> `<Lang>` pair
(`src/i18n/Lang.astro` emits `<span class="l en">…</span><span class="l ru"
lang="ru">…</span>`): the same static HTML serves both a Russian and an
English screen-reader session, and only the CSS stance rules can pick between
them.

### The CSS being replaced

`src/styles/site.css` carries a `/* Toggle groups. */` region with six rules
(`.toggle-group`, `.toggle-group button`, `:first-child`, `:last-child`,
`+ button`, `[aria-pressed='true']`) plus the interleaved `.toggle-bar` and
`.toggle-bar noscript` rules, and — separately, roughly 400 lines further
down under the "Tap targets" comment — a second `.toggle-group button` rule
declaring `display: inline-flex; align-items: center; min-block-size: 32px`.
There is also a `@media print` rule listing
`.site-header, .toggle-group, .ctas { display: none; }`.

### The gates that observe all of this

- `test/a11y.test.ts` — `TARGET_SELECTORS` includes `'.toggle-group button'`
  and requires a `min-block-size` >= 24px for each entry; also asserts the
  global `:focus-visible` rule, the absence of any `animation`/`transition`,
  and the `.toggle-bar` rule.
- `test/header.test.ts` — T1..T6; T4 and T5 describe the segmented container
  and its divider, T6 pins `.toggle-group button` to exactly one 32px
  `min-block-size`. Both this file and `a11y.test.ts` strip `/* … */`
  comments before parsing and use the shared flat-regex parser in
  `test/support/css-rules.ts`, whose `ruleBlockBodies()` matches an exact
  comma-split selector and returns every matching block (including one inside
  `@media print`).
- `test/nav.test.ts` — asserts two `.toggle-group` divs per component, each
  with `role="group"` and `aria-labelledby`, and no `aria-label`.
- `test/ui.test.ts` — every `ui` entry is a non-empty `{ en, ru }` of the
  same kind. It pins specific keys by value but pins neither
  `langToggleLabel` nor `themeToggleLabel`, so removing them is safe.
- `scripts/check-no-metrics.mjs` — first command in `npm test`; fails on any
  `\b[0-9]{2,}\b` under `src/pages`, `src/components`, `src/layouts` that no
  `RULES` classifier and no `ALLOW` entry accounts for, **and** fails on a
  stale `ALLOW` value that matches nothing.
- `scripts/check-contrast.mjs` — second command in `npm test`; resolves
  `SEMANTIC_TOKENS` against the vendored, content-hashed
  `public/assets/mctl/mctl.baf7fec1.css` and checks `PAIRS` in both themes,
  plus thirteen content-link lines. It has no `surface-card` entry today.
- `scripts/check-dist.mjs` — run from `Dockerfile` line 6
  (`RUN npm run build && node scripts/check-dist.mjs && node
  scripts/csp-hash.mjs > …`) and therefore in CI's `build` job.
  `checkApproachPage()` iterates **every** `<svg>` on
  `dist/approach/index.html`.

## Proposed solution

### 1. Markup: two plain buttons per component, one per stance

Each component drops both wrapper `<div>`s and one inner button per stance,
keeping exactly the button that corresponds to that stance and giving it the
*other* stance's `data-set-*` value. The stance classes (`t dark`, `t light`,
`l en`, `l ru`) move from the deleted wrapper onto the button itself, so the
existing four `display: none` rules keep doing all the work with no CSS
change. `aria-pressed` disappears: a single button is not a two-state segment
set, and with the glyph naming the active state there is nothing for it to
express.

The accessible name pattern is unchanged in kind and only multiplied: instead
of one shared `.visually-hidden` label span per component, there are now two
— one per button — because the two buttons no longer share a purpose
("Language") but have distinct ones ("Switch to Russian" / "Switch to
English"). Each span sits as a sibling immediately after its button, and the
`aria-labelledby` id references it. Appendix A / B.

Why buttons and not a link or a single button that cycles: the delegated
listener in `Base.astro` reads `dataset.setLang` / `dataset.setTheme` off the
clicked element, so the target value must be static markup. A single
"cycling" button would need JavaScript to compute the next value, which the
static-output constraint (ADR-0002) rules out.

### 2. Strings: four new `ui` keys, two removed

`themeSwitchToDark` / `themeSwitchToLight` / `langSwitchToEn` /
`langSwitchToRu` replace the two group labels. They are the accessible names,
so they are full sentences ("Switch to dark theme"), not the two-letter
visible labels — `langEn` / `langRu` / `themeDark` / `themeLight` stay for the
visible text and, in the theme toggle's case, are simply no longer referenced
by that component while remaining valid dictionary entries the way
`ctaColophon` and `detailsContactSummary` already are.

Careful reading of the issue: `themeDark`/`themeLight` are named as "still
used (visible label text)". After Appendix A the theme button's visible
content is an SVG, not a `<Lang>` pair, so `themeDark`/`themeLight` become
unreferenced. They are still **not removed** — that is what the issue says,
and the repository already tolerates unreferenced keys by precedent
(`ctaColophon`, `detailsContactSummary`, with `test/ui.test.ts` asserting
they stay). Recorded here so a reviewer does not read it as an oversight.

### 3. CSS: one flat class, no container

`.icon-toggle` is a fixed 32x32 inline-flex box with the border, radius and
background that the deleted `.toggle-group` container used to carry, moved
onto the button itself. `.lang-toggle` adds only typography for the
two-letter label. `.icon-toggle svg` sizes the glyph to 20px inside the 32px
box. There is deliberately no `overflow` anywhere: the Q16 lesson was that an
`overflow: hidden` container clips the `outline-offset` focus ring, and with
no container the problem cannot arise — Appendix D's comment says so, and
Appendix E2's new header test asserts it mechanically so a future edit cannot
reintroduce it.

`--surface-card` is the right token because these are small raised chips
against the page background, the same role `mctl.css` ships that token for;
`--surface-elevated` is reserved for the `:hover` state so hover reads as a
lift rather than a colour change, and no `transition` is added (criterion 20).

### 4. Gate work

Three scripts observe the markup and must move with it. Two are authorised by
the issue; one was found by reading the clone.

**`check-no-metrics.mjs` (Appendix G).** The SVG coordinates produce 70
matches, all unclassified — the `CSS length` rule needs a `px`/`rem`/… suffix,
the `year in copy` rule needs a four-digit `19xx`/`20xx`, and neither applies
to `d="M20.5 14.5c-1.1.45…"`. Rather than trust the issue's list, the
investigation imported `scanForTypedNumbers()` and `RULES` from the real
script and ran them, with an empty `ALLOW`, over a temp tree holding exactly
Appendix A's file. Result: 70 matches, 70 unclassified, distinct values
`[1,2,3,5,7,10,12,14,18,19,22,24,25,45,55,75,78,85,95,99]` — byte-identical
to the issue's list. That is the list in Appendix G, and the appendix records
how to recompute it if a coordinate ever changes, because the same script
also fails on a value that no longer matches anything.

**`check-contrast.mjs` (Appendix F).** `SEMANTIC_TOKENS` gains
`surface-card` in both themes; `PAIRS` gains one `kind: 'text'` entry. The
ratios were computed during investigation from the vendored tokens actually
in the tree: `#a4a8ae` over `#15181d` = 7.45:1 (dark), `#3a3f47` over
`#fffdf8` = 10.42:1 (light). Both clear 4.5:1, so no `EXEMPTIONS` entry is
needed. The reported pair count moves 27 -> 29, which is why the
accessibility checklist's contrast row is corrected too.

**`check-dist.mjs` (Appendix H) — the change the issue does not mention.**
`checkApproachPage()`'s per-slice loop runs over `extractSvgSlices(html)`,
i.e. every `<svg>` on `dist/approach/index.html`, and requires each to have
`role="img"`, a resolving `aria-labelledby` and exactly one `<title>` and one
`<desc>`. The header is on every page, so Appendix A's two decorative
`aria-hidden="true"` glyphs land there and produce six failures; the same
slices would also be added to the 12 KB `MAX_SVG_BYTES` budget the docstring
scopes to the diagram. The script runs inside `Dockerfile`, so this fails the
image build, and the issue's own acceptance criterion 7 names it. The fix is
one line: filter the slice list to the diagram's own `cycle-svg` class, which
`src/components/CycleDiagram.astro` puts on both variants
(`class={`cycle-svg cycle-${v.key}`}`). Everything downstream —
`slices.length < 2`, `svgBytes`, the per-slice loop, `sawNarrowSlice` — keeps
its exact prior meaning, and the check becomes what its docstring always
claimed it was.

### 5. Documentation and journal

`docs/accessibility-checklist.md` gets four note rewrites and one re-walk log
entry (Appendix I). Two of the four are direct consequences the issue did not
name — the "No motion" row cites the deleted `[aria-pressed='true']` rule,
and the "Contrast in both themes" row states a pair count that section F
changes — and are included rather than left contradicting the code. One new
journal entry (Appendix J) with `status: in_progress`, per `AGENTS.md`.

## Alternatives

1. **Keep `role="group"` with a single button inside.** Rejected: a group of
   one is not a group, it adds an announced container with no members for a
   screen reader to move between, and it would keep the wrapper `<div>` this
   cycle exists to delete. `test/nav.test.ts`'s replacement assertion
   (Appendix E1) actively forbids it.

2. **Use `aria-label` now that each button has its own distinct purpose.**
   Rejected, and this is the single most load-bearing decision in the cycle.
   The site renders one HTML document per page for both languages; a literal
   `aria-label="Switch to Russian"` would be announced verbatim to a Russian
   screen-reader user reading the Russian stance of the same document.
   `aria-labelledby` -> `.visually-hidden` span -> `<Lang>` pair routes the
   accessible name through the same `display: none` stance mechanism as the
   visible text, which is the only mechanism this static site has.
   `checkNavigationState()` in `scripts/check-dist.mjs` independently fails
   the build on an `aria-label` mixing Latin and Cyrillic, so the older
   slash-joined workaround is not available either.

3. **Show the destination rather than the active state** (moon = "click for
   dark"). Rejected: confirmed with the site owner against an interactive
   preview. Showing the active state also lets the two hidden-by-CSS stances
   map one-to-one onto the two buttons with no extra markup — the moon button
   *is* the dark-stance button — so the design and the mechanism agree.

4. **An icon for the language toggle too** (a globe, or a flag). Rejected in
   the issue's out-of-scope list: there is no legible single glyph for a
   two-language toggle, and a flag names a country rather than a language.
   `EN`/`RU` at 12px/600 stays as text, which is why Appendix F picks the
   4.5:1 text threshold rather than the 3:1 non-text one.

5. **Ship the glyphs as `public/` SVG files referenced by `<img>` instead of
   inline markup**, to sidestep `check-no-metrics.mjs` entirely. Rejected:
   an `<img>` cannot inherit `currentColor`, so the glyph would need a
   separate asset per theme and would stop tracking `--surface-fg-muted`; it
   would also add two HTTP requests to a site whose whole point is zero
   third-party and minimal first-party requests, and
   `scripts/vendor-assets.mjs` SHA-pins `public/assets/mctl/*` anyway. The
   `ALLOW` entry is the cheaper and more honest answer.

6. **Also delete `.toggle-group` from the `@media print` selector list.**
   Rejected for this cycle (requirements.md, Open question 1): unauthorised
   by the issue, already redundant because the same rule hides
   `.site-header`, and cited as the worked example in two test-file header
   comments. Left as a one-line follow-up.

## Platform impact

**Migrations / data.** None. No content collection, no schema, no metrics,
no build-time data file changes. `src/data/assets.json` and
`public/assets/mctl/*` are untouched, so `npm run vendor` produces no diff
and CI's "Vendored tree matches the commit" step stays green. The one
regenerated artefact is `public/styles/site.css`, which `.gitignore` already
excludes and whose hash is pinned through `src/data/assets.json`'s fifth
`styles[]` entry by the vendor step.

**Backward compatibility.** The click contract is unchanged:
`[data-set-lang]` / `[data-set-theme]` with the same four values, read by the
same untouched delegated listener, persisted to the same `localStorage` keys.
A returning visitor's stored preference keeps working across the deploy.
`Base.astro` is not edited, so the CSP script hash does not move and
`test/csp.test.ts` / `scripts/csp-hash.mjs` are unaffected.

**Bilingual parity.** `scripts/check-dist.mjs` counts occurrences of the
literal substrings `class="l en"` and `class="l ru"` per built page and
requires them equal. The new language buttons render
`class="l en icon-toggle lang-toggle"`, which does not contain the literal
`class="l en"` (a space follows `en`, not a quote), exactly as today's
`class="toggle-group l en"` does not. Every `<Lang>` component still emits
one span of each. Parity is preserved by construction.

**Resource impact.** Net HTML delta per page is roughly +900 bytes (two
inline SVGs plus four bilingual hidden spans) minus roughly 400 bytes (two
wrapper `<div>`s, four `aria-pressed` attributes and four deleted buttons
across the two components) — well inside `MAX_INDEX_BYTES` (40 KB), and the
script prints the measured size on every run. Stylesheet size is roughly
flat: six rules out, four in. No new requests, no new fonts, no JavaScript.

**Risks and mitigations.**

| Risk | Mitigation |
| --- | --- |
| The `check-dist.mjs` gap (Appendix H) is missed and the Docker build fails after merge | Appendix H specifies the one-line fix verbatim and requirements.md criterion 16 makes a passing `node scripts/check-dist.mjs` a condition of done; the approver is asked to read it (Open question 3) |
| The `ALLOW` list drifts from the SVG coordinates and `check-no-metrics.mjs` reports a stale value | Appendix G records that the list was produced by running the gate's own matcher, and tells the implementer to recompute rather than hand-adjust after any coordinate change |
| `minBlockSizes(siteCss, '.icon-toggle')` returns more than one value and T6's `deepEqual([32])` fails | `ruleBlockBodies()` matches exact comma-split selectors, so `.icon-toggle:hover` and `.icon-toggle svg` are different selectors; Appendix D declares `min-block-size` in exactly one `.icon-toggle` block, and Appendix D also deletes the old tap-target rule that would otherwise leave a second one |
| Appendix D's comment mentions `overflow`, tripping the new header test's `.every()` assertion | Both `test/header.test.ts` and `test/a11y.test.ts` strip `/* … */` comments at read time before parsing; noted inline in Appendix E2 |
| The focus ring is clipped or invisible on the new buttons | No `overflow` on `.icon-toggle` (asserted), no per-class focus rule, and the global `:focus-visible` rule uses `outline-offset` so the ring draws outside a 32px box that has no clipping ancestor. Visual confirmation remains a reviewer step, per `AGENTS.md` |
| A screen reader announces the wrong language | Structural: the name comes from a `<Lang>` pair inside a `.visually-hidden` span, governed by the same stance rules as visible text. An actual NVDA/VoiceOver sweep stays a reviewer step, never an acceptance criterion |
| Contrast regression in one theme | `scripts/check-contrast.mjs` now checks the exact pair the new background introduces, in both themes, at the text threshold, and fails the build below 4.5:1 |

**Rollback.** Single commit, no data or schema change — see `tasks.md`.
