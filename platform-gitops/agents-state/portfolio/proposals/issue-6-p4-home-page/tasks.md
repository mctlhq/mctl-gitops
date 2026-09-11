# Tasks: issue-6-p4-home-page

- [ ] 1. Add `src/data/metrics.json` with the placeholder snapshot: `generated_at`
      null, `sources.github` = `{collected_at: null, method: "placeholder", repos: null, commits: null, releases: null}`,
      `sources.mctl` = `{collected_at: null, method: "placeholder", services: null, devloop_proposals: null}`.
      — DoD: the file exists, is valid JSON, contains no digit anywhere, and
      `node -e "JSON.parse(require('fs').readFileSync('src/data/metrics.json'))"` exits 0.

- [ ] 2. Add `src/lib/metrics.ts` (depends on 1): zero-import module in the style
      of `src/lib/journal.ts` — no `astro:*`, no `zod` — exporting `EM_DASH`,
      the `Metrics` / `MetricSourceGithub` / `MetricSourceMctl` interfaces,
      `formatStat(value: number | null): string`, `snapshotDate(generatedAt: string | null): string`
      and `metricProblems(raw: unknown): string[]`. `formatStat` must branch on
      `value === null`, never on falsiness, so a real `0` renders as `0`.
      — DoD: the file's import list is empty; `node --test` can import it
      directly; `formatStat(0)` returns `'0'` and `formatStat(null)` returns
      the em dash U+2014.

- [ ] 3. Add `src/components/Stat.astro` (depends on 2): props
      `{ value: number | null; labelEn: string; labelRu: string }`, rendering
      `<div class="stat">` with `<span class="stat-value" data-stat>{formatStat(value)}</span>`
      and `<span class="stat-label"><Lang en={labelEn} ru={labelRu} /></span>`.
      The value element carries no `.l` class.
      — DoD: `npm run check` passes; the component emits exactly one
      `class="l en"` and one `class="l ru"` per instance.

- [ ] 4. Add `src/components/Details.astro`: props
      `{ summaryEn: string; summaryRu: string; open?: boolean }` (default
      `false`), rendering `<details class="block" open={open}>` with a
      `<summary>` holding a `Lang` pair and a default `<slot />` for the body.
      No script, no scoped `<style>`.
      — DoD: `npm run check` passes; the rendered markup contains no
      `<script>`; the block opens and closes with JavaScript disabled.

- [ ] 5. Extend `src/i18n/ui.ts` with every string from issue #6, verbatim
      (depends on nothing): `heroThesis`, `heroSubline`, `statRepositories`,
      `statCommits`, `statReleases`, `statServices`, `statCaptionPrefix`
      (`Snapshot` / `Снимок`), `ctaWork`, `ctaColophon`, `detailsRunSummary`,
      `detailsWorkSummary`, `detailsContactSummary`, plus the array-valued
      `detailsRunItems` (nine items) and `detailsWorkItems` (five bullets).
      Set `homeTitle` to `{ en: 'Dmitrii Mashkov', ru: 'Dmitrii Mashkov' }` and
      delete `homeLede`.
      — DoD: every EN and RU string matches the issue character for character,
      including proper nouns and the `·`-separated bullets split into five
      array entries; `detailsRunItems.en.length === detailsRunItems.ru.length === 9`;
      `detailsWorkItems` both length 5; `npm run check` passes.

- [ ] 6. Rewrite `src/pages/index.astro` (depends on 1, 2, 3, 4, 5): structure
      only, zero copy literals. Order — `<h1 class="hero-name">Dmitrii Mashkov</h1>`
      unpaired, thesis, sub-line, `<section class="stats">` with four `<Stat>`
      bound to `metrics.sources.github.repos` / `.commits` / `.releases` and
      `metrics.sources.mctl.services`, the caption built from
      `snapshotDate(metrics.generated_at)`, the two CTAs to `/work/` and
      `/colophon/` (trailing slash mandatory), then the three `<Details>`.
      Blocks 1 and 2 use one `<ul class="l en">` and one
      `<ul class="l ru" lang="ru">`; block 3 holds the GitHub and mailto links
      with unpaired link text. Remove `<section id="work">` and
      `<section id="approach">`. Do not touch `src/components/Nav.astro`.
      — DoD: the file contains no digit outside heading tag names; `npm run check`
      passes; `npm run dev` renders all four tiles as em dashes and the caption
      as `Snapshot —`.

