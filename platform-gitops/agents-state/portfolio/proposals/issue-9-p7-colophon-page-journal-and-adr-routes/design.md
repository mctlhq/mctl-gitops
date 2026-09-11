# Design: issue-9-p7-colophon-page-journal-and-adr-routes

## Current state

**Content model.** `src/content.config.ts` defines three collections. `journal`
globs `src/content/journal/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]-*.md` with
`generateId: idFromFile`, so an entry's id is its filename stem (e.g.
`2026-09-11-home-page`). Its strict schema carries `service`, `issue`,
`proposal_slug`, optional `pr` and `release`, `visibility`, the bilingual
`title` and `decided`, five `stamp` fields (`issue_opened_at` required, the
other four optional) and `interventions: [{what, why, at}]` defaulting to `[]`.
`stamp` validates an ISO 8601 string with an offset and then `.transform()`s it
into a `Date`, so `entry.data.issue_opened_at` is a `Date` at render time, not a
string. `adr` globs `src/content/adr/[0-9][0-9][0-9][0-9]-*.md` through
`adrLoader()`, which additionally runs `checkAdrBodies` from `src/lib/adr.ts`;
its schema carries `id` (number), bilingual `title`, `status`, `date`
(`YYYY-MM-DD`), optional `supersedes` and `visibility`.

**Computation helpers.** `src/lib/journal.ts` already exports `leadTimeHours`
(returns `null` when `deployed_at` is absent, throws `RangeError` when it
precedes `issue_opened_at`) and `interventionCount`. Both are unit-tested in
`test/journal.test.ts`. `src/lib/metrics.ts` exports `EM_DASH` and `formatStat`.
Both library modules are deliberately zero-import so `node --test` can load them
with Node's native TypeScript stripping and no build step.

**Content on disk.** `src/content/journal/` holds seven entries, all
`visibility: public`: two for platform repositories (`mctl-agents` 330,
`mctl-api` 281, both with `deployed_at` and two interventions each), P1 (issue
3, three interventions), P2 (issue 4, three interventions), and P4/P5/P6 (issues
6, 7, 8) which stop at `proposal_approved_at`. There is no entry for the P3
cycle (issue 5). `src/content/adr/` holds `0001`, `0002` and `0005`, all public,
each a Nygard body of five bilingual sections.

**Pages and rendering.** `src/pages/index.astro` already links `/colophon/`,
which currently falls through to `src/pages/404.astro`. `src/pages/work.astro`
is the model for a collection-driven page: `getCollection('projects')`, filter,
sort, render through a component. `src/components/ProjectCard.astro` is the
model for rendering a collection body: `import { render } from 'astro:content'`
then `const { Content } = await render(entry)`. There is no route in the repo
that uses `getStaticPaths` over a collection; `src/pages/dev/[check].astro` uses
`getStaticPaths` but returns `[]` outside `astro dev`.

**Copy and bilingual mechanics.** Every user-facing string lives in
`src/i18n/ui.ts` as an `{ en, ru }` pair (or a pair of equal-length arrays) and
renders through `src/i18n/Lang.astro`, which emits
`<span class="l en">…</span><span class="l ru" lang="ru">…</span>`.
`src/styles/site.css` hides one side per `:root[data-lang]`. `ui.navColophon`
and `ui.footerColophonLabel` are already defined and unused;
`src/components/Nav.astro` links only `/`, `/work/` and `/approach/`.

**Footer.** `src/components/Footer.astro` already does
`import pkg from '../../package.json'` and renders
`<span data-release>{pkg.version}</span>`. `package.json`'s `version` is
maintained by release-please with `include-v-in-tag: false`, so it is already a
`v`-less semver (`0.1.4` in this clone; `0.1.5` on `main` after PR 33). The
issue's footer requirement is therefore already met by construction; what is
missing is a check that keeps it met, and the stale comment above the markup
that says the release value has "no build-arg / git-describe source wired up
yet".

