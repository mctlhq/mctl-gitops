# Design: issue-108-q18-single-icon-button-toggles-replace-t

## Current state

Read in the clone at `mctlhq/portfolio@c1dd71f`.

**Markup.** `src/components/Nav.astro` renders a `.site-header` flex row: a
`#nav-label` `.visually-hidden` span, `<nav class="site-nav">` with four
literal anchors, and `<div class="toggle-bar"><LangToggle /><ThemeToggle />
</div>`. `src/components/LangToggle.astro` renders two
`<div class="toggle-group l en|ru" role="group"
aria-labelledby="lang-toggle-label">` wrappers, each with two `<button
type="button" data-set-lang="en|ru" aria-pressed="true|false">` children
holding `<Lang en={ui.langEn.en} ...>`, followed by the shared
`#lang-toggle-label` hidden span and a `<noscript><p>`.
`src/components/ThemeToggle.astro` is the same shape for `data-set-theme` and
`#theme-toggle-label`. Twelve elements in total for two binary controls.

**Stance mechanism.** `src/styles/site.css` lines 43-57 hide the inactive
half: `:root[data-lang='en'] .l.ru { display: none }`,
`:root[data-lang='ru'] .l.en { display: none }`,
`:root[data-theme='dark'] .t.light { display: none }`,
`:root[data-theme='light'] .t.dark { display: none }`. There is no
client-side re-render: `src/layouts/Base.astro` ships a single `is:inline`
head script (CSP-hash pinned) that only writes `data-lang` / `data-theme` on
`<html>` and persists them, with one delegated listener
`e.target.closest?.("[data-set-lang],[data-set-theme]")`. Because `closest()`
walks up from the event target, a click landing on an inner `<svg>` or
`<path>` still resolves the owning button — the new glyph markup needs no
script change.

**Accessible naming.** Every control names itself with `aria-labelledby`
pointing at a `.visually-hidden` span nesting `<Lang>`
(`src/i18n/Lang.astro` emits `<span class="l en">…</span><span class="l ru"
lang="ru">…</span>`), never a literal `aria-label`. `checkNavigationState()`
in `scripts/check-dist.mjs` fails the build on any `aria-label` value mixing
Latin and Cyrillic, and `test/nav.test.ts` forbids the slash-joined bilingual
template literal.

**Styles.** `site.css` lines 183-231 hold the `/* Toggle groups. */` block:
`.toggle-group` (inline-flex, `gap: 0`, `1px solid var(--surface-line)`,
`var(--mctl-radius-md)`), `.toggle-bar`, `.toggle-bar noscript`,
`.toggle-group button`, `:first-child` / `:last-child` corner radii,
`button + button` divider and `button[aria-pressed='true']` accent fill.
Lines 613-621 add the tap-target exception `.toggle-group button {
display: inline-flex; align-items: center; min-block-size: 32px }`. A single
global `:focus-visible { outline: var(--focus-ring-width) solid
var(--focus-ring); outline-offset: var(--focus-ring-offset) }` sits at line
93. The `@media print` block lists `.site-header, .toggle-group, .ctas {
display: none }`.

**Tokens.** `public/assets/mctl/mctl.baf7fec1.css` ships the semantic layer:
`:root` (dark) and `[data-theme='light']` each declare `--surface-card`
alongside `--surface-bg`, `--surface-elevated`, `--surface-fg`,
`--surface-fg-muted` and `--surface-line`. Raw values: `mctl-surface-dark-card
#15181d`, `mctl-surface-light-card #fffdf8`, `mctl-radius-lg 8px`,
`mctl-typography-font-weight-semibold 600`. `site.css` never declares
`--surface-card` itself, exactly as it never declares `--surface-elevated`.

**Gates.** `npm test` = `check-no-metrics.mjs` + `check-contrast.mjs` + 37
`node --test` files. `scripts/check-dist.mjs` runs in the `Dockerfile`
(`npm run build && node scripts/check-dist.mjs && node scripts/csp-hash.mjs`),
so the CI `build` job fails on it. `scripts/check-contrast.mjs` has no
`surface-card` entry in `SEMANTIC_TOKENS`. `test/header.test.ts` T4/T5/T6 and
`test/a11y.test.ts`'s `TARGET_SELECTORS` pin `.toggle-group`;
`test/nav.test.ts` pins `role="group"`; `docs/accessibility-checklist.md`
names `.toggle-group button` and the `[aria-pressed='true']` swap.

