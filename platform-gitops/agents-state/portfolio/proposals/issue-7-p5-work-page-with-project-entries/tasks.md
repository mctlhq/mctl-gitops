# Tasks: issue-7-p5-work-page-with-project-entries

- [ ] 1. Make `repo` optional in `src/content.config.ts`: change
      `repo: githubUrl` to `repo: githubUrl.optional()` inside
      `projectsSchema`. Leave `checkProjectParity` alone — its
      `en[0].data.repo === ru[0].data.repo` comparison is already correct when
      both sides are `undefined`. — DoD: `npm run check` passes with the
      existing `mctl-api` pair, and a project file with no `repo:` line no
      longer fails validation.

- [ ] 2. Extend `src/i18n/ui.ts` (depends on nothing). Add to the `ui` object
      the five `{ en, ru }` string pairs listed in `requirements.md` ->
      "Interface strings added to `src/i18n/ui.ts`": `workGroupPlatform`,
      `workGroupProducts`, `workDetailsSummary`, `workMetricsLabel`,
      `workPageTitle`. Add `stackChipRu` as a **separate named export outside
      the `ui` object** with exactly the two entries `'design tokens'` and
      `'upstream fork'`. — DoD: `npm test` passes (`test/ui.test.ts` iterates
      only `Object.entries(ui)`, so `stackChipRu` must not be a `ui` key), and
      `npm run check` reports no type error.

- [ ] 3. Write the fourteen `src/content/projects/<slug>.en.md` files (depends
      on 1). Frontmatter fields, `stack`, `summary` and the bullet body are
      copied character for character from the copy tables in
      `requirements.md`. `order` is the global 1..14 number given there;
      `group` is `platform` for 1-6 and `product` for 7-14;
      `repo` is `https://github.com/mctlhq/<slug>` except
      `pelican-libertex-social`
      (`https://github.com/mashkoffdmitry/pelican-libertex-social`) and
      `pfeifenpatenschaft-backend` (**no `repo` field at all**). Rewrite the
      existing `mctl-api.en.md` to the issue's stack and summary, keeping its
      `links` entry for `https://docs.mctl.ai`. Write each file directly, never
      through a shell `echo`/`sed` pipeline, so em dashes and typographic
      apostrophes survive. — DoD: fourteen `*.en.md` files exist; each body is a
      markdown bullet list whose items match the EN detail bullets exactly.

- [ ] 4. Write the fourteen `src/content/projects/<slug>.ru.md` files (depends
      on 3). Same `slug`, `name`, `group`, `order`, `repo` (or its absence) and
      **byte-identical `stack` array** as the English file — `checkProjectParity`
      compares `stack` with `JSON.stringify` and fails the build on any
      difference. `summary` and the body are the RU strings from
      `requirements.md`; `links[].label` is the Russian label where a link has
      one (`Документация` for `mctl-api`). — DoD: `npm run check` passes, and
      `astro dev` + `/dev/collections` reports `projects: 28`.

- [ ] 5. Create `src/components/ProjectCard.astro` (depends on 2). Props
      `{ en, ru }` as `CollectionEntry<'projects'>`; `const { Content: BodyEn }
      = await render(en)` and the same for `ru`, with `render` imported from
      `astro:content`. Markup per `design.md` section 2: `<article
      class="project" id={slug}>`, `<h3 class="project-name">`, a
      `<Lang>`-paired summary, `<ul class="chips">` built from
      `en.data.stack.map(...)` with `stackChipRu[chip] ?? chip` on the Russian
      side, and `<details class="block project-details">` holding the two
      rendered bodies as an `.l.en` / `.l.ru` pair, the links list, and the
      metrics line with a named `metrics` slot whose fallback is
      `formatStat(null)`. Render the repository anchor only when
      `en.data.repo` is defined, with the link text derived from the URL
      (`host + path`). Do not add `tabindex`, `role` or any script. — DoD: no
      chip, project name, summary or URL appears as a literal in the component;
      `npm run check` passes.

- [ ] 6. Create `src/pages/work.astro` (depends on 4, 5). `getCollection('projects')`,
      split by `lang`, index the Russian entries by `slug`, filter by `group`
      and sort by `data.order`; render `<Base title={ui.workPageTitle.en}>`, an
      `<h1>` with the existing `ui.navWork` pair, then two `<section>` blocks
      (Platform, then Products) each with an `<h2>` `<Lang>` pair and its
      `ProjectCard` list. — DoD: `npm run build` emits `dist/work/index.html`
      containing 14 `<article class="project"` occurrences, 6 in the first
      section and 8 in the second, in the order listed in `requirements.md`.

- [ ] 7. Add the `/* Work page. */` block to `src/styles/site.css` (depends on
      5). `.project`, `.project-name`, `.project-summary`, `.chips`, `.chip`,
      `.project-links`, `.project-metrics`, using the existing
      `--mctl-space-*`, `--mctl-radius-*` and `--surface-*` tokens. Reuse the
      existing `.block` class on the card's `<details>` so the 44px summary
      target and the print rules apply. `--font-editorial` must not appear in
      any new selector. Keep the two rendered-body wrappers as **direct**
      children of the `<details>` so the existing print override
      `:root[data-lang='en'] .block > .l.ru` still matches. — DoD:
      `grep -c 'font-editorial' src/styles/site.css` is unchanged from `main`
      (one occurrence, `.hero-name`), and `npm run vendor` regenerates
      `public/styles/site.css` with the new rules committed.

