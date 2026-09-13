# Q14: ten projects on /work/, service links, the seerrsense claim corrected, the rehearsal-host note dropped

## Context

`/work/` currently presents fourteen projects, drawn from twenty-eight files
in `src/content/projects/` (one `.en.md` and one `.ru.md` per slug). The owner
has decided that four of those entries do not belong on this site:
`mctl-agent` (one letter apart from `mctl-agents`, so the pair reads as a typo
rather than as two systems), `mctl-pairdesk`, `pfeifenpatenschaft-backend` and
`mctl-openclaw`. Ten entries remain, and their `order` values have to be
renumbered to run 1..10 contiguously per language, platform before product.

The same editorial pass found three further corrections. The `seerrsense`
summary claims the project serves "Seerr, Radarr and Sonarr", while the code
integrates only Seerr — measured against `mctlhq/seerrsense` at commit
`0efe127`: `src/providers/` holds exactly one directory, `seerr`; the only
upstream endpoints called are `/api/v1/auth/me`, `/api/v1/request` and
`/api/v1/status`; a case-insensitive grep for `radarr|sonarr` over the
TypeScript source returns nothing. The colophon's build-and-deploy chain
(`ui.colophonChainItems` in `src/i18n/ui.ts`) ends with a note about the
temporary rehearsal host `preview.dmitriimashkov.com` — true today, but a
migration state, not a standing decision, and it publishes an internal host
name that gives a reader nothing. And six of the remaining ten projects run a
public service that a reader can open, while `ProjectCard.astro`'s existing
optional `links` array is used by exactly one project, `mctl-api`.

Two of the four removals carry structure that outlives them.
`pfeifenpatenschaft-backend` is the only entry with `private: true` and no
`repo:`, so removing it would leave `ProjectCard.astro`'s private branch (line
68), the `workPrivateRepo` string, the schema's `private` field,
`NO_REPO_SLUGS` in `test/projects.test.ts` and three named assertions without
a subject. The capability is real and stays; its proof moves off production
content and onto a fixture — the same rule the repository learned in issue #83,
that a test keyed to one named entry breaks the moment that entry legitimately
changes. `mctl-openclaw` was the one entry whose rendered commit and release
counts came from an upstream project rather than the owner's work, disclaimed
only in body prose; removing it closes that gap, so no later cycle needs to
invent a `metrics_scope` field.

## User stories

- AS a reader of `/work/` I WANT ten distinct, contiguously ordered projects
  SO THAT the list reads as a curated body of work rather than as a dump
  containing a near-duplicate pair that looks like a typo.
- AS a reader of a project card I WANT a link to the running service beside
  the repository link SO THAT I can open and use the thing being described
  instead of only reading its source.
- AS a reader of the `seerrsense` card I WANT the summary to name only what
  the code integrates SO THAT the site does not overstate one integration as
  three.
- AS a reader of the colophon I WANT the build-and-deploy chain to list only
  standing decisions SO THAT the page does not state something false about
  itself the day a temporary host is decommissioned.
- AS the maintainer of this repository I WANT the private-repository
  capability proven by a fixture rather than by a named production project
  SO THAT removing or editing a project never silently removes the proof.
- AS the maintainer I WANT counts in the test suite derived from
  `EXPECTED_SLUGS` wherever they can be SO THAT a list and a count that must
  agree cannot drift apart again.

## Acceptance criteria (EARS)

### Removal and renumbering

- WHEN the change is complete THE SYSTEM SHALL hold exactly twenty files in
  `src/content/projects/`, covering ten slugs with one `en` and one `ru` file
  each, and none of `mctl-agent`, `mctl-pairdesk`,
  `pfeifenpatenschaft-backend` or `mctl-openclaw` SHALL appear anywhere under
  `src/`.
- WHEN the eight files `mctl-agent.en.md`, `mctl-agent.ru.md`,
  `mctl-pairdesk.en.md`, `mctl-pairdesk.ru.md`,
  `pfeifenpatenschaft-backend.en.md`, `pfeifenpatenschaft-backend.ru.md`,
  `mctl-openclaw.en.md` and `mctl-openclaw.ru.md` are deleted THE SYSTEM
  SHALL renumber the remaining twenty files so that `order` runs 1..10 once
  per language and matches exactly:

  | order | slug | group |
  |---|---|---|
  | 1 | `mctl-api` | platform |
  | 2 | `mctl-gitops` | platform |
  | 3 | `mctl-agents` | platform |
  | 4 | `mctl-portal` | platform |
  | 5 | `mctl-design` | platform |
  | 6 | `mctl-telegram` | product |
  | 7 | `seerrsense` | product |
  | 8 | `mctl-academy` | product |
  | 9 | `mctl-loyalty` | product |
  | 10 | `pelican-libertex-social` | product |

- WHILE the twenty files exist THE SYSTEM SHALL keep five `group: platform`
  and five `group: product` entries per language, platform ordered before
  product.
