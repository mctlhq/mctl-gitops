# Tasks: issue-49-q5-navigation-state-disclosure-defaults

- [ ] 1. Add the three new bilingual strings to `src/i18n/ui.ts`:
  `skipToContent` (`Skip to content` / `Перейти к содержимому`),
  `breadcrumbLabel` (`Breadcrumb` / `Навигационная цепочка`),
  `ctasLabel` (`Page shortcuts` / `Быстрые ссылки`) — DoD: the three keys exist
  with exactly those values, `npm run check` passes, and `test/ui.test.ts`
  (every `ui` entry is a non-empty `{ en, ru }` pair) stays green.

- [ ] 2. Hoist `<main>` into `src/layouts/Base.astro` as
  `<main id="main" tabindex="-1"><slot /></main>`, and remove the `<main>`
  wrapper from all seven pages (`src/pages/index.astro`, `work.astro`,
  `approach.astro`, `404.astro`, `colophon/index.astro`,
  `colophon/journal/[...slug].astro`, `colophon/adr/[...slug].astro`), keeping
  their children — DoD: `npm run build` succeeds and
  `node scripts/check-dist.mjs` still reports exactly one `<main>` per page;
  `test/approach.test.ts`'s "no `tabindex` in approach.astro" assertion passes
  unchanged.

- [ ] 3. (depends on 1, 2) Add the skip link as the first child of `<body>` in
  `src/layouts/Base.astro`: `<a class="skip-link" href="#main"><Lang
  en={ui.skipToContent.en} ru={ui.skipToContent.ru} /></a>`, before `<Nav />`
  — DoD: every built page's first `<a` or `<button` inside `<body>` is the skip
  link, and its href is `#main`.

- [ ] 4. (depends on 3) Style `.skip-link` in `src/styles/site.css`: clipped out
  of layout when unfocused, and on `:focus` visible with `display: inline-flex;
  align-items: center; min-block-size: 44px`, `background:
  var(--surface-elevated)`, `color: var(--surface-fg)`, `border: 1px solid
  var(--surface-line)`, `border-radius: var(--mctl-radius-md)` — DoD: no
  `animation` or `transition` property is introduced anywhere in the file
  (`test/a11y.test.ts` asserts this), and the colour pair is one
  `scripts/check-contrast.mjs` already covers (`surface-fg` over
  `surface-elevated`).

- [ ] 5. Wrap `<LangToggle />` and `<ThemeToggle />` in
  `<div class="toggle-bar">` in `src/components/Nav.astro`, and add
  `.toggle-bar { display: flex; flex-wrap: wrap; gap: var(--mctl-space-4);
  padding-block: var(--mctl-space-4); }` plus
  `.toggle-bar noscript { flex-basis: 100%; }` to `src/styles/site.css` —
  DoD: the two groups are separated by a declared gap, not by a whitespace text
  node; `.toggle-group`'s own `inline-flex` and `--mctl-space-2` gap are
  unchanged.

- [ ] 6. Add `aria-current` to `src/components/Nav.astro`, derived from
  `Astro.url.pathname` at build time: normalise to a trailing slash, emit
  `'page'` on an exact match, `'true'` when the path starts with a nav item's
  href and that href is not `/`, and `undefined` otherwise. Keep the four
  anchors as literal elements with their literal `href="/…/"` strings — DoD:
  `/`, `/work/`, `/approach/`, `/colophon/` each emit exactly one
  `aria-current="page"`; `/colophon/journal/<id>/` and `/colophon/adr/<id>/`
  emit exactly one `aria-current="true"` on the Colophon link; `/404.html`
  emits none; `test/approach.test.ts`'s `href="/approach/"` assertion on
  `Nav.astro` still passes.

- [ ] 7. (depends on 6) Add
  `.site-nav a[aria-current] { color: var(--accent); text-decoration:
  underline; text-underline-offset: 0.25em; text-decoration-thickness: 2px; }`
  to `src/styles/site.css` — DoD: the rule matches on attribute presence (both
  `page` and `true`), carries a colour and an underline, and introduces no
  colour token outside those `scripts/check-contrast.mjs` already resolves.

- [ ] 8. (depends on 1) Add `src/components/Breadcrumb.astro`: a
  `<nav class="breadcrumb" aria-labelledby="breadcrumb-label">` holding a
  `.visually-hidden` span with the `breadcrumbLabel` pair and an `<ol>` of
  `Home` (link to `/`), `Colophon` (link to `/colophon/`) and a non-link
  `<span aria-current="page">` carrying the `currentEn` / `currentRu` props —
  DoD: the component renders four `<Lang>` pairs, so `class="l en"` and
  `class="l ru"` counts stay equal.

