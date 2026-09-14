# Q18: single icon-button toggles replace the segmented pill

## Context

The header's two auxiliary controls are still the Q16 segmented pill: each of
`src/components/LangToggle.astro` and `src/components/ThemeToggle.astro`
renders two `<div class="toggle-group ...">` wrappers (one per CSS stance),
each holding two `<button>` elements joined by a `border-inline-start`
divider, with `role="group"`, a shared `aria-labelledby` and `aria-pressed`
on the segments. On a phone that reads as a small control panel wedged into
the navigation line. This cycle replaces both with a single tidy button per
control: one button whose glyph is the sun or the moon depending on which
theme is currently active, and one button whose text is `EN` or `RU`
depending on which language is currently active. The glyph/label always shows
the **currently active** state (moon visible while dark is active, `EN`
visible while English is active), not the destination a click leads to. The
two controls keep their current order — language, then theme — inside
`.toggle-bar`.

This is layout, markup and style only. No new page content, no change to what
a click does (still `[data-set-lang]` / `[data-set-theme]`, handled by the
existing delegated listener in the `is:inline` script in
`src/layouts/Base.astro`, untouched here), and no change to
`src/components/Nav.astro`, which already renders `<LangToggle />` then
`<ThemeToggle />` inside `<div class="toggle-bar">`.

The site renders every page ONCE per language/theme stance and hides the
inactive stance with CSS (`:root[data-lang='en'] .l.ru { display: none }` and
`:root[data-theme='dark'] .t.light { display: none }` at the top of
`src/styles/site.css`). There is no client-side re-render, so a button's
accessible name cannot be a hardcoded `aria-label`: the same static HTML
serves an English and a Russian screen-reader session, and a fixed English
string would be read aloud on the Russian page. Every existing control on
this site solves that with `aria-labelledby` pointing at a `.visually-hidden`
span that nests a bilingual `<Lang>` component, so the CSS stance mechanism
toggles the accessible name exactly the way it toggles visible text. This
cycle keeps that pattern — a per-button hidden span, not a per-button
`aria-label` — even though a single button is no longer part of a
`role="group"` set.

Two build gates in the repository do not survive this markup change on their
own and are therefore part of the cycle: `scripts/check-no-metrics.mjs`
(section G below) and `scripts/check-dist.mjs` (section H below, discovered by
reading the script in the clone — see design.md, "Platform impact").

## User stories

- AS a visitor on a phone I WANT the header's language and theme controls to
  be two small single buttons instead of two segmented pills SO THAT the
  navigation line reads as navigation rather than as a control panel.
- AS a visitor I WANT the visible glyph or label to name the state I am
  currently in SO THAT I can tell at a glance whether I am in dark or light
  theme, and in English or Russian, without clicking anything.
- AS a screen-reader user in either language I WANT each button to announce
  its purpose in the language the page is currently rendering SO THAT I never
  hear an English label on the Russian page.
- AS a keyboard user I WANT the focus ring to be fully visible on both
  buttons SO THAT I can see where focus is, unclipped by any container.
- AS a visitor with JavaScript disabled I WANT both `<noscript>` paragraphs
  to still render SO THAT the controls' inertness is explained rather than
  silent.
- AS the repository maintainer I WANT `npm test`, `scripts/check-contrast.mjs`,
  `scripts/check-links.mjs`, `scripts/check-dist.mjs` and
  `scripts/check-headers.mjs` to keep passing SO THAT the Docker build and the
  pre-merge gate stay green and the change is evidenced by a run, not by prose.

## Acceptance criteria (EARS)

1. WHEN `src/components/LangToggle.astro` is rendered THE SYSTEM SHALL emit
   exactly two `<button type="button" class="… icon-toggle …">` elements, no
   wrapping `<div>` and no `role="group"`, matching Appendix B character for
   character.
2. WHEN `src/components/ThemeToggle.astro` is rendered THE SYSTEM SHALL emit
   exactly two `<button type="button" class="… icon-toggle …">` elements, no
   wrapping `<div>` and no `role="group"`, matching Appendix A character for
   character.
3. WHILE the page is in dark stance THE SYSTEM SHALL show the moon button
   (`.t.dark`, `data-set-theme="light"`) and hide the sun button, and WHILE
   the page is in light stance THE SYSTEM SHALL show the sun button
   (`.t.light`, `data-set-theme="dark"`) and hide the moon button.
4. WHILE the page is in English stance THE SYSTEM SHALL show the `EN` button
   (`.l.en`, `data-set-lang="ru"`) and hide the `RU` button, and WHILE the
   page is in Russian stance THE SYSTEM SHALL show the `RU` button
   (`.l.ru`, `data-set-lang="en"`) and hide the `EN` button.
