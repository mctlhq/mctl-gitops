# Tasks: issue-7-p5-work-page-with-project-entries

- [ ] 1. Add the seven new entries to `src/i18n/ui.ts` (`workTitle`,
  `workGroupPlatform`, `workGroupProducts`, `workRepoLabel`,
  `workMetricsLabel`, `chipDesignTokens`, `chipUpstreamFork`) with the exact
  strings from `requirements.md`, plus the `CHIP_TRANSLATIONS` map and the
  `chipRu(chip)` export built from `ui.chipDesignTokens` and
  `ui.chipUpstreamFork`. Edit no existing entry.
  — DoD: `npm test` passes `test/ui.test.ts` unchanged; `chipRu('design tokens')`
  returns `дизайн-токены`, `chipRu('Go')` returns `undefined`.

- [ ] 2. Add `src/lib/projects.ts` with `ProjectFrontmatter`, `ProjectPair`,
  `pairByLang`, `inGroup`, `repoLinkText` and `chipLabel` as specified in
  `design.md` (depends on 1) — DoD: the module imports nothing but
  `../i18n/ui`, so `node --test` loads it with no build step; `pairByLang`
  throws naming the slug when a language is missing or duplicated; `inGroup`
  returns a new array sorted by `order` ascending and does not mutate its
  input; `chipLabel` returns `{ en: chip, ru: chip }` for an unregistered chip.

- [ ] 3. Add `perRepo(metrics, slug)` and the `MetricPerRepo` interface to
  `src/lib/metrics.ts`, reading `sources.github.per_repo[slug]` defensively and
  yielding `null` for any missing level or non-integer value. Change no existing
  export and do not edit `src/data/metrics.json`.
  — DoD: `perRepo(JSON.parse(readFileSync('src/data/metrics.json')), 'mctl-api')`
  returns `{ commits: null, releases: null }`; `metricProblems` on the real
  snapshot still returns `[]`.

- [ ] 4. Write the fourteen project content pairs under
  `src/content/projects/` — twenty-six new files plus a rewrite of
  `mctl-api.en.md` and `mctl-api.ru.md` — with the frontmatter (`slug`, `lang`,
  `name`, `group`, `order`, `repo`, `stack`, `summary`) and markdown bodies
  reproduced character for character from the "Exact project copy" section of
  `requirements.md`. Keep `mctl-api`'s existing `links` block. Use
  `https://github.com/mashkoffdmitry/pelican-libertex-social` for project 12 and
  `https://github.com/mctlhq/<slug>` for the other thirteen.
  — DoD: `npm run check` (`astro sync && astro check`) passes, meaning all
  twenty-eight files satisfy the `projectsSchema` `strictObject` and
  `checkProjectParity`; `src/content/projects/` contains exactly 28 files;
  every RU summary and body contains Cyrillic and no EN one does.

- [ ] 5. Add `src/components/ProjectCard.astro` as specified in `design.md`
  (depends on 2, 3, 4) — DoD: the root element is
  `<details class="block card">` with no `open` attribute; the `<summary>`
  contains an `<h3>` with `project.name`, a `<Lang>` pair for the summary and
  one `<span class="chip">` per `stack` element produced by
  `project.stack.map(...)`; the body contains `<div class="l en">` and
  `<div class="l ru" lang="ru">` wrapping the two `render()`ed `<Content />`
  components, the repository link, any `links` entries, and the two
  `formatStat(perRepo(...))` metric values; the file contains no chip string
  literal, no digit outside `<h3>`, and no `tabindex`, `role` or `on*`
  attribute.

- [ ] 6. Add `src/pages/work.astro` as specified in `design.md` (depends on 1,
  2, 5) — DoD: `npm run build` emits `dist/work/index.html`; the page renders
  `<h1>` from `ui.navWork`, two `<section class="work-group">` elements with
  `<h2>` headings from `ui.workGroupPlatform` then `ui.workGroupProducts`, and
  fourteen `<details>` elements — six then eight — in the order listed in
  `requirements.md`; the page adds no `<script>`.

- [ ] 7. Append the card rules to `src/styles/site.css` (`.work-group`,
  `.card-name`, `.card-summary`, `.chips`, `.chip`, `.card-links`,
  `.card-metrics`, `.card-metric-value`) without editing any existing rule, then
  run `npm run vendor` and commit the regenerated `public/styles/site.css`
  (depends on 5, 6) — DoD: `git status` shows both files modified; no added
  rule references `--font-editorial`; `.card-links a` has
  `min-block-size: 44px`; the `@media print` block is unchanged.

- [ ] 8. Repoint `src/components/Nav.astro`'s Work link from `/#work` to
  `/work/` (depends on 6) — DoD: exactly one line changes in that file; the
  Approach link still reads `/#approach`; `npm test` still passes
  `test/home.test.ts`.

- [ ] 9. Register `test/projects.test.ts` and `test/work.test.ts` in the `test`
  script of `package.json` (depends on 10, 11) — DoD: `npm test` output names
  both files and reports zero failures; no other `package.json` field changes.

- [ ] 10. Run the link check and record it: build, extract every `href` from
  `dist/work/index.html`, request each one, and print the URL and HTTP status.
  Paste the script and its full output into the pull request description
  (depends on 6) — DoD: every status is 200. If `https://docs.mctl.ai` is not
  200, remove the `links` block from both `mctl-api` files, rebuild, re-run, and
  state the removal in the description.

