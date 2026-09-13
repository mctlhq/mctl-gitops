# Tasks: issue-103-q16-compact-segmented-language-and-theme

All CSS below is inlined verbatim in `requirements.md`. Copy it from there
character for character; do not paraphrase a declaration.

- [ ] 1. In `src/styles/site.css`, in the `/* Navigation. */` section,
  immediately **before** the `.site-nav` rule (currently line 99), add the new
  `.site-header` block: `display: flex; flex-wrap: wrap; align-items: center;
  justify-content: space-between; gap: var(--mctl-space-4);
  padding-block: var(--mctl-space-2);
  border-bottom: 1px solid var(--surface-line);`. Leave the existing
  `.site-header, .site-footer, main { max-width: var(--content-max);
  margin-inline: auto; }` block (line 81) exactly as it is.
  — DoD: the file contains two non-print rule blocks naming `.site-header`; the
  new one is at a lower line number than the `@media print` block that sets
  `.site-header { display: none }`, so print still hides the header.

- [ ] 2. (depends on 1) Rewrite the `.site-nav` block to exactly
  `display: flex; flex-wrap: wrap; gap: var(--mctl-space-4);
  padding-block: 0;`. The `border-bottom` is **deleted**, not copied — it now
  lives on `.site-header`. `.site-nav a`, `.site-nav a:hover` and
  `.site-nav a[aria-current]` are untouched.
  — DoD: no rule block in `src/styles/site.css` whose selector list contains
  `.site-nav` (or any `.site-nav …` descendant selector) declares
  `border-bottom`.

- [ ] 3. (depends on 1) Replace the whole `/* Toggle groups. */` region
  (currently lines 176-202) with the five blocks from `requirements.md`:
  `.toggle-group` (border, `border-radius`, `gap: 0`, `display: inline-flex`),
  `.toggle-bar` (the three pinned declarations plus `padding-block: 0`,
  `margin-inline-start: auto`, `justify-content: flex-end`),
  `.toggle-bar noscript` (`flex-basis: 100%`, `text-align: end`),
  `.toggle-group button`, `.toggle-group button:first-child`,
  `.toggle-group button:last-child`, `.toggle-group button + button` and
  `.toggle-group button[aria-pressed='true']`. Replace, do not append: the old
  `padding:` shorthand, `background: var(--surface-elevated)`, per-button
  `border`/`border-radius` and the `border-color: var(--accent)` on the pressed
  state all go away. Add a short comment above `.toggle-group` recording that
  `overflow: hidden` is deliberately not used because it would clip the
  `outline-offset` focus ring of the first and last segment.
  — DoD: `.toggle-group` declares a `border` and a `border-radius` and no
  `overflow`; `.toggle-group button` declares `border: 0` and
  `background: transparent`; `.toggle-group button + button` declares
  `border-inline-start`; no `animation` or `transition` anywhere in the file.

- [ ] 4. (depends on 1) Split the tap-target rule at line 577. `.site-nav a,
  .site-footer a` keeps `display: inline-flex; align-items: center;
  min-block-size: 44px;`. Add a sibling `.toggle-group button { display:
  inline-flex; align-items: center; min-block-size: 32px; }` immediately after
  it, with a comment naming the trade: 32px is above the 24px floor
  `test/a11y.test.ts` enforces and above the WCAG 2.2 AA 2.5.8 minimum, below
  the 2.5.5 AAA 44px the site keeps on every navigation link, footer link, CTA,
  disclosure summary and standalone link.
  — DoD: `.toggle-group button` resolves to exactly one `min-block-size` in the
  whole file and it is `32px`; `.site-nav a` and `.site-footer a` resolve to
  `44px`; `.cta`, `.block > summary`, `.skip-link:focus`, `.project-links a`,
  `.breadcrumb a`, `.journal-meta a`, `.table-scroll a` and `.contact-list a`
  are byte-identical to `main`.

- [ ] 5. (depends on 4) In `docs/accessibility-checklist.md`, replace the
  Evidence cell of the "Target size at least 24px" row with the replacement text
  quoted in `requirements.md`, character for character. A markdown table cell
  cannot contain newlines, so it goes in as one line — the wrapping in the
  quote is presentational. Add a "Re-walk log" bullet for issue #103 (Q16)
  recording that the language and theme segments moved onto the navigation line
  and dropped from 44px to 32px, and that `overflow: hidden` was deliberately
  not used on `.toggle-group` so the focus ring on the first and last segment
  stays unclipped.
  — DoD: `grep -n "44px" docs/accessibility-checklist.md` shows no occurrence
  paired with `.toggle-group button`; the row still reads `pass`; the new 32px
  claim matches what task 4 actually shipped.

