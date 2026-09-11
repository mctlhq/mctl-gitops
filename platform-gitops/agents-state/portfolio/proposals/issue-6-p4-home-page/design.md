# Design: issue-6-p4-home-page

## Current state

**The page.** `src/pages/index.astro` is 18 lines of placeholder from P2: it
wraps `src/layouts/Base.astro`, prints `ui.homeTitle` in an `<h1>` and
`ui.homeLede` in a `<p>`, then emits two empty sections:

```astro
<section id="work"><h2><Lang en={ui.navWork.en} ru={ui.navWork.ru} /></h2></section>
<section id="approach"><h2><Lang en={ui.navApproach.en} ru={ui.navApproach.ru} /></h2></section>
```

`src/components/Nav.astro` links to `/#work` and `/#approach`, which is the
only thing that references those ids.

**The layout.** `src/layouts/Base.astro` takes a single `title: string` prop,
hardcodes `<html lang="en" data-lang="en" data-theme="dark">`, and links five
stylesheets in this order: `/assets/mctl/mctl.css`, `/assets/mctl/global.css`,
`/assets/mctl/prose.css`, `/assets/fonts/fonts.css`, `/styles/site.css`. It
carries the one inline preference script (a 391-byte one-liner) that sets
`data-lang` / `data-theme` from `localStorage` and registers a click listener
for `[data-set-lang]` / `[data-set-theme]`, with the `localStorage` read and
write each guarded separately, as `AGENTS.md` requires after the #16 failure.

**Bilingual mechanism.** `src/i18n/Lang.astro` is three lines and emits
`<span class="l en">{en}</span><span class="l ru" lang="ru">{ru}</span>`.
`src/styles/site.css` hides one half with
`:root[data-lang='en'] .l.ru { display: none }` and its mirror. Nothing is
language-aware at build time: both languages are always in the document. Every
string lives in `src/i18n/ui.ts`, a flat `as const` object of `{ en, ru }`
pairs with `export type UiKey = keyof typeof ui`. The file imports nothing.

**Design tokens.** `public/assets/mctl/mctl.css` is `@mctlhq/css` 0.5.0,
vendored and SHA-256-pinned by `scripts/vendor-assets.mjs`. It defines
`--font-display` (Onest), `--font-mono` (JetBrains Mono) and `--font-editorial`
(Instrument Serif), the `--mctl-space-1..10` scale (4 px → 132 px), a type
scale including `--mctl-typography-font-size-stat: clamp(40px, 4vw, 56px)` and
`--mctl-typography-font-size-hero: clamp(48px, 8.4vw, 132px)`, and the
`--surface-*` / `--accent*` / `--focus-ring*` families for both themes.
`public/assets/mctl/global.css` sets only `box-sizing` and `<body>`; it is not
a reset, so element defaults such as the `<details>` disclosure marker survive.
Neither vendored file styles `details` or `summary` — grep finds no match.

**Fonts.** `public/assets/fonts/fonts.css` is generated. `Onest` and
`JetBrains Mono` each ship `latin`, `latin-ext`, `cyrillic` and `cyrillic-ext`
faces; `Instrument Serif` ships only `latin` and `latin-ext`, and
`scripts/vendor-assets.mjs` records this deliberately as
`hasCyrillic: false`. This is the machine-readable form of the typography
constraint carried from #4.

**Styling convention.** `src/styles/site.css` is the source of truth and is
copied to `public/styles/site.css` by `scripts/vendor-assets.mjs` on
`prebuild`; the copy is gitignored. `astro.config.mjs` sets
`inlineStylesheets: 'never'` with a comment explaining that the
`style-src 'self'` CSP header carries no `'unsafe-inline'`, so any Astro-owned
stylesheet has to become an `_astro/*.css` link. Serving site CSS from
`public/` sidesteps that entirely.

**Build and gates.** `package.json`: `prebuild` = `npm run vendor && npm test`;
`test` = `node --test test/journal.test.ts test/adr.test.ts` — an explicit file
list, so a new test file is invisible until it is added there. `Dockerfile`
runs `npm run build && node scripts/csp-hash.mjs > /app/csp-script-src.txt` in
the builder stage and substitutes the hash into `nginx.conf`'s
`__SCRIPT_SRC_HASHES__`, failing if the placeholder survives.
`scripts/csp-hash.mjs` walks `dist/**/*.html`, requires exactly one distinct
inline script body, and caps it at 400 bytes — precedent for enforcing a
budget against `dist/` rather than against source. `.github/workflows/build.yml`
runs `npm test` and then a no-push Docker build on every pull request, so
anything the Dockerfile enforces gates the PR. `.github/workflows/claude-review.yml`
passes conventions that explicitly tell the reviewer to flag "any number typed
into templates or content instead of read from `src/data/metrics.json`".

