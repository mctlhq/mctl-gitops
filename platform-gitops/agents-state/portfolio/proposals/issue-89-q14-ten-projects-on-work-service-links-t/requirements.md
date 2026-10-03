# Q14: ten projects on /work/, service links, the corrected seerrsense claim, the rehearsal-host note dropped

## Context

`/work/` currently renders fourteen projects, two per slug (`<slug>.en.md` and
`<slug>.ru.md` under `src/content/projects/`). The owner has decided that four
of those fourteen entries do not belong there: `mctl-agent` (one letter apart
from `mctl-agents`, so the pair reads as a typo rather than as two systems),
`mctl-pairdesk`, `pfeifenpatenschaft-backend` and `mctl-openclaw`. Eight files
go and the remaining twenty are renumbered so `order` runs 1..10 once per
language. Two of the removed entries carry structure that outlives them:
`pfeifenpatenschaft-backend` is the only project with `private: true` and no
`repo:`, so the private-repo capability (`ProjectCard.astro`'s `private`
branch, the `private` field in the projects schema, `ui.workPrivateRepo`) loses
its only subject and its proof has to move onto a fixture; `mctl-openclaw` was
the one entry whose rendered commit and release counts came from an upstream
fork rather than from the owner's work, and removing it closes that gap.

The same pass found three more corrections. The `seerrsense` summary claims
"Seerr, Radarr and Sonarr" while the code (`mctlhq/seerrsense` at `0efe127`)
integrates only Seerr: one provider directory, three Seerr endpoints, no Radarr
or Sonarr client. The colophon's build-and-deploy chain
(`ui.colophonChainItems`) ends with a note about a temporary rehearsal host,
which describes a migration state rather than the standing chain and publishes
an internal host name. And six projects run a public service that a reader can
open, while their cards offer only a repository link — `ProjectCard.astro`
already renders an optional `links` array, and exactly one project
(`mctl-api`, linking `https://docs.mctl.ai`) uses it.

## User stories

- AS a reader of `/work/` I WANT ten distinct, contiguously ordered projects
  SO THAT the list reads as a curated body of work rather than as a dump
  containing a near-duplicate slug.
- AS a reader of a project card I WANT a link to the running service, beside
  the repository link SO THAT I can open the thing itself rather than only its
  source.
- AS a reader of `seerrsense` I WANT the summary to name only what the project
  integrates SO THAT the site does not overstate its scope.
- AS a reader of the colophon I WANT the build-and-deploy chain to describe the
  standing chain only SO THAT the page does not go stale — and start stating
  something false about the site — the day the rehearsal host is decommissioned.
- AS the next project without a public repository I WANT the private-repo
  capability to still exist and still be proven SO THAT my card renders
  correctly without anyone reinstating a removed entry.
- AS a maintainer I WANT counts in the tests derived from the expected project
  set rather than hand-typed twice SO THAT a list and a count cannot drift
  apart again.

## Acceptance criteria (EARS)

### Removal and renumbering

- WHEN the implementer removes the four slugs `mctl-agent`, `mctl-pairdesk`,
  `pfeifenpatenschaft-backend` and `mctl-openclaw` THE SYSTEM SHALL contain
  exactly twenty files under `src/content/projects/`, ten slugs, one `en` and
  one `ru` file each.
- WHEN `order` is renumbered THE SYSTEM SHALL produce exactly this table, once
  per language, preserving today's relative order within each group and keeping
  platform before product:

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

- WHILE both language files of a slug exist THE SYSTEM SHALL keep them
  identical on `order`, `group`, `repo`, `stack` and `links[].url`, as
  `checkProjectParity` in `src/content.config.ts` already requires.
- WHILE this change is in flight THE SYSTEM SHALL leave every summary, body
  bullet and stack chip unchanged except the `seerrsense` correction below.

### The private-repo capability

- WHILE `pfeifenpatenschaft-backend` no longer exists THE SYSTEM SHALL keep the
  `private` field in the projects schema (`src/content.config.ts`), the
  `private` branch in `src/components/ProjectCard.astro` and the
  `ui.workPrivateRepo` string in `src/i18n/ui.ts`.
- WHEN the private-repo tests run THE SYSTEM SHALL build a project entry from a
  fixture (in memory or in a fixture directory, matching whatever
  `test/journal-build.test.ts` does for its content trees) and assert that a
  `private: true` entry with no `repo:` renders the private chip and no
  repository link, and that a `private`-less entry with a `repo:` renders the
  link and no chip.
