# Q5: navigation state, disclosure defaults and accessibility affordances

## Context

The portfolio site renders four main pages (`/`, `/work/`, `/approach/`,
`/colophon/`) plus one page per public journal entry and ADR, from a single
layout (`src/layouts/Base.astro`) and a single header component
(`src/components/Nav.astro`). Four defects in that shell make the site harder
to use than it looks. The two toggle groups (`src/components/LangToggle.astro`,
`src/components/ThemeToggle.astro`) are adjacent `inline-flex` elements with no
spacing of their own, so in Russian the active `RU` and `Тёмная` buttons sit
flush and read as one wide button with two labels. No nav item marks the
current page, and journal and ADR pages are not in the menu at all, so a reader
who arrives from a search result has no positional cue. On `/` all three
`<Details>` blocks and on `/approach/` all three are collapsed, so
`/approach/` reads as a heading, a paragraph and a diagram. Finally several
accessibility affordances are missing or inert: `.toggle-group` is a bare
`<div>` carrying an `aria-label` (not announced on a generic element), the
`aria-label` strings are bilingual and get read out in full in both languages,
there is no skip link past the header's eight focusable controls, and the home
page section titles are `<summary>` text with no heading so heading navigation
finds only the `h1`.

This matters because the site's stated purpose is to be a verifiable artifact
of the DevLoop (`AGENTS.md`, ADR-0001). A site that fails its own accessibility
checklist, hides its most-sought content behind a click and reads two languages
at once to a screen reader undercuts the claim. All four defects are in the
shared shell, so one cycle fixes them for every page at once. Note that the
language and theme toggles only became operable when the CSP hash quoting
landed; every change here must be confirmed in a browser with the toggles
actually working, which is a reviewer step, not an acceptance criterion.

## User stories

- AS a Russian-reading visitor on a 360px phone I WANT the language and theme
  toggles to be visibly separate controls SO THAT I do not read `RU Тёмная` as
  one button with two labels.
- AS a returning visitor I WANT the navigation to show which page I am on SO
  THAT I can orient myself without re-reading the page content.
- AS a reader arriving on a journal entry or an ADR from a search result I WANT
  a breadcrumb and a marked nav section SO THAT I know where in the site I
  landed and how to get back up.
- AS a first-time visitor I WANT the most-sought block on each page to be open
  already SO THAT `/` shows me how to make contact and `/approach/` explains the
  diagram without a click.
- AS a screen reader user I WANT each toggle group to have a name, in one
  language, and a skip link past the header SO THAT I am not read a
  slash-joined bilingual string and do not tab through eight controls before
  the content.
- AS a screen reader user navigating by heading I WANT the home page section
  titles in the heading outline SO THAT the page has more structure than a
  single `h1`.

## Copy (the contract)

Three new bilingual strings are added to `src/i18n/ui.ts`. The issue supplies no
copy for them, so this proposal fixes it here, character for character. Every
other string this change renders already exists in `src/i18n/ui.ts`
(`navLabel`, `navHome`, `navWork`, `navApproach`, `navColophon`,
`langToggleLabel`, `themeToggleLabel`) and is reused unchanged.

| Key | en | ru |
| --- | --- | --- |
| `skipToContent` | `Skip to content` | `Перейти к содержимому` |
| `breadcrumbLabel` | `Breadcrumb` | `Навигационная цепочка` |
| `ctasLabel` | `Page shortcuts` | `Быстрые ссылки` |

The breadcrumb's first two entries reuse `ui.navHome` (`Home` / `Главная`) and
`ui.navColophon` (`Colophon` / `Колофон`). The breadcrumb's last entry is the
journal entry's own `title.en` / `title.ru` from its frontmatter, or, on an ADR
page, the zero-padded identifier `ADR-NNNN` in both languages (an identifier,
untranslated, per `AGENTS.md`).

## Acceptance criteria (EARS)

### Toggle group spacing

- WHEN the header renders THE SYSTEM SHALL wrap `<LangToggle />` and
  `<ThemeToggle />` in a single container element in `src/components/Nav.astro`
  that carries the class `toggle-bar`.
- WHILE `src/styles/site.css` is the stylesheet of record THE SYSTEM SHALL
  declare a `.toggle-bar` rule containing `display: flex`, `flex-wrap: wrap`
  and `gap: var(--mctl-space-4)`, so that the distance between the two groups
  does not depend on a whitespace text node in the markup.