**Testable-logic convention.** `src/lib/journal.ts` opens with a comment: "Zero-import
helper module: no `astro:content`, no `astro/loaders`, no `zod`. This keeps the
module importable by plain `node --test`, with no build step." `src/lib/adr.ts`
follows it. Both are exercised by `test/*.test.ts` written in TypeScript and
run under Node's native type stripping.

**What does not exist.** There is no `src/data/` directory. `metrics.json` is
referenced only in `AGENTS.md` and in the review conventions. There is no
`Stat`, no `Details` component, and no ADR that this issue revises.

## Proposed solution

Six source changes, one data file, one build-time check script, and three test
files. Nothing in the reserved human-only set of `AGENTS.md` is touched.

### 1. `src/data/metrics.json` — the placeholder snapshot

```json
{
  "generated_at": null,
  "sources": {
    "github": {
      "collected_at": null,
      "method": "placeholder",
      "repos": null,
      "commits": null,
      "releases": null
    },
    "mctl": {
      "collected_at": null,
      "method": "placeholder",
      "services": null,
      "devloop_proposals": null
    }
  }
}
```

Every leaf that will ever hold a fact is `null`, including the timestamps.
`devloop_proposals` is in the schema and in the file even though no tile uses
it, because P8b generates the whole object and the schema should not change
then. A JSON module import is already precedent in this repo —
`src/components/Footer.astro` does `import pkg from '../../package.json'` — so
`resolveJsonModule` is on via `astro/tsconfigs/strict` and no loader is needed.

### 2. `src/lib/metrics.ts` — zero-import, node-testable

Follows the `src/lib/journal.ts` convention exactly: no `astro:*` import, no
`zod`, so `node --test` can exercise it without a build step.

```ts
export const EM_DASH = '—';

export interface MetricSourceGithub {
  collected_at: string | null;
  method: string;
  repos: number | null;
  commits: number | null;
  releases: number | null;
}
export interface MetricSourceMctl {
  collected_at: string | null;
  method: string;
  services: number | null;
  devloop_proposals: number | null;
}
export interface Metrics {
  generated_at: string | null;
  sources: { github: MetricSourceGithub; mctl: MetricSourceMctl };
}

export function formatStat(value: number | null): string;   // null -> EM_DASH
export function snapshotDate(generatedAt: string | null): string;  // null -> EM_DASH, else YYYY-MM-DD
export function metricProblems(raw: unknown): string[];     // [] when the file is well formed
```

`formatStat` returns the em dash for `null` and `String(value)` otherwise — no
`Intl.NumberFormat`, because a single value element is shared by both
languages and EN/RU group digits differently (see Open questions).
`snapshotDate` slices the first ten characters after validating against
`ISO_WITH_OFFSET`-shaped input; an ISO date is language-neutral, which is why
the caption needs no per-language date formatting. `metricProblems` is the
validator the test drives: it checks the key set, that each metric is `null` or
a non-negative integer, that `method` is a non-empty string, and that a
non-null timestamp parses.

Declaring `Metrics` here and casting the JSON import at the use site keeps the
component signatures stable across P8b: today TypeScript infers `null` for
every value in the literal, and without the cast, `Stat`'s `value` prop would
narrow to `null` and then widen to `number` when P8b writes digits, changing
type-check results in a cycle that touches no `.ts` file.

### 3. `src/components/Stat.astro`

```astro
---
import Lang from '../i18n/Lang.astro';
import { formatStat } from '../lib/metrics';
interface Props { value: number | null; labelEn: string; labelRu: string }
const { value, labelEn, labelRu } = Astro.props;
---
<div class="stat">
  <span class="stat-value" data-stat>{formatStat(value)}</span>
  <span class="stat-label"><Lang en={labelEn} ru={labelRu} /></span>
</div>
```

