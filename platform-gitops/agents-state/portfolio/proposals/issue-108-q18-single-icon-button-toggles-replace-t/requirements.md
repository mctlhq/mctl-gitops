# Q18: single icon-button toggles replace the segmented pill

## Context

The site header currently carries two Q16 segmented pills: `LangToggle.astro`
renders two `<div class="toggle-group l en/ru" role="group">` wrappers, each
holding two `<button>` elements joined by a `border-inline-start` divider, and
`ThemeToggle.astro` does the same for the theme. Each control therefore shows
two adjacent labels at once (`EN|RU`, `Dark|Light`) with an `aria-pressed`
colour swap marking the active half. On a phone the pair reads as a small
control panel wedged into the navigation line.

This cycle replaces both pills with one tidy button each. Each component keeps
exactly the same two-element-per-CSS-stance structure it has today (`.l.en` /
`.l.ru`, `.t.dark` / `.t.light`, hidden from each other by the existing
`:root[data-lang]` / `:root[data-theme]` `display: none` rules), but each
stance becomes a single 32x32px bordered square button holding one glyph (a
moon while the dark theme is active, a sun while light is active) or one
two-letter label (`EN` while English is active, `RU` while Russian is active).
The glyph and the label always name the **currently active** state, confirmed
with the site owner against an interactive preview; the button's accessible
name says where a click leads. Nothing about what a click does changes: the
buttons keep `[data-set-lang]` / `[data-set-theme]`, and the delegated click
listener in `src/layouts/Base.astro` is untouched.

Because the site renders each page once and hides the inactive language and
theme stance with CSS, a button's accessible name cannot be a hardcoded
`aria-label` string — the same static HTML serves an English and a Russian
screen-reader session. Every existing control solves this with
`aria-labelledby` pointing at a `.visually-hidden` span that nests the
bilingual `<Lang>` component. This cycle keeps that pattern per button, even
though a single button is no longer part of a `role="group"` set.

## User stories

- AS a visitor on a phone I WANT the header's language and theme controls to
  be two small single-purpose buttons SO THAT the navigation line reads as a
  navigation line and not as a control panel.
- AS a visitor I WANT each control's glyph or label to show the state that is
  active right now SO THAT I can tell at a glance which theme and which
  language I am reading in.
- AS a screen-reader user in either language I WANT every control to announce
  its purpose in the language I am reading SO THAT the control is usable
  without a second, foreign-language reading.
- AS a keyboard user I WANT the focus ring to be fully visible on both
  buttons SO THAT I never lose my place in the header.
- AS a visitor with JavaScript disabled I WANT the two `<noscript>`
  explanations to keep rendering SO THAT an inert control is explained rather
  than silently broken.
- AS the repository owner I WANT `npm test` and every `scripts/check-*.mjs`
  gate to keep passing SO THAT the change is proven by the build rather than
  by an opinion.

## Acceptance criteria (EARS)

Markup

- WHEN `src/components/ThemeToggle.astro` is rendered THE SYSTEM SHALL emit
  exactly two `<button type="button" class="t dark icon-toggle">` /
  `<button type="button" class="t light icon-toggle">` elements, no wrapping
  `<div>`, no `role="group"` and no `aria-label`, with the file's content
  exactly as given in design.md section A.
- WHEN `src/components/LangToggle.astro` is rendered THE SYSTEM SHALL emit
  exactly two `<button type="button" class="l en icon-toggle lang-toggle">` /
  `<button type="button" class="l ru icon-toggle lang-toggle">` elements, no
  wrapping `<div>`, no `role="group"` and no `aria-label`, with the file's
  content exactly as given in design.md section B.
- WHILE the dark theme is active THE SYSTEM SHALL show the moon glyph on a
  button whose `data-set-theme` is `light` and whose accessible name is
  "Switch to light theme" / "Переключить на светлую тему".
- WHILE the light theme is active THE SYSTEM SHALL show the sun glyph on a
  button whose `data-set-theme` is `dark` and whose accessible name is
  "Switch to dark theme" / "Переключить на тёмную тему".
- WHILE English is active THE SYSTEM SHALL show the label `EN` on a button
  whose `data-set-lang` is `ru` and whose accessible name is "Switch to
  Russian" / "Переключить на русский".
- WHILE Russian is active THE SYSTEM SHALL show the label `RU` on a button
  whose `data-set-lang` is `en` and whose accessible name is "Switch to
  English" / "Переключить на английский".
- WHERE a button needs an accessible name THE SYSTEM SHALL take it from
  `aria-labelledby` pointing at a sibling `<span class="visually-hidden">`
  that nests a bilingual `<Lang>` component, and SHALL NOT use a literal
  `aria-label` anywhere in either component.