5. WHERE a button needs an accessible name THE SYSTEM SHALL supply it through
   `aria-labelledby` pointing at a sibling `.visually-hidden` span that nests
   a bilingual `<Lang>` component, and THE SYSTEM SHALL NOT emit any
   `aria-label` attribute in either component.
6. THE SYSTEM SHALL render every `.icon-toggle` as a 32x32px box
   (`inline-size`, `block-size`, `min-inline-size` and `min-block-size` all
   `32px`) with a `1px solid var(--surface-line)` border,
   `var(--mctl-radius-lg)` corners, a `var(--surface-card)` background and
   `var(--surface-fg-muted)` foreground, matching Appendix D character for
   character.
7. WHEN an `.icon-toggle` receives keyboard focus THE SYSTEM SHALL show the
   site's existing global `:focus-visible` outline, unclipped, using no
   per-class focus rule and declaring no `overflow` on `.icon-toggle`.
8. THE SYSTEM SHALL add the four `ui` keys in Appendix C character for
   character, and SHALL remove `langToggleLabel` and `themeToggleLabel`,
   which name the now-deleted `role="group"` sets and have no remaining
   reference. `langEn`, `langRu`, `themeDark`, `themeLight`, `langNoScript`
   and `themeNoScript` SHALL NOT be removed.
9. THE SYSTEM SHALL delete the entire `/* Toggle groups. */` block in
   `src/styles/site.css` (the `.toggle-group`, `.toggle-group button`,
   `.toggle-group button:first-child`, `.toggle-group button:last-child`,
   `.toggle-group button + button` and
   `.toggle-group button[aria-pressed='true']` rules) and the separate
   `.toggle-group button { display: inline-flex; align-items: center;
   min-block-size: 32px; }` rule in the tap-target block, replacing them with
   Appendix D.
10. THE SYSTEM SHALL leave the `.toggle-bar` and `.toggle-bar noscript` rules
    with their Q16 declarations (`display: flex`, `flex-wrap: wrap`,
    `gap: var(--mctl-space-4)`, `padding-block: 0`,
    `margin-inline-start: auto`, `justify-content: flex-end`, and
    `flex-basis: 100%` / `text-align: end` on the noscript paragraphs)
    untouched.
11. WHEN `node --test test/nav.test.ts` runs THE SYSTEM SHALL pass the
    replacement test in Appendix E1, and every other assertion in that file
    (the bilingual-template-literal check, `Base.astro`'s skip link,
    `Nav.astro`'s four literal hrefs, `Nav.astro`'s `aria-labelledby`) SHALL
    keep passing unchanged.
12. WHEN `node --test test/a11y.test.ts` runs THE SYSTEM SHALL pass with
    `'.toggle-group button'` replaced by `'.icon-toggle'` in
    `TARGET_SELECTORS` and no other entry in that array changed; every other
    test in that file SHALL keep passing unchanged.
13. WHEN `node --test test/header.test.ts` runs THE SYSTEM SHALL pass with T4
    and T5 removed outright, the replacement test in Appendix E2 added in
    their place, and T6 reading `.icon-toggle` in place of
    `.toggle-group button`; T1, T2 and T3 SHALL keep passing unchanged.
14. WHEN `node scripts/check-contrast.mjs` runs THE SYSTEM SHALL resolve the
    new `surface-card` semantic token in both themes and SHALL check and pass
    the `surface-fg-muted` over `surface-card` pair at the 4.5:1 text
    threshold, per Appendix F, reporting 29 pairs checked (up from 27).
15. WHEN `node scripts/check-no-metrics.mjs` runs THE SYSTEM SHALL exit 0 and
    report zero unclassified matches, with the `ThemeToggle.astro` ALLOW entry
    in Appendix G present and no stale value in it.
16. WHEN `node scripts/check-dist.mjs` runs against a real `dist/` tree THE
    SYSTEM SHALL exit 0, with `checkApproachPage()` scoped to the DevLoop
    cycle diagram's own `<svg>` elements per Appendix H, so the two decorative
    `aria-hidden` glyphs the header now renders on every page do not fail its
    `role="img"` / `aria-labelledby` / `<title>` / `<desc>` assertions or
    consume the diagram's 12 KB byte budget.
