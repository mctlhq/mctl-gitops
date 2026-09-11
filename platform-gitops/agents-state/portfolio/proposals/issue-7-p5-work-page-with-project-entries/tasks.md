# Tasks: issue-7-p5-work-page-with-project-entries

- [ ] 1. Add `src/lib/projects.ts`: an import-free module (same discipline as
  `src/lib/metrics.ts` and `src/lib/adr.ts`) exporting `GROUP_ORDER`,
  `pairByLang` and `groupProjects`, generic over the frontmatter subset
  `{ slug, lang, group, order }`. — DoD: the module has an empty import list;
  `groupProjects` returns `platform` before `product` with each group's pairs
  sorted by ascending `order` and ties broken by `slug`; `pairByLang` throws
  naming the slug when a language is missing; `node --test` can import it
  directly with no build step.

- [ ] 2. Extend `src/i18n/ui.ts` (depends on nothing) with `workTitle` (Latin on
  both sides, like `homeTitle`), `workHeading` (`Work` / `Работы`),
  `workGroupPlatform` (`Platform` / `Платформа`), `workGroupProducts`
  (`Products` / `Продукты`), `projectStackLabel` (`Stack` / `Стек`),
  `projectRepoLabel` (`Repository` / `Репозиторий`) and `projectMetricsPending`,
  plus a **separate** export `chipWords` seeded with
  `'design tokens' -> дизайн-токены` and `'upstream fork' -> форк upstream`. —
  DoD: `npm test` still passes `test/ui.test.ts` unchanged (the chip dictionary
  is a sibling export, never a nested key inside `ui`); `npm run check` reports
  no type error; no language, tool or product name appears in `chipWords`.

- [ ] 3. Author the thirteen new project pairs under `src/content/projects/`
  (`mctl-gitops`, `mctl-agents`, `mctl-agent`, `mctl-portal`, `mctl-design`,
  `mctl-telegram`, `seerrsense`, `mctl-academy`, `mctl-loyalty`,
  `mctl-pairdesk`, `pelican-libertex-social`, `pfeifenpatenschaft-backend`,
  `mctl-openclaw`) as `<slug>.en.md` + `<slug>.ru.md`, copying the frontmatter
  shape of the existing `mctl-api` files. `order` is the issue's global number
  (platform 1-6, product 7-14); `repo` is `https://github.com/mctlhq/<slug>`
  except `pelican-libertex-social`
  (`https://github.com/mashkoffdmitry/pelican-libertex-social`); `summary` and
  `stack` are the issue's wording verbatim. Detail bullets go in the markdown
  body as a plain bullet list, per language, for the ten projects the issue
  supplies them for; `mctl-openclaw`'s bullets must state that repository totals
  reflect upstream and the owner's contribution is the fork layer and the
  deployment pipeline. The four projects with no issue-supplied bullets
  (`mctl-loyalty`, `mctl-pairdesk`, `pelican-libertex-social`,
  `pfeifenpatenschaft-backend`) get an empty body — do not invent prose. — DoD:
  `npx astro sync` passes, meaning every file validates against `projectsSchema`
  and `checkProjectParity` finds one `en` and one `ru` per slug agreeing on
  `group`, `order`, `repo`, `stack` and `links[].url`; bodies carry no `.l.en` /
  `.l.ru` spans and no HTML; EN and RU bullet counts match per project.

- [ ] 4. Update the existing `mctl-api` pair (depends on 3 for consistency of
  shape): replace `summary` and `stack` with the issue's wording
  (`Go`, `chi`, `mcp-go`, `OAuth 2.0 PKCE`, `OpenAPI`), keep `order: 1`,
  `group: platform` and the `Docs` link to `https://docs.mctl.ai`, and replace
  the one-paragraph body with the issue's three detail bullets in each language.
  — DoD: both files still validate; `npx astro sync` passes; the `Docs` link is
  still present with its per-language label.