- [ ] 6. Create `test/support/css-rules.ts` exporting
  `ruleBlockBodies(css, selector): string[]` — every rule block body whose
  comma-split, whitespace-normalised selector list contains the exact
  `selector`, in source order — and `minBlockSizes(css, selector): number[]`,
  built on it. Move the parsing logic out of `test/a11y.test.ts`'s
  `minBlockSizeProblems` and rewrite that function as a thin wrapper over
  `minBlockSizes` so its return values, its two synthetic self-tests and all
  eleven `TARGET_SELECTORS` assertions behave identically. Do not write a second
  parser anywhere.
  — DoD: `test/a11y.test.ts` contains no regex literal for rule-block splitting
  in `minBlockSizeProblems`; every existing `test/a11y.test.ts` test still
  passes with no change to its assertions.

- [ ] 7. (depends on 6) Create `test/header.test.ts` with assertions 1-6 from
  section D (see `## Tests` below). **Do not** use the "last block wins" loop
  shape from the existing `.toggle-bar` test for `.site-header` or
  `.toggle-group`: the flat rule regex also matches the `@media print` block
  `.site-header, .toggle-group, .ctas { display: none; }`, so last-wins resolves
  both selectors to `display: none;`. Use `ruleBlockBodies(...).some(...)` for
  "a block declares X" and `.every(...)` for "no block declares X". Never a bare
  `assert.match` against the whole stylesheet.
  — DoD: each of T1-T6 below fails when its corresponding declaration is removed
  from `src/styles/site.css` (spot-check at least T2 and T4 by temporary local
  edit, then revert).

- [ ] 8. (depends on 7) Add `test/header.test.ts` to the explicit `node --test`
  file list in the `test` script of `package.json`, after `test/a11y.test.ts`.
  — DoD: `npm test` output names `test/header.test.ts` among the executed files.

- [ ] 9. In `src/i18n/ui.ts`, `aboutParagraphs`, first entry of each language,
  replace the opening sentence only. EN: `Nine years of production engineering.`
  becomes `Production engineering since 2017.` — the literal is double-quoted
  because it contains `team's`; keep it double-quoted. RU:
  `Девять лет продакшн-инженерии.` becomes `Продакшн-инженерия с 2017 года.`
  Everything after the opening sentence, in both languages, stays character for
  character as it is today. The second and third paragraphs are untouched.
  — DoD: the two paragraphs differ from `main` only in their first sentence.

- [ ] 10. (depends on 9) Update `test/ui.test.ts` — the `aboutParagraphs` test
  at line 189 pins both full arrays as verbatim literals (EN at line 191, RU at
  line 196). Apply the identical sentence replacement there. `test/home.test.ts`
  derives its expectations from `ui` and needs no edit.
  — DoD: `npm test` passes; no other test file mentions `Nine years` or
  `Девять лет`.

- [ ] 11. (depends on 1-10) Add the cycle's journal entry at
  `src/content/journal/2026-09-13-q16-compact-segmented-language-and-theme.md`
  (use the actual date), following `docs/journal.md` and the shape of
  `src/content/journal/2026-09-13-q15-conversion-first-home.md`:
  `service: portfolio`, `issue: https://github.com/mctlhq/portfolio/issues/103`,
  `proposal_slug: issue-103-q16-compact-segmented-language-and-theme`, the PR
  URL, `status: in_progress`, `visibility: public`, a bilingual `title`, a
  `seoTitle`, a bilingual `decided` narrative describing this cycle,
  `interventions: []` and `issue_opened_at`. Leave `release`, `merged_at` and
  `released_at` out — `.github/workflows/journal-closure.yml` fills them in and
  flips `status` to `complete` after the release.
  — DoD: `npm test` passes (the journal content-collection schema validates the
  entry); at most one entry in `src/content/journal/` is `in_progress`.

- [ ] 12. (depends on 1-11) Run the full gate: `npm test`,
  `node scripts/check-contrast.mjs`, `node scripts/check-links.mjs`,
  `node scripts/check-dist.mjs` and `node scripts/check-headers.mjs` (the latter
  three after `npm run build`). If the implementer concludes a markup change to
  `Nav.astro`, `LangToggle.astro` or `ThemeToggle.astro` is needed, it does
  **not** make it — that is a finding to record, in a committed file, not a
  silent edit.
  — DoD: all five pass. `git diff --stat` touches only `src/styles/site.css`,
  `src/i18n/ui.ts`, `docs/accessibility-checklist.md`, `test/a11y.test.ts`,
  `test/support/css-rules.ts`, `test/header.test.ts`, `test/ui.test.ts`,
  `package.json` and the new journal entry.