17. THE SYSTEM SHALL update `docs/accessibility-checklist.md` per Appendix I:
    the "Target size at least 24px" row names `.icon-toggle` at 32px, the
    "Group naming in the active language" row describes the per-button
    `aria-labelledby` pattern, the "No motion" row no longer cites the
    retired `[aria-pressed='true']` colour swap, the "Contrast in both
    themes" row reports 29 checked pairs, and one re-walk log entry for this
    issue is added in the same style as the existing Q16 entry.
18. THE SYSTEM SHALL add exactly one new journal entry at
    `src/content/journal/2026-09-14-q18-single-icon-button-toggles.md` per
    Appendix J, `status: in_progress` with no `release`, `released_at` or
    `deployed_at` (the repository currently holds no other `in_progress`
    entry, and `checkJournalCollection()` allows at most one).
19. WHILE JavaScript is enabled THE SYSTEM SHALL keep both clicks working
    through the untouched delegated listener in `src/layouts/Base.astro`, and
    WHILE JavaScript is disabled THE SYSTEM SHALL still render both
    `<noscript>` paragraphs.
20. THE SYSTEM SHALL NOT introduce any `animation` or `transition` property
    anywhere in `src/styles/site.css`.
21. IF `npm test`, `node scripts/check-contrast.mjs`,
    `node scripts/check-links.mjs`, `node scripts/check-dist.mjs` or
    `node scripts/check-headers.mjs` fails THEN THE SYSTEM SHALL NOT be
    considered done.

## Out of scope

- `src/components/Nav.astro`. It already renders `<LangToggle />` then
  `<ThemeToggle />` in that order inside `<div class="toggle-bar">`; nothing
  in it changes.
- `src/layouts/Base.astro`'s inline script, its CSP hash, and the delegated
  `[data-set-lang]` / `[data-set-theme]` click handler.
- `.toggle-bar`'s own CSS. Two 32px buttons fit the existing right-aligned
  flex row without adjustment.
- Any accent-tinted variant of the glyph/label colour. `--surface-fg-muted`
  is the only colour these two controls ever use, matching every other
  auxiliary (non-CTA) control on the site.
- Any radius or size other than `--mctl-radius-lg` / 32px. These were
  compared live against three alternatives before the issue was written;
  8px/32px is the settled choice and is not to be re-litigated here.
- Icons for anything other than the theme toggle. The language control stays
  text (`EN` / `RU`) — there is no legible single glyph for a two-language
  toggle.
- Any change to `public/assets/mctl/*` (SHA-pinned by
  `scripts/vendor-assets.mjs`) or to any other page section, the footer, the
  hero, or the stats.
- Any change to `test/support/css-rules.ts`, `test/link-cascade.test.ts` or
  the header of `test/header.test.ts` beyond what sections E and H require.
  Their prose references to `.toggle-group` describe the `@media print`
  selector list, which this cycle leaves in place (see Open questions).

## Open questions

1. **The `@media print` selector list still names `.toggle-group`.**
   `src/styles/site.css`'s print block declares
   `.site-header, .toggle-group, .ctas { display: none; }`. After this cycle
   no element carries `toggle-group`, so that selector is inert — but it was
   already redundant, because the same rule hides `.site-header`, which
   contains `.toggle-bar` and therefore both buttons. The issue authorises no
   change to it, and the header comments in `test/header.test.ts` and
   `test/support/css-rules.ts` cite `.toggle-group` as the worked example of a
   selector that resolves to two rule blocks. Decision taken: leave the print
   selector list exactly as it is. Cleaning it up is a one-line follow-up for
   a later cycle.
2. **`docs/accessibility-checklist.md`'s "No motion" and "Contrast in both
   themes" rows go stale as a side effect.** The issue's criterion 6 names
   only the "Target size" and "Group naming" rows, but the "No motion" row
   asserts that "the only visual change on interaction is the
   `[aria-pressed='true']` colour swap on the language/theme toggles", and
   that rule is deleted here; and the "Contrast in both themes" row states
   "Twenty-seven pairs now clear their threshold", which becomes twenty-nine
   once section F adds one pair evaluated in two themes. Both corrections are
   specified verbatim in Appendix I. Flagged for the approver: this is two
   more sentences of documentation than the issue literally asked for, kept
   because leaving a checklist row that contradicts the code is worse.
3. **`scripts/check-dist.mjs` needs a change the issue does not authorise
   (Appendix H).** Verified by reading the clone:
   `checkApproachPage()` extracts *every* `<svg>` on
   `dist/approach/index.html` and asserts `role="img"`, a resolving
   `aria-labelledby`, exactly one `<title>` and exactly one `<desc>` on each.
   The header renders on every page, so the two new decorative
   `aria-hidden="true"` sun/moon glyphs land on the approach page and would
   produce six failures; the script runs in the `Dockerfile` (`RUN npm run
   build && node scripts/check-dist.mjs && …`), so the image build and CI's
   `build` job would fail. Acceptance criterion 7 of the issue explicitly
   requires `check-dist.mjs` to pass, so the fix is in scope by consequence
   even though the file is not in the issue's "Files expected to change"
   list. This is the same shape of gap the issue's own section G records for
   `check-no-metrics.mjs`. **The approver should read Appendix H before
   approving.**