**Build gates.** `npm run prebuild` runs `npm run vendor && npm test`;
`package.json`'s `test` script names each test file explicitly, so a new test
file must be added there or it never runs. `scripts/check-dist.mjs` runs after
`astro build` inside the `Dockerfile` and already enforces: no `.js` under
`dist/`, equal `class="l en"` / `class="l ru"` counts in every
`dist/**/*.html`, a 40 KB cap on `dist/index.html`, and the P6 SVG rules.
`scripts/csp-hash.mjs` enforces exactly one inline script body of at most 400
bytes. `.github/workflows/build.yml` runs `npm test` and a no-push Docker build
on every pull request, so both gates run pre-merge.

## Proposed solution

### 1. A new zero-import helper: `src/lib/colophon.ts`

Everything the page computes that is not already in `src/lib/journal.ts` goes
into one new module, written in the same zero-import style as its two siblings
so that both `.astro` pages and `scripts/check-dist.mjs` can import it and
`node --test` can load it directly:

- `EM_DASH` — re-declared locally with a comment, exactly as `src/lib/metrics.ts`
  re-declares `ISO_WITH_OFFSET`, to keep the import list empty.
- `cycleDate(id: string): string` — the leading `YYYY-MM-DD` of an entry id;
  throws when the id does not start with one.
- `compareCyclesNewestFirst(a, b)` over `{ id, issueOpenedAt }` — `cycleDate`
  descending, then `issueOpenedAt` descending, then `id` descending. A total
  order, so the row order is stable across builds.
- `formatLeadTime(hours: number | null): string` — `EM_DASH` when `null`,
  otherwise `hours.toFixed(1)`. Branches on `=== null`, never on falsiness, so a
  genuine `0.0` renders as `0.0` (the bug `formatStat` already guards against).
- `formatStamp(value: Date | string | null | undefined): string` — `EM_DASH`
  when absent, otherwise `YYYY-MM-DD HH:MMZ` built from `toISOString()`. Locale
  APIs are avoided on purpose: the output must be identical in both languages
  and identical on every build machine.
- `githubRefLabel(url: string): string` — `portfolio#12` / `mctl-api#282` from a
  GitHub issue or pull request URL; throws on a URL it cannot parse, so a typo
  fails the build instead of rendering an empty cell.
- `visibilityOf(source: string): 'public' | 'private' | null` and
  `publicIds(files: {id, source}[]): string[]` — frontmatter-level helpers used
  only by `scripts/check-dist.mjs`, which cannot call `getCollection`.
- `interventionsInSource(source: string): number` — counts `- what:` items in a
  frontmatter block, again only for the post-build check.

### 2. `src/components/CycleTable.astro`

Takes the public journal entries as a prop, sorts them with
`compareCyclesNewestFirst`, and renders one `<table class="cycle-table">` with a
bilingual `<caption>` and `<th scope="col">` headers from the new `ui` keys. Per
row: `cycleDate(entry.id)`; `entry.data.service` (a proper noun, untranslated);
the bilingual `title` as a link to `/colophon/journal/<id>/`;
`githubRefLabel(entry.data.issue)` as a link; the same for `pr` or `EM_DASH`;
`entry.data.release` or `EM_DASH`; `formatLeadTime(leadTimeHours(entry.data))`;
`interventionCount(entry.data)`. Numbers, ids and service names are
language-neutral, so the only `Lang` pairs in a row are the headers and the
title — `class="l en"` and `class="l ru"` stay equal per row by construction.
The table is wrapped in a `div` with `overflow-x: auto` for narrow viewports;
no `--font-editorial` anywhere.

### 3. `src/pages/colophon/index.astro`

`getCollection('journal', ({ data }) => data.visibility === 'public')` and the
same for `adr`. Renders: `<h1>` (`ui.navColophon`), the intro paragraph, the
"Build and deploy chain" section as a bilingual `<ul>` pair driven by
`ui.colophonChainItems` (the same `.l en` / `.l ru` list pattern
`index.astro` already uses for `detailsRunItems`), the "Cycles" section with
`<CycleTable>` followed by the two totals, and the "Decisions" section with the
ADR index table sorted by `data.id` ascending, each row linking to
`/colophon/adr/<id>/` from its `ADR-NNNN` cell.

The totals are rendered as
`<span data-cycle-count={cycles.length}>` and
`<span data-interventions-total={total}>` where
`total = cycles.reduce((sum, e) => sum + interventionCount(e.data), 0)`. The
`data-` attributes mirror the existing `data-stat` / `data-release` hooks and
are what `scripts/check-dist.mjs` reads; nothing about the numbers is typed.
Sections are plain `<section><h2>` blocks, not `<details>`: this page is
evidence and must be readable without interaction (and without JavaScript).