The value is one element shared by both languages — a number is a number in
both — so it carries no `.l` class and cannot disturb the parity count. The
label is a `Lang` pair, which contributes exactly one `class="l en"` and one
`class="l ru"`. `data-stat` is the hook the `dist` checker uses to prove that
every rendered value traces back to the JSON.

### 4. `src/components/Details.astro`

```astro
---
import Lang from '../i18n/Lang.astro';
interface Props { summaryEn: string; summaryRu: string; open?: boolean }
const { summaryEn, summaryRu, open = false } = Astro.props;
---
<details class="block" open={open}>
  <summary><Lang en={summaryEn} ru={summaryRu} /></summary>
  <slot />
</details>
```

Native `<details>`, no script — the disclosure behaviour is the user agent's,
which is the only way to have a collapsible block under ADR-0002. Body markup
arrives through the default slot so the page keeps ownership of the three very
different bodies (a list, a list, two links).

### 5. `src/i18n/ui.ts` — copy, including the two lists

All copy from the issue is added here, so `src/pages/index.astro` holds
structure and zero literals. New string pairs: `heroThesis`, `heroSubline`,
`statRepositories`, `statCommits`, `statReleases`, `statServices`,
`statCaptionPrefix`, `ctaWork`, `ctaColophon`, `detailsRunSummary`,
`detailsWorkSummary`, `detailsContactSummary`. `homeTitle` becomes
`{ en: 'Dmitrii Mashkov', ru: 'Dmitrii Mashkov' }` (a `<title>` holds one
string, and the name is identical in both languages); `homeLede` is removed,
superseded by `heroThesis` and `heroSubline`.

Two entries are array-valued rather than string-valued:

```ts
detailsRunItems: { en: ['k3s on Hetzner, provisioned with OpenTofu', ...], ru: [...] },
detailsWorkItems: { en: [...five bullets...], ru: [...five bullets...] },
```

This is the first array in `ui.ts`; `UiKey = keyof typeof ui` is unaffected.
A new `test/ui.test.ts` walks the whole object and asserts that every entry has
a non-empty `en` and `ru` of the same kind, and that array entries have equal
lengths — the mechanical form of `AGENTS.md`'s "every user-facing string exists
in both languages", which until now has been checked only by eye.

### 6. `src/pages/index.astro` — structure only

```astro
---
import Base from '../layouts/Base.astro';
import Lang from '../i18n/Lang.astro';
import Stat from '../components/Stat.astro';
import Details from '../components/Details.astro';
import { ui } from '../i18n/ui';
import { snapshotDate, type Metrics } from '../lib/metrics';
import raw from '../data/metrics.json';
const metrics = raw as Metrics;
const date = snapshotDate(metrics.generated_at);
---
```

The `<main>` carries, in order:

- `<h1 class="hero-name">Dmitrii Mashkov</h1>` — one text node, unpaired. It is
  the only element on the page allowed `var(--font-editorial)`: Instrument
  Serif has no Cyrillic subset, and this string is Latin-only and identical in
  both languages, which is exactly the exemption the issue's typography
  constraint grants.
- `<p class="thesis"><Lang en={ui.heroThesis.en} ru={ui.heroThesis.ru} /></p>`
  and the same shape for `heroSubline` — both in `var(--font-display)`.
- `<section class="stats">` with four `<Stat>` whose `value` props are
  `{metrics.sources.github.repos}`, `.commits`, `.releases` and
  `{metrics.sources.mctl.services}`, followed by
  `<p class="stat-caption"><Lang en={`${ui.statCaptionPrefix.en} ${date}`} ru={`${ui.statCaptionPrefix.ru} ${date}`} /></p>`.
  With the placeholder that prints `Snapshot —` / `Снимок —`.
- `<nav class="ctas">` (or a plain `<p>`) with the two anchors to `/work/` and
  `/colophon/`, each wrapping a `Lang` pair. Trailing slashes are mandatory —
  `astro.config.mjs` sets `trailingSlash: 'always'`.
- Three `<Details>`. Block 1 and block 2 take **one `<ul>` per language**
  rather than a `Lang` pair per item:

  ```astro
  <ul class="l en">{ui.detailsRunItems.en.map((t) => <li>{t}</li>)}</ul>
  <ul class="l ru" lang="ru">{ui.detailsRunItems.ru.map((t) => <li>{t}</li>)}</ul>
  ```

  One `class="l en"` and one `class="l ru"` per list, so parity holds, each
  list reads as a single-language list, and the four items that are identical
  in both languages (`CloudNativePG`, `Temporal`, `Backstage`, `Cloudflare`)
  simply repeat, which is what a translated list does. Block 3 holds the two
  links, whose visible text (`github.com/mctlhq`,
  `hello@dmitriimashkov.com`) is identical in both languages and therefore
  unpaired.