4. **`issue_opened_at` for the journal entry — corrected by the approver.**
   Issue #108's actual `createdAt` is `2026-09-13T22:48:25Z` (`gh issue view
   108 --json createdAt`); Appendix J is corrected to that value below,
   replacing the implementer-unreachable placeholder this proposal
   originally computed. This is the same reading Q17 (portfolio#105)
   establishes as the convention: the issue's own creation instant, not a
   round or guessed value.
5. **`dist/index.html`'s 40 KB cap.** `MAX_INDEX_BYTES` in
   `scripts/check-dist.mjs` is 40 KB. The net markup delta here is small
   (roughly +900 bytes of SVG and hidden spans, minus roughly 400 bytes of
   deleted wrapper divs and `aria-pressed` attributes), so no problem is
   expected, and the script prints the measured size on every run. No
   mitigation is proposed; if the cap were ever hit, that is a separate
   issue.

---

## Appendix A — `src/components/ThemeToggle.astro`, full replacement

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

## Appendix B — `src/components/LangToggle.astro`, full replacement

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

## Appendix C — `src/i18n/ui.ts`

Add four new keys, character for character, placed near the existing
`langEn` / `langRu` / `themeDark` / `themeLight` keys:

```ts
themeSwitchToDark: { en: 'Switch to dark theme', ru: 'Переключить на тёмную тему' },
themeSwitchToLight: { en: 'Switch to light theme', ru: 'Переключить на светлую тему' },
langSwitchToEn: { en: 'Switch to English', ru: 'Переключить на английский' },
langSwitchToRu: { en: 'Switch to Russian', ru: 'Переключить на русский' },
```

Remove `langToggleLabel: { en: 'Language', ru: 'Язык' },` and
`themeToggleLabel: { en: 'Theme', ru: 'Тема' },`. They named the now-deleted
`role="group"` sets; after Appendices A and B the only references to them in
the repository are gone (verified: `langToggleLabel` and `themeToggleLabel`
appear today only in `src/i18n/ui.ts`, `LangToggle.astro` and
`ThemeToggle.astro`). `langEn`, `langRu`, `themeDark`, `themeLight`,
`langNoScript` and `themeNoScript` are all still used (visible label text and
`<noscript>` copy) and are NOT removed. If a test pins
`langToggleLabel` / `themeToggleLabel`, update that test in the same commit
rather than leaving the keys in place to satisfy it.

## Appendix D — `src/styles/site.css`

Delete the entire `/* Toggle groups. */` block — the `.toggle-group`,
`.toggle-group button`, `.toggle-group button:first-child`,
`.toggle-group button:last-child`, `.toggle-group button + button` and
`.toggle-group button[aria-pressed='true']` rules — keeping the `.toggle-bar`
and `.toggle-bar noscript` rules that sit between them exactly as they are.
Also delete the separate `.toggle-group button` rule near the tap-target
block (the one declaring `display: inline-flex; align-items: center;
min-block-size: 32px;` under the "Tap targets" comment) together with the
three-line comment above it that describes the language and theme segments.
Replace with, character for character:

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

The site's single global `:focus-visible` rule (`:focus-visible { outline:
var(--focus-ring-width) solid var(--focus-ring); outline-offset:
var(--focus-ring-offset); }`) already covers `.icon-toggle`; no per-class
focus override is needed or wanted. `--surface-card` is a token
`public/assets/mctl/mctl.css` already ships and defines for both stances
(`--surface-card: var(--mctl-surface-dark-card)` /
`var(--mctl-surface-light-card)`); `scripts/check-contrast.mjs` does not yet
resolve it (see Appendix F).

Do NOT add a `.toggle-bar` or `.toggle-bar noscript` change — both keep their
Q16 declarations (`gap`, `margin-inline-start: auto`,
`justify-content: flex-end`, `text-align: end` on the noscript paragraphs)
untouched; two 32px buttons fit that layout exactly as the two former pills
did.

## Appendix E — tests

### E1. `test/nav.test.ts`

Replace the test named `'LangToggle.astro and ThemeToggle.astro give every
.toggle-group role="group" and an aria-labelledby, never an aria-label'`
with, character for character:

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