### 4. `src/pages/colophon/journal/[...slug].astro` and `.../adr/[...slug].astro`

Both use `getStaticPaths` over the collection with the `visibility === 'public'`
filter and `params: { slug: entry.id }`, passing the entry through `props`. The
filter inside `getStaticPaths` is the whole of the privacy mechanism: Astro
emits pages only for returned paths, so a private entry produces no file, and
because neither route reads any other entry, no private title or body text can
leak into another page. The ADR page renders the body through
`const { Content } = await render(entry)`, exactly as `ProjectCard.astro` does;
the ADR body already carries its own `.l en` / `.l ru` pairs, enforced by
`checkAdrBodies`. Journal entries have empty bodies, so the journal page renders
frontmatter only: kicker, bilingual title, `decided`, a definition list of
service / issue / pr / release / the five timestamps via `formatStamp` / the
computed lead time, and an ordered list of interventions (`what`, `why`, `at`).
Both pages use `src/layouts/Base.astro` and end with a link back to `/colophon/`.

### 5. Footer, navigation, styles

`src/components/Footer.astro` keeps `import pkg from '../../package.json'` and
the `data-release` hook; only the stale comment is corrected to state that the
release tag *is* the built `package.json` version (release-please, no `v`
prefix). `src/components/Nav.astro` gains `<a href="/colophon/">` using
`ui.navColophon`, so the new page is reachable from every page rather than only
from the home CTA. `src/styles/site.css` gains `.cycle-table`, `.adr-table`,
`.colophon-totals`, `.entry-meta` and `.intervention` rules built from
`--mctl-*` tokens and `var(--font-display)` / `var(--font-mono)`; `npm run
vendor` copies the file to `public/styles/site.css` as it already does.

### 6. Backfill

One new file for the P3 cycle and four added keys on each of the three P4-P6
entries, with the exact values listed in `requirements.md`. The timestamps were
read from GitHub during this investigation: `merged_at` is the pull request's
`mergedAt` (PRs 21, 24, 28, 32), `released_at` is the release's `publishedAt`
(0.1.2 through 0.1.5), `issue_opened_at` is the issue's `createdAt`, and the P3
`proposal_approved_at` is `approval.approved_at` from
`platform-gitops/agents-state/portfolio/proposals/issue-5-.../.status.yaml`.
This matches how the existing P1/P2 entries were filled (P1's
`released_at: 2026-09-11T00:17:50Z` is exactly the 0.1.0 release timestamp).

No `interventions` are added. The only human commits during those four cycles
touched `AGENTS.md` and the release configuration — files `AGENTS.md` itself
permits a human to edit — so under the bootstrap boundary they are not manual
interventions, and inventing entries would corrupt the one number on the page
that is supposed to be uncomfortable. No `deployed_at` is added either: the
service has not been onboarded yet (`MCTL_ONBOARDED` is still unset), and
production evidence is P9. The consequence is visible and correct: six of the
eight rows show an em dash for lead time.

### 7. Gates

- `scripts/check-dist.mjs` gains `checkColophonPages()`: asserts
  `dist/colophon/index.html` exists; compares the directory set under
  `dist/colophon/journal/` and `dist/colophon/adr/` against `publicIds()`
  computed from `src/content/`, in both directions; asserts no private id string
  occurs in any `dist/` path or in `dist/colophon/index.html`; compares
  `data-cycle-count` against the number of public journal files and
  `data-interventions-total` against the summed `- what:` count; and compares the
  `data-release` text in `dist/index.html` against `package.json`'s `version`,
  failing if it differs or starts with `v`.
- `test/colophon.test.ts` (added to the `test` script in `package.json`)
  unit-tests every `src/lib/colophon.ts` export, asserts that no file in
  `src/content/journal/` contains a `lead_time`-style key or any key outside the
  schema, and makes the same source-level assertions `test/work.test.ts` makes:
  no `--font-editorial`, no `tabindex`, no hard-coded copy in the new templates,
  `getStaticPaths` filtering on `visibility`.

## Alternatives

