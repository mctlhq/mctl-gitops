# Design: issue-89-q14-ten-projects-on-work-service-links-t

## Current state

### The content collection

`src/content/projects/` holds twenty-eight Markdown files, one `.en.md` and
one `.ru.md` per slug, fourteen slugs in total. Today's `order` and `group`
values, read from the `.en.md` files:

| order | slug | group |
|---|---|---|
| 1 | `mctl-api` | platform |
| 2 | `mctl-gitops` | platform |
| 3 | `mctl-agents` | platform |
| 4 | `mctl-agent` | platform |
| 5 | `mctl-portal` | platform |
| 6 | `mctl-design` | platform |
| 7 | `mctl-telegram` | product |
| 8 | `seerrsense` | product |
| 9 | `mctl-academy` | product |
| 10 | `mctl-loyalty` | product |
| 11 | `mctl-pairdesk` | product |
| 12 | `pelican-libertex-social` | product |
| 13 | `pfeifenpatenschaft-backend` | product |
| 14 | `mctl-openclaw` | product |

`src/content.config.ts` defines `projectsSchema` (lines 35-46) as a
`z.strictObject` with `slug`, `lang`, `name`, `group` (`platform | product`),
`order` (non-negative integer), optional `repo` (a `https://github.com/...`
regex), optional `private` (boolean), `stack` (non-empty array), `summary`
(one line — `.refine((s) => !s.includes('\n'))`) and optional
`links: z.array(z.strictObject({ label, url: httpsUrl })).optional()`.

`checkProjectParity` (lines 57-92) runs from `projectsLoader()` after the
glob loader has synced every file. It requires exactly one `en` and one `ru`
entry per slug, and equality of `group`, `order`, `repo`, `private`, `stack`
and the ordered list of `links[].url`. `name`, `summary` and `links[].label`
are explicitly allowed to differ, which is what makes a translated label legal
and a differing `url` illegal. The loader runs on `astro sync`, `astro check`,
`astro dev` and `astro build` alike, so nothing bypasses it.

### The card

`src/components/ProjectCard.astro` takes the `en` and `ru` entry of one slug.
Line 18 derives `repoLabel` from `en.data.repo`; lines 19-20 read
`en.data.links ?? []` and `ru.data.links ?? []`; line 24 computes
`hasLinks = Boolean(en.data.repo) || links.length > 0`. The template renders
`<ul class="project-links">` when `hasLinks` (lines 46-59): first the
repository `<li>` when `en.data.repo` is set, then one `<li>` per entry of
`links`, pairing `link.label` with `ruLinks[index]?.label ?? link.label`
through `<Lang>`. So a service link is an addition to the same list the
repository link already occupies — index-aligned across languages, which is
exactly what `checkProjectParity`'s ordered `links[].url` comparison protects.

Lines 60-67 render the metrics line only `{en.data.repo && ...}`, through
`repoMetrics(metrics, en.data.repo)` and `formatStat(...)`. Lines 68-72 render
the private chip from `{en.data.private && (...)}` with
`ui.workPrivateRepo.en` / `.ru` — an explicit field, deliberately not `!repo`.

`src/lib/metrics.ts`'s `repoMetrics` returns `EMPTY_REPO_METRIC` when the repo
key is absent from `metrics.json`, and `formatStat(null)` renders an em dash,
so a fixture project with an unknown repository renders without throwing.

`src/pages/work.astro` loads the collection, filters `lang === 'en'`, builds a
`Map` of the Russian entries by slug, and renders two `<section>`s — `platform`
then `product` — each sorted by `a.data.order - b.data.order`. There is no
per-project page and no per-project route, so deleting content files removes
no route and changes no sitemap entry.

### The tests that encode the current set

`test/projects.test.ts` holds `EXPECTED_SLUGS` (lines 11-26, all fourteen),
`NO_REPO_SLUGS = new Set(['pfeifenpatenschaft-backend'])` (line 28), and
hand-typed counts: 28 files and 14 slugs (lines 38-42), 6 platform and 8
product (lines 60-75), `order` 1..14 (lines 77-86). Three assertions name
`pfeifenpatenschaft-backend` directly: the "no repo: line" test (lines 88-93),
the repository-pattern test that skips it via `NO_REPO_SLUGS` (lines 95-107),
and the T6 metrics-key test that skips it the same way (lines 124-140).