Every other assertion in `test/nav.test.ts` (the bilingual-template-literal
check, `Base.astro`'s skip link, `Nav.astro`'s four literal hrefs,
`Nav.astro`'s `aria-labelledby`, `Nav.astro` emitting no `<script`) is
unaffected and must keep passing unchanged.

### E2. `test/header.test.ts`

Remove test T4 (`'some .toggle-group block declares a border and a
border-radius, and no .toggle-group block declares overflow'`) and test T5
(`'a rule block whose selector list includes .toggle-group button + button
declares border-inline-start'`) outright: there is no more segmented
container and no more adjacent-sibling divider for either to describe. Add
one replacement test in their place, character for character:

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
32px, .site-nav a and .site-footer a resolve to 44px'`) to read
`.icon-toggle` in place of `.toggle-group button`, in both the test name and
the `minBlockSizes(siteCss, …)` argument; its `.site-nav a` /
`.site-footer a` assertions are unchanged. T1, T2 and T3 (the `.site-header`
row, `.site-nav`'s missing `border-bottom`, `.toggle-bar`'s
`margin-inline-start: auto`) are unrelated to this cycle and must keep
passing unchanged.

Note for the implementer: `ruleBlockBodies()` matches an *exact*
comma-split selector, so `.icon-toggle:hover` and `.icon-toggle svg` are not
`.icon-toggle` and do not enter either list; Appendix D therefore yields
exactly one `.icon-toggle` body and `minBlockSizes(siteCss, '.icon-toggle')`
is exactly `[32]`. Both test files strip `/* … */` comments before parsing,
so the word `overflow` inside Appendix D's comment cannot trip the
`.every()` assertion.

### E3. `test/a11y.test.ts`

In `TARGET_SELECTORS`, replace the literal `'.toggle-group button'` with
`'.icon-toggle'`. No other entry in that array changes. All other tests in
this file (the `:focus-visible` rule, the no-animation/no-transition
assertion, the `.toggle-bar` rule, `.site-nav a[aria-current]`'s colour and
text-decoration, `Lang.astro` emitting `lang="ru"`, and the table
assertions) must keep passing unchanged.

## Appendix F — `scripts/check-contrast.mjs`

`SEMANTIC_TOKENS` has no entry for the `--surface-*-card` token this cycle
introduces as `.icon-toggle`'s background, so the new glyph/label colour
cannot be checked without extending it. Add, character for character, to
BOTH the `dark` and `light` objects in `SEMANTIC_TOKENS`:

```js
'surface-card': 'mctl-surface-dark-card',
```
```js
'surface-card': 'mctl-surface-light-card',
```

(the dark value in the `dark` object, the light value in the `light` object —
same placement pattern as the six existing keys in each).

Add one entry to `PAIRS`, character for character:

```js
{ fg: 'surface-fg-muted', bg: 'surface-card', kind: 'text' },
```

`kind: 'text'` (the 4.5:1 threshold), not `'focus-ring'` (3:1): the language
button's `EN` / `RU` label is real text at 12px/600, below the WCAG
large-text threshold (18.66px bold), so it needs the stricter ratio — and
because both buttons inherit their colour from the same
`color: var(--surface-fg-muted)` declaration via `currentColor` on the SVG,
one pair covers the theme button's icon too (a non-text glyph, which only
strictly needs 3:1, clears the stricter number for free). Do not add a
second, separate `kind: 'focus-ring'` pair for the icon — that would just
duplicate the same two hex values under a lower bar.

Measured against the vendored tokens in the clone
(`public/assets/mctl/mctl.baf7fec1.css`): dark `#a4a8ae` over `#15181d` is
7.45:1; light `#3a3f47` over `#fffdf8` is 10.42:1. Both clear 4.5:1 with
room. The run's summary line goes from 27 pairs checked to 29 (14 -> 16 from
the `PAIRS` loop across two themes, plus the unchanged 13 content-link
lines).

## Appendix G — `scripts/check-no-metrics.mjs`

`check-no-metrics.mjs` runs first in `npm test`
(`node scripts/check-no-metrics.mjs && node scripts/check-contrast.mjs &&
node --test …`) and fails the build on any two-or-more-digit run
(`\b[0-9]{2,}\b`) under `src/components/**` that is not classified by a
`RULES` pattern or named in `ALLOW`. The sun/moon SVG markup in Appendix A is
full of fractional coordinates (`1.75`, `19.78`, `4.22`, …), and the digits
after each decimal point are exactly this shape of match — e.g. `"75"` from
`stroke-width="1.75"`, `"01"` from `y1="18.01"`. A first implementation
attempt on this issue ran the gate, found 60+ unclassified matches,
correctly identified that no authorisation for an `ALLOW` entry existed, and
stopped without committing. This appendix is that authorisation.

