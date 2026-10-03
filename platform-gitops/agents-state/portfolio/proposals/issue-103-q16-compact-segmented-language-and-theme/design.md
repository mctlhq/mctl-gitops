# Design: issue-103-q16-compact-segmented-language-and-theme

## Current state

### Markup (unchanged by this cycle)

`src/components/Nav.astro` renders:

```
<header class="site-header">
  <span id="nav-label" class="visually-hidden">…</span>
  <nav class="site-nav" aria-labelledby="nav-label"> 4 × <a> </nav>
  <div class="toggle-bar">
    <LangToggle />
    <ThemeToggle />
  </div>
</header>
```

`src/components/LangToggle.astro` and `src/components/ThemeToggle.astro` each
emit two sibling `div.toggle-group` elements (`.l.en` / `.l.ru` and `.t.dark` /
`.t.light`; one of each pair is hidden by the existing language/theme CSS), each
holding exactly two `<button>` elements, plus one `.visually-hidden` label span
and one `<noscript><p>`. All of this stays exactly as it is.

### Stylesheet (`src/styles/site.css`, 827 lines)

Four regions matter.

1. Layout, around line 81:

   ```css
   .site-header,
   .site-footer,
   main {
     max-width: var(--content-max);
     margin-inline: auto;
   }
   ```

   This is the only `.site-header` declaration outside `@media print`.
   `.site-header` is therefore an ordinary block box today — which is why
   `.toggle-bar` falls onto its own line.

2. `/* Navigation. */`, line 99: `.site-nav` carries
   `display: flex; flex-wrap: wrap; gap: var(--mctl-space-4);
   padding-block: var(--mctl-space-4); border-bottom: 1px solid var(--surface-line);`.
   The bottom rule lives here, so it stops short of the toggles.

3. `/* Toggle groups. */`, lines 176-202: `.toggle-group` is
   `display: inline-flex; gap: var(--mctl-space-2)`; `.toggle-bar` is
   `display: flex; flex-wrap: wrap; gap: var(--mctl-space-4);
   padding-block: var(--mctl-space-4)`; `.toggle-bar noscript` is
   `flex-basis: 100%`. Each `.toggle-group button` is its own filled box
   (`background: var(--surface-elevated)`, `border: 1px solid var(--surface-line)`,
   `border-radius: var(--mctl-radius-md)`, `padding: var(--mctl-space-1)
   var(--mctl-space-3)`), and `[aria-pressed='true']` swaps to
   `background: var(--accent); color: var(--accent-fg); border-color: var(--accent)`.

4. Tap targets, line 577:

   ```css
   .site-nav a,
   .toggle-group button,
   .site-footer a {
     display: inline-flex;
     align-items: center;
     min-block-size: 44px;
   }
   ```

   `.cta` (line 288), `.block > summary` (line 319) and `.skip-link:focus`
   (line 391) declare their own 44px; `.project-links a, .breadcrumb a,
   .journal-meta a, .table-scroll a` (line 595) declare 24px.

The global focus indicator is
`:focus-visible { outline: var(--focus-ring-width) solid var(--focus-ring);
outline-offset: var(--focus-ring-offset); }` at line 93. `outline-offset` puts
the ring *outside* the element box — which is exactly why `overflow: hidden` on
`.toggle-group` would clip the first and last segment's ring.

### The `@media print` block (line ~803) — the trap in this cycle

```css
@media print {
  :root { … }
  .site-header,
  .toggle-group,
  .ctas {
    display: none;
  }
  …
}
```

`test/a11y.test.ts` resolves rule blocks with a flat regex,
`/([^{}]+)\{([^}]*)\}/g`, and matches on
`m[1].split(',').map(s => s.trim().replace(/\s+/g,' ')).includes(selector)`.
That regex does not understand `@media` nesting, so the print block's
`.site-header, .toggle-group, .ctas { display: none; }` is matched as an
ordinary rule block. Verified against the current file:

```
.site-header -> 2 blocks: "max-width: …; margin-inline: auto;" | "display: none;"
.toggle-group -> 2 blocks: "display: inline-flex; gap: …;"     | "display: none;"
.site-nav    -> 1 block
.toggle-bar  -> 1 block
```

The existing `.toggle-bar` test uses a *last block wins* loop (`if (…) block =
m[2]`) and gets away with it only because `.toggle-bar` appears exactly once.
Writing tests 1 and 4 in that same shape would resolve `.site-header` and
`.toggle-group` to `display: none;` and fail. This is the single sharpest
implementation hazard in this cycle.

### Tests and scripts

- `package.json`'s `test` script enumerates every test file by name in one
  `node --test …` invocation. A new `test/header.test.ts` that is not added to
  that list never runs, and the cycle would ship green with zero new coverage.