The placeholder `<section id="work">` and `<section id="approach">` disappear.
`src/components/Nav.astro` is deliberately not touched: `/#work` then resolves
to the home page with no matching fragment, which every browser treats as "top
of document" — a soft degradation, unlike re-pointing the links at `/work/`
and `/approach/`, which would hard-404 until P5 and P6 land.

### 7. `src/styles/site.css` — all new rules, no component `<style>`

Appended sections, using only `@mctlhq/css` tokens:

- **Hero**: `.hero-name { font-family: var(--font-editorial); font-size: var(--mctl-typography-font-size-hero); line-height: var(--mctl-typography-line-height-hero); letter-spacing: var(--mctl-typography-letter-spacing-hero) }`.
  `.thesis` uses `--mctl-typography-font-size-lede`; `.subline` uses body size
  and `--surface-fg-muted`.
- **Stats**: `.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: var(--mctl-space-5) }`.
  At 360 px the body's `padding-inline: var(--mctl-space-4)` leaves 328 px, so
  `auto-fit` settles on two columns (2 × 140 + 24 = 304) and four tiles become
  a 2 × 2 block with no overflow. `.stat-value { font-size: clamp(28px, 8vw, 40px); font-variant-numeric: tabular-nums; }`
  — deliberately smaller than `--mctl-typography-font-size-stat`
  (`clamp(40px, 4vw, 56px)`), which at 360 px would put a future five-digit
  commit count at 40 px into a 156 px tile and blow the "no horizontal scroll"
  criterion the moment P8b lands.
- **Tap targets**: `min-block-size: 44px` plus vertical padding on
  `.cta`, `.block > summary`, `.site-nav a`, `.toggle-group button` and
  `.site-footer a`, with `display: inline-flex; align-items: center` on the
  anchors and buttons only. `<summary>` keeps its default display: setting
  `display: flex` on a `<summary>` removes the disclosure marker in Chromium,
  so it gets `padding-block: var(--mctl-space-3)` and `min-block-size` instead.
  Touching the nav and toggle rules is unavoidable — the acceptance criterion
  says *every* tap target on the page at 360 px, and those controls are on the
  page — and it is a pure addition to rules that already exist in this file.
- **Details**: `.block { border-top: 1px solid var(--surface-line) }`,
  `.block > summary { cursor: pointer }`, list spacing. Nothing overrides
  `list-style` on `summary`.
- **Print**:

  ```css
  @media print {
    :root { --surface-bg: #fff; --surface-fg: #111; --surface-fg-muted: #444; --surface-line: #bbb; }
    .site-header, .toggle-group, .ctas { display: none; }
    .block > *:not(summary) { display: block !important; content-visibility: visible !important; }
    a[href^='http']::after { content: ' (' attr(href) ')'; font-size: var(--mctl-typography-font-size-xs); }
  }
  ```

  The colour override matters because `src/layouts/Base.astro` hardcodes
  `data-theme="dark"`; without it a printed page is near-white text on a ground
  browsers do not print. The `content-visibility` line is belt-and-braces: the
  HTML rendering spec has moved the closed-`<details>` rule from `display: none`
  to `content-visibility: hidden`, and different browser versions are on
  different sides of that change.

### 8. `scripts/check-dist.mjs` — the mechanical gate

Modelled directly on `scripts/csp-hash.mjs`: walk `dist/`, exit non-zero with a
named reason. Three assertions, each mapping to an acceptance criterion:

1. no file under `dist/` ends in `.js`;
2. for every `dist/**/*.html`, the count of `class="l en"` equals the count of
   `class="l ru"`, reported per file;
3. `dist/index.html` is under 40 960 bytes.

Wired into the `Dockerfile` builder stage as
`RUN npm run build && node scripts/check-dist.mjs && node scripts/csp-hash.mjs > /app/csp-script-src.txt`.
That is the same place the inline-script budget is already enforced, and
`.github/workflows/build.yml`'s `build` job builds the image on every pull
request, so all three criteria gate the PR without touching the workflow file.
`npm test` cannot host these checks: `prebuild` runs `npm test` *before*
`astro build`, so `dist/` does not exist yet at that point.