Add one entry to `ALLOW` in `scripts/check-no-metrics.mjs`, character for
character, in the same array as the existing `CycleDiagram.astro` and
`Base.astro` entries:

```js
{
  file: 'src/components/ThemeToggle.astro',
  values: [1, 2, 3, 5, 7, 10, 12, 14, 18, 19, 22, 24, 25, 45, 55, 75, 78, 85, 95, 99],
  reason:
    'Hand-authored sun/moon SVG glyphs: stroke-width, viewBox extent and path/line ' +
    'coordinates. ThemeToggle.astro is props-less and never imports ' +
    'src/data/metrics.json, so none of these can be a metric value; most are the ' +
    'leading-zero or fractional tail of a decimal coordinate (e.g. "75" from ' +
    'stroke-width="1.75", "01" from y1="18.01") that \\b[0-9]{2,}\\b matches as a ' +
    'standalone token.',
},
```

This is the exact, complete distinct-value set for the markup in Appendix A.
It was recomputed during investigation by importing the real
`scanForTypedNumbers()` and `RULES` from `scripts/check-no-metrics.mjs` and
running them, with an empty `ALLOW`, over a temporary tree containing exactly
Appendix A's file: 70 matches, 70 unclassified, distinct values
`[1,2,3,5,7,10,12,14,18,19,22,24,25,45,55,75,78,85,95,99]` — identical to the
list above. If any implementer changes a single coordinate in Appendix A's
SVGs, this list must be recomputed the same way (run
`node scripts/check-no-metrics.mjs` against the new markup and read its
"not permitted" lines) rather than hand-adjusted, exactly as the file's own
header comment requires ("a stale ALLOW entry … is itself a failure"): the
script reports both an unclassified match and a listed value that matches
nothing.

`LangToggle.astro` introduces no numeric literals and needs no entry.

## Appendix H — `scripts/check-dist.mjs`

Not named in the issue; required for the issue's own acceptance criterion 7
("`scripts/check-dist.mjs` … pass"). See Open question 3.

`checkApproachPage()` in `scripts/check-dist.mjs` today does:

```js
  const slices = extractSvgSlices(html);
```

where `extractSvgSlices(html)` returns `html.match(/<svg\b[\s\S]*?<\/svg>/g)`
— *every* `<svg>` on `dist/approach/index.html`. It then asserts, per slice,
`role="img"`, an `aria-labelledby` whose every token resolves to a
`<title>`/`<desc>` `id` inside the same `<svg>`, and exactly one `<title>`
and one `<desc>`; and it sums every slice's bytes against
`MAX_SVG_BYTES` (12 KB). Both assertions are scoped, in the function's own
docstring, to "the two inline `<svg>` variants of the DevLoop cycle diagram".
Appendix A puts two decorative `aria-hidden="true"` glyphs into the header,
which `src/layouts/Base.astro` renders on every page including
`/approach/`, so without this change the script emits six new problems (a
missing `role="img"`, a missing `aria-labelledby` and a
`0 <title> and 0 <desc>` count for each glyph) and exits 1 — failing the
`RUN npm run build && node scripts/check-dist.mjs && …` step in `Dockerfile`
and therefore CI's `build` job.

Replace that one line with, character for character:

```js
  // Issue #108 (Q18): the header's ThemeToggle renders two decorative,
  // aria-hidden sun/moon <svg> glyphs into every page, this one included.
  // The per-slice loop below asserts the DevLoop cycle diagram's own
  // contract (role="img", an aria-labelledby resolving to a <title>/<desc>
  // pair) and the 12 KB budget this function's docstring scopes to "the two
  // inline <svg> variants of the DevLoop cycle diagram" -- neither applies
  // to a decorative glyph. Narrow the slice list to the diagram by the
  // `cycle-svg` class src/components/CycleDiagram.astro puts on both
  // variants, so an unrelated inline icon anywhere in the layout can
  // neither fail this check nor eat the diagram's byte budget.
  const slices = extractSvgSlices(html).filter((slice) => /\bcycle-svg\b/.test(svgOpenTag(slice)));
```

`src/components/CycleDiagram.astro` renders both variants as
`class={`cycle-svg cycle-${v.key}`}`, so the filter keeps exactly the two
slices the function was written for; `slices.length < 2`, `svgBytes`, the
per-slice loop and the `sawNarrowSlice` check all keep their existing
meaning. Nothing else in `scripts/check-dist.mjs` changes, and no other
function in that file inspects `<svg>` elements.