## Tests

- [ ] T1. `test/header.test.ts`: some `.site-header` rule block body declares
  all four of `display: flex`, `flex-wrap: wrap`,
  `justify-content: space-between` and `border-bottom`. Resolve with
  `ruleBlockBodies`, then assert on a single body — not one body per
  declaration, and not the last body, which is the `@media print`
  `display: none;` one.
- [ ] T2. `test/header.test.ts`: **no** rule block body whose selector list
  contains `.site-nav` declares `border-bottom`. The rule moved to
  `.site-header`; it was not duplicated.
- [ ] T3. `test/header.test.ts`: the `.toggle-bar` block body declares
  `margin-inline-start: auto`. The existing `test/a11y.test.ts` assertion on
  `display: flex`, `flex-wrap: wrap` and `gap: var(--mctl-space-4)` stays where
  it is and keeps passing.
- [ ] T4. `test/header.test.ts`: some `.toggle-group` body declares both a
  `border` and a `border-radius`, and **every** `.toggle-group` body declares no
  `overflow`. The `some` is what steps past the print block; the `every` is what
  pins the deliberate absence of `overflow: hidden`.
- [ ] T5. `test/header.test.ts`: `ruleBlockBodies(css, '.toggle-group button +
  button')` is non-empty and some body declares `border-inline-start`.
- [ ] T6. `test/header.test.ts`: `minBlockSizes(css, '.toggle-group button')`
  deep-equals `[32]` — exactly one declaration, value 32 —
  `minBlockSizes(css, '.site-nav a')` contains `44`, and
  `minBlockSizes(css, '.site-footer a')` contains `44`. Uses the extracted
  helper from task 6; no second parser.
- [ ] T7. Regression, no new code: the eleven `TARGET_SELECTORS` 24px-floor
  assertions, the "no animation or transition anywhere" assertion, the
  `.toggle-bar` assertion and the `.site-nav a[aria-current]` colour plus
  text-decoration assertion in `test/a11y.test.ts` all still pass, with their
  assertion text unchanged.
- [ ] T8. Regression, no new code: `test/nav.test.ts` (two `.toggle-group` divs
  per component, `role="group"`, `aria-labelledby`, the four literal nav
  anchors) and `scripts/check-dist.mjs`'s `checkNavigationState()` still pass —
  proof that the markup did not change.
- [ ] T9. Regression, no new code: `scripts/check-contrast.mjs` still reports
  every pair at or above its minimum, with no pair added and no threshold
  changed. `--surface-fg-muted`/`--surface-bg` and `--accent-fg`/`--accent` are
  already in its `PAIRS` array.
- [ ] T10. `test/ui.test.ts`: `aboutParagraphs.en[0]` begins
  `Production engineering since 2017.` and `aboutParagraphs.ru[0]` begins
  `Продакшн-инженерия с 2017 года.`, with the remainder of each paragraph
  unchanged.

Reviewer steps (per `AGENTS.md`, never acceptance criteria): confirm in a real
browser at 1440px, 768px and 320px that the header is one line with the toggles
flush right and a single rule underneath, that the toggles wrap right-aligned
below 768px with no horizontal overflow at 320px, that tabbing through all four
segments shows an unclipped focus ring on the first and last segment of each
group in both `data-theme` values, and that print output still omits the header.

## Rollback

The change is one commit against one branch, CSS plus docs plus tests plus two
strings, with no data, no schema, no dependency and no deployment coupling.

1. Before merge: close the PR. Nothing shipped.
2. After merge, before release: `git revert <merge-sha>` on a branch, PR, merge.
   `src/styles/site.css`, `src/i18n/ui.ts`,
   `docs/accessibility-checklist.md`, `test/a11y.test.ts`, `test/ui.test.ts`,
   `package.json` and the journal entry return to their previous contents;
   `test/support/css-rules.ts` and `test/header.test.ts` disappear, and because
   task 8's `package.json` entry is reverted in the same commit, `npm test`
   does not then fail on a missing file. Verify `npm test` passes on the revert
   branch before merging it.
3. After release and deploy: `mctl_rollback_service team_name=<team>
   component_name=portfolio target_tag=<previous tag>` restores the previously
   released image immediately, then revert as in step 2 so the next release does
   not reintroduce the change.

Partial rollback is possible and cheap if only one half is at fault: section E
(tasks 9-10) touches only `src/i18n/ui.ts` and `test/ui.test.ts`; the header
work (tasks 1-8) touches neither. Reverting either half alone leaves the suite
green.