- [ ] 9. (depends on 8) Render `<Breadcrumb>` above the `<h1>` on
  `src/pages/colophon/journal/[...slug].astro` (passing `entry.data.title.en` /
  `.ru`) and `src/pages/colophon/adr/[...slug].astro` (passing
  `ADR-${padAdrId(entry.data.id)}` for both languages) — DoD: every journal and
  ADR page shows the breadcrumb as the first element inside `<main>`.

- [ ] 10. (depends on 8) Style the breadcrumb in `src/styles/site.css`:
  `.breadcrumb ol { display: flex; flex-wrap: wrap; gap: var(--mctl-space-2);
  list-style: none; margin: 0 0 var(--mctl-space-3); padding: 0; font-size:
  var(--mctl-typography-font-size-sm); }` and
  `.breadcrumb li + li::before { content: '/'; margin-inline-end:
  var(--mctl-space-2); color: var(--surface-fg-muted); }` — DoD: separators come
  from CSS only, so no screen reader announces them; no `animation` or
  `transition` is introduced.

- [ ] 11. Add `role="group"` to both `.toggle-group` divs in
  `src/components/LangToggle.astro` and both in
  `src/components/ThemeToggle.astro`, replace the slash-joined `groupLabel`
  `aria-label` with `aria-labelledby="lang-toggle-label"` /
  `aria-labelledby="theme-toggle-label"`, and add one
  `<span id="…" class="visually-hidden"><Lang en={…} ru={…} /></span>` per
  component bound to `ui.langToggleLabel` / `ui.themeToggleLabel` — DoD: no
  `groupLabel` const remains, no `aria-label` in either file, and each group's
  name resolves through a single `<Lang>` pair.

- [ ] 12. (depends on 1) Replace the slash-joined `navLabel` `aria-label` on
  `<nav class="site-nav">` in `src/components/Nav.astro` with
  `aria-labelledby="nav-label"` plus a `.visually-hidden` span bound to
  `ui.navLabel`, and do the same for the `.ctas` `<nav>` in
  `src/pages/index.astro` with `aria-labelledby="ctas-label"` bound to the new
  `ui.ctasLabel` — DoD: no `${…en} / ${…ru}` template literal remains in
  `src/components/`, `src/layouts/` or `src/pages/index.astro`; the
  `.table-scroll` label in `src/pages/colophon/index.astro` is left untouched
  (out of scope).

- [ ] 13. Add a boolean `heading?: boolean` prop (default `false`) to
  `src/components/Details.astro` that wraps the summary text in
  `<h2 class="block-title">`, leaving the optional `.visually-hidden` suffix
  span outside the heading — DoD: `heading` is a boolean, never a numeric
  level; with `heading` unset the rendered markup is byte-identical to today.

- [ ] 14. (depends on 13) Pass the bare `heading` flag to all three `<Details>`
  on `src/pages/index.astro`, pass `open` to the `Contact` block only, and pass
  `open` to the `Gates` block only on `src/pages/approach.astro` — DoD:
  `dist/index.html` has exactly one `<details open>` (Contact) and three
  `<summary><h2` openings; `dist/approach/index.html` has exactly one
  `<details open>` (Gates) and no `<summary><h2`; `src/pages/work.astro` is not
  touched; the "no digit in the template" tests in `test/home.test.ts` and
  `test/approach.test.ts` still pass.

- [ ] 15. (depends on 13) Add
  `.block > summary h2 { display: inline; font: inherit; margin: 0; }` to
  `src/styles/site.css` — DoD: the native `display: list-item` marker on
  `.block > summary` and the existing summary line appearance are unchanged.

- [ ] 16. Correct the stale comment in `scripts/check-links.mjs` (around line
  72) that states no `href="#..."` exists on the site — DoD: the comment names
  the skip link as the one bare fragment href and the classification behaviour
  is unchanged.

- [ ] 17. (depends on 2-15) Re-walk the WCAG 2.2 AA checklist in
  `docs/accessibility-checklist.md`: rewrite the "Heading hierarchy" row for
  the three new home-page `<h2>` titles, and add rows for "Bypass blocks (skip
  link)", "Current page indication" and "Group naming in the active language",
  each citing the file or script that backs it; append a short "Re-walk log"
  line recording that the checklist was re-walked for this issue and what
  changed — DoD: every row is `pass` or `reviewer step`, no row is `fail`, and
  every `pass` cites a committed file, a build script or a test.