## Appendix I — `docs/accessibility-checklist.md`

Four table-row notes and one re-walk log entry. Replace only the note cell
(the third column) of each named row; leave the row's Item and Result cells
as they are.

**"Target size at least 24px" row** — replace the note with, character for
character:

```
`src/styles/site.css` sets `min-block-size: 44px` — above the 24px CSS Working Group "AA equivalent" floor named in the issue — on `.site-nav a`, `.site-footer a`, `.cta` and `.block > summary`, and a fixed 32x32px box (`inline-size`, `block-size`, `min-inline-size` and `min-block-size`, all `32px`) on `.icon-toggle`, the two auxiliary single-button language and theme controls in the header; both are above the 24px floor, both are asserted by `test/a11y.test.ts`, and T6 in `test/header.test.ts` pins the 32px figure to exactly one declaration.
```

**"Group naming in the active language" row** — replace the note with,
character for character:

```
Since issue #108 (Q18) each auxiliary control is a single `<button class="… icon-toggle …">` rather than a `role="group"` pair, so there is no group left to name: every button carries its own `aria-labelledby` pointing at its own `.visually-hidden` bilingual `<Lang>` span (`theme-toggle-to-light`, `theme-toggle-to-dark` in `src/components/ThemeToggle.astro`; `lang-toggle-to-ru`, `lang-toggle-to-en` in `src/components/LangToggle.astro`). A literal `aria-label` is still ruled out for the reason it always was: the page is rendered once and the stance is switched with CSS, so one hardcoded English string would be read aloud in a Russian session. The `site-nav` `<nav>` and the home page's `.ctas` `<nav>` keep the same `aria-labelledby` mechanism. `checkNavigationState()` fails the build on any remaining `aria-label` value that mixes a Latin and a Cyrillic letter, exempting only the out-of-scope `.table-scroll` region on `dist/colophon/index.html`; `test/nav.test.ts` asserts the two `.icon-toggle` buttons per component, each with an `aria-labelledby`, and the absence of `role="group"`, of any `aria-label` and of any remaining `${…en} / ${…ru}` template literal in `src/components/`, `src/layouts/` and `src/pages/index.astro`.
```

**"No motion" row** — replace the note with, character for character:

```
`src/styles/site.css` declares no `animation` or `transition` property anywhere in the file (grep-verified and asserted by `test/a11y.test.ts`); since issue #108 (Q18) retired the `[aria-pressed='true']` segment rule, the only visual changes on interaction are the `.icon-toggle:hover` background swap and the `:focus-visible` outline, both instantaneous.
```

**"Contrast in both themes" row** — in its existing note, replace the single
sentence opening `Twenty-seven pairs now clear their threshold, up from
fourteen:` with, character for character:

```
Twenty-nine pairs now clear their threshold, up from fourteen — issue #108 (Q18) added `surface-fg-muted` over `surface-card`, the new `.icon-toggle` background, at the 4.5:1 text minimum in both themes (7.45:1 dark, 10.42:1 light):
```

Leave the rest of that note (the tightest-pair sentence about `accent` over
`surface-bg` at 4.81:1 and the print override at 5.62:1) unchanged.

**Re-walk log** — append one entry after the existing Issue #103 (Q16)
entry, character for character:

```
- Issue #108 (Q18, single icon-button toggles): the two segmented pills were
  replaced by one 32x32px bordered button each -- a sun or moon glyph for the
  theme, an `EN`/`RU` label for the language, both naming the state that is
  currently active rather than the one a click leads to. `role="group"` and
  `aria-pressed` are gone, so each button now carries its own
  `aria-labelledby` pointing at its own `.visually-hidden` bilingual span; the
  target size stays 32px and the site's single global `:focus-visible` rule
  still draws the ring unclipped, because `.icon-toggle` declares no
  `overflow` and no per-class focus override was added.
  `scripts/check-contrast.mjs` gained the `surface-fg-muted` over
  `surface-card` pair the new button background introduces, taking the
  checked total from twenty-seven to twenty-nine.
```

## Appendix J — the journal entry

Create `src/content/journal/2026-09-14-q18-single-icon-button-toggles.md`
with exactly this frontmatter and no body (every existing entry is
frontmatter only):

