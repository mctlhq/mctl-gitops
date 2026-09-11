# P4a: render the hero name in the reader's script

## Context

The home page (`src/pages/index.astro`) renders the hero as a hard-coded
`<h1 class="hero-name">Dmitrii Mashkov</h1>`. Every other user-facing string on
that page goes through the `Lang` component (`src/i18n/Lang.astro`) as an
`.l.en` / `.l.ru` pair sourced from the `ui` dictionary in `src/i18n/ui.ts`.
The name is the single exception. `AGENTS.md` (site constraints) now states
that the name is a translated string, not a proper noun exempt from
translation: English renders `Dmitrii Mashkov`, Russian renders
`Дмитрий Машков`. A Russian reader shown a transliteration of a Russian name
reads a page that was translated rather than written — on a site whose entire
argument is that it was written.

This is not a defect in PR #24 (issue #6, `src/content/journal/2026-09-11-home-page.md`).
That cycle implemented an approved proposal that required the unpaired string;
`AGENTS.md` was amended afterwards and the amendment does not reach backwards
onto an already-approved proposal. This proposal is the new contract.

The change also carries a typography consequence. `.hero-name` is currently set
in `var(--font-editorial)`, which
`public/assets/mctl/mctl.css` resolves to `'Instrument Serif', Georgia, serif`.
The vendored Instrument Serif faces
(`public/assets/fonts/instrument-serif-latin-400-normal.woff2` and its
latin-ext/italic siblings) declare only Latin and Latin-Extended
`unicode-range`s — the family ships no Cyrillic — so `Дмитрий Машков` would
fall through to `Georgia, serif`, a different family from the rest of the page.
Onest (`var(--font-display)` → `'Onest', system-ui, -apple-system, sans-serif`)
is vendored with Cyrillic and Cyrillic-Extended subsets at weights 300–700
(`public/assets/fonts/onest-cyrillic-700-normal.woff2` and siblings), so the
hero moves to Onest. The `<title>` element holds exactly one string and stays
Latin: a browser tab is a filing label, not prose.

## User stories

- AS a Russian-reading visitor I WANT the hero name rendered as
  `Дмитрий Машков` SO THAT the page reads as written in my language rather
  than machine-translated.
- AS an English-reading visitor I WANT the hero name rendered as
  `Dmitrii Mashkov` SO THAT nothing about the current behaviour regresses.
- AS a reader on either side of the toggle I WANT the hero set in a family
  that actually contains my script SO THAT the name does not drop onto a
  fallback face that matches nothing else on the page.
- AS a maintainer I WANT the suite to fail if the pair is ever collapsed back
  to one string SO THAT a later "simplification" cannot silently undo this
  cycle.

## Acceptance criteria (EARS)

- WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose
  `ui.heroName` as `{ en: 'Dmitrii Mashkov', ru: 'Дмитрий Машков' }`.
- WHEN `src/i18n/ui.ts` is loaded THE SYSTEM SHALL expose `ui.homeTitle`
  unchanged as `{ en: 'Dmitrii Mashkov', ru: 'Dmitrii Mashkov' }`.
- WHEN the home page is rendered THE SYSTEM SHALL emit the hero `<h1>` through
  the `Lang` component with `en={ui.heroName.en}` and `ru={ui.heroName.ru}`,
  and SHALL NOT contain the name as a literal string in the template of
  `src/pages/index.astro`.
- WHEN `npm run build` completes THE SYSTEM SHALL produce a `dist/index.html`
  in which `Dmitrii Mashkov` appears inside an element carrying
  `class="l en"` and `Дмитрий Машков` appears inside an element carrying
  `class="l ru"`, both inside the element carrying `class="hero-name"`.
- WHILE any page of `dist/` is inspected THE SYSTEM SHALL keep the number of
  `class="l en"` occurrences equal to the number of `class="l ru"`
  occurrences.