1. **Write `lead_time_hours` and `interventions_count` into the frontmatter and
   read them directly.** Simplest possible page, and rejected outright: the
   issue forbids it (`grep -r lead_time src/content` must be empty), `AGENTS.md`
   requires the two values to be computed at build time, and a hand-written lead
   time is exactly the kind of unverifiable claim this page exists to replace.

2. **One combined route `src/pages/colophon/[...slug].astro` covering both
   journal entries and ADRs.** Fewer files, but the two entry kinds share no
   frontmatter and render nothing in common, so the single page would be two
   templates behind a discriminator, and `getStaticPaths` would have to merge
   two collections with a prefix convention to avoid id collisions. Two routes,
   as the issue specifies, keep each `getStaticPaths` filter trivially auditable
   — which matters, because that filter is the privacy boundary.

3. **Prove the private-entry rule with a committed `visibility: private`
   fixture.** It would exercise the exclusion directly, but a private entry
   whose only purpose is to be excluded is content that says nothing, and the
   ADR/journal conventions in `AGENTS.md` treat these directories as the real
   record. Instead `scripts/check-dist.mjs` compares the generated route set
   against the public id set in both directions, which fails the build the first
   time a private entry does leak, without shipping a fake entry.

4. **Render the totals and the cycle count into plain text only, without
   `data-` attributes.** Less markup, but then no gate can check criterion 2
   mechanically: a post-build script would have to scrape prose. The repository
   already uses `data-stat` and `data-release` as machine-readable hooks for
   exactly this reason, and `AGENTS.md` requires evidence to live in a script
   that runs in the build rather than in a pull request description.

## Platform impact

- **Migrations:** none. No schema change to `src/content.config.ts`, no change
  to `nginx.conf`, the `Dockerfile`, the CSP header or the deployment shape.
  `try_files $uri $uri/index.html` already serves the new nested directories.
- **Backward compatibility:** additive. `/colophon/` was a dead link from the
  home page and starts resolving; existing pages are untouched except
  `src/components/Nav.astro` (one link) and `src/components/Footer.astro` (a
  comment).
- **Resource impact:** four to five new HTML documents plus one per public
  entry (8 journal + 3 ADR = 11 today), a few kilobytes each. No new runtime
  dependency, no new font, no new third-party request, no `.js`. The 40 KB cap
  applies to `dist/index.html` only and is unaffected.
- **Risk: Node TypeScript stripping in `scripts/check-dist.mjs`.**
  `check-dist.mjs` is plain JavaScript and would now import
  `src/lib/colophon.ts`. Node 24 (the `node:24-alpine` builder and the CI
  `setup-node` version) strips types natively, which is already how
  `node --test test/*.ts` loads `src/lib/journal.ts`. Mitigation: keep
  `colophon.ts` to strippable syntax only — no `enum`, no `namespace`, no
  parameter properties, no `satisfies`-dependent runtime behaviour — the same
  constraint the existing lib modules already satisfy. If the import still
  fails, inline the three frontmatter regexes into `check-dist.mjs` and keep the
  render-side helpers in `colophon.ts`.
- **Risk: `leadTimeHours` throws on a data error.** It raises `RangeError` when
  `deployed_at` precedes `issue_opened_at`. Rendering it inside the table makes
  that a build failure rather than a nonsense cell — intended, and the backfill
  values are ordered correctly (every `merged_at` precedes its `released_at`).
- **Risk: bilingual parity on the new pages.** Every row mixes translated cells
  with language-neutral ones. Mitigation: keep all translated text inside
  `Lang`, and rely on the existing per-file `class="l en"` / `class="l ru"`
  equality check in `scripts/check-dist.mjs`, which now covers 12 more
  documents.
- **Risk: the P6 release number moves.** `release: 0.1.5` for the approach-page
  entry is the release cut from PR 33 (published `2026-09-11T09:26:43Z`). If a
  further release lands before this cycle merges, the P6 entry stays 0.1.5 — it
  names the release that first contained the P6 merge commit, not the latest
  tag. Reviewer check, not an automatable one.
- **Risk: the footer check compares against a moving version.** The check reads
  `package.json` at build time and compares it to the built HTML, so it stays
  true after every release-please bump; it asserts agreement, never a literal.