**Two verified facts that shape this design.**

1. `checkApproachPage()` in `scripts/check-dist.mjs` (lines 90-181) iterates
   **every** `<svg>` slice in `dist/approach/index.html` and requires
   `role="img"`, a resolving `aria-labelledby`, exactly one `<title>` and one
   `<desc>`, a `viewBox` and no `width`/`height`. The header renders on that
   page, so the two new decorative theme glyphs would add six failures and
   break acceptance criterion 7. Section G fixes this.
2. `scripts/check-dist.mjs`'s bilingual parity counts the literal substring
   `class="l en"` / `class="l ru"`. The new language buttons emit
   `class="l en icon-toggle lang-toggle"` / `class="l ru icon-toggle
   lang-toggle"`, which match neither needle, and the `<Lang>` components
   inside the buttons and hidden spans stay balanced — parity is unaffected.

## Proposed solution

Six source files change plus two documentation files. Every block below is
the literal text to write.

### A. `src/components/ThemeToggle.astro` — full replacement

Replace the entire file with, character for character:

```astro
---
import Lang from '../i18n/Lang.astro';
import { ui } from '../i18n/ui';
---

<button type="button" class="t dark icon-toggle" data-set-theme="light" aria-labelledby="theme-toggle-to-light">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">
    <path d="M20.5 14.5c-1.1.45-2.3.7-3.55.7-5.25 0-9.5-4.25-9.5-9.5 0-1.25.25-2.45.7-3.55C4.6 3.4 2.5 6.95 2.5 11c0 5.8 4.7 10.5 10.5 10.5 4.05 0 7.6-2.1 8.85-4.9 0-.03.02-.07.03-.1z" />
  </svg>
</button>
<span id="theme-toggle-to-light" class="visually-hidden"><Lang en={ui.themeSwitchToLight.en} ru={ui.themeSwitchToLight.ru} /></span>
<button type="button" class="t light icon-toggle" data-set-theme="dark" aria-labelledby="theme-toggle-to-dark">
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" aria-hidden="true" focusable="false">
    <circle cx="12" cy="12" r="4.5" />
    <line x1="12" y1="1.75" x2="12" y2="4.25" />
    <line x1="12" y1="19.75" x2="12" y2="22.25" />
    <line x1="4.22" y1="4.22" x2="5.99" y2="5.99" />
    <line x1="18.01" y1="18.01" x2="19.78" y2="19.78" />
    <line x1="1.75" y1="12" x2="4.25" y2="12" />
    <line x1="19.75" y1="12" x2="22.25" y2="12" />
    <line x1="4.22" y1="19.78" x2="5.99" y2="18.01" />
    <line x1="18.01" y1="5.99" x2="19.78" y2="4.22" />
  </svg>
</button>
<span id="theme-toggle-to-dark" class="visually-hidden"><Lang en={ui.themeSwitchToDark.en} ru={ui.themeSwitchToDark.ru} /></span>
<noscript>
  <p><Lang en={ui.themeNoScript.en} ru={ui.themeNoScript.ru} /></p>
</noscript>
```

The first button (`.t.dark`, visible while the page is in dark stance) shows
the MOON and switches to light; the second (`.t.light`) shows the SUN and
switches to dark. This is the "currently active" reading confirmed with the
site owner — moon means dark is on right now, not "click to go dark".

### B. `src/components/LangToggle.astro` — full replacement

Replace the entire file with, character for character:

```astro
---
import Lang from '../i18n/Lang.astro';
import { ui } from '../i18n/ui';
---

<button type="button" class="l en icon-toggle lang-toggle" data-set-lang="ru" aria-labelledby="lang-toggle-to-ru">
  <Lang en={ui.langEn.en} ru={ui.langEn.ru} />
</button>
<span id="lang-toggle-to-ru" class="visually-hidden"><Lang en={ui.langSwitchToRu.en} ru={ui.langSwitchToRu.ru} /></span>
<button type="button" class="l ru icon-toggle lang-toggle" data-set-lang="en" aria-labelledby="lang-toggle-to-en">
  <Lang en={ui.langRu.en} ru={ui.langRu.ru} />
</button>
<span id="lang-toggle-to-en" class="visually-hidden"><Lang en={ui.langSwitchToEn.en} ru={ui.langSwitchToEn.ru} /></span>
<noscript>
  <p><Lang en={ui.langNoScript.en} ru={ui.langNoScript.ru} /></p>
</noscript>
```

### C. `src/i18n/ui.ts`

Add four new keys, character for character (place near the existing
`langEn` / `langRu` / `themeDark` / `themeLight` keys):

```ts
themeSwitchToDark: { en: 'Switch to dark theme', ru: 'Переключить на тёмную тему' },
themeSwitchToLight: { en: 'Switch to light theme', ru: 'Переключить на светлую тему' },
langSwitchToEn: { en: 'Switch to English', ru: 'Переключить на английский' },
langSwitchToRu: { en: 'Switch to Russian', ru: 'Переключить на русский' },
```

Remove `langToggleLabel` and `themeToggleLabel` — they named the now-deleted
`role="group"` sets and have no remaining reference after sections A/B.
`langEn`, `langRu`, `themeDark`, `themeLight`, `langNoScript`,
`themeNoScript` are NOT removed. (Note: after section A, `themeDark` and
`themeLight` are no longer rendered anywhere; they are kept deliberately, see
requirements.md "Open questions".) If a test pins
`langToggleLabel`/`themeToggleLabel`, update that test in the same commit
rather than leaving the keys in place to satisfy it — a repo-wide grep at
`c1dd71f` finds no such test, so this is a guard, not a known edit.

### D. `src/styles/site.css`

Delete the entire `/* Toggle groups. */` block (the `.toggle-group`,
`.toggle-group button`, `.toggle-group button:first-child`,
`.toggle-group button:last-child`, `.toggle-group button + button` and
`.toggle-group button[aria-pressed='true']` rules) — but KEEP the
`.toggle-bar` and `.toggle-bar noscript` rules that currently sit inside that
same region, unchanged and in place. Also delete the `.toggle-group button`
selector's `min-block-size: 32px` rule near the tap-target block (the
`display: inline-flex; align-items: center; min-block-size: 32px` rule and
its preceding comment). Replace with, character for character:

```css
/* Icon toggles (issue #108, Q18): one button per CSS stance -- .t.dark/
 * .t.light, .l.en/.l.ru -- the same mutually-exclusive display:none
 * mechanism as every other bilingual/theme element on the site, just one
 * glyph or label each instead of a two-button segmented pair. No inner
 * divider and no overflow: the lesson from the Q16 segmented control (an
 * overflow:hidden container clips the :focus-visible ring) doesn't even
 * arise here, but is worth restating: this class must never gain one. */
.icon-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  inline-size: 32px;
  block-size: 32px;
  min-inline-size: 32px;
  min-block-size: 32px;
  padding: 0;
  border: 1px solid var(--surface-line);
  border-radius: var(--mctl-radius-lg);
  background: var(--surface-card);
  color: var(--surface-fg-muted);
  cursor: pointer;
}
.icon-toggle:hover {
  background: var(--surface-elevated);
}
.icon-toggle svg {
  inline-size: 20px;
  block-size: 20px;
}
.lang-toggle {
  font-family: var(--font-display);
  font-size: 12px;
  font-weight: var(--mctl-typography-font-weight-semibold);
  letter-spacing: 0.02em;
}
```

Place this replacement where the deleted `/* Toggle groups. */` rules were
(after the `.breadcrumb` rules, around the retained `.toggle-bar` block), and
add NO second `.icon-toggle` rule block anywhere else in the file — in
particular do not re-add a `min-block-size` for it in the tap-target section.
`test/header.test.ts` T6 asserts `minBlockSizes(siteCss, '.icon-toggle')`
equals exactly `[32]`, so a second declaration fails the build.