- WHILE a `<noscript>` paragraph from either toggle is a child of `.toggle-bar`
  THE SYSTEM SHALL give it its own line rather than letting it sit beside the
  toggles (a `flex-basis: 100%` rule or equivalent).

### Current page marking

- WHEN `src/components/Nav.astro` renders THE SYSTEM SHALL derive the current
  path from `Astro.url.pathname` at build time, with no client-side script.
- WHEN the rendered path equals a nav item's `href` THE SYSTEM SHALL emit
  `aria-current="page"` on that item's `<a>` and on no other nav item.
- IF the rendered path is under `/colophon/` but is not `/colophon/` itself
  (that is, a `/colophon/journal/<id>/` or `/colophon/adr/<id>/` page) THEN THE
  SYSTEM SHALL emit `aria-current="true"` on the `Colophon` nav item and on no
  other nav item.
- IF the rendered path matches no nav item and is not under `/colophon/`
  (the 404 page) THEN THE SYSTEM SHALL emit no `aria-current` attribute in the
  site navigation.
- WHILE `src/styles/site.css` is the stylesheet of record THE SYSTEM SHALL
  style `.site-nav a[aria-current]` — matching on attribute presence, so both
  `page` and `true` are covered — with both a distinct colour and an underline,
  so colour is never the sole indicator.
- WHEN a journal or ADR page renders THE SYSTEM SHALL place a breadcrumb
  navigation above the page's `<h1>`, listing `Home`, `Colophon` and the
  current entry, where the first two are links to `/` and `/colophon/` and the
  last is not a link and carries `aria-current="page"`.

### Disclosure defaults

- WHEN `/` renders THE SYSTEM SHALL emit exactly one `<details>` element with
  the `open` attribute, and that element SHALL be the `Contact` /
  `Контакты` block.
- WHEN `/approach/` renders THE SYSTEM SHALL emit exactly one `<details>`
  element with the `open` attribute, and that element SHALL be the `Gates` /
  `Контрольные точки` block.
- WHILE this change is in effect THE SYSTEM SHALL leave every other
  `<details>` block on the site — `What I run`, `How I work` on `/`, `Numbers`
  and `Proven open source` on `/approach/`, and all fourteen on `/work/` —
  closed on first load.

### Accessibility affordances

- WHEN either toggle group renders THE SYSTEM SHALL emit `role="group"` on the
  `.toggle-group` element.
- WHEN either toggle group renders THE SYSTEM SHALL give it an accessible name
  in the active language only, never a slash-joined bilingual string.
- WHEN the site navigation renders THE SYSTEM SHALL give the `<nav>` landmark
  an accessible name in the active language only.
- WHEN the home page's call-to-action `<nav>` renders THE SYSTEM SHALL give it
  an accessible name in the active language only, using the `ctasLabel` copy
  above.
- WHEN any page renders THE SYSTEM SHALL emit a skip link as the first
  focusable element inside `<body>`, before the header, whose `href` is
  `#main` and whose text is the `skipToContent` copy above.
- WHILE the skip link is unfocused THE SYSTEM SHALL keep it out of the visual
  layout; WHEN it receives focus THE SYSTEM SHALL render it visibly, with no
  `animation` or `transition` property anywhere in `src/styles/site.css`.
- WHEN any page renders THE SYSTEM SHALL emit exactly one `<main>` element
  carrying `id="main"` and `tabindex="-1"`, so that activating the skip link
  moves focus into the content region.
- WHEN a home-page disclosure block renders THE SYSTEM SHALL wrap its summary
  text in an `<h2>` inside the `<summary>`, so all three appear in the heading
  outline below the single `h1`.
- WHILE the `<h2>` sits inside a `<summary>` THE SYSTEM SHALL keep the native
  disclosure marker and the existing visual appearance of the summary line
  (an `.block > summary h2 { display: inline; font: inherit; margin: 0 }` rule
  or equivalent).

### Evidence and invariants

- WHEN `npm test` runs THE SYSTEM SHALL assert, from source, the
  `.toggle-bar` rule's three declarations, the `.site-nav a[aria-current]`
  colour-plus-underline rule, the `role="group"` plus single-language name on
  both toggles, the `open` prop on exactly the two named blocks, and the
  continued absence of any `animation` or `transition` in
  `src/styles/site.css`.