- IF `ProjectCard.astro` is mutated to read `!repo` instead of the `private`
  field THEN THE SYSTEM SHALL fail the fixture test, and the mutation evidence
  SHALL be recorded in the test file, never in the pull request description.
- WHEN `NO_REPO_SLUGS` in `test/projects.test.ts` loses its only member THE
  SYSTEM SHALL either carry an empty exception set or restate the assertion it
  feeds as "every project that declares a `repo:` matches the repository
  pattern and resolves to a `metrics.json` key", with no per-slug exception
  list.

### Counts

- WHEN the tests encode the project set THE SYSTEM SHALL update every count
  that encodes the old one: 28 files to 20, 14 slugs to 10, 6 platform and 8
  product to 5 and 5, order range 1..14 to 1..10, 14 distinct names per
  language to 10.
- IF a count can be derived from the expected slug set rather than typed twice
  THEN THE SYSTEM SHALL derive it.

### The seerrsense correction

- WHEN `src/content/projects/seerrsense.en.md` is corrected THE SYSTEM SHALL
  carry exactly this `summary` line:

```
summary: "Natural-language media requests for Seerr over MCP: the model interprets intent, provider IDs stay the source of truth."
```

- WHEN `src/content/projects/seerrsense.ru.md` is corrected THE SYSTEM SHALL
  carry exactly this `summary` line:

```
summary: "Запросы медиа на естественном языке для Seerr через MCP: модель интерпретирует намерение, идентификаторы провайдеров остаются источником истины."
```

- WHEN the body of each `seerrsense` file is corrected THE SYSTEM SHALL add one
  body bullet, as the last bullet, exactly — English
  `- one upstream: Seerr, which is what drives Radarr and Sonarr` and Russian
  `- один апстрим — Seerr, и уже он управляет Radarr и Sonarr`.
- WHILE the `seerrsense` files are edited THE SYSTEM SHALL change nothing else
  in either file: `stack`, `repo`, `group`, the other bullets and the `order`
  set by the table above stay as they are.

### The chain list

- WHEN `ui.colophonChainItems` is edited THE SYSTEM SHALL delete exactly one
  item from `ui.colophonChainItems.en` —
  `Rehearsal host preview.dmitriimashkov.com shares the same certificate and stays until the apex has been observed`
  — and exactly one from `ui.colophonChainItems.ru` —
  `Репетиционный хост preview.dmitriimashkov.com делит тот же сертификат и остаётся, пока апекс не будет отнаблюдён`.
- WHILE those two items are removed THE SYSTEM SHALL keep every other item in
  both arrays exactly as it is, including
  `Live at dmitriimashkov.com; www redirects to it with a 301` and
  `Работает на dmitriimashkov.com; www перенаправляется на него с кодом 301`,
  and SHALL keep the two arrays equal in length, as `test/ui.test.ts` requires.
- WHILE the chain item is removed THE SYSTEM SHALL leave `src/lib/chain.ts` and
  `CHAIN_LINKS` untouched: the removed item carries no linkified identifier.

### Service links

- WHEN the service links are added THE SYSTEM SHALL add a `links` array to both
  language files of six projects, with exactly these addresses and labels,
  `url` identical in the `en` and `ru` file of a slug as `checkProjectParity`
  requires, the label translated exactly as `mctl-api` already does with `Docs`
  and `Документация`, and no trailing slash, matching the existing
  `https://docs.mctl.ai` entry:

| slug | `url` | EN label | RU label |
|---|---|---|---|
| `mctl-portal` | `https://app.mctl.ai` | `Portal` | `Портал` |
| `mctl-design` | `https://ui.mctl.ai` | `Storybook` | `Storybook` |
| `mctl-telegram` | `https://tg.mctl.ai` | `Service` | `Сервис` |
| `seerrsense` | `https://seerrsense.mctl.ai` | `Service` | `Сервис` |
| `mctl-academy` | `https://academy.mctl.ai` | `Service` | `Сервис` |
| `mctl-loyalty` | `https://labs-mctl-loyalty.mctl.ai` | `Service` | `Сервис` |

- WHILE `mctl-design` is edited THE SYSTEM SHALL keep `Storybook` untranslated
  in both files: it is a product name, and `AGENTS.md` keeps proper nouns,
  hostnames and identifiers out of translation.
- WHILE service links are added THE SYSTEM SHALL keep `mctl-api`'s existing
  `Docs` / `Документация` entry unchanged and give it nothing further, and
  SHALL give `mctl-gitops` and `pelican-libertex-social` no `links` array.
- WHILE service links are added THE SYSTEM SHALL leave the repository link each
  card already renders untouched: the service link is an addition beside it,
  not a replacement.