The site's single global `:focus-visible` rule already covers `.icon-toggle`
(no per-class focus override is needed or wanted). `--surface-card` is the
same token `mctl.css` already ships — declared in its semantic layer under
`:root` (dark, `#15181d`) and `[data-theme='light']` (`#fffdf8`), resolved the
same way `site.css` already resolves `--surface-elevated`;
`scripts/check-contrast.mjs` does not yet resolve it (see section F).

Do NOT add a `.toggle-bar` or `.toggle-bar noscript` change — both keep their
Q16 declarations (`gap`, `margin-inline-start: auto`,
`justify-content: flex-end`, `text-align: end` on the noscript paragraphs)
untouched; two 32px buttons fit that layout exactly as the two former pills
did.

One further edit in the same file: the `@media print` block currently reads

```css
  .site-header,
  .toggle-group,
  .ctas {
    display: none;
  }
```

Replace `.toggle-group` there with `.icon-toggle`, leaving the other two
selectors and the declaration as they are. This keeps the print rule pointing
at a class that still exists; it changes no rendering, because `.site-header`
already hides the whole header row in print. Verified against the tests: the
flat parser in `test/support/css-rules.ts` will then resolve `.icon-toggle` to
two bodies (the real one and this `display: none` one), which T4's replacement
handles with `.some()`/`.every()`, and which leaves `minBlockSizes` at `[32]`
because the print body declares none.

### E. Tests

**`test/nav.test.ts`** — replace the test named `'LangToggle.astro and
ThemeToggle.astro give every .toggle-group role="group" and an
aria-labelledby, never an aria-label'` with, character for character:

```ts
test('LangToggle.astro and ThemeToggle.astro render exactly two .icon-toggle buttons, each with its own aria-labelledby, no role="group" and no aria-label', () => {
  for (const [name, source] of [
    ['LangToggle.astro', langToggle],
    ['ThemeToggle.astro', themeToggle],
  ] as const) {
    const buttonTags = source.match(/<button\s+type="button"\s+class="[^"]*icon-toggle[^"]*"[^>]*>/g) ?? [];
    assert.equal(buttonTags.length, 2, `${name}: expected exactly two .icon-toggle buttons`);
    for (const tag of buttonTags) {
      assert.match(tag, /aria-labelledby="/, `${name}: ${tag} is missing aria-labelledby`);
    }
    assert.doesNotMatch(source, /role="group"/, `${name}: no role="group" should remain -- a single button is not a set`);
    assert.doesNotMatch(source, /aria-label=/, `${name}: no aria-label should remain`);
    assert.doesNotMatch(source, /groupLabel/, `${name}: no groupLabel const should remain`);
  }
});
```

Every other assertion in `test/nav.test.ts` (bilingual-template-literal check,
`Base.astro`'s skip link, `Nav.astro`'s four literal hrefs) is unaffected and
must keep passing unchanged. The file's top comment still describes the old
`role="group"` pairs; refresh that prose to describe the per-button
`aria-labelledby` pattern (comment only, no assertion change).

**`test/a11y.test.ts`** — in `TARGET_SELECTORS`, replace the literal
`'.toggle-group button'` with `'.icon-toggle'`. No other entry in that array
changes. All other tests in this file (`:focus-visible` rule, no
animation/transition, the `.toggle-bar` rule, `.site-nav a[aria-current]`
colour+text-decoration, `Lang.astro` emitting `lang="ru"`) must keep passing
unchanged.

**`test/header.test.ts`** — remove test T4 (`'some .toggle-group block
declares a border and a border-radius, and no .toggle-group block declares
overflow'`) and test T5 (`'a rule block whose selector list includes
.toggle-group button + button declares border-inline-start'`) outright: there
is no more segmented container and no more adjacent-sibling divider for either
to describe. Add one replacement test in their place, character for character:

```ts
test('some .icon-toggle block declares border, border-radius and background, and no .icon-toggle block declares overflow', () => {
  const bodies = ruleBlockBodies(siteCss, '.icon-toggle');
  assert.ok(bodies.length > 0, 'expected at least one .icon-toggle rule block');
  assert.ok(
    bodies.some((b) => /\bborder:\s*[^;]+;/.test(b) && /border-radius:/.test(b) && /background:/.test(b)),
    'expected a .icon-toggle block declaring border, border-radius and background',
  );
  assert.ok(
    bodies.every((b) => !/\boverflow\s*:/.test(b)),
    'expected no .icon-toggle block to declare overflow',
  );
});
```