- [ ] 5. Add `src/components/ProjectCard.astro` (depends on 2) taking
  `{ en, ru }` collection entries, rendering a `<details class="project-card">`
  whose `<summary>` holds the mono project name, the bilingual one-line summary
  and a `.chips` list mapped from `en.data.stack` through `chipWords` with a
  pass-through default; and whose body holds each language's compiled markdown
  (`const { Content } = await render(entry)` from `astro:content`) inside a
  matched `.l.en` / `.l.ru` wrapper pair, the repository link plus any
  `links`, and a `<slot name="metrics">` whose fallback is
  `formatStat(null)` from `src/lib/metrics.ts`. — DoD: no project string, URL or
  chip label is a literal in the component; no `<a>`, `<button>` or `tabindex`
  inside `<summary>`; no `var(--font-editorial)` anywhere in the file; the
  component emits exactly as many `class="l en"` as `class="l ru"` for any input
  including an empty body.

- [ ] 6. Add `src/pages/work.astro` (depends on 1 and 5): `getCollection(
  'projects')` into `groupProjects`, `<Base title={ui.workTitle.en}>`, a
  bilingual `<h1>`, one `<section>` per group with a bilingual `<h2>`, and one
  `<ProjectCard>` per pair. — DoD: `npm run build` emits `dist/work/index.html`
  with fourteen cards, six under the Platform heading and eight under Products,
  in the issue's order; no digit appears in the rendered template outside HTML
  heading tag names; the page renders in English with JavaScript disabled and
  every card expands.

- [ ] 7. Append a `/* Work page. */` block to `src/styles/site.css` (depends on
  5) for `.project-group`, `.project-card`, `.project-card > summary`, `.chips`,
  `.chip`, `.project-links` and `.project-metrics`, using `var(--font-display)`
  for translated text and `var(--font-mono)` for names and chips, keeping
  `display: list-item` and `min-block-size: 44px` on the summary, and adding
  `.project-card` to the existing `@media print` force-expand selector list.
  Then run `npm run vendor` and commit the regenerated
  `public/styles/site.css`. — DoD: the new block contains no
  `var(--font-editorial)`; `public/styles/site.css` in the commit is
  byte-identical to `src/styles/site.css`; every summary is at least 44px tall at
  360px and at desktop width; the home page's appearance is unchanged.

- [ ] 8. Point `src/components/Nav.astro`'s Work link at `/work/` instead of the
  deleted `/#work` anchor (depends on 6). — DoD: one-line href change, no other
  edit to the file; `/work/` is reachable from the header on every page. Flag
  this in the pull-request description as the one edit outside the issue's stated
  file list (requirements open question 3).

- [ ] 9. Extend `scripts/check-dist.mjs` (depends on 6) with one assertion:
  `dist/work/index.html` exists and contains exactly fourteen occurrences of
  `<details class="project-card"`. — DoD: the script still fails on a `.js` file
  under `dist/`, still fails on unequal `class="l en"` / `class="l ru"` counts in
  any document, still caps `dist/index.html` at 40 KB, and now fails if the work
  page is missing or has the wrong card count; `docker build .` succeeds, since
  the `Dockerfile` runs this script.

- [ ] 10. Add `scripts/check-links.mjs` and a `check:links` entry in
  `package.json`'s `scripts` (depends on 6): extract every `href` from
  `dist/**/*.html`, de-duplicate, resolve site-relative hrefs against the files
  on disk and absolute `https://` hrefs over the network (`HEAD`, falling back to
  `GET`), print one `status url` line per link, exit non-zero if any is not 200.
  — DoD: the script is **not** referenced by `prebuild`, `.github/workflows/build.yml`
  or the `Dockerfile`, so no build gains a network dependency; running
  `npm run build && npm run check:links` locally produces the table pasted into
  the pull-request description.

- [ ] 11. Register the new tests in `package.json`'s `test` script (depends on
  12 and 13) by appending `test/projects.test.ts test/work.test.ts` to the
  explicit file list. — DoD: `npm test` visibly runs seven files; CI
  (`.github/workflows/build.yml`, which calls `npm test`) exercises both.