## Tests

- [ ] T1. Extend `test/a11y.test.ts`: assert the `.toggle-bar` rule declares
  `display: flex`, `flex-wrap: wrap` and `gap: var(--mctl-space-4)`; assert a
  rule whose selector list includes `.site-nav a[aria-current]` declares both a
  `color` and a `text-decoration`; add `.skip-link:focus` to
  `TARGET_SELECTORS`; keep the existing "no animation or transition" assertion
  green.

- [ ] T2. Add `test/nav.test.ts` over the sources of `Nav.astro`,
  `LangToggle.astro`, `ThemeToggle.astro`, `Base.astro`, `Breadcrumb.astro` and
  `src/pages/index.astro`: `Nav.astro` reads `Astro.url.pathname` and emits
  `aria-current`; the four literal `href="/…/"` anchors survive; both toggles
  carry `role="group"` on every `.toggle-group` and an `aria-labelledby`
  instead of an `aria-label`; both `<nav>` landmarks use `aria-labelledby`; and
  none of those files contains a `${…\.en} / ${…\.ru}` template literal.

- [ ] T3. Extend `test/home.test.ts`: exactly three `<Details` tags on
  `index.astro`, every one carrying `heading`, exactly one carrying `open`, and
  that one bound to `ui.detailsContactSummary`. Extend
  `test/approach.test.ts`: exactly three `<Details` tags, exactly one carrying
  `open`, bound to `ui.detailsGatesSummary`, and none carrying `heading`.

- [ ] T4. Extend `scripts/check-dist.mjs` with `checkNavigationState(html,
  rel)` run over every built HTML file: `<main id="main" tabindex="-1">`
  present; a `href="#main"` anchor occurring before the first `<nav`; exactly
  one `aria-current` inside the `.site-nav` block on the four main pages and
  the journal/ADR pages and zero on `404.html`; and no `aria-label` value
  containing both a Latin and a Cyrillic letter, with a single named exemption
  for the `.table-scroll` region on `dist/colophon/index.html` (Colophon tables
  are out of scope this cycle).

- [ ] T5. Extend `scripts/check-dist.mjs`'s `checkHomePage()` and
  `checkApproachPage()`: exactly one `<details open>` on each of
  `dist/index.html` and `dist/approach/index.html`, exactly three
  `<summary><h2` openings on `dist/index.html`, and zero on
  `dist/approach/index.html` and `dist/work/index.html`.

- [ ] T6. Full gate: `npm test` and `npm run build` both exit zero, followed by
  `node scripts/check-dist.mjs` exiting zero — which also re-proves
  `class="l en"` equals `class="l ru"` on every changed page, no `.js` under
  `dist/`, `dist/index.html` under the 40960-byte cap, and no new `<style>`
  element or `style="…"` attribute.

- [ ] T7. Reviewer steps (named as such, never acceptance criteria, per
  `AGENTS.md`): at 360px in a real browser with the toggles operable, confirm
  `RU` and `Тёмная` are visibly separate and the header wraps without overflow
  in both languages and both themes; confirm the skip link appears on first
  Tab and lands focus in the content; confirm the current-page underline and
  colour read clearly in both themes.

## Rollback

The change is presentation-only: static markup and CSS, no data, no schema, no
persisted state, no new runtime dependency and no change to the inline head
script or its CSP hash. Rollback is therefore a plain revert.

1. Revert the merge commit on `main` (`git revert -m 1 <merge-sha>`) through a
   normal pull request; release-please cuts the next patch tag.
2. If the regression is already live and cannot wait for a release, roll the
   deployed image back to the previous tag with
   `mctl_rollback_service(team_name="labs", component_name="portfolio",
   target_tag="<previous>")` — read the current tag from
   `mctl_get_service_config` first. No gitops values are edited by hand and no
   DNS or domain change is involved.
3. Partial rollback is safe and cheap if only one of the four parts misbehaves:
   the disclosure defaults are two props (task 14), the current-page marking is
   one frontmatter helper plus one CSS rule (tasks 6-7), and the toggle spacing
   is one wrapper plus one CSS rule (task 5). Reverting task 2 (the `<main>`
   hoist) requires reverting task 3 with it, since the skip link's target lives
   there.
4. `public/styles/site.css` is gitignored and regenerated by `prebuild`, so no
   stale vendored copy survives a revert.