- `minBlockSizeProblems(css, selector, floor)` in `test/a11y.test.ts` is
  module-local, not exported, and returns problem *strings* only — it cannot
  report "exactly one declaration, equal to 32px".
- `scripts/check-contrast.mjs`'s `PAIRS` array (line 87) is static and already
  contains `{ fg: 'surface-fg-muted', bg: 'surface-bg', kind: 'text' }` and
  `{ fg: 'accent-fg', bg: 'accent', kind: 'text' }`. The new style introduces no
  pair the script does not already check.
- `scripts/check-dist.mjs`'s `checkNavigationState()` parses
  `<nav class="site-nav">` and counts `aria-current`; it reads markup only, and
  the markup does not change.
- `test/nav.test.ts` asserts `role="group"` / `aria-labelledby` and exactly two
  `.toggle-group` divs per component, at source level.
- `test/link-cascade.test.ts` explicitly classifies `.site-nav a` and
  `.toggle-group button` as *not* members of any modelled link family — it is
  unaffected.
- `test/ui.test.ts:190-197` pins both `aboutParagraphs` arrays as verbatim
  literals. `test/home.test.ts` imports `ui` and derives its expectations, so it
  self-updates.

### `.visually-hidden` and the new flex container

`.visually-hidden` (line 398) is `position: absolute`. `#nav-label` is therefore
out of flow and does **not** become a flex item when `.site-header` becomes a
flex container — `justify-content: space-between` sees two items, `.site-nav`
and `.toggle-bar`, not three. Same for `#lang-toggle-label` and
`#theme-toggle-label` inside `.toggle-bar`. No markup change is needed to make
the flex row behave.

## Proposed solution

CSS-only, in `src/styles/site.css`, plus one doc correction, one string
correction, and new source-level tests. Five edits to the stylesheet, all
inlined verbatim in `requirements.md`:

1. **Header becomes the row.** Add a new `.site-header` block in the
   `/* Navigation. */` section, immediately before `.site-nav`. It sets
   `display: flex; flex-wrap: wrap; align-items: center;
   justify-content: space-between; gap: var(--mctl-space-4);
   padding-block: var(--mctl-space-2);
   border-bottom: 1px solid var(--surface-line);`. The existing
   `.site-header, .site-footer, main` max-width block is left untouched, so the
   rule still spans exactly the `--content-max` column.

   *Placement is load-bearing.* The new block must sit **before** the
   `@media print` block, which sets `.site-header { display: none }` at equal
   specificity. Print wins only on source order. Putting the new block at the
   end of the file would make the header print.

2. **Navigation loses the rule and the padding.** `.site-nav` keeps
   `display: flex`, `flex-wrap: wrap` and `gap: var(--mctl-space-4)`; its
   `border-bottom` is deleted (moved, not duplicated) and `padding-block` becomes
   `0`, because the row padding now lives on `.site-header`.

3. **Toggle bar goes to the right edge.** `.toggle-bar` keeps the three
   declarations `test/a11y.test.ts` already pins, drops its `padding-block` to
   `0`, and gains `margin-inline-start: auto` plus `justify-content: flex-end`.
   `margin-inline-start: auto` is what pushes it right *and* what keeps it
   right-aligned after it wraps to its own line — `justify-content:
   space-between` on the wrapped parent would otherwise leave a lone item at the
   start. `justify-content: flex-end` handles the bar's own internal wrap (the
   two controls onto two lines at 320px). Belt and braces, both cheap, both
   asserted.

4. **Segmented control.** `.toggle-group` becomes the bordered box
   (`border: 1px solid var(--surface-line)`, `border-radius:
   var(--mctl-radius-md)`, `gap: 0`); the buttons become borderless, transparent,
   `--surface-fg-muted` at `--mctl-typography-font-size-sm` with `line-height: 1`
   and `padding-inline: var(--mctl-space-3); padding-block: 0`; the divider is
   `.toggle-group button + button { border-inline-start: 1px solid
   var(--surface-line); }`; the ends are rounded per segment via
   `border-start-start-radius` / `border-end-start-radius` on `:first-child` and
   `border-start-end-radius` / `border-end-end-radius` on `:last-child`; the
   pressed segment keeps the existing `--accent` / `--accent-fg` swap, minus the
   now-meaningless `border-color`.

   The entire `/* Toggle groups. */` block is **replaced**, not appended to. The
   old rule uses the `padding:` shorthand and `background: var(--surface-elevated)`;
   leaving it in place and layering the new declarations on top would work by
   cascade but leaves two contradictory descriptions of the same control in the
   file for the next reader.

   `overflow: hidden` is deliberately not used and must not be reintroduced. The
   logical corner-radius properties give the same rounded-ends shape while
   leaving the `outline-offset` focus ring of the first and last segment
   unclipped — the exact indicator the checklist claims the site has. The tests
   pin its absence so a later "simplification" cannot quietly bring it back.