### 9. Tests

- `test/metrics.test.ts` — drives `metricProblems` over the real
  `src/data/metrics.json` (read with `node:fs`, so it fails the moment the file
  drifts from the schema) and over hand-built bad objects: a missing key, a
  negative value, a float, a string where a number belongs, an unparseable
  `generated_at`. Plus `formatStat(null) === '—'`, `formatStat(0) === '0'`
  (the guard must test `null`, not falsiness — a real zero is a fact),
  `snapshotDate(null) === '—'`,
  `snapshotDate('2026-09-11T01:42:36Z') === '2026-09-11'`.
- `test/home.test.ts` — reads `src/pages/index.astro` as text and asserts it
  imports `../data/metrics.json`, that every `value=` prop on a `<Stat` tag is
  an expression rooted at `metrics.sources.`, and that stripping heading tag
  names (`/<\/?h[1-6]\b/g`) leaves a source with no digit at all. The last
  assertion is the executable form of "no digit that represents a metric
  appears in `index.astro`", and it has a useful side effect: `k3s` carries a
  digit, so inlining the `What I run` list into the page instead of putting it
  in `ui.ts` fails the test.
- `test/ui.test.ts` — EN/RU parity over the whole `ui` object, including equal
  array lengths.
- All three are appended to the `test` script in `package.json`, which lists
  test files explicitly.

### Why the acceptance criteria come out satisfied

| Criterion | Mechanism |
| --- | --- |
| 1 `l en` count = `l ru` count | `Lang` pairs and paired `<ul>`s only; `scripts/check-dist.mjs` check 2 |
| 2 no metric digit in `index.astro` | all copy in `ui.ts`, values from JSON; `test/home.test.ts` |
| 3 LCP is text | page carries no image, no `background-image`, no video; fonts already `font-display: swap` |
| 4 `index.html` < 40 KB | `scripts/check-dist.mjs` check 3 |
| 5 360 px: no h-scroll, 44 px targets | `auto-fit` 2-column grid, tile-local font clamp, `min-block-size: 44px` |
| 6 no `.js`, same-origin only | ADR-0002 holds; `scripts/check-dist.mjs` check 1; no new external URL |

## Alternatives

**Per-item `Lang` pairs inside the two lists, instead of one `<ul>` per
language.** It keeps parity automatically and needs no array entries in
`ui.ts`. Dropped: nine list items become nine span pairs, the four items that
are identical in both languages are emitted twice for nothing, and a
screen reader walking the EN list still traverses nine hidden RU spans
interleaved with the visible text. The per-language `<ul>` emits the same two
`.l` classes as a single `Lang` pair, so parity is just as mechanical, and
each list is a clean single-language list.

**Build-time language variants — `/` and `/ru/` as two rendered pages.** Half
the document weight, correct `lang` on `<html>`, and no `.l` machinery. Dropped
because it contradicts the site's already-shipped architecture: ADR-0002 fixed
the bilingual switch as CSS-driven, `src/i18n/Lang.astro`, `src/styles/site.css`
and the 400-byte preference script all implement it, and acceptance criterion 1
literally counts `.l en` / `.l ru` pairs in the built page. Revisiting that
belongs in an ADR of its own, not in the cycle that writes the landing page.

**A `metrics` content collection under `src/content/`, validated by Zod in
`src/content.config.ts`.** It would reuse the validation machinery the ADR and
journal collections already use. Dropped: content collections are for many
files of the same shape, this is one singleton JSON; `AGENTS.md` names the path
`src/data/metrics.json` explicitly; and the collection API is async and
Astro-only, so P8b's generator and `node --test` could not both read it without
a build. A zero-import `src/lib/metrics.ts` plus a plain JSON import gives the
same validation strength with `test/metrics.test.ts` as the enforcer.

**Scoped `<style>` blocks in `Stat.astro` and `Details.astro`.** The idiomatic
Astro answer and it keeps each component self-contained. Dropped: with
`inlineStylesheets: 'never'` (set because the CSP has no `'unsafe-inline'`),
every scoped block becomes another render-blocking `_astro/*.css` request, and
Astro's scoping hashes add a `data-astro-cid-*` attribute to every element,
which is page weight against a 40 KB budget. `src/styles/site.css` is already
declared the source of truth in its own header comment.