`test/work.test.ts` asserts the card's structure from source text: T3 (lines
448-468) checks the `hasLinks` gate, the `en.data.repo` metrics gate, the
`{en.data.private && (` private branch — and then reads
`pfeifenpatenschaft-backend.en.md` / `.ru.md` off disk to assert `private:
true`, no `repo:`, no `links:`. T4 (lines 472-481) asserts fourteen distinct
project names per language.

`test/ui.test.ts` asserts that every `ui` entry has `en` and `ru` of the same
kind and, for arrays, of equal length — which is what makes deleting one item
from each `colophonChainItems` array mandatory rather than optional.
`test/chain.test.ts` reads `ui.colophonChainItems` and `CHAIN_LINKS` from
`src/lib/chain.ts`; `CHAIN_LINKS` linkifies only
`github.com/mctlhq/portfolio` and `ghcr.io/mctlhq/portfolio`, neither of which
appears in the rehearsal-host item, so `src/lib/chain.ts` needs no change.

`ui.colophonChainItems` lives at `src/i18n/ui.ts:203-222`; the rehearsal-host
items are lines 211 (en) and 220 (ru), the last element of each array. The
only other occurrences of `preview.dmitriimashkov.com` in the repository are
in `src/content/journal/2026-09-11-production-cutover.md` (lines 39 and 47),
a dated record that stays.

### The fixture pattern already in the repository

`test/journal-build.test.ts` builds isolated Astro trees:
`makeFixtureTree()` copies the committed `src/` into an `mkdtemp` directory,
deletes and recreates one content subdirectory with fixture files, copies
`astro.config.mjs`, `package.json` and `tsconfig.json`, symlinks
`node_modules` and `public`, and optionally overwrites
`src/content.config.ts`. `runAstro()` spawns
`node_modules/astro/bin/astro.mjs` directly (never `npm run build`, which
would recurse through `prebuild`). Schema and loader cases use `astro sync`;
the markup case uses `astro build` and reads `dist/.../index.html`. This is
the pattern the private-repo proof will reuse, pointed at
`src/content/projects` instead of `src/content/journal`.

`package.json`'s `test` script enumerates every test file passed to `node
--test`, so a new test file is invisible to `npm test` until it is added
there.

## Proposed solution

Five mechanical edits plus one new test file. Nothing in `work.astro`,
`ProjectCard.astro` or `content.config.ts` changes.

### 1. Delete eight files, renumber twenty

Delete `mctl-agent.{en,ru}.md`, `mctl-pairdesk.{en,ru}.md`,
`pfeifenpatenschaft-backend.{en,ru}.md` and `mctl-openclaw.{en,ru}.md` from
`src/content/projects/`. Then rewrite the `order:` line of the remaining
twenty files so both language files of a slug carry the same value:

| order | slug | group | today |
|---|---|---|---|
| 1 | `mctl-api` | platform | 1 |
| 2 | `mctl-gitops` | platform | 2 |
| 3 | `mctl-agents` | platform | 3 |
| 4 | `mctl-portal` | platform | 5 |
| 5 | `mctl-design` | platform | 6 |
| 6 | `mctl-telegram` | product | 7 |
| 7 | `seerrsense` | product | 8 |
| 8 | `mctl-academy` | product | 9 |
| 9 | `mctl-loyalty` | product | 10 |
| 10 | `pelican-libertex-social` | product | 12 |

Relative order inside each group is preserved and platform stays before
product, so the visible ordering of the survivors does not change — only the
gaps close. Because `work.astro` sorts within a group and never reads the
global range, the renumbering is cosmetic at render time and load-bearing only
for `test/projects.test.ts`'s 1..10 assertion; doing it keeps `order` a dense
sequence rather than a set with holes, which is what the acceptance criterion
asks for.

### 2. Correct `seerrsense`

Replace the `summary` line of `src/content/projects/seerrsense.en.md` with
exactly:

```
summary: "Natural-language media requests for Seerr over MCP: the model interprets intent, provider IDs stay the source of truth."
```

and the `summary` line of `src/content/projects/seerrsense.ru.md` with exactly:

```
summary: "Запросы медиа на естественном языке для Seerr через MCP: модель интерпретирует намерение, идентификаторы провайдеров остаются источником истины."
```

Append one body bullet to each file, as the last bullet, exactly — English:

```
- one upstream: Seerr, which is what drives Radarr and Sonarr
```

Russian:

```
- один апстрим — Seerr, и уже он управляет Radarr и Sonarr
```

Today's bullets are `- OAuth for both Claude and ChatGPT`, `- per-user
connections`, `- directory submissions` (en) and `- OAuth для Claude и
ChatGPT`, `- подключения на пользователя`, `- заявки в каталоги` (ru); the new
bullet goes after those three and nothing else in either file changes. The
bullet keeps the context the removed words carried — Seerr drives Radarr and
Sonarr, SeerrSense drives Seerr — in the body, where it is a statement about
the upstream rather than a claim about this project's integrations, while the
`summary` (the line the card shows without expanding) names only Seerr.
`summary` stays a single line, as the schema's `.refine` requires.

### 3. Add six `links` arrays

Insert a `links:` block after the `summary:` line of both language files of
six slugs, in the shape `mctl-api` already uses:

| slug | `url` | EN label | RU label |
|---|---|---|---|
| `mctl-portal` | `https://app.mctl.ai` | `Portal` | `Портал` |
| `mctl-design` | `https://ui.mctl.ai` | `Storybook` | `Storybook` |
| `mctl-telegram` | `https://tg.mctl.ai` | `Service` | `Сервис` |
| `seerrsense` | `https://seerrsense.mctl.ai` | `Service` | `Сервис` |
| `mctl-academy` | `https://academy.mctl.ai` | `Service` | `Сервис` |
| `mctl-loyalty` | `https://labs-mctl-loyalty.mctl.ai` | `Service` | `Сервис` |