- [ ] 7. Extend `src/styles/site.css` (depends on 6): hero / thesis / sub-line
      typography (`--font-editorial` on `.hero-name` only, `--font-display`
      everywhere else), `.stats` as
      `repeat(auto-fit, minmax(140px, 1fr))` with `gap: var(--mctl-space-5)`,
      `.stat-value { font-size: clamp(28px, 8vw, 40px); font-variant-numeric: tabular-nums; }`,
      `min-block-size: 44px` plus padding on `.cta`, `.block > summary`,
      `.site-nav a`, `.toggle-group button` and `.site-footer a`, `.block`
      borders and list spacing, and the `@media print` block (light colour
      overrides, hide `.site-header` / `.toggle-group` / `.ctas`, force
      `.block > *:not(summary)` visible with both `display: block !important`
      and `content-visibility: visible !important`, append `attr(href)` after
      external links). Use only `@mctlhq/css` tokens. Do not add a `<style>`
      block to any component.
      — DoD: no component contains a `<style>` element; `dist/_astro/` gains no
      new `.css` file; `<summary>` still shows its disclosure marker.

- [ ] 8. Add `scripts/check-dist.mjs` (depends on 6), modelled on
      `scripts/csp-hash.mjs`: walk `dist/`, exit non-zero with a named reason if
      (a) any file ends in `.js`, (b) any `dist/**/*.html` has an unequal count
      of `class="l en"` and `class="l ru"`, reported per file, or (c)
      `dist/index.html` is 40 960 bytes or larger. Print the measured byte size
      and both counts on success.
      — DoD: `npm run build && node scripts/check-dist.mjs` exits 0 and prints
      the numbers; deleting one `<Lang>` half makes it exit non-zero naming the
      file.

- [ ] 9. Wire the checker into the `Dockerfile` builder stage (depends on 8):
      `RUN npm run build && node scripts/check-dist.mjs && node scripts/csp-hash.mjs > /app/csp-script-src.txt`.
      Change nothing else in the Dockerfile and nothing in
      `.github/workflows/build.yml`, whose `build` job already builds the image
      on every pull request.
      — DoD: `docker build .` succeeds; temporarily raising a check's threshold
      to an impossible value makes `docker build .` fail at that step.

- [ ] 10. Register the new tests in `package.json` (depends on T1, T2, T3):
      `"test": "node --test test/journal.test.ts test/adr.test.ts test/metrics.test.ts test/home.test.ts test/ui.test.ts"`.
      Do not add a dependency and do not let `package-lock.json` change; if it
      must, regenerate it with `npm install --package-lock-only` per `AGENTS.md`.
      — DoD: `npm test` reports five files; `git diff --stat package-lock.json`
      is empty.

- [ ] 11. Add the journal entry `src/content/journal/YYYY-MM-DD-home-page.md`
      (depends on 6), matching the `journal` schema in `src/content.config.ts`:
      `service: portfolio`, `issue: https://github.com/mctlhq/portfolio/issues/6`,
      `proposal_slug: issue-6-p4-home-page`, `visibility: public`, bilingual
      `title` and `decided`, quoted ISO timestamps with a timezone, and an
      `interventions` entry for any human edit made during the cycle.
      — DoD: `npm run check` passes (the schema is `strictObject`, so a stray
      key fails the build); no credential, internal hostname or third party
      appears in a `public` entry.

## Tests

- [ ] T1. `test/metrics.test.ts` — `metricProblems` returns `[]` for the real
      `src/data/metrics.json` read off disk with `node:fs`, and returns a
      problem for each of: a missing `sources.mctl` key, `repos: -1`,
      `commits: 1.5`, `releases: "12"`, `method: ""`, and
      `generated_at: 'not-a-timestamp'`. Plus `formatStat(null) === '—'`,
      `formatStat(0) === '0'`, `formatStat(42) === '42'`,
      `snapshotDate(null) === '—'`,
      `snapshotDate('2026-09-11T01:42:36Z') === '2026-09-11'`.