- WHILE both language files of a slug exist THE SYSTEM SHALL keep their
  `order`, `group`, `repo`, `stack` and `links[].url` identical, as
  `checkProjectParity` in `src/content.config.ts` already requires.
- WHEN the renumbering is applied THE SYSTEM SHALL change no `summary`, body
  bullet, stack chip or link anywhere except the `seerrsense` correction
  below and the six `links` additions below.
- WHEN `/work/` is built THE SYSTEM SHALL render ten project entries in that
  order in both languages, with no empty group heading and no gap in the list.

### The private-repository capability

- WHILE `pfeifenpatenschaft-backend` no longer exists THE SYSTEM SHALL still
  declare the `private` field in the projects schema
  (`src/content.config.ts`), still render the `{en.data.private && (...)}`
  branch in `src/components/ProjectCard.astro`, and still export
  `ui.workPrivateRepo` from `src/i18n/ui.ts`.
- WHEN the test suite runs THE SYSTEM SHALL prove, from a fixture rather than
  from any file in the committed `src/content/projects/` tree, that a
  `private: true` entry with no `repo:` renders the private chip and no
  repository link, and that an entry with a `repo:` and no `private` field
  renders the repository link and no private chip.
- IF `ProjectCard.astro`'s private branch is mutated to read `!en.data.repo`
  instead of `en.data.private` THEN THE SYSTEM SHALL fail that fixture test,
  and the mutation evidence SHALL live in the committed test file, never in
  the pull request description.
- WHEN `NO_REPO_SLUGS` in `test/projects.test.ts` loses its only member THE
  SYSTEM SHALL either leave it empty or restate the assertion it feeds as
  "every project that declares a `repo:` matches the repository pattern and
  resolves to a `metrics.json` key", with no per-slug exception list.

### Counts

- WHEN `test/projects.test.ts` and `test/work.test.ts` run THE SYSTEM SHALL
  encode the new set everywhere the old one was encoded: 28 files becomes 20,
  14 slugs becomes 10, 6 platform and 8 product become 5 and 5, the order
  range 1..14 becomes 1..10, and 14 distinct names per language becomes 10.
- WHERE a count can be derived from `EXPECTED_SLUGS` rather than typed twice
  THE SYSTEM SHALL derive it.
- WHEN the suite runs THE SYSTEM SHALL contain no test that names
  `pfeifenpatenschaft-backend`, `mctl-agent`, `mctl-pairdesk` or
  `mctl-openclaw`; `grep -rn` for those four slugs over `src/` and `test/`
  SHALL return nothing.

### The seerrsense correction

- WHEN `src/content/projects/seerrsense.en.md` is written THE SYSTEM SHALL
  carry exactly this `summary` line:

```
summary: "Natural-language media requests for Seerr over MCP: the model interprets intent, provider IDs stay the source of truth."
```

- WHEN `src/content/projects/seerrsense.ru.md` is written THE SYSTEM SHALL
  carry exactly this `summary` line:

```
summary: "Запросы медиа на естественном языке для Seerr через MCP: модель интерпретирует намерение, идентификаторы провайдеров остаются источником истины."
```

- WHEN each `seerrsense` file is written THE SYSTEM SHALL append exactly one
  body bullet, as the last bullet, character for character — English:

```
- one upstream: Seerr, which is what drives Radarr and Sonarr
```

  and Russian:

```
- один апстрим — Seerr, и уже он управляет Radarr и Sonarr
```

- WHILE the correction is applied THE SYSTEM SHALL change nothing else in
  either `seerrsense` file: `stack`, `repo`, `group`, the other bullets and
  the `order` value of 7 from the table above stay as they are.
- WHEN the schema validates the two files THE SYSTEM SHALL keep `summary` a
  single line, and neither `summary` SHALL mention Radarr or Sonarr.

### The chain list

- WHEN `src/i18n/ui.ts` is edited THE SYSTEM SHALL delete exactly one item
  from `ui.colophonChainItems.en`:

```
Rehearsal host preview.dmitriimashkov.com shares the same certificate and stays until the apex has been observed
```

  and exactly one item from `ui.colophonChainItems.ru`:

```
Репетиционный хост preview.dmitriimashkov.com делит тот же сертификат и остаётся, пока апекс не будет отнаблюдён
```

- WHILE the two arrays are edited THE SYSTEM SHALL leave every other item
  exactly as it is, including `Live at dmitriimashkov.com; www redirects to
  it with a 301` and `Работает на dmitriimashkov.com; www перенаправляется на
  него с кодом 301`, and SHALL keep the two arrays equal in length, as
  `test/ui.test.ts` requires.
- WHEN the edit is complete THE SYSTEM SHALL make `grep -rn
  "preview.dmitriimashkov.com" src/i18n/ui.ts` return nothing, while the
  journal entry for the cutover keeps its own mentions of the rehearsal host:
  it is a dated record of what happened and is not being rewritten.