- WHEN the `.hero-name` rule in `src/styles/site.css` is resolved through the
  custom-property chain declared in `public/assets/mctl/mctl.css` THE SYSTEM
  SHALL yield a font stack whose first family is `Onest`.
- WHILE the `.hero-name` rule exists THE SYSTEM SHALL NOT reference
  `Instrument Serif`, nor `var(--font-editorial)` or any other custom property
  that resolves to it, in that rule.
- WHEN `dist/index.html` is inspected THE SYSTEM SHALL contain exactly
  `<title>Dmitrii Mashkov</title>`, with no Cyrillic character inside the
  `<title>` element, independent of the `data-lang` value the reader selects.
- IF `ui.heroName.en` and `ui.heroName.ru` are ever made equal THEN THE SYSTEM
  SHALL fail `npm test` with a message naming `heroName`.
- IF a file under `dist/` ends in `.js` THEN THE SYSTEM SHALL fail the image
  build via `scripts/check-dist.mjs`.
- WHEN `npm test` is run THE SYSTEM SHALL pass, and WHEN `npm run build` is
  run THE SYSTEM SHALL pass.

## Copy

| key | value |
|---|---|
| `heroName.en` | `Dmitrii Mashkov` |
| `heroName.ru` | `Дмитрий Машков` |
| `homeTitle.en` | `Dmitrii Mashkov` (unchanged) |
| `homeTitle.ru` | `Dmitrii Mashkov` (unchanged) |

No other string on the site changes. The `description` prop passed to
`Base.astro` from `src/pages/index.astro`, the `og:site_name` value in
`src/layouts/Base.astro`, the `workPageTitle` / `approachPageTitle` /
`colophonPageTitle` entries and the text inside `public/og.svg` all keep their
current Latin wording.

## Out of scope

- Any other string on the home page or anywhere else on the site.
- The `<title>` values of the other pages, `og:site_name`, the `meta`
  description, and the Latin name baked into `public/og.svg`.
- Finding new work for `Instrument Serif`. It remains referenced through
  `--font-editorial` by the vendored `public/assets/mctl/prose.css`, so it is
  not orphaned by this change; whether it deserves a new home on this page is
  a design question for a later cycle, and the answer to "our editorial font
  has no Cyrillic" is not "then write the name in the wrong script".
- Removing the Instrument Serif font files or their licence from
  `public/assets/fonts/`, and any change to `scripts/vendor-assets.mjs`.
- The calls to action still pointing at `/work/` and `/colophon/`, which land
  in issues #7 and #9.
- Any change to the vendored files under `public/assets/mctl/` — they are
  regenerated from upstream by `npm run vendor` and pinned by SHA-256.

## Open questions

- `.hero-name` declares no `font-weight`, so the hero inherits the user
  agent's bold default for `<h1>`. Instrument Serif ships weight 400 only, so
  today's hero is a synthesized bold; Onest ships a real 700 face, so the
  rendered weight will change even though no declaration does. This proposal
  resolves the ambiguity by declaring the weight explicitly as
  `var(--mctl-typography-font-weight-bold)` (700), matching the current
  intent of a bold hero with a face that actually has one. A lighter editorial
  setting (500/600) is a design call for a later cycle, not this one.
- The issue names `test/ui.test.ts` **or** `test/home.test.ts` for the new
  assertions. This proposal puts dictionary-level assertions in
  `test/ui.test.ts` and page/CSS-level assertions in `test/home.test.ts`,
  which matches how the two files are already split.
- Acceptance criteria stated against built output (`dist/index.html`) cannot
  run inside `npm test`: `prebuild` is `npm run vendor && npm test`, which
  executes before `astro build`. They are therefore enforced by
  `scripts/check-dist.mjs`, which the `Dockerfile` runs immediately after
  `npm run build` and which the `build` job of `.github/workflows/build.yml`
  exercises by building the image. This mirrors the existing arrangement for
  issues #6, #8, #9 and #10 and is treated as settled, not open.
