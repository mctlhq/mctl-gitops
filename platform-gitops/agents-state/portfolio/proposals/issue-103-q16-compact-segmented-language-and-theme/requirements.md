# Q16: compact segmented language and theme toggles on the navigation line

## Context

The site header currently spends a whole row on four chunky buttons. `Nav.astro`
renders `header.site-header > nav.site-nav + div.toggle-bar`, and because
`.site-header` is an ordinary block box, `.toggle-bar` falls onto a line of its
own below the navigation rule. Each of the four `.toggle-group button` elements
(`EN`, `RU`, `Dark`, `Light`) is a 44px-tall filled box with its own border and
its own `--surface-elevated` background. The first thing a visitor sees under
the page title is therefore a control panel rather than the site. These controls
are auxiliary: they belong on the navigation line, at its right edge, in a
weight that reads as a setting and not as a call to action.

This cycle is layout and style only. No new strings beyond one carried copy
correction, no new elements, no change to what the toggles do or how they are
announced. `.site-header` becomes the flex row and takes over the bottom rule
from `.site-nav`, so one line runs under the navigation *and* the toggles;
`.toggle-bar` is pushed to the right edge; the two buttons of each group join
into one bordered segmented control with a single internal divider. The target
size of the two auxiliary controls drops from 44px to 32px — still above the
24px floor `test/a11y.test.ts` enforces and above the WCAG 2.2 AA 2.5.8
minimum, below the 2.5.5 AAA 44px the site keeps everywhere else — and
`docs/accessibility-checklist.md`, which currently asserts 44px for
`.toggle-group button`, is corrected so it stays true.

Section E carries one unrelated item: the first `aboutParagraphs` entry still
opens with a count measured from an unnamed "now". The Q15 review raised it,
the issue and proposal were corrected mid-cycle, the finding was downgraded to
P3, and because the shepherd only forwards P1 and P2 the corrected sentence
never reached the code. Contract and code are out of step; this cycle closes
that.

## User stories

- AS a first-time visitor I WANT the header to be one line of navigation with
  the language and theme settings tucked at its right edge SO THAT the first
  thing I see below the page title is the site rather than a control panel.
- AS a keyboard user I WANT a focus outline on every segment, including the
  first and last of each group, that is not clipped on any side SO THAT I can
  always see where I am.
- AS a reader on a 320px phone I WANT the toggles to wrap to their own line and
  stay right-aligned SO THAT nothing overflows the column and the controls stay
  reachable.
- AS a reader using a pointer I WANT each control to read as one bordered box
  with a filled pressed segment SO THAT the current language and theme are
  obvious without reading the words twice.
- AS a maintainer I WANT `docs/accessibility-checklist.md` and
  `test/a11y.test.ts` to keep describing the stylesheet that actually ships SO
  THAT the checklist stays evidence rather than a claim.
- AS a reader of the home page I WANT the opening sentence of the "Who I am"
  section to name a year rather than a count measured from an unnamed "now" SO
  THAT the page does not silently go stale.

## Acceptance criteria (EARS)

Layout and style

- WHEN the site is rendered at a viewport of 768px or wider THE SYSTEM SHALL
  place the four toggle segments on the same line as the four navigation links,
  flush to the right edge of the `--content-max` column, with a single 1px rule
  running under the whole header row.
- WHILE the viewport is narrower than the width at which the header row fits on
  one line THE SYSTEM SHALL wrap `.toggle-bar` to a line of its own and keep it
  right-aligned, with nothing overflowing the column at 320px.
- THE SYSTEM SHALL declare a `.site-header` rule block, separate from and
  additional to the existing
  `.site-header, .site-footer, main { max-width: var(--content-max);
  margin-inline: auto; }` block which stays exactly as it is, containing
  character for character:

  ```css
  .site-header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--mctl-space-4);
    padding-block: var(--mctl-space-2);
    border-bottom: 1px solid var(--surface-line);
  }
  ```

- THE SYSTEM SHALL declare `.site-nav` character for character as:

  ```css
  .site-nav {
    display: flex;
    flex-wrap: wrap;
    gap: var(--mctl-space-4);
    padding-block: 0;
  }
  ```

- THE SYSTEM SHALL declare `.toggle-bar` character for character as:

  ```css
  .toggle-bar {
    display: flex;
    flex-wrap: wrap;
    gap: var(--mctl-space-4);
    padding-block: 0;
    margin-inline-start: auto;
    justify-content: flex-end;
  }
  ```

- IF any rule block's selector list contains the exact selector `.site-nav`
  THEN THE SYSTEM SHALL NOT declare `border-bottom` in that block — the rule
  moves to `.site-header`, it is not duplicated.

Segmented control