For example, `mctl-portal.en.md` gains

```
links:
  - label: "Portal"
    url: https://app.mctl.ai
```

and `mctl-portal.ru.md` gains the same block with `label: "Портал"`. No
trailing slash on any `url`, matching the existing `https://docs.mctl.ai`
entry. `Storybook` stays untranslated in both files: it is a product name, and
`AGENTS.md` keeps proper nouns, hostnames and identifiers out of translation.
`mctl-api` keeps its existing `Docs` / `Документация` entry unchanged and
gains nothing; `mctl-gitops` and `pelican-libertex-social` gain no `links`
array. The repository link each card already renders is untouched — the
service link is an addition beside it, not a replacement.

Two existing mechanisms make this safe without touching the card:
`checkProjectParity` compares the ordered `links[].url` lists of the two
files, so a typo in one language fails the build rather than rendering a
mismatched pair; and `ProjectCard.astro` pairs labels by index
(`ruLinks[index]?.label ?? link.label`), so one entry per file in the same
position is all the component needs. `scripts/check-links.mjs` classifies
off-origin hrefs as `skipped` and never fetches, so six new external links add
six skipped entries and no network dependency.

### 4. Drop the rehearsal-host chain item

Delete exactly one string from `ui.colophonChainItems.en` in `src/i18n/ui.ts`:

```
Rehearsal host preview.dmitriimashkov.com shares the same certificate and stays until the apex has been observed
```

and exactly one from `ui.colophonChainItems.ru`:

```
Репетиционный хост preview.dmitriimashkov.com делит тот же сертификат и остаётся, пока апекс не будет отнаблюдён
```

Both are the last element of their array. Every other item stays exactly as
it is, including `Live at dmitriimashkov.com; www redirects to it with a 301`
and `Работает на dmitriimashkov.com; www перенаправляется на него с кодом
301` — a 301 at the edge is a standing decision, not a transient one. The
arrays go from seven items to six each and stay equal in length, which is what
`test/ui.test.ts` enforces. `src/lib/chain.ts` and `CHAIN_LINKS` are
untouched. The journal entry
`src/content/journal/2026-09-11-production-cutover.md` keeps its own mentions
of the rehearsal host: it is a dated record of what happened.

### 5. Move the private-repo proof to a fixture

The capability stays whole: the `private` field in `projectsSchema`, the
`{en.data.private && (...)}` branch at `ProjectCard.astro:68-72`, and
`ui.workPrivateRepo`. What moves is its subject.