- WHEN either component is rendered THE SYSTEM SHALL still emit its
  `<noscript><p>` paragraph with the unchanged `langNoScript` /
  `themeNoScript` copy.

Strings

- WHEN `src/i18n/ui.ts` is read THE SYSTEM SHALL contain the four new keys
  `themeSwitchToDark`, `themeSwitchToLight`, `langSwitchToEn` and
  `langSwitchToRu` with the exact values in Appendix A, placed near the
  existing `langEn` / `langRu` / `themeDark` / `themeLight` keys.
- WHEN `src/i18n/ui.ts` is read THE SYSTEM SHALL NOT contain
  `langToggleLabel` or `themeToggleLabel`, and SHALL still contain `langEn`,
  `langRu`, `themeDark`, `themeLight`, `langNoScript` and `themeNoScript`.
- IF a test pins `langToggleLabel` or `themeToggleLabel` THEN THE SYSTEM SHALL
  have that test updated in the same commit rather than the keys retained to
  satisfy it.

Style

- WHEN `src/styles/site.css` is read THE SYSTEM SHALL contain no
  `.toggle-group`, `.toggle-group button`, `.toggle-group button:first-child`,
  `.toggle-group button:last-child`, `.toggle-group button + button` or
  `.toggle-group button[aria-pressed='true']` rule block, and no
  `.toggle-group button` `min-block-size: 32px` rule in the tap-target block.
- WHEN `src/styles/site.css` is read THE SYSTEM SHALL contain the
  `.icon-toggle`, `.icon-toggle:hover`, `.icon-toggle svg` and `.lang-toggle`
  rules exactly as given in design.md section D, giving each button a 32x32px
  box, a `1px solid var(--surface-line)` border, `var(--mctl-radius-lg)`
  corners, a `var(--surface-card)` background and
  `color: var(--surface-fg-muted)`.
- WHILE `.icon-toggle` exists THE SYSTEM SHALL declare no `overflow` property
  on it, so the global `:focus-visible` outline (drawn outside the box by
  `outline-offset`) is never clipped.
- WHEN a `.icon-toggle` receives keyboard focus THE SYSTEM SHALL show the
  site's existing single global `:focus-visible` outline, with no per-class
  focus rule added.
- WHEN `src/styles/site.css` is read THE SYSTEM SHALL keep `.toggle-bar` and
  `.toggle-bar noscript` exactly as Q16 left them (`display: flex`,
  `flex-wrap: wrap`, `gap: var(--mctl-space-4)`, `padding-block: 0`,
  `margin-inline-start: auto`, `justify-content: flex-end`, and
  `flex-basis: 100%` / `text-align: end` on the noscript paragraphs).
- WHEN `src/styles/site.css` is read THE SYSTEM SHALL declare no `animation`
  or `transition` property anywhere in the file.
- WHERE the `@media print` block lists the selectors it hides THE SYSTEM SHALL
  name `.icon-toggle` in place of the now-deleted `.toggle-group`, leaving the
  rest of that declaration list (`.site-header`, `.ctas`) unchanged.

Untouched behaviour

- WHEN `src/components/Nav.astro` is read THE SYSTEM SHALL still render
  `<LangToggle /><ThemeToggle />`, in that order, inside `.toggle-bar`, with
  the file otherwise unchanged.
- WHEN a visitor with JavaScript enabled clicks either button THE SYSTEM SHALL
  apply the language or theme through the unchanged delegated
  `[data-set-lang],[data-set-theme]` click listener in
  `src/layouts/Base.astro`, whose `e.target.closest?.(...)` lookup resolves the
  owning button even when the click lands on the inner SVG.
- IF `src/layouts/Base.astro`'s inline script is edited THEN THE SYSTEM SHALL
  be considered out of contract: the script's SHA-256 is pinned in the CSP and
  this cycle changes neither.

Build gates

- WHEN `scripts/check-contrast.mjs` runs THE SYSTEM SHALL resolve
  `surface-card` to `mctl-surface-dark-card` in the `dark` map and
  `mctl-surface-light-card` in the `light` map, and SHALL check one new
  `{ fg: 'surface-fg-muted', bg: 'surface-card', kind: 'text' }` pair at the
  4.5:1 text threshold in both themes, with no second `kind: 'focus-ring'`
  pair for the same two colours.
- WHEN `scripts/check-dist.mjs` runs against a built `dist/` THE SYSTEM SHALL
  exit zero: `checkApproachPage()` SHALL skip decorative `aria-hidden="true"`
  SVGs before asserting `role="img"`, `aria-labelledby`, a single
  `<title>`/`<desc>` pair and the viewBox rules, so the two header theme
  glyphs that now render on every page do not fail a check written for the
  cycle diagram.