- [ ] 11. Verify the no-JavaScript and keyboard path by hand and record it in
  the pull request description (depends on 6, 7) — DoD: the description states
  that with JavaScript disabled a card was opened and closed with Tab plus
  Enter and with Tab plus Space, that the focus ring was visible on the
  `<summary>`, and that a HAR capture of `/work/` shows same-origin requests
  only. It also records the byte size of `dist/work/index.html`.

## Tests

- [ ] T1. `test/projects.test.ts` — unit tests for `src/lib/projects.ts`:
  `pairByLang` pairs a two-entry fixture and hoists `group`, `order`, `repo`,
  `stack`, `name`; throws naming the slug for an `en`-only fixture, for a
  `ru`-only fixture, and for a duplicated language; `inGroup` returns only the
  requested group, sorted by `order` ascending, and leaves the input array
  order untouched; `repoLinkText('https://github.com/mctlhq/mctl-api')` returns
  `github.com/mctlhq/mctl-api`; `chipLabel('design tokens')` returns
  `{ en: 'design tokens', ru: 'дизайн-токены' }` and `chipLabel('Telegram Mini App')`
  returns the same string on both sides.

- [ ] T2. `test/projects.test.ts` — content-file sweep over
  `src/content/projects/`, done with `readdir`/`readFileSync` only (no
  `astro:content`, which `node --test` cannot load): exactly 28 files matching
  `*.{en,ru}.md`; the fourteen expected slugs each have both files; each file's
  frontmatter `lang:` value matches its filename suffix; each `*.ru.md`
  `summary:` line and body contain at least one Cyrillic character
  (`/[Ѐ-ӿ]/`) and no `*.en.md` summary or body does; every `repo:`
  line matches `^https://github\.com/`.

- [ ] T3. `test/work.test.ts` — source assertions on
  `src/pages/work.astro`: it imports `getCollection` from `astro:content` and
  `ProjectCard`; it renders exactly two `<section class="work-group">`
  occurrences (or one, produced by a two-element data array — assert the group
  array has exactly two entries); its group headings come from
  `ui.workGroupPlatform` and `ui.workGroupProducts`; it contains no `<script`.

- [ ] T4. `test/work.test.ts` — source assertions on
  `src/components/ProjectCard.astro`: it contains `<details` and `<summary`; it
  contains no `open=`, `tabindex`, `role=` or `on` + `click`; chips are rendered
  by a `.map(` over `stack`; the file contains none of the twenty-two distinct
  chip strings from the fourteen stack arrays as a literal (acceptance
  criterion 4); it contains `class="l en"` and `class="l ru"` exactly as many
  times as each other; it references `formatStat` and `perRepo` and contains no
  numeric literal other than inside the `<h3>`/`</h3>` tag names.

- [ ] T5. `test/work.test.ts` — typography guard: the rules added to
  `src/styles/site.css` for `.card*`, `.chip*` and `.work-group` contain no
  `--font-editorial` reference, so no Instrument Serif can carry Russian text
  (constraint carried from #4).

- [ ] T6. `test/work.test.ts` — version-drift guard: the body of
  `src/content/projects/mctl-design.en.md` contains the `MCTL_VERSION` value
  parsed out of `scripts/vendor-assets.mjs`, and the body of
  `mctl-design.ru.md` contains the same value. This is the one version number
  the issue's copy types into content; the test keeps it from drifting from the
  version actually vendored.

- [ ] T7. `test/metrics.test.ts` — extend with `perRepo`: returns
  `{ commits: null, releases: null }` for the real `src/data/metrics.json`, for
  an unknown slug against a fixture that does have `per_repo`, and for a
  fixture whose `per_repo` value is a string or a negative number; returns the
  integers when the fixture supplies valid non-negative ones; returns `0` rather
  than `null` for a zero value, so `formatStat` renders `0`.

- [ ] T8. Build gates, run as one step: `npm run check`, `npm test`,
  `npm run build`, then `node scripts/check-dist.mjs` and
  `node scripts/csp-hash.mjs`. DoD: `check-dist` reports equal
  `class="l en"` / `class="l ru"` counts for `dist/work/index.html` and no
  `.js` anywhere under `dist/`; `csp-hash` still prints exactly one hash and
  reports one distinct inline script body under the 400-byte budget; the CSP
  placeholder in `nginx.conf` needs no update because the hash is unchanged.

## Rollback

The change is additive and confined to `src/`, `public/styles/site.css` and
`package.json`'s `test` script. No database, no schema, no snapshot, no
infrastructure.

1. **Before merge.** Close the pull request and delete the branch. `main` is
   untouched: `/work/` returns the 404 page again, exactly as today.
2. **After merge, before release.** Revert the merge commit on a branch and
   merge the revert through the normal gate. Because
   `src/pages/index.astro`, `Base.astro`, `Details.astro`, `Stat.astro`,
   `Lang.astro`, `src/content.config.ts`, `src/data/metrics.json`,
   `nginx.conf`, `Dockerfile` and the three scripts are never edited, the
   revert cannot conflict with anything but its own files. `Nav.astro`'s Work
   link returns to `/#work` with the revert.
3. **After release and deploy.** `mctl_rollback_service team_name=<team>
   component_name=portfolio target_tag=<previous tag>` — the previous image
   still serves every route this change does not add, and `/work/` reverts to
   the 404 page. Then revert on `main` as in step 2 so the next release does not
   reintroduce the change.
4. **Partial rollback.** If only the metrics row is at fault (for example P8b
   lands a `per_repo` shape that renders something wrong), delete the
   `.card-metrics` block from `src/components/ProjectCard.astro` and the
   `perRepo` call above it; the cards keep working with no other change, because
   `perRepo` has no other caller. If only one project's copy is wrong, edit that
   slug's two files — no other project and no template is involved.