- THE SYSTEM SHALL declare the segmented control character for character as:

  ```css
  .toggle-group {
    display: inline-flex;
    gap: 0;
    border: 1px solid var(--surface-line);
    border-radius: var(--mctl-radius-md);
  }
  .toggle-group button {
    font: inherit;
    font-size: var(--mctl-typography-font-size-sm);
    line-height: 1;
    color: var(--surface-fg-muted);
    background: transparent;
    border: 0;
    border-radius: 0;
    padding-inline: var(--mctl-space-3);
    padding-block: 0;
    cursor: pointer;
  }
  .toggle-group button:first-child {
    border-start-start-radius: var(--mctl-radius-md);
    border-end-start-radius: var(--mctl-radius-md);
  }
  .toggle-group button:last-child {
    border-start-end-radius: var(--mctl-radius-md);
    border-end-end-radius: var(--mctl-radius-md);
  }
  .toggle-group button + button {
    border-inline-start: 1px solid var(--surface-line);
  }
  .toggle-group button[aria-pressed='true'] {
    background: var(--accent);
    color: var(--accent-fg);
  }
  ```

- WHILE either `data-theme` value is active THE SYSTEM SHALL render each control
  as one bordered box with a single internal divider, the pressed segment filled
  with `--accent` on `--accent-fg`, and the unpressed segment `--surface-fg-muted`
  on no fill.
- THE SYSTEM SHALL NOT declare `overflow` on `.toggle-group`. `overflow: hidden`
  is the obvious way to round the ends and is deliberately not used: it clips the
  `:focus-visible` outline of the first and last segment, which is exactly the
  indicator `docs/accessibility-checklist.md` claims the site has. The
  per-segment corner radii above achieve the same shape without clipping.
- WHEN a segment receives keyboard focus THE SYSTEM SHALL show the global
  `:focus-visible` outline unclipped on every side, including on the first and
  last segment of each group.
- THE SYSTEM SHALL introduce no new colour pair: `--surface-fg-muted` over
  `--surface-bg` and `--accent-fg` over `--accent` are already resolved by
  `scripts/check-contrast.mjs` in both themes and already above 4.5:1, so no new
  exemption and no threshold change is needed.

`<noscript>` paragraphs

- THE SYSTEM SHALL declare, character for character:

  ```css
  .toggle-bar noscript {
    flex-basis: 100%;
    text-align: end;
  }
  ```

Target size

- THE SYSTEM SHALL replace the current combined hit-area rule

  ```css
  .site-nav a,
  .toggle-group button,
  .site-footer a {
    display: inline-flex;
    align-items: center;
    min-block-size: 44px;
  }
  ```

  with the split pair, character for character:

  ```css
  .site-nav a,
  .site-footer a {
    display: inline-flex;
    align-items: center;
    min-block-size: 44px;
  }
  .toggle-group button {
    display: inline-flex;
    align-items: center;
    min-block-size: 32px;
  }
  ```

- THE SYSTEM SHALL resolve `.toggle-group button` to exactly one
  `min-block-size` declaration whose value is `32px`, and `.site-nav a` and
  `.site-footer a` to `44px`.
- THE SYSTEM SHALL leave `.cta`, `.block > summary`, `.skip-link:focus`,
  `.project-links a`, `.breadcrumb a`, `.journal-meta a`, `.table-scroll a` and
  `.contact-list a` unchanged. The 32px trade applies ONLY to the language and
  theme segments.
- THE SYSTEM SHALL replace the Evidence cell of the "Target size at least 24px"
  row in `docs/accessibility-checklist.md` with, character for character:

  > `src/styles/site.css` sets `min-block-size: 44px` — above the 24px CSS
  > Working Group "AA equivalent" floor named in the issue — on `.site-nav a`,
  > `.site-footer a`, `.cta` and `.block > summary`, and `min-block-size: 32px`
  > on `.toggle-group button`, the two auxiliary language and theme segments in
  > the header; both are above the 24px floor and both are asserted by
  > `test/a11y.test.ts`.

- THE SYSTEM SHALL NOT leave any claim of 44px for `.toggle-group button` in
  `docs/accessibility-checklist.md`.

Behaviour preserved

- WHILE JavaScript is enabled THE SYSTEM SHALL keep the language and theme
  toggles working exactly as they do today.
- WHILE JavaScript is disabled THE SYSTEM SHALL still render both halves of each
  control and both `<noscript><p>` sentences.
- THE SYSTEM SHALL keep `role="group"`, `aria-labelledby` and `aria-pressed`
  exactly as they are on both toggle components.
- THE SYSTEM SHALL NOT introduce any `animation` or `transition` property
  anywhere in `src/styles/site.css`.
- THE SYSTEM SHALL keep the existing `test/a11y.test.ts` assertions passing
  unchanged in behaviour: the 24px floor for every selector in its
  `TARGET_SELECTORS` list, the "no animation or transition anywhere" assertion,
  the `.toggle-bar` rule assertion (`display: flex`, `flex-wrap: wrap`,
  `gap: var(--mctl-space-4)`), and the `.site-nav a[aria-current]` colour plus
  text-decoration assertion.

Tests