- [ ] T2. `test/home.test.ts` — reads `src/pages/index.astro` as text and
      asserts: it imports `../data/metrics.json`; every `value=` prop on a
      `<Stat` tag is an expression rooted at `metrics.sources.`; there are
      exactly four `<Stat` occurrences; and `source.replace(/<\/?h[1-6]\b/g, '')`
      contains no `\d`. It also asserts the file contains neither `id="work"`
      nor `id="approach"`, and that both `/work/` and `/colophon/` appear with
      their trailing slash.

- [ ] T3. `test/ui.test.ts` — walks every entry of `ui` and asserts both `en`
      and `ru` exist, are the same kind (string or array), are non-empty, and,
      for arrays, are the same length. This is the mechanical form of
      `AGENTS.md`'s "every user-facing string exists in both languages".

- [ ] T4. Build-gate check: `npm run build && node scripts/check-dist.mjs`
      exits 0; `node scripts/csp-hash.mjs` still prints exactly one
      `sha256-…` token, proving the page added no second inline script;
      `find dist -name '*.js'` prints nothing; `wc -c dist/index.html` is under
      40 960.

- [ ] T5. Manual, Chrome DevTools at 360 x 800 with device emulation:
      `document.documentElement.scrollWidth <= document.documentElement.clientWidth`;
      every nav link, toggle button, CTA, `<summary>` and contact link measures
      at least 44 px tall in the box model; each `<summary>` still shows its
      disclosure marker; the four tiles sit in a 2 x 2 grid. Record the
      measurements in the pull request description.

- [ ] T6. Manual, Chrome print preview and Save as PDF: text is dark on white,
      the site header and both toggles are absent, and all three `<details>`
      bodies are visible even though they are closed on screen. If the
      `content-visibility` override does not take effect in the installed
      Chrome, report it on the pull request rather than working around it by
      opening the blocks by default.

- [ ] T7. Manual, Chrome DevTools Performance panel with the page loaded from
      the built image (`docker run` the image, load over localhost): the LCP
      entry's element is a text node — the hero name or the thesis — not an
      image. In the Network panel, every request is same-origin; export the HAR
      and confirm no third-party host appears. Also confirm the JS filter shows
      zero script resources.

- [ ] T8. Manual, JavaScript disabled: English renders, all three `<details>`
      still open and close, and the `<noscript>` notices from
      `src/components/LangToggle.astro` and `src/components/ThemeToggle.astro`
      are visible.

## Rollback

The change is one pull request touching only source, one data file, one build
script and the Dockerfile — no migration, no persisted state, no external
resource.

1. **Before merge**: close the pull request. Nothing is deployed; the branch
   `feat/agents-issue-6-p4-home-page` can be deleted.
2. **After merge, before release**: revert the merge commit on `main`
   (`git revert -m 1 <sha>`) through a new pull request. `src/pages/index.astro`
   returns to the P2 placeholder, `src/components/Nav.astro`'s `/#work` and
   `/#approach` anchors find their sections again, and `src/data/metrics.json`
   disappears with nothing depending on it.
3. **After deploy**: `mctl_rollback_service(team_name='labs', component_name='portfolio', target_tag=<previous semver>)`
   — per `README.md` the service is `labs/portfolio` and images are
   `ghcr.io/mctlhq/portfolio:<semver>`; the tag before this cycle is the one
   recorded in the previous journal entry's `release` field (`0.1.1` at the
   time of writing). Then revert on `main` as in step 2 so the next release does
   not reintroduce the change.

Partial rollback is available and cheap: if only the build gate misbehaves,
drop `node scripts/check-dist.mjs` from the `Dockerfile` `RUN` line — the page
itself is unaffected and the three criteria fall back to manual review. If only
the print stylesheet misbehaves, delete the `@media print` block from
`src/styles/site.css`; nothing else depends on it.