- WHEN `node scripts/check-dist.mjs` runs against a built `dist/` THE SYSTEM
  SHALL fail if any built page lacks `<main id="main" tabindex="-1">`, lacks a
  `#main` skip link before its first `<nav>`, carries a number of
  `aria-current` attributes in `.site-nav` other than exactly one on the four
  main pages and the journal/ADR pages and exactly zero on `/404.html`, or
  carries an `aria-label` containing both a Latin and a Cyrillic letter
  (excepting the `.table-scroll` region on `/colophon/`, which this cycle does
  not touch).
- WHEN `node scripts/check-dist.mjs` runs THE SYSTEM SHALL fail if
  `dist/index.html` or `dist/approach/index.html` contains a number of
  `<details open>` elements other than exactly one, or if `dist/index.html`
  contains a number of `<summary><h2` openings other than exactly three.
- WHILE this change is in effect THE SYSTEM SHALL keep the count of
  `class="l en"` equal to the count of `class="l ru"` in every built HTML file,
  as `scripts/check-dist.mjs` already asserts.
- WHILE this change is in effect THE SYSTEM SHALL emit no `.js` file under
  `dist/`, add no `<style>` element or `style="…"` attribute, and leave the
  inline `<head>` script in `src/layouts/Base.astro` and its CSP hash in
  `security-headers.conf` byte-for-byte unchanged.
- WHEN the WCAG 2.2 AA checklist in `docs/accessibility-checklist.md` is
  re-walked THE SYSTEM SHALL record the result in that file, updating the
  heading-hierarchy row for the new `<h2>` titles and adding rows for bypass
  blocks (the skip link), current-page indication, and group naming in the
  active language.
- WHEN `npm test` and `npm run build` run THE SYSTEM SHALL exit zero for both.

## Out of scope

- The CSP hash quoting and the header guards in `security-headers.conf` and
  `nginx.conf`.
- Content link colour, the Colophon tables (including the bilingual
  `aria-label` on the `.table-scroll` region in
  `src/pages/colophon/index.astro`), timestamps and lead time.
- The `/work/` page, including its fourteen disclosure names; no `<details>`
  there is opened and no `<h2>` is added to its summaries.
- `og:image`, font preload, `Cache-Control`, the DevLoop diagram
  (`src/components/CycleDiagram.astro`) and the hero name wrap.
- Adding `<h2>` to the `/approach/` disclosure summaries (see Open questions).
- Any change to `src/data/metrics.json`, the journal, the ADRs or the release
  machinery.

## Open questions

- The issue's "Files expected to change" list omits five files this change must
  also touch: `src/pages/work.astro`, `src/pages/colophon/index.astro`,
  `src/pages/404.astro`, `src/pages/colophon/journal/[...slug].astro` and
  `src/pages/colophon/adr/[...slug].astro`. All seven pages author their own
  `<main>` today; the skip link must land on `<main id="main">` on every page,
  so `<main>` is hoisted into `src/layouts/Base.astro` and removed from each
  page. Proceeding on that reading: the list is "expected", not exhaustive, and
  a skip link that works on two pages out of seven would not satisfy AC 5.
- The issue gives no ARIA token for "mark `Colophon` as the current section" on
  journal and ADR pages. `aria-current="page"` would be false there (it is not
  that page), so this proposal uses `aria-current="true"`. The issue's own
  styling selector, `nav a[aria-current]`, matches on attribute presence, which
  is consistent with two different values.
- Acceptance criterion 6 names only the home page for `<h2>` inside
  `<summary>`. `/approach/` has the identical defect, but it is not named and
  `/work/` is explicitly out of scope, so `/approach/` is left alone. Raise a
  follow-up issue if the reviewer wants it included.
- The home page's `.ctas` `<nav>` carries a bilingual `aria-label`
  (`See the work / Смотреть работы`) — the same defect as the two toggle
  groups, on a file that is in scope. It is fixed here with the `ctasLabel`
  copy above. The equivalent label on `/colophon/`'s `.table-scroll` region is
  left alone because Colophon tables are explicitly out of scope.
- "The skip link moves focus to `<main>`" is implemented with `tabindex="-1"`
  on `<main>`; browsers differ on whether a fragment target that is not
  otherwise focusable receives focus or only a sequential-focus starting point.
  Confirming the focus actually lands, in a browser, is a reviewer step, not an
  acceptance criterion (`AGENTS.md`, "Issue contract").
- Acceptance criterion 1 ("at 360px in Russian the buttons are visibly
  separate; the header wraps without overflow") cannot be proven without a
  browser. The mechanical criterion is the `.toggle-bar` rule above; the visual
  confirmation at 360px in both languages is a reviewer step.