Update T6 (`'.toggle-group button resolves to exactly one min-block-size of
32px...'`) to read `.icon-toggle` in place of `.toggle-group button` — its
name string and its `minBlockSizes(siteCss, '.toggle-group button')` call
both — while its `.site-nav a` / `.site-footer a` assertions are unchanged.
T1, T2 and T3 (the `.site-header` row, `.site-nav`'s missing `border-bottom`,
`.toggle-bar`'s `margin-inline-start: auto`) are unrelated to this cycle and
must keep passing unchanged. The file's top comment names `.toggle-group` as
the two-body example; update that prose to name `.icon-toggle` (comment only).

### F. `scripts/check-contrast.mjs`

`SEMANTIC_TOKENS` has no entry for the `--surface-*-card` token this cycle
introduces as `.icon-toggle`'s background, so the new glyph/label colour
cannot be checked without extending it. Add, character for character, to BOTH
the `dark` and `light` objects in `SEMANTIC_TOKENS`:

```js
'surface-card': 'mctl-surface-dark-card',
```
```js
'surface-card': 'mctl-surface-light-card',
```

(dark value in the `dark` object, light value in the `light` object — same
placement pattern as the six existing keys in each).

Add one entry to `PAIRS`, character for character:

```js
{ fg: 'surface-fg-muted', bg: 'surface-card', kind: 'text' },
```

`kind: 'text'` (the 4.5:1 threshold), not `'focus-ring'` (3:1): the language
button's `EN`/`RU` label is real text at 12px/600, below the WCAG large-text
threshold (18.66px bold), so it needs the stricter ratio — and because both
buttons inherit their colour from the same `color: var(--surface-fg-muted)`
declaration via `currentColor` on the SVG, one pair covers the theme button's
icon too (a non-text glyph, which only strictly needs 3:1, clears the stricter
number for free). Do not add a second, separate `kind: 'focus-ring'` pair for
the icon — that would just duplicate the same two hex values under a lower
bar.

Measured from the vendored token file during this investigation: `#a4a8ae`
over `#15181d` = **7.45:1** (dark), `#3a3f47` over `#fffdf8` = **10.42:1**
(light). Both clear 4.5:1, and `CONTENT_LINK_SEMANTIC_TOKENS` inherits the new
key automatically through its `{ ...SEMANTIC_TOKENS.dark }` spread with no
further edit.

### G. `scripts/check-dist.mjs` — required for acceptance criterion 7

`checkApproachPage()` audits every `<svg>` in `dist/approach/index.html` for
`role="img"`, a resolving `aria-labelledby`, exactly one `<title>` and one
`<desc>`, a `viewBox` and no `width`/`height`. That audit was written for the
two `CycleDiagram.astro` variants. After section A the site header — which
renders on every page, including `/approach/` — contributes two decorative
`aria-hidden="true"` glyph SVGs, which would produce six spurious failures and
break the Dockerfile step `npm run build && node scripts/check-dist.mjs`.

In `checkApproachPage()`, replace

```js
  const slices = extractSvgSlices(html);
```

with, character for character:

```js
  // Issue #108 (Q18): the header's theme toggle renders two decorative
  // aria-hidden="true" glyph <svg> elements on every page, this one
  // included. A decorative icon inside a button that already carries an
  // aria-labelledby name must NOT also claim role="img" and a <title>/<desc>
  // pair -- it would announce the control twice. Filtered on the one
  // attribute that states exactly that, never on a class allow-list, so a
  // future named diagram is still audited by default.
  const slices = extractSvgSlices(html).filter((slice) => !/aria-hidden="true"/.test(svgOpenTag(slice)));
```

Everything downstream (`slices.length < 2`, the `MAX_SVG_BYTES` sum, the
per-slice loop, the `cycle-narrow` viewBox cap) then applies to the two
diagram variants exactly as before, and the 12 KB diagram budget keeps
measuring the diagram rather than absorbing ~1 KB of header glyphs.

### H. `docs/accessibility-checklist.md`

Replace the "Target size at least 24px" row with, character for character:

```
| Target size at least 24px | pass | `src/styles/site.css` sets `min-block-size: 44px` — above the 24px CSS Working Group "AA equivalent" floor named in the issue — on `.site-nav a`, `.site-footer a`, `.cta` and `.block > summary`, and a fixed 32px box (`inline-size`, `block-size`, `min-inline-size` and `min-block-size` together) on `.icon-toggle`, the two single-button auxiliary language and theme controls in the header; both are above the 24px floor and both are asserted by `test/a11y.test.ts`. |
```

Replace the "Group naming in the active language" row with, character for
character:

```
| Group naming in the active language | pass | Since issue #108 (Q18) the language and theme controls are single buttons, not `role="group"` sets: `src/components/LangToggle.astro` and `src/components/ThemeToggle.astro` each render two `.icon-toggle` buttons, one per CSS stance, and every one of them takes its accessible name from `aria-labelledby` pointing at its own `.visually-hidden` bilingual `<Lang>` span — never a literal `aria-label`, which would read one fixed language aloud on both stances of a page that is rendered once and toggled with CSS. The `site-nav` `<nav>` and the home page's `.ctas` `<nav>` keep the same `aria-labelledby` mechanism for their landmarks. `checkNavigationState()` fails the build on any remaining `aria-label` value that mixes a Latin and a Cyrillic letter, exempting only the out-of-scope `.table-scroll` region on `dist/colophon/index.html`; `test/nav.test.ts` asserts the two `.icon-toggle` buttons, their `aria-labelledby`, the absence of `role="group"` and of any `aria-label` at the source level, and the absence of any remaining `${…en} / ${…ru}` template literal in `src/components/`, `src/layouts/` and `src/pages/index.astro`. |
```

Replace the "No motion" row with, character for character:

```
| No motion | pass | `src/styles/site.css` declares no `animation` or `transition` property anywhere in the file (grep-verified and asserted by `test/a11y.test.ts`); the only visual change on interaction is the `.icon-toggle:hover` background swap and the `:focus-visible` outline, both instantaneous. |
```

Append to the "Re-walk log", after the issue #103 entry, character for
character:

```
- Issue #108 (Q18, single icon-button toggles): the Q16 segmented pill is
  gone. Each auxiliary control is now one 32x32px bordered `.icon-toggle`
  button per CSS stance -- a moon or sun glyph for the theme, an `EN`/`RU`
  label for the language -- always showing the currently active state, so the
  "Target size at least 24px" row names `.icon-toggle` instead of
  `.toggle-group button`. With no `role="group"` set left to name, every
  button carries its own `aria-labelledby` pointing at a `.visually-hidden`
  bilingual `<Lang>` span, and the "Group naming in the active language" row
  is rewritten around that per-button pattern. The theme glyphs are
  decorative `aria-hidden="true"` SVGs inside an already-named button, so
  `checkApproachPage()` in `scripts/check-dist.mjs` now skips `aria-hidden`
  SVGs before demanding `role="img"` and a `<title>`/`<desc>` pair -- that
  requirement describes the cycle diagram, not an icon whose button already
  carries the name. No per-class focus rule was added: the site's single
  global `:focus-visible` outline covers `.icon-toggle`, and the class must
  never gain `overflow`, which would clip it.
```

### I. Journal entry

Add `src/content/journal/2026-09-13-q18-single-icon-button-toggles.md`,
frontmatter only and no body, in exactly the shape of
`2026-09-13-q16-compact-segmented-language-and-theme.md`: `service:
portfolio`, `issue:
https://github.com/mctlhq/portfolio/issues/108`, `proposal_slug:
issue-108-q18-single-icon-button-toggles-replace-t`, `status: in_progress`,
`visibility: public`, `indexing: noindex`, the `title`, `seoTitle` and
`decided` values from requirements.md Appendix B, `interventions: []`, and
`issue_opened_at` as a quoted ISO 8601 UTC timestamp (from `gh issue view 108
--repo mctlhq/portfolio --json createdAt`, falling back to
`'2026-09-13T18:00:00Z'`). No `pr`, `release`, `merged_at`, `released_at` or
`deployed_at` — the journal-closure workflow writes those.

## Alternatives

1. **Keep `role="group"` with one button inside.** Rejected: a group of one is
   not a set, screen readers announce a pointless group boundary, and it would
   keep `langToggleLabel`/`themeToggleLabel` alive for no reader benefit. The
   per-button `aria-labelledby` span carries strictly more information ("switch
   to X") in the reader's own language.
2. **Show the destination instead of the active state** (sun while dark is on,
   meaning "click for light"). Rejected: the site owner compared both readings
   live and chose active-state; the destination is still announced, through the
   accessible name, so the two conventions coexist without ambiguity for a
   screen-reader user.
3. **An icon for the language toggle too** (a globe or a "文A"-style glyph).
   Rejected in the issue: no single glyph legibly distinguishes two specific
   languages, and `EN`/`RU` at 12px/600 in `--font-display` is unambiguous at
   the same 32px target.
4. **Give each glyph `role="img"` + `<title>`/`<desc>` instead of patching
   `scripts/check-dist.mjs`.** Rejected: it contradicts section A's
   character-for-character markup, double-announces a button that already has
   an accessible name, and would need a bilingual `<title>` the SVG cannot
   express through the `.l.en`/`.l.ru` mechanism.
5. **Scope `checkApproachPage()`'s SVG scan to the `<main>` slice instead of
   filtering `aria-hidden`.** Considered and dropped: it would silently exempt
   any future decorative-or-not SVG placed in the header or footer, whereas
   the `aria-hidden="true"` filter names the exact property that makes an
   audit exemption correct.
6. **Keep `.toggle-group` in the `@media print` selector list.** Dropped: the
   class would exist nowhere else in the repository, making the print rule
   dead code; `.icon-toggle` in its place keeps every print selector live at
   zero rendering cost.

## Platform impact

- **Migrations / data.** None. No content collection schema, no metrics, no
  build config, no `public/assets/mctl/*` change.
- **Backward compatibility.** `localStorage.lang` / `localStorage.theme` keep
  their names and values; a returning visitor's preference still applies on
  the first frame through the unchanged inline script. The CSP script hash is
  unchanged because `Base.astro` is untouched.
- **Resource impact.** Net HTML per page: the two inline glyph SVGs add about
  1.0 KB (moon ~350 bytes, sun ~660 bytes), minus roughly 0.4 KB of removed
  wrapper/button markup. `MAX_INDEX_BYTES` in `scripts/check-dist.mjs` is
  40 KB and `MAX_SVG_BYTES` (approach page, diagram only after section G) is
  12 KB; both are reported on every passing run, so the implementer sees the
  actual numbers. Risk if `dist/index.html` is already near 40 KB: check the
  printed figure; no mitigation is expected to be needed and none is
  pre-authorised (raising a cap is out of scope).
- **Risk: the approach-page SVG audit (section G).** Highest-impact risk in
  this cycle, because it fails only at `node scripts/check-dist.mjs` after a
  full build, not in `npm test`. Mitigation: task 7 makes running the built
  check part of the definition of done.
- **Risk: a second `.icon-toggle` rule block.** `test/header.test.ts` T6
  requires exactly one `min-block-size` for the selector. Mitigation: section
  D states the constraint explicitly and task 3's DoD names it.
- **Risk: partial deletion of the `/* Toggle groups. */` region.**
  `.toggle-bar` and `.toggle-bar noscript` live inside that region and must
  survive; `test/a11y.test.ts` and `test/header.test.ts` T3 fail loudly if
  they do not.
- **Risk: keyboard focus.** `.icon-toggle` declares no `overflow` and no
  per-class focus rule, so the global `:focus-visible` outline draws outside
  the 32px box with the existing `outline-offset`. Visual confirmation in a
  browser is a reviewer step, per AGENTS.md, not an acceptance criterion.
- **Accessibility posture.** Unchanged or better: the accessible name gains a
  verb ("Switch to …") in the reader's language, the target size stays 32px,
  and the decorative glyph is correctly hidden from the accessibility tree.
- **Rollback.** Single-commit revert; see tasks.md.