- THE SYSTEM SHALL add assertions, in a new `test/header.test.ts` or in
  `test/a11y.test.ts`, that resolve a rule block and then assert on its
  declarations — never a bare `assert.match` against the whole stylesheet —
  covering:
  1. The `.site-header` rule block declares `display: flex`, `flex-wrap: wrap`,
     `justify-content: space-between` and a `border-bottom`.
  2. No rule block whose selector list includes `.site-nav` declares
     `border-bottom`.
  3. The `.toggle-bar` block declares `margin-inline-start: auto`, in addition
     to the three declarations the existing test already pins.
  4. The `.toggle-group` block declares a `border` and a `border-radius` and
     does NOT declare `overflow`.
  5. A rule block whose selector list includes `.toggle-group button + button`
     declares `border-inline-start`.
  6. `.toggle-group button` resolves to exactly one `min-block-size` and it is
     `32px`, while `.site-nav a` and `.site-footer a` resolve to `44px`, using
     the existing `minBlockSizeProblems` parser rather than a second one.
- IF a new test file is added THEN THE SYSTEM SHALL add it to the explicit
  `node --test` file list in the `test` script of `package.json`, because that
  script enumerates every test file by name and a file not named there never
  runs.
- WHEN `npm test`, `scripts/check-contrast.mjs`, `scripts/check-links.mjs`,
  `scripts/check-dist.mjs` and `scripts/check-headers.mjs` are run THE SYSTEM
  SHALL pass all of them.

Carried copy correction (section E)

- THE SYSTEM SHALL replace, in `src/i18n/ui.ts`, `aboutParagraphs`, first entry,
  the opening sentence only, leaving the rest of each paragraph character for
  character as it is today:
  - en — from `Nine years of production engineering.` to
    `Production engineering since 2017.`
  - ru — from `Девять лет продакшн-инженерии.` to
    `Продакшн-инженерия с 2017 года.`
- THE SYSTEM SHALL update every test that pins either full paragraph in the same
  commit. `test/ui.test.ts` pins both literals verbatim; `test/home.test.ts`
  derives its expectations from `ui` and needs no edit.

Journal

- THE SYSTEM SHALL add one journal entry for this cycle under
  `src/content/journal/`, per `AGENTS.md` and `docs/journal.md`, with
  `status: in_progress`, the issue URL, this proposal slug, the PR URL, a
  bilingual `decided` narrative and `issue_opened_at`; `merged_at`,
  `released_at`, `release` and `status: complete` are filled in later by
  `.github/workflows/journal-closure.yml`.

## Out of scope

- Any change to `src/components/Nav.astro`, `src/components/LangToggle.astro` or
  `src/components/ThemeToggle.astro` markup. The markup already is
  `header.site-header > nav.site-nav + div.toggle-bar`, with two `.toggle-group`
  divs per control (one per language / per theme, the other hidden by CSS), each
  holding exactly two `<button>` elements. If a markup change appears necessary,
  that is a finding to report, not a silent edit.
- Icons in place of the `Dark` / `Light` / `EN` / `RU` words. The labels stay
  words, in both languages, because the accessible name comes from the label.
- A sticky or fixed header.
- Any change to the footer, the hero, the stats or any page body.
- Any new colour token.
- Any change to `public/assets/mctl/*` (SHA-pinned).
- Any animation or transition.
- Any other Q15 review finding beyond the single sentence in section E.
- Any change to the inline `<head>` preference script or its CSP hash.

## Open questions

- The issue's "Files expected to change" list does not name a journal entry, but
  `AGENTS.md` requires one entry per DevLoop cycle and every prior cycle
  (`2026-09-13-q15-conversion-first-home.md`,
  `2026-09-13-q14-ten-projects-and-service-links.md`) has one. Proceeding with
  the entry: omitting it would be the larger deviation. The bilingual `decided`
  prose is not supplied by the issue; the implementer writes it describing this
  cycle, as every prior implementer did.
- Test 2 says "no rule block whose selector list includes `.site-nav`". Read as
  a substring it would also catch `.site-nav a`, `.site-nav a:hover` and
  `.site-nav a[aria-current]`, none of which declares `border-bottom` today
  either. Proceeding with the exact-token reading used by the repo's existing
  `selectors.includes(selector)` helper, which is both the narrower and the
  stricter-to-implement one, and noting that the substring reading also passes.
- The issue does not say where in `src/styles/site.css` the new `.site-header`
  block goes. Proceeding with: immediately before `.site-nav` in the
  `/* Navigation. */` section, which is after the `.site-header, .site-footer,
  main` layout block and well before the `@media print` block that sets
  `.site-header { display: none }`. Source order matters here — see design.md.
- The issue does not state a breakpoint for criterion 1's "768px and wider". The
  wrap is natural (`flex-wrap: wrap` with no media query); with
  `--content-max: 768px` and `--mctl-space-4` gaps, four nav links plus two
  32px-tall segmented controls fit on one line at 768px in both languages. No
  `@media` rule is added.
- Whether `padding-block: var(--mctl-space-2)` (8px) on `.site-header` leaves
  enough breathing room above the rule, given `.site-nav` and `.toggle-bar` both
  drop to `padding-block: 0`, is a visual judgement. The issue specifies the
  value explicitly, so it is used as given; a visual confirmation in a real
  browser is a reviewer step, not an acceptance criterion.