### The issue's ten acceptance criteria, verbatim

1. `src/content/projects/` holds exactly twenty files, ten slugs, one `en` and one `ru` each, and none of the four removed slugs appears anywhere under `src/`.
2. `order` runs 1..10 once per language and matches the table in A.2 exactly, with five platform and five product entries per language.
3. `/work/` builds and renders ten project entries in that order, in both languages, with no empty group heading and no gap in the list.
4. The `private` field, the `ProjectCard` branch and `workPrivateRepo` still exist, and a fixture test proves the private chip renders from the `private` field and not from a missing `repo:`, with committed mutation evidence.
5. No test names `pfeifenpatenschaft-backend`, `mctl-agent`, `mctl-pairdesk` or `mctl-openclaw`; `grep -rn` for those four slugs over `src/` and `test/` returns nothing.
6. Neither `seerrsense` file mentions Radarr or Sonarr in its `summary`; both carry the exact strings from D.10 and D.11 and the bullet from D.12; `summary` stays a single line, as the schema requires.
7. Six projects carry a `links` entry with the exact address and the exact EN and RU label from F.17; `checkProjectParity` passes, so every `links[].url` matches across the two files of a slug; `/work/` renders both the repository link and the service link on those cards in both languages.
8. `grep -rn "preview.dmitriimashkov.com" src/i18n/ui.ts` returns nothing; both chain arrays are one item shorter and equal in length; the `www` 301 item is still present in both languages. The journal entry for the cutover keeps its own mentions of the rehearsal host: it is a dated record of what happened and is not being rewritten.
9. `npm run vendor && npm test`, `npm run build`, `node scripts/check-dist.mjs` and `node scripts/check-links.mjs` pass.
10. This cycle writes its own journal entry with `status: in_progress`, and completes the previous cycle's entry if the closure workflow has not already done so.

Reviewer step, not an acceptance criterion: look at `/work/` in a browser at 390px and at 1440px, in both languages, and confirm the two group headings still read correctly with five entries each.

## Out of scope

Verbatim from the issue:

- Any change to the copy, stack chips or body bullets of the nine remaining projects other than `seerrsense`, and any `links` change beyond the six additions in section F, and any change to `seerrsense` beyond the two summary lines and the one bullet in section D.
- Decommissioning `preview.dmitriimashkov.com` itself, or any DNS, certificate or custom-domain change. Those are the release owner's actions through the mctl and Cloudflare MCP tools.
- Featured case studies, per-project pages, the archive layout, or any other restructuring of `/work/`. That is a separate cycle and needs owner data this one does not.
- Adding a `metrics_scope` field. The only entry that needed it is being removed.
- Removing the `private` capability itself.
- `src/data/metrics.json`. It is a snapshot of twenty-four repositories and is not a list of what the site shows; leaving keys for removed projects in it is correct, and regenerating it is a separate, dated action.

## Open questions

- **Criterion 1/5 versus the `src/data/metrics.json` out-of-scope item.**
  `src/data/metrics.json` carries the per-repo keys `mctlhq/mctl-agent`,
  `mctlhq/mctl-pairdesk` and `mctlhq/mctl-openclaw`, and the issue explicitly
  says leaving them there is correct. A literal `grep -rn` over `src/` for those
  slugs therefore cannot return nothing. Proceeding with the only reading that
  satisfies both: the removed-slug search is word-bounded and excludes
  `src/data/metrics.json`, which is out of scope by the issue's own statement.
  The committed guard test states that exclusion in one place.
- **`mctl-agent` is a proper prefix of `mctl-agents`.** A plain substring grep
  for `mctl-agent` will always match the ten remaining `mctl-agents` files.
  Proceeding with a word-bounded search (`mctl-agent\b`), which does not match
  inside `mctl-agents`.
- **Where the shared expected-project table lives.** Criterion C.9 asks for
  counts to be derived rather than typed twice, and both `test/projects.test.ts`
  and `test/work.test.ts` need the same number. Proceeding with one small
  non-test support module under `test/` that both import, rather than
  duplicating the table or importing one test file from another (which would
  re-run its tests).
- **Journal `indexing` value for this cycle's entry.** The schema defaults to
  `index`; the three most recent entries are internal build notes carrying
  `indexing: noindex`. Proceeding with `noindex`, matching the preceding
  entries, since this is a content-curation record rather than a page that
  answers a search question.
- Nothing else. The issue supplies the full copy, the full order table, the full
  link table and the full acceptance and out-of-scope lists.