A new `test/project-card-private.test.ts` reuses
`test/journal-build.test.ts`'s tree-copying approach, replacing
`src/content/projects` instead of `src/content/journal`, then running
`node_modules/astro/bin/astro.mjs build` in the temporary tree and reading
`dist/work/index.html`. The fixture set is four slugs (each as an `en` and a
`ru` file, so `checkProjectParity` passes), using stack chips that already
exist in `stackChipRu`/`stackChipUntranslated` so `ProjectCard`'s chip guard
does not throw:

| fixture slug | `repo:` | `private:` | expected markup |
|---|---|---|---|
| `fixture-private` | absent | `true` | private chip, no repository link |
| `fixture-public` | present | absent | repository link, no private chip |
| `fixture-neither` | absent | absent | neither chip nor repository link |
| `fixture-both` | present | `true` | repository link **and** private chip |

The first two rows are the two directions the issue names. The last two are
the discriminators that give the mutation something real to fail on:

- Mutation `{!en.data.repo && (` in place of `{en.data.private && (`:
  `fixture-neither` would gain a private chip it must not have, and
  `fixture-both` would lose the chip it must have. Either assertion kills the
  mutant. Without those two rows the mutant survives, because
  `fixture-private` and `fixture-public` alone cannot distinguish `private`
  from `!repo`.

The mutation evidence is executed, not narrated: the test builds a second
fixture tree in which the copied (never the committed) `ProjectCard.astro` has
that one branch textually replaced, runs the same build, and asserts the
mutant's `dist/work/index.html` violates at least one of the assertions the
unmutated build satisfies. The mutation string, the reasoning above and the
expected kill are written as comments in the test file — per `AGENTS.md`, this
evidence goes into a committed file that `npm test` runs, never into a pull
request description the implementer cannot edit.

The new file is added to `package.json`'s `test` script so `npm test` invokes
it. The fixture tree never touches the real `src/`; it is created under
`mkdtemp` and removed in a `finally`.

### 6. Update the counts, drop the named assertions

In `test/projects.test.ts`:

- `EXPECTED_SLUGS` becomes the ten survivors, in the order of the table above.
- `NO_REPO_SLUGS` becomes empty — or, preferably, is deleted and the two
  assertions it gated are restated as "every project that declares a `repo:`
  matches the repository pattern and resolves to a `metrics.json` key", so
  there is no exception list to leave stale. A file-level `repo` presence
  check replaces the `continue`: a project without `repo:` is simply not
  subject to the pattern or metrics-key rules.
- The file-count assertion derives from `EXPECTED_SLUGS`:
  `EXPECTED_SLUGS.length * 2` for files and `EXPECTED_SLUGS.length` for
  distinct slugs, rather than the literals 28 and 14. The same for the order
  range: `Array.from({ length: EXPECTED_SLUGS.length }, (_, i) => i + 1)`.
- The group counts become 5 and 5; where possible they too are derived, by
  counting the `group` frontmatter values rather than typing both numbers.
  The two group counts must still sum to `EXPECTED_SLUGS.length`, which is
  the assertion worth keeping explicit.
- The `pfeifenpatenschaft-backend has no repo:` test is deleted; the private
  capability it half-covered is now covered by the fixture test.

In `test/work.test.ts`:

- T3's `pfeifenpatenschaft-backend` case (lines 461-468) is deleted. The three
  source-text assertions in T3 that check `hasLinks`, the metrics gate and the
  `{en.data.private && (` branch stay: they are assertions about the
  component, not about a project.
- T4's fourteen becomes ten, read from the directory listing rather than typed
  twice where practical.

This is the same defect class the repository has already paid for twice — a
list and a count both hand-typed, required to agree — so the direction of
travel is: one source of truth (`EXPECTED_SLUGS`, or the directory listing),
everything else derived.

### 7. The journal entry

This cycle writes `src/content/journal/2026-09-13-<slug>.md` with `status:
in_progress`, `service: portfolio`, the issue URL, `proposal_slug:
issue-89-q14-ten-projects-on-work-service-links-t`, `visibility: public`,
bilingual `title` and `decided`, and `issue_opened_at`. Per `docs/journal.md`,
an in-progress entry carries no release, release time or deployment time, and
at most one entry may be `in_progress` across the collection — the loader
enforces it. The previous cycle's entry,
`src/content/journal/2026-09-13-q13-link-hit-areas-titles-indexing-and-share-image-alt.md`,
is already `status: complete` with `pr`, `release: 0.1.24`, `merged_at` and
`released_at` recorded, so the closure workflow has already done its work and
nothing is owed there; the implementer verifies this rather than assuming it.
If the entry's English `title` exceeds 65 characters, it needs an explicit
`seoTitle`, as `test/title.test.ts` enforces through
`journalPageTitle`/`titleProblems`.