- WHEN `npm test` runs THE SYSTEM SHALL pass, including the replaced
  `test/nav.test.ts` case, the `.icon-toggle` entry in `test/a11y.test.ts`'s
  `TARGET_SELECTORS`, and `test/header.test.ts` with T4 and T5 removed, the
  new `.icon-toggle` block test in their place and T6 reading `.icon-toggle`.
- WHEN `scripts/check-links.mjs` and `scripts/check-headers.mjs` run THE
  SYSTEM SHALL pass unchanged.

Documentation

- WHEN `docs/accessibility-checklist.md` is read THE SYSTEM SHALL name
  `.icon-toggle` at 32px in its "Target size at least 24px" row instead of
  `.toggle-group button`, SHALL describe the per-button `aria-labelledby`
  pattern in its "Group naming in the active language" row instead of the
  retired `role="group"` pair, SHALL stop citing the deleted
  `[aria-pressed='true']` colour swap in its "No motion" row, and SHALL carry
  one new re-walk log entry for issue #108 in the style of the Q16 entry.
- WHEN the cycle is committed THE SYSTEM SHALL carry one journal entry at
  `src/content/journal/2026-09-13-q18-single-icon-button-toggles.md` in the
  same frontmatter-only shape as the Q16 entry, per AGENTS.md's
  one-entry-per-cycle rule.

## Out of scope

- `src/components/Nav.astro` — it already renders `<LangToggle />` then
  `<ThemeToggle />` inside `.toggle-bar` and is not edited.
- `src/layouts/Base.astro`'s inline `is:inline` script and its CSP hash.
- `.toggle-bar` / `.toggle-bar noscript` CSS: two 32px buttons fit the
  existing right-aligned flex row with no adjustment.
- Any accent-tinted variant of the glyph or label colour;
  `--surface-fg-muted` is the only colour these controls ever use.
- Any radius or size other than `var(--mctl-radius-lg)` (8px) and 32px —
  settled live against three alternatives before the issue was written.
- Icons for the language control: it stays the text `EN` / `RU`.
- Any change to `public/assets/mctl/*` (SHA-pinned vendored tokens and fonts),
  to any other page section, to the footer, the hero or the stats.
- Any new page content beyond the one journal entry the repository's
  per-cycle rule requires.
- Adding a `kind: 'focus-ring'` contrast pair for the glyph, or any exemption
  entry in `scripts/check-contrast.mjs`'s `EXEMPTIONS`.

## Open questions

- The issue states `themeDark` and `themeLight` are "still used (visible label
  text)". After section A they are not: the theme buttons hold SVG glyphs, and
  a repo-wide grep finds no other reference. The issue is nevertheless explicit
  that they are NOT removed, so this proposal keeps them as unreferenced
  dictionary entries. No test pins their use, so nothing fails either way.
  Recorded for the reviewer; resolving it is a later cleanup, not this cycle.