```md
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/108
proposal_slug: issue-108-q18-single-icon-button-toggles-replace-t
status: in_progress
visibility: public
indexing: noindex
title:
  en: "Q18: single icon-button toggles replace the segmented pill"
  ru: "Q18: одиночные кнопки-иконки вместо сегментированного переключателя"
seoTitle: "Single icon-button language and theme toggles — Dmitrii Mashkov"
decided:
  en: "The header's language and theme controls were still the Q16 segmented pill: two <div class=\"toggle-group\"> wrappers per control, one per CSS stance, each holding two buttons joined by an internal divider, with role=group, a shared aria-labelledby and aria-pressed on the segments. On a phone that reads as a control panel wedged into the navigation line. This cycle replaces each control with a single 32x32px bordered button: one carrying a hand-authored sun or moon glyph, one carrying an EN or RU label, both naming the state that is currently active rather than the destination a click leads to. Because the site renders every page once per stance and hides the inactive half with CSS, a hardcoded aria-label would be read aloud in the wrong language, so each button keeps the site's existing pattern -- aria-labelledby pointing at its own visually-hidden bilingual span -- even though a single button is no longer part of a set. Nav.astro, Base.astro's delegated click listener and .toggle-bar's own CSS are untouched; the whole toggle-groups CSS region and the separate 32px tap-target rule are replaced by one .icon-toggle block that declares no overflow, so the global focus ring stays unclipped, and no per-class focus override was added. Three build gates moved with the markup: check-no-metrics.mjs gained an ALLOW entry for the SVG's fractional coordinates, computed by running the gate's own matcher rather than estimated; check-contrast.mjs learned to resolve the surface-card token the new button background uses and now checks surface-fg-muted over it at the 4.5:1 text minimum in both themes, taking its checked total from twenty-seven pairs to twenty-nine; and check-dist.mjs's approach-page SVG audit, which asserted role=img and a title/desc pair on every inline SVG on that page, was narrowed to the DevLoop cycle diagram's own cycle-svg class, so a decorative aria-hidden glyph in the shared header can neither fail an audit written for the diagram nor eat its 12 KB byte budget."
  ru: "Переключатели языка и темы в шапке всё ещё были сегментированной плашкой из Q16: по два <div class=\"toggle-group\"> на контрол, по одному на каждое CSS-состояние, в каждом две кнопки, разделённые внутренней линией, с role=group, общим aria-labelledby и aria-pressed на сегментах. На телефоне это читалось как пульт управления, втиснутый в строку навигации. Этот цикл заменяет каждый контрол одной кнопкой 32x32px с рамкой: одна несёт нарисованную вручную иконку солнца или луны, другая — надпись EN или RU, и обе показывают состояние, активное прямо сейчас, а не то, куда ведёт клик. Поскольку сайт рендерит каждую страницу один раз на состояние и прячет неактивную половину через CSS, жёстко заданный aria-label читался бы вслух не на том языке, поэтому каждая кнопка сохраняет уже принятый на сайте приём — aria-labelledby, указывающий на собственный visually-hidden двуязычный span, — даже несмотря на то, что одиночная кнопка больше не входит в группу. Nav.astro, делегированный обработчик кликов в Base.astro и собственный CSS .toggle-bar не тронуты; весь блок toggle groups и отдельное правило тап-таргета в 32px заменены одним блоком .icon-toggle, который не объявляет overflow, поэтому глобальное кольцо фокуса не обрезается, и отдельного правила фокуса для класса не добавлено. Вместе с разметкой сдвинулись три контрольных скрипта: check-no-metrics.mjs получил запись ALLOW для дробных координат SVG, вычисленную запуском собственного матчера гейта, а не на глаз; check-contrast.mjs научился резолвить токен surface-card, который использует новый фон кнопки, и теперь проверяет surface-fg-muted поверх него по порогу 4.5:1 для текста в обеих темах, доводя число проверяемых пар с двадцати семи до двадцати девяти; а проверка SVG на странице approach в check-dist.mjs, требовавшая role=img и пары title/desc от каждого встроенного SVG на этой странице, сужена до собственного класса cycle-svg диаграммы DevLoop, чтобы декоративная иконка с aria-hidden в общей шапке не могла ни провалить аудит, написанный для диаграммы, ни съесть её бюджет в 12 КБ."
interventions: []
issue_opened_at: '2026-09-13T22:48:25Z'
---
```

`scripts/close-journal.mjs` fills `status: complete`, `pr`, `release`,
`merged_at` and `released_at` after the release; do not write them here.
`statusEvidenceProblems()` in `src/lib/journal.ts` rejects an `in_progress`
entry that carries `release`, `released_at` or `deployed_at`, and
`checkJournalCollection()` rejects a second `in_progress` entry — the
repository currently has none, so this is the only one.