- [ ] 12. Write `src/content/journal/2026-09-11-work-page.md` per `AGENTS.md`
  (depends on 6): `service: portfolio`, the #7 issue URL, `proposal_slug:
  issue-7-p5-work-page-with-project-entries`, `visibility: public`, bilingual
  `title` and `decided`, the timestamps known at merge time, and an
  `interventions` entry for anything a human had to do (for example publishing a
  private repository so its link returns 200). — DoD: `npx astro sync` passes the
  `journal` schema, including quoted ISO timestamps with a timezone.

- [ ] 13. Open the pull request with the link-check table from task 10 in its
  description, the Nav change from task 8 called out, and every non-200 URL named
  rather than quietly amended. — DoD: `.github/workflows/build.yml` is green
  (`npm test` plus the Docker build, which runs `check-dist.mjs` and
  `csp-hash.mjs`); the description shows the status of every URL on `/work/`.

## Tests

- [ ] T1. `test/projects.test.ts` — `groupProjects` returns `platform` then
  `product`; within each group, pairs are sorted by ascending `order` with `slug`
  breaking ties; `pairByLang` pairs `en` with `ru` by slug and throws naming the
  slug when either language is missing; an empty input yields two empty groups.

- [ ] T2. `test/work.test.ts` (source-text assertions, in the style of
  `test/home.test.ts`) — `src/pages/work.astro` imports `getCollection` and
  `groupProjects` and contains no project name, URL or chip literal; stripping
  heading tag names from its template leaves no digit; the `<summary>` region of
  `src/components/ProjectCard.astro` contains no `<a `, no `<button` and no
  `tabindex`; neither file nor the new `src/styles/site.css` work-page block
  contains `font-editorial`.

- [ ] T3. `test/work.test.ts` (content assertions) — reading
  `src/content/projects/`: exactly fourteen slugs, each with one `.en.md` and one
  `.ru.md`; six with `group: platform` and eight with `group: product`; the set
  of `order` values is 1-6 in platform and 7-14 in product; every `repo` equals
  `https://github.com/mctlhq/<slug>` except `pelican-libertex-social`; EN and RU
  bullet counts match for every project that has a body.

- [ ] T4. `npm run check` (`astro sync && astro check`) — no type error from the
  new `ProjectCard` props, the `render()` import or the `chipWords` lookup.

- [ ] T5. `npm run build && node scripts/check-dist.mjs` — no `.js` under
  `dist/`; equal `class="l en"` and `class="l ru"` counts in
  `dist/work/index.html` and every other document; `dist/index.html` still under
  40 KB; exactly fourteen `<details class="project-card"` in the work page.

- [ ] T6. `npm run build && npm run check:links` — every URL on `/work/` returns
  200; the output table goes into the pull-request description. Any non-200 is
  reported by name, not fixed by editing the URL.

- [ ] T7. Manual keyboard pass on the built page: Tab reaches every card's
  `<summary>` in document order, Enter toggles it, Space toggles it, focus stays
  visible via the existing `:focus-visible` rule in `src/styles/site.css`.

- [ ] T8. Manual no-JavaScript pass: with scripting disabled, `/work/` renders
  English, every card expands, every link is clickable, and the language toggle
  shows its existing `langNoScript` notice.

- [ ] T9. Manual network pass: a HAR capture of `/work/` shows same-origin
  requests only — no third-party font, stylesheet or beacon — and the page
  reports no CSP violation under the `default-src 'self'` header in
  `nginx.conf`.

- [ ] T10. Manual bilingual spot check at 360px and desktop width: switching to
  RU changes every summary, group heading, detail bullet and the two plain-word
  chips, while `Go`, `PostgreSQL`, `Temporal`, `Backstage` and the project names
  stay untranslated; every per-repo metric shows an em dash.

## Rollback

Every change is additive except four small edits, so rollback is cheap at three
levels:

1. **Before merge** — close the pull request. Nothing has shipped: `main` is
   untouched and no image was pushed.
2. **After merge, before deploy** — revert the merge commit on a branch and merge
   the revert. The four non-additive edits restore cleanly: `mctl-api`'s previous
   `summary`, `stack` and body; `Nav.astro`'s `/#work` href; the appended
   `src/styles/site.css` block and its `public/styles/site.css` copy; and
   `package.json`'s `test` and `scripts` entries. Deleting
   `src/pages/work.astro` alone is enough to remove the page while keeping the
   content: `/work/` returns the 404 page again, and `src/pages/index.astro`'s
   CTA becomes a dead link exactly as it is today.
3. **After deploy** — `mctl_rollback_service` to the previous image tag for the
   `portfolio` service, per `AGENTS.md` (deployments happen only through mctl MCP
   tools; no `kubectl`, no hand-edited gitops values). Record the rollback as an
   intervention in the next cycle's journal entry.

No data migration, no schema change and no secret is involved, so there is
nothing to undo outside git and the image tag. If only the link check fails,
the narrower fix is to amend the affected content file's `repo`/`links` in a
follow-up rather than to revert the page.