## Alternatives

**Keep `pfeifenpatenschaft-backend` purely to keep the private-repo test
green.** Rejected: it inverts the relationship between the site and its tests
— production content would exist to satisfy an assertion. It is also the exact
failure the repository already named in issue #83, where a test keyed to one
named entry broke the moment that entry legitimately changed. The fixture
costs one test file and removes the coupling permanently.

**Assert the private branch only from `ProjectCard.astro`'s source text, as
T3 already does, and add no fixture build.** Rejected: source-text matching
cannot distinguish "the branch exists" from "the branch renders the right
thing for the right input", and it cannot be killed by the `!repo` mutation —
a mutated file would simply fail a different regex, which proves the regex,
not the behaviour. Acceptance criterion 4 asks for rendered proof.

**Build the fixture entirely in memory by importing `ProjectCard.astro` and
rendering it with an Astro container API.** Rejected: nothing else in this
repository does it, the component's `await render(entry)` needs a real content
store, and `test/journal-build.test.ts` already established the tree-copy
pattern as the way this repository proves rendered markup. Reusing a pattern
the suite already carries beats introducing a second one.

**Replace the repository link with the service link on the six cards.**
Rejected by the issue and by the site's purpose: the repository is the
evidence, the service is the artifact, and a reader wants both. The card's
existing `project-links` list already renders them side by side with no layout
change needed.

**Remove the `private` field, branch and string along with the project.**
Rejected: explicitly out of scope, and it would have to be reinstated by the
next project without a public repository — exactly the churn the issue is
avoiding. It would also re-open the `!repo` conflation that T3 was written to
close.

## Platform impact

- **Migrations**: none. No database, no persisted state. The content
  collection is rebuilt from files on every build.
- **Routes and sitemap**: unchanged. `/work/` is a single page; there are no
  per-project routes, so `scripts/check-dist.mjs`'s expected route set is
  unaffected by the deletions. The new journal entry adds one route, which
  that script derives from the journal directory.
- **Backward compatibility**: four project cards disappear from `/work/`.
  Their anchors (`<article class="project" id={slug}>`) disappear with them,
  so any external deep link of the form `/work/#mctl-openclaw` degrades to the
  top of `/work/` — acceptable for a curated portfolio and explicitly the
  owner's decision.
- **`src/data/metrics.json`**: untouched, as required. It remains a snapshot
  of twenty-four repositories; keys for removed projects stay. Dropping the
  `NO_REPO_SLUGS` exception rather than restating it per-slug means the
  metrics-key assertion now reads "every declared repo resolves", which the
  remaining ten all do.
- **Risk: a `links[].url` mismatch between the two files of a slug.**
  Mitigated by `checkProjectParity`, which fails `astro sync` and therefore
  `npm run build` before anything renders.
- **Risk: the fixture build test is slow or flaky in CI.** It spawns an Astro
  build per tree, like `test/journal-build.test.ts` already does. Mitigated by
  keeping the fixture set to four slugs, symlinking `node_modules` and
  `public` rather than copying, and cleaning up in a `finally`. If the second
  (mutant) build proves too costly, the mutation can be applied to the same
  tree and rebuilt in place rather than in a fresh `mkdtemp`.
- **Risk: the chain arrays drift out of equal length.** Mitigated by
  `test/ui.test.ts`, which asserts equal length for every array-valued `ui`
  entry, and by `test/chain.test.ts`, which reads the arrays directly.
- **Risk: a stale reference to a removed slug survives somewhere under
  `src/`.** Mitigated by the acceptance criterion's `grep -rn` over `src/` and
  `test/` for all four slugs, which the implementer runs before opening the
  pull request.
- **Resource impact**: `/work/` gets smaller — four fewer cards, four fewer
  rendered bodies. Six additional external anchors add no requests at build
  time (`check-links.mjs` never fetches) and none at runtime.