- The issue's section F covers `scripts/check-contrast.mjs` but does not
  mention `scripts/check-dist.mjs`, whose `checkApproachPage()` requires
  `role="img"`, `aria-labelledby` and exactly one `<title>`/`<desc>` on
  **every** `<svg>` in `dist/approach/index.html`. The two new decorative
  header glyphs render there, so acceptance criterion 7 ("check-dist.mjs
  passes") cannot hold without the `aria-hidden` filter specified in design.md
  section G. This proposal treats that filter as in scope because the issue's
  own acceptance criterion demands it; the alternative — giving each glyph
  `role="img"` plus a `<title>`/`<desc>` — contradicts the character-for-
  character markup in section A and would double-announce an already-named
  button. Reviewer: this is the one place the proposal adds a file the issue
  did not name.
- The issue says "no new page content", while AGENTS.md requires one journal
  entry per DevLoop cycle and the Q16 cycle wrote one. This proposal reads
  "page content" as the site's own sections (hero, work, approach, footer) and
  still writes the journal entry, whose bilingual copy is fixed in Appendix B.
  If the reviewer disagrees, task 9 can be dropped without affecting any other
  acceptance criterion.
- `issue_opened_at` for the journal entry is not knowable from the issue body.
  The implementer takes it from `gh issue view 108 --repo mctlhq/portfolio
  --json createdAt` and falls back to `'2026-09-13T18:00:00Z'` if that is
  unavailable; no other timestamp is written by hand.
- The 1px `var(--surface-line)` border measures 1.14:1 (dark) and 1.48:1
  (light) against `var(--surface-card)` — below WCAG 1.4.11's 3:1 for a UI
  component boundary. It is the same border relationship the Q16 pill already
  shipped, the glyph/label itself carries the meaning at 7.45:1 / 10.42:1, and
  the issue explicitly forbids adding a second contrast pair here. Left as is
  and recorded.

## Appendix A — exact strings (copy is the contract)

New `src/i18n/ui.ts` keys, character for character:

- `themeSwitchToDark`: en `Switch to dark theme`, ru `Переключить на тёмную тему`
- `themeSwitchToLight`: en `Switch to light theme`, ru `Переключить на светлую тему`
- `langSwitchToEn`: en `Switch to English`, ru `Переключить на английский`
- `langSwitchToRu`: en `Switch to Russian`, ru `Переключить на русский`

Unchanged keys still rendered by the two components: `langEn` (`EN` / `EN`),
`langRu` (`RU` / `RU`), `langNoScript`, `themeNoScript`.

Removed keys: `langToggleLabel`, `themeToggleLabel`.

## Appendix B — journal entry copy (character for character)

`title.en`: `Q18: single icon-button toggles`

`title.ru`: `Q18: одиночные кнопки-иконки вместо сегментированных переключателей`

`seoTitle`: `Single icon-button language and theme toggles — Dmitrii Mashkov`

`decided.en`:

`The header's two auxiliary controls were the Q16 segmented pill: two adjacent buttons joined by a divider, EN|RU and Dark|Light, which on a phone read as a small control panel wedged into the navigation line. This cycle replaces each pill with a single 32x32px bordered button per CSS stance -- a moon glyph while the dark theme is active, a sun while light is active, the text EN while English is active and RU while Russian is active. The glyph and the label name the state that is active right now, confirmed with the site owner against an interactive preview; the accessible name says where a click leads. Nothing about behaviour changed: the buttons keep [data-set-lang] and [data-set-theme], Base.astro's delegated click listener and its CSP-pinned hash are untouched, Nav.astro still renders LangToggle before ThemeToggle, and both noscript paragraphs still render. Because the site renders every page once per stance and hides the inactive half with CSS, an accessible name cannot be a hardcoded aria-label string, so each button keeps the site's aria-labelledby pattern pointing at its own visually-hidden bilingual Lang span even though a single button is no longer a role="group" set. The .toggle-group rules are gone, replaced by .icon-toggle (32px box, --surface-line border, --mctl-radius-lg corners, --surface-card background, --surface-fg-muted glyph) and .lang-toggle for the two-letter label; the class deliberately declares no overflow, which would clip the global :focus-visible ring, and no per-class focus rule. scripts/check-contrast.mjs gained a surface-card entry in both theme maps and one surface-fg-muted-over-surface-card text pair, measuring 7.45:1 dark and 10.42:1 light. scripts/check-dist.mjs's approach-page SVG audit now skips aria-hidden="true" glyphs before demanding role="img" and a title/desc pair: that requirement belongs to the cycle diagram, not to a decorative icon inside an already-named button.`

`decided.ru`:

`Два вспомогательных контрола в шапке были сегментированной «пилюлей» из Q16: две соседние кнопки, разделённые линией, EN|RU и Dark|Light, — на телефоне это читалось как маленькая панель управления, втиснутая в строку навигации. Этот цикл заменяет каждую «пилюлю» одной кнопкой 32x32px с рамкой на каждое CSS-состояние: луна, пока активна тёмная тема, солнце, пока активна светлая, текст EN, пока активен английский, и RU, пока активен русский. Глиф и подпись называют состояние, активное прямо сейчас, — это подтверждено с владельцем сайта на интерактивном превью; доступное имя сообщает, куда ведёт клик. Поведение не изменилось: кнопки сохраняют [data-set-lang] и [data-set-theme], делегированный обработчик клика в Base.astro и его хеш в CSP не тронуты, Nav.astro по-прежнему рендерит LangToggle перед ThemeToggle, оба абзаца noscript остаются на месте. Поскольку сайт рендерит каждую страницу один раз на состояние и прячет неактивную половину через CSS, доступное имя не может быть жёстко заданной строкой aria-label, поэтому каждая кнопка сохраняет принятый на сайте приём aria-labelledby, указывающий на собственный visually-hidden двуязычный span с Lang, — даже если одиночная кнопка больше не является набором role="group". Правила .toggle-group удалены, их место заняли .icon-toggle (бокс 32px, рамка --surface-line, скругление --mctl-radius-lg, фон --surface-card, глиф цвета --surface-fg-muted) и .lang-toggle для двухбуквенной подписи; класс намеренно не объявляет overflow, который обрезал бы глобальное кольцо :focus-visible, и не получает собственного правила фокуса. В scripts/check-contrast.mjs добавлены запись surface-card в обе тематические карты и одна текстовая пара surface-fg-muted поверх surface-card: 7.45:1 в тёмной теме и 10.42:1 в светлой. Проверка SVG на странице approach в scripts/check-dist.mjs теперь пропускает глифы с aria-hidden="true", прежде чем требовать role="img" и пару title/desc: это требование относится к диаграмме цикла, а не к декоративной иконке внутри уже названной кнопки.`