5. **`<noscript>` alignment.** `.toggle-bar noscript` gains `text-align: end`, so
   the full-width sentence reads as deliberately right-aligned with the bar
   above it rather than centred by accident.

6. **Target size split.** The three-selector 44px block splits into
   `.site-nav a, .site-footer a { … 44px }` and a new
   `.toggle-group button { … 32px }`. 32px clears the 24px floor
   `test/a11y.test.ts` enforces and the WCAG 2.2 AA 2.5.8 minimum; it is below
   the 2.5.5 AAA 44px the site exceeds everywhere else. That is a named,
   deliberate trade for a header that does not shout, scoped to the two
   auxiliary controls only.

   `docs/accessibility-checklist.md`'s "Target size at least 24px" Evidence cell
   currently names 44px for `.toggle-group button` and would become false; it is
   replaced with the verbatim text in `requirements.md`. Markdown table cells
   cannot contain newlines, so the replacement text goes into the cell as one
   line; the line wrapping shown in the issue and in `requirements.md` is
   presentational.

7. **Colour contract.** No new colour pair. `--surface-fg-muted` over
   `--surface-bg` and `--accent-fg` over `--accent` are already in
   `check-contrast.mjs`'s `PAIRS`, both themes, both above 4.5:1. No exemption,
   no threshold change, no token added.

### Test architecture

The parser must be shared, and the print-block hazard must be designed out.
Extract the block-resolution logic from `test/a11y.test.ts` into
`test/support/css-rules.ts` — `test/support/` already exists and already holds
`expected-projects.ts`, so the convention is established, and a file under
`test/support/` is not a test file and is correctly absent from the `npm test`
list.

```ts
// test/support/css-rules.ts
export function ruleBlockBodies(css: string, selector: string): string[]
export function minBlockSizes(css: string, selector: string): number[]
```

`ruleBlockBodies` returns **every** matching block body in source order, not the
last one. `test/a11y.test.ts`'s `minBlockSizeProblems` is rewritten as a thin
wrapper over `minBlockSizes`, so its behaviour, its two synthetic self-tests and
all eleven `TARGET_SELECTORS` assertions are unchanged. `test/header.test.ts`
imports both helpers. No second parser is written anywhere.

Because `.site-header` and `.toggle-group` each resolve to two blocks (the real
one and the print one), the new assertions are written as quantifiers, not as
"the block":

- test 1: `ruleBlockBodies(css, '.site-header').some(b => …)` for each of
  `display: flex`, `flex-wrap: wrap`, `justify-content: space-between`,
  `border-bottom` — and all four satisfied by the *same* body, so the assertion
  finds one body satisfying all four rather than four bodies satisfying one each.
- test 2: `ruleBlockBodies(css, '.site-nav').every(b => !/border-bottom/.test(b))`.
- test 3: the `.toggle-bar` body additionally declares `margin-inline-start: auto`.
- test 4: `.some(b => border && border-radius)` **and**
  `.every(b => !/\boverflow\s*:/)` — the print body has no `overflow`, so the
  `every` holds, and the `some` finds the real block rather than `display: none;`.
- test 5: `ruleBlockBodies(css, '.toggle-group button + button')` is non-empty and
  some body declares `border-inline-start`.
- test 6: `minBlockSizes(css, '.toggle-group button')` deep-equals `[32]`
  (exactly one, and 32), `minBlockSizes(css, '.site-nav a')` and
  `minBlockSizes(css, '.site-footer a')` each contain `44`.

`test/header.test.ts` is added to the `node --test` list in `package.json`'s
`test` script, between `test/a11y.test.ts` and `test/seo.test.ts`.

### Section E

`src/i18n/ui.ts`, `aboutParagraphs`, first entry of each language: the opening
sentence only is replaced. Both are single-line string literals in the file, so
this is one substring edit per language — the EN literal is double-quoted
(it contains `team's`) and must stay double-quoted. `test/ui.test.ts:191` and
`test/ui.test.ts:196` carry the same two literals and are updated in the same
commit. Nothing else in the paragraph changes.

## Alternatives

1. **`overflow: hidden` on `.toggle-group` instead of per-segment radii.** One
   declaration instead of six; the obvious idiom for a segmented control. Dropped
   because `:focus-visible` uses `outline-offset`, so the ring is drawn outside
   the button box and `overflow: hidden` on the parent clips it on the outer edge
   of the first and last segment — silently invalidating the "Focus visibility on
   links and buttons" row of `docs/accessibility-checklist.md` for four of the
   site's interactive elements. The issue names this explicitly and a test pins
   the absence.