- WHILE the chain item is removed THE SYSTEM SHALL leave `src/lib/chain.ts`
  and `CHAIN_LINKS` untouched: the removed item carries no linkified
  identifier.

### Service links

- WHEN the six projects below are edited THE SYSTEM SHALL add a `links` array
  to both language files of each, with exactly these addresses and labels:

  | slug | `url` | EN label | RU label |
  |---|---|---|---|
  | `mctl-portal` | `https://app.mctl.ai` | `Portal` | `Портал` |
  | `mctl-design` | `https://ui.mctl.ai` | `Storybook` | `Storybook` |
  | `mctl-telegram` | `https://tg.mctl.ai` | `Service` | `Сервис` |
  | `seerrsense` | `https://seerrsense.mctl.ai` | `Service` | `Сервис` |
  | `mctl-academy` | `https://academy.mctl.ai` | `Service` | `Сервис` |
  | `mctl-loyalty` | `https://labs-mctl-loyalty.mctl.ai` | `Service` | `Сервис` |

- WHILE a slug carries a `links` array THE SYSTEM SHALL keep `url` identical
  between its `en` and `ru` file, as `checkProjectParity` requires, translate
  only the label exactly as `mctl-api` already does with `Docs` and
  `Документация`, and write no trailing slash, matching the existing
  `https://docs.mctl.ai` entry.
- WHILE `Storybook` is the label for `mctl-design` THE SYSTEM SHALL leave it
  untranslated in both files: it is a product name, and `AGENTS.md` keeps
  proper nouns, hostnames and identifiers out of translation.
- WHILE the six additions are made THE SYSTEM SHALL leave `mctl-api`'s
  existing `Docs` / `Документация` entry unchanged and add nothing to it, and
  SHALL give `mctl-gitops` and `pelican-libertex-social` no `links` array.
- WHEN a card with both a `repo:` and a `links` entry renders THE SYSTEM
  SHALL show the repository link and the service link side by side: the
  service link is an addition beside the repository link, never a
  replacement.

### Build and journal

- WHEN the implementation is complete THE SYSTEM SHALL pass `npm run vendor
  && npm test`, `npm run build`, `node scripts/check-dist.mjs` and `node
  scripts/check-links.mjs`.
- WHEN this cycle starts THE SYSTEM SHALL write its own journal entry under
  `src/content/journal/` with `status: in_progress`, and SHALL complete the
  previous cycle's entry if the closure workflow has not already done so.

### Reviewer step (not an acceptance criterion)

- Look at `/work/` in a browser at 390px and at 1440px, in both languages,
  and confirm the two group headings still read correctly with five entries
  each.

## Out of scope

- Any change to the copy, stack chips or body bullets of the nine remaining
  projects other than `seerrsense`, any `links` change beyond the six
  additions listed above, and any change to `seerrsense` beyond the two
  summary lines and the one bullet.
- Decommissioning `preview.dmitriimashkov.com` itself, or any DNS,
  certificate or custom-domain change. Those are the release owner's actions
  through the mctl and Cloudflare MCP tools.
- Featured case studies, per-project pages, the archive layout, or any other
  restructuring of `/work/`. That is a separate cycle and needs owner data
  this one does not.
- Adding a `metrics_scope` field. The only entry that needed it is being
  removed.
- Removing the `private` capability itself.
- `src/data/metrics.json`. It is a snapshot of twenty-four repositories and
  is not a list of what the site shows; leaving keys for removed projects in
  it is correct, and regenerating it is a separate, dated action.
- No change to `src/pages/work.astro`, `src/components/ProjectCard.astro` or
  `src/content.config.ts` is expected; if one proves necessary, it is the
  minimum that keeps the private capability working.

## Open questions

- The fixture test must be registered somewhere `npm test` invokes it.
  `package.json`'s `test` script lists every test file explicitly, so a new
  file such as `test/project-card-private.test.ts` has to be added to that
  list; adding it to an already-listed file (`test/work.test.ts`) is the
  alternative. Proceeding with a new file plus the one-line `package.json`
  registration, because the fixture test spawns an Astro build and is slower
  and structurally different from the source-text assertions in
  `test/work.test.ts`. Either satisfies the criteria as long as `npm test`
  actually runs it.
- The issue permits the fixture to be built "in memory (or in a fixture
  directory, matching whatever `test/journal-build.test.ts` does for its
  content trees)". Proceeding with the `test/journal-build.test.ts` approach —
  a temporary tree copied from `src/`, with `src/content/projects` replaced —
  because it exercises the real schema, the real loader and the real rendered
  markup, which an in-memory assertion over the `.astro` source text cannot do
  and which is what acceptance criterion 4 asks to be proven.
- `scripts/snapshot-metrics.mjs` mentions `mctl-openclaw` in explanatory
  comments about forks. Acceptance criterion 5 scopes the grep to `src/` and
  `test/` only, and `src/data/metrics.json` is explicitly out of scope, so
  those comments stay. Proceeding on that reading.