- [ ] 8. Repoint `src/components/Nav.astro` from `href="/#work"` to
      `href="/work/"` (depends on 6). Leave `/#approach` untouched. — DoD: the
      nav item resolves to the new page from every page of the site.

- [ ] 9. Run the full local gate (depends on 6, 7, 8): `npm run check`,
      `npm test`, `npm run build`, `node scripts/check-dist.mjs`. — DoD: all
      four succeed; `check-dist` reports equal `class="l en"` and
      `class="l ru"` counts for `dist/work/index.html` and no `.js` under
      `dist/`.

- [ ] 10. Write the link-check script and paste it with its output into the
      pull request description (depends on 9). It extracts every `href` from
      `dist/work/index.html`, resolves site-relative paths against the deployed
      origin, requests each URL and prints `url -> status`. Do **not** commit it
      into `npm test`: CI must not depend on network reachability. — DoD: the
      PR description carries the script and a run where every line ends in
      `200`, including the absence of any `pfeifenpatenschaft-backend` URL.

- [ ] 11. Add the journal entry
      `src/content/journal/2026-09-11-work-page.md` (depends on 9), per
      AGENTS.md: `service: portfolio`, `issue:` the issue URL,
      `proposal_slug: issue-7-p5-work-page-with-project-entries`,
      `visibility: public`, bilingual `title` and `decided`, `issue_opened_at`
      and `proposal_approved_at`. Do not hand-write lead time or intervention
      counts — they are computed at build time. — DoD: `npm run check` passes
      with the new entry and its frontmatter validates against the `journal`
      schema.

- [ ] 12. Open the pull request from a branch (never commit to `main`), with a
      conventional-commit title (`feat: add the work page with project
      entries`) and a body listing each acceptance criterion with the evidence
      for it. — DoD: the `build` workflow is green and the automated reviewer
      has run.

## Tests

- [ ] T1. `test/projects.test.ts` — reads the files under
      `src/content/projects/` as text (no YAML dependency; follow the
      source-reading style of `test/home.test.ts`). Asserts: 28 files, 14
      distinct slugs matching the list in `requirements.md`; every slug has
      exactly one `.en.md` and one `.ru.md`; `lang:` in each file matches its
      filename suffix; 6 files per language carry `group: platform` and 8 carry
      `group: product`; the `order:` values are 1..14 once per language;
      `pfeifenpatenschaft-backend.{en,ru}.md` contain no `repo:` line; every
      other `repo:` value matches
      `^https://github\.com/(mctlhq|mashkoffdmitry)/<slug>$`.

- [ ] T2. `test/projects.test.ts` — for each slug, the `stack:` line is
      byte-identical between the `.en.md` and `.ru.md` file (the same invariant
      `checkProjectParity` enforces at build time, surfaced as a fast unit
      failure with a readable message).

- [ ] T3. `test/work.test.ts` — reads `src/pages/work.astro` and
      `src/components/ProjectCard.astro` as text. Asserts: `ProjectCard`
      derives chips from `en.data.stack` and contains none of the chip literals
      (`TypeScript`, `PostgreSQL`, `Go`, `design tokens`, `upstream fork`, ...);
      neither file contains `--font-editorial`; neither file contains
      `tabindex`; `work.astro` sorts on `data.order`; `work.astro` imports
      `ProjectCard` and `getCollection`.

- [ ] T4. `test/ui.test.ts` (existing, unmodified) must still pass, proving
      `stackChipRu` was exported outside the `ui` object.

- [ ] T5. Wire T1-T3 into the `test` script in `package.json` by appending the
      new files to the `node --test` argument list. A test nothing invokes is
      not a test (AGENTS.md); `.github/workflows/build.yml` already runs
      `npm test` and needs no change.

- [ ] T6. Manual check recorded in the PR description: with JavaScript disabled,
      `/work/` renders the English content and every card expands; tabbing
      reaches each `<summary>` with a visible focus ring and Enter and Space
      both toggle it; a HAR capture of `/work/` shows same-origin requests only.

## Rollback

The change is additive and self-contained; nothing is deployed or migrated
until the release workflow runs.

- Before merge: close the pull request. `main` is untouched.
- After merge, before release: revert the merge commit
  (`git revert -m 1 <sha>`) on a branch and merge that. This removes
  `src/pages/work.astro`, `src/components/ProjectCard.astro`, the 28 project
  files, the `site.css` block, the `ui.ts` additions, the `Nav.astro` href and
  the `repo` optionality in one step. The home page CTA then points at `/work/`
  again with no page behind it — the state `main` is in today — so the revert
  should be followed by re-running this proposal rather than left standing.
- After release and deploy: `mctl_rollback_service` with the previous image tag
  for the `portfolio` service, then revert as above. No data, secret or gitops
  value is involved, so there is nothing else to undo.