2. **Keep the 44px target on `.toggle-group button` and shrink only
   horizontally.** Would preserve WCAG 2.5.5 AAA on every control. Dropped
   because a 44px-tall segmented control is not compact — it forces
   `.site-header`'s row height to 44px plus padding and the toggles still read as
   a control panel, just a narrower one. 32px is a deliberate, named,
   narrowly-scoped trade, above both the 24px floor the suite enforces and the
   2.5.8 AA minimum, and it is documented in the checklist rather than hidden.

3. **CSS Grid on `.site-header` instead of flex with `margin-inline-start: auto`.**
   `grid-template-columns: 1fr auto` would place nav and toggles without an auto
   margin. Dropped because the wrap behaviour at narrow widths then needs an
   explicit `@media` breakpoint (grid does not wrap the way `flex-wrap` does),
   which the issue's acceptance criteria deliberately avoid, and because the
   existing `.site-nav`, `.toggle-bar` and `.site-footer` rules are all flex —
   a grid header would be the only one of its kind in the file.

4. **Put the bottom rule on a wrapper `<div>` inside `.site-header`.** Would
   avoid touching `.site-nav` at all. Dropped: it requires a markup change to
   `Nav.astro`, which is explicitly out of scope.

5. **Add the new assertions to `test/a11y.test.ts` and skip `test/header.test.ts`
   and the shared support module entirely.** Simplest diff, no `package.json`
   edit, and the helper is already in scope. Dropped because `a11y.test.ts` is
   already 170 lines covering five unrelated concerns (focus, target size,
   motion, `lang`, table wrapping), and header layout is a sixth. The support
   extraction is the part that actually earns its keep — it is what makes
   "reuse the existing helper rather than writing a second parser" mechanically
   true rather than a comment. This alternative remains a valid fallback if the
   extraction proves noisier than expected.

## Platform impact

**Migrations / backward compatibility.** None. Static Astro site, no data, no
API, no persisted state. The inline `<head>` preference script is untouched, so
its CSP SHA-256 hash does not move and `test/csp.test.ts` /
`scripts/check-headers.mjs` are unaffected. No dependency change, no lockfile
change, so the `--package-lock-only` rule in `AGENTS.md` does not come into play.

**Resource impact.** `src/styles/site.css` grows by roughly 25 lines net. No new
asset, no new request, no change to `public/assets/mctl/*` (SHA-pinned).
`scripts/check-dist.mjs` and `scripts/check-links.mjs` see identical markup and
identical link sets.

**Risks and mitigations.**

| Risk | Mitigation |
| --- | --- |
| Tests 1 and 4 written in the `.toggle-bar` "last block wins" shape resolve to the `@media print` `display: none;` body and fail. | Design mandates `ruleBlockBodies` returning all bodies plus `.some`/`.every` quantifiers; the hazard is stated in the test task's DoD. |
| New `.site-header` block placed after `@media print`, so the header prints. | Task 1 fixes the insertion point: `/* Navigation. */` section, immediately before `.site-nav`. A visual print check is a reviewer step; the ordering is checkable by reading the file. |
| `test/header.test.ts` added but not listed in `package.json`'s `test` script — ships green with zero coverage. | Explicit task and DoD: `npm test` output must name `test/header.test.ts`. |
| `overflow: hidden` reintroduced later as a "cleanup". | Test 4's `every(b => !/overflow:/)` pins its absence in the suite, and the reason is recorded in both the stylesheet comment and the checklist. |
| `border-bottom` duplicated on `.site-nav` instead of moved, giving a double rule. | Test 2 pins its absence. |
| A stray `transition` sneaks in with the border/background changes. | Existing `test/a11y.test.ts` "no animation or transition anywhere" assertion already covers the whole file. |
| Section E edit drifts the rest of the paragraph by a character. | Only the opening sentence is replaced; `test/ui.test.ts` pins both full arrays verbatim and fails on any other drift. |
| 32px at `--mctl-typography-font-size-sm` (13px) with `line-height: 1` makes the words feel cramped, or the segmented control overflows at 320px in Russian. | `flex-wrap: wrap` on both `.site-header` and `.toggle-bar` plus `justify-content: flex-end` handles the wrap; the labels are `EN`/`RU`/`Dark`/`Light`/`Тёмная`/`Светлая` and `padding-inline: var(--mctl-space-3)` (12px) leaves margin. A real-browser check at 320px is a reviewer step per `AGENTS.md`. |
| Contrast regression from `--surface-fg-muted` on `--surface-bg`. | Already one of `check-contrast.mjs`'s 27 checked pairs, both themes, above 4.5:1. Wired into `npm test`, so a regression fails the build. |

**Rollback.** Single-commit revert; see `tasks.md`.