**Enforcing the 40 KB / no-`.js` / parity checks in `npm test` rather than in
the Dockerfile.** Simpler to run locally. Dropped because `prebuild` is
`npm run vendor && npm test`, which runs *before* `astro build` — at that
moment `dist/` is either absent or stale, so the test would validate the
previous build. `scripts/csp-hash.mjs` already establishes post-build checking
in the image build as this repo's pattern for exactly this reason.

## Platform impact

**Migrations.** None. No database, no schema, no persisted state. The one new
data file is a static asset compiled into the image.

**Backward compatibility.**

- `ui.homeLede` is removed and `ui.homeTitle.ru` changes from
  `Дмитрий Машков` to `Dmitrii Mashkov`. `homeLede` has exactly one consumer,
  `src/pages/index.astro`, which this proposal rewrites; `astro check` catches
  any straggler through `UiKey`.
- `src/pages/index.astro` loses `#work` and `#approach`. `src/components/Nav.astro`
  keeps linking to them; a fragment with no target scrolls to the top of the
  document, which is a graceful degradation until P5 and P6. Deliberately not
  fixed here — see Out of scope.
- The two CTAs point at `/work/` and `/colophon/`, which do not exist. nginx
  serves `/404.html` (`error_page 404 /404.html` in `nginx.conf`), and
  `src/pages/404.astro` is bilingual and already shipped, so a reader who
  clicks early gets a proper page rather than an nginx default. **This is the
  most visible risk of merging P4 before P5/P7** and the reviewer should decide
  consciously whether that is acceptable or whether the CTAs should be held
  back. Mitigation if it is not: render the two CTAs as disabled text until the
  target pages exist — but that contradicts the issue's copy, so this proposal
  ships the links as specified.
- `src/styles/site.css` gains `min-block-size` on `.site-nav a`,
  `.toggle-group button` and `.site-footer a`. These are global, so `/404.html`
  gets taller nav and toggle controls too. That is an improvement, not a
  regression, and `404.astro` has no tap-target criterion of its own.

**Resource impact.** Page weight grows from roughly 4 KB to an estimated
12-16 KB of HTML for `index.html` — both languages of a thesis, a sub-line,
four tiles, two CTAs and fourteen list items — against the 40 KB ceiling,
which `scripts/check-dist.mjs` turns into a build failure rather than a
review note. No new font file, no new stylesheet request, no new script byte:
the document still links the same five stylesheets and carries the same single
inline script. nginx already gzips `text/css` but note `gzip_types` does not
list `text/html`, because nginx always compresses `text/html` when `gzip on`
— so the HTML is compressed on the wire regardless. No change to CPU, memory
or replica count; the container is nginx serving static files.

**Risks and mitigations.**

- *A number gets typed into the page anyway.* Three independent nets:
  `test/home.test.ts` fails the build on any digit outside a heading tag name;
  `scripts/check-dist.mjs` can be extended to diff rendered `[data-stat]` text
  against the JSON; and `claude-review.yml` already instructs the reviewer to
  flag exactly this.
- *Bilingual parity silently drifts.* `scripts/check-dist.mjs` check 2 fails
  the image build, and `test/ui.test.ts` fails earlier, at `npm test`.
- *The `<summary>` disclosure marker disappears.* Caused by `display: flex` on
  `<summary>`; the design uses `min-block-size` and `padding-block` instead,
  and T5 checks the marker is present at 360 px.
- *Printed page comes out blank or unreadable.* Two causes, both addressed in
  the `@media print` block: the hardcoded dark theme, and closed `<details>`.
  The `content-visibility` override is unverifiable without a real browser, so
  T6 is a manual print-preview check the implementer must actually run.
- *A future five-digit commit count overflows a 360 px tile.* The tile-local
  `clamp(28px, 8vw, 40px)` and `overflow-wrap` are chosen now so that P8b is a
  data-only change.
- *`npm test` silently skips the new tests.* `package.json`'s `test` script
  lists files explicitly; forgetting to add one is a silent no-op, not an
  error. T7 asserts the run reports all five files.
- *Lockfile damage.* This proposal adds no dependency, so `package-lock.json`
  must not change at all. If it does, the implementer ran a bare
  `npm install` — `AGENTS.md` requires `npm install --package-lock-only`, and
  the #16 cycle lost an hour to exactly this.
