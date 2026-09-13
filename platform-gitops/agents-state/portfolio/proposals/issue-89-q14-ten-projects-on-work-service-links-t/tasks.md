# Tasks: issue-89-q14-ten-projects-on-work-service-links-t

- [ ] 1. Delete the eight content files of the four removed slugs:
  `src/content/projects/mctl-agent.en.md`, `mctl-agent.ru.md`,
  `mctl-pairdesk.en.md`, `mctl-pairdesk.ru.md`,
  `pfeifenpatenschaft-backend.en.md`, `pfeifenpatenschaft-backend.ru.md`,
  `mctl-openclaw.en.md`, `mctl-openclaw.ru.md` — DoD: `src/content/projects/`
  holds exactly twenty files, ten slugs, one `en` and one `ru` each.

- [ ] 2. Renumber `order` in the remaining twenty files (depends on 1), both
  language files of a slug carrying the same value, to exactly:

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

  (changes: `mctl-portal` 5 -> 4, `mctl-design` 6 -> 5, `mctl-telegram` 7 -> 6,
  `seerrsense` 8 -> 7, `mctl-academy` 9 -> 8, `mctl-loyalty` 10 -> 9,
  `pelican-libertex-social` 12 -> 10; `mctl-api`, `mctl-gitops` and
  `mctl-agents` keep 1, 2, 3.) No `group`, `repo`, `stack`, `name`, `summary`
  or body bullet changes here — DoD: `order` runs 1..10 once per language,
  five platform and five product entries per language, `astro sync` passes
  `checkProjectParity`.

- [ ] 3. Correct `src/content/projects/seerrsense.en.md` (depends on 2):
  replace its `summary` line with exactly

  ```
  summary: "Natural-language media requests for Seerr over MCP: the model interprets intent, provider IDs stay the source of truth."
  ```

  and append, as the last body bullet, exactly
  `- one upstream: Seerr, which is what drives Radarr and Sonarr` — DoD: the
  `summary` is one line, mentions neither Radarr nor Sonarr, and `stack`,
  `repo`, `group`, `name` and the three existing bullets are unchanged.

- [ ] 4. Correct `src/content/projects/seerrsense.ru.md` (depends on 2):
  replace its `summary` line with exactly

  ```
  summary: "Запросы медиа на естественном языке для Seerr через MCP: модель интерпретирует намерение, идентификаторы провайдеров остаются источником истины."
  ```

  and append, as the last body bullet, exactly
  `- один апстрим — Seerr, и уже он управляет Radarr и Sonarr` — DoD: as task
  3, for the Russian file.

- [ ] 5. Add a `links` array to both language files of six projects (depends on
  2), in the shape `src/content/projects/mctl-api.en.md` already uses
  (two-space indented list item, quoted `label`, bare `url`, no trailing
  slash), with exactly:

  | slug | `url` | EN label | RU label |
  |---|---|---|---|
  | `mctl-portal` | `https://app.mctl.ai` | `Portal` | `Портал` |
  | `mctl-design` | `https://ui.mctl.ai` | `Storybook` | `Storybook` |
  | `mctl-telegram` | `https://tg.mctl.ai` | `Service` | `Сервис` |
  | `seerrsense` | `https://seerrsense.mctl.ai` | `Service` | `Сервис` |
  | `mctl-academy` | `https://academy.mctl.ai` | `Service` | `Сервис` |
  | `mctl-loyalty` | `https://labs-mctl-loyalty.mctl.ai` | `Service` | `Сервис` |

  `Storybook` stays untranslated in both files. `mctl-api` keeps its existing
  `Docs` / `Документация` entry and gains nothing; `mctl-gitops` and
  `pelican-libertex-social` gain no `links` array; no existing `repo:` line is
  touched — DoD: `astro sync` passes `checkProjectParity` (identical
  `links[].url` across the two files of every slug) and exactly seven project
  slugs carry a `links:` line (the six above plus `mctl-api`).

- [ ] 6. Delete one chain item per language in `src/i18n/ui.ts`: exactly
  `Rehearsal host preview.dmitriimashkov.com shares the same certificate and stays until the apex has been observed`
  from `ui.colophonChainItems.en` and exactly
  `Репетиционный хост preview.dmitriimashkov.com делит тот же сертификат и остаётся, пока апекс не будет отнаблюдён`
  from `ui.colophonChainItems.ru`. Every other item in both arrays stays byte
  for byte as it is, including
  `Live at dmitriimashkov.com; www redirects to it with a 301` and
  `Работает на dmitriimashkov.com; www перенаправляется на него с кодом 301`.
  Do not touch `src/lib/chain.ts` or `CHAIN_LINKS` — DoD:
  `grep -rn "preview.dmitriimashkov.com" src/i18n/ui.ts` returns nothing, both
  arrays hold six items, `test/ui.test.ts` and `test/chain.test.ts` pass.

- [ ] 7. Add `test/support/expected-projects.ts` (depends on 2): a plain
  module, not a test file, exporting `EXPECTED_PROJECTS` — one
  `{ slug, group, order }` row per project, in the order of the table in task 2
  — and `EXPECTED_SLUGS` derived from it — DoD: the module is imported by two
  test files, is absent from the `npm test` file list in `package.json`, and
  running `npm test` executes no test from it.

- [ ] 8. Rework `test/projects.test.ts` (depends on 1, 2, 3, 4, 5, 7):
  import `EXPECTED_PROJECTS` / `EXPECTED_SLUGS` instead of the hand-typed
  fourteen-slug list; derive the file count (`EXPECTED_SLUGS.length * 2`, 28 ->
  20), the slug count (14 -> 10), the group counts (6 and 8 -> 5 and 5, from
  `EXPECTED_PROJECTS`) and the order range (1..14 -> 1..10, from
  `EXPECTED_PROJECTS`); add a direct per-file assertion that `order` and
  `group` match the row for that slug; delete `NO_REPO_SLUGS`, both
  `continue` guards it feeds, and the test
  `pfeifenpatenschaft-backend has no repo: line in either language file`;
  restate the two surviving assertions as "every project that declares a
  `repo:` matches `https://github.com/(mctlhq|mashkoffdmitry)/<slug>` and
  resolves through `repoKey` to a `src/data/metrics.json` per_repo key", with
  no per-slug exception list — DoD: no hand-typed count remains that duplicates
  a derivable one, the file names none of the four removed slugs, and
  `node --test test/projects.test.ts` passes.

- [ ] 9. Add three assertions to `test/projects.test.ts` (depends on 8):
  (a) neither `seerrsense` file's `summary` matches `/radarr|sonarr/i` and both
  carry the exact strings from tasks 3 and 4 and the new bullet; (b) the six
  slugs of task 5 carry exactly the listed `url` and the listed EN and RU
  label, and `mctl-gitops` and `pelican-libertex-social` carry no `links:`
  line; (c) a walk of `src/` and `test/` finds no word-bounded occurrence of
  `mctl-agent`, `mctl-pairdesk`, `pfeifenpatenschaft-backend` or
  `mctl-openclaw`, excluding `src/data/metrics.json` — which the issue's
  out-of-scope list keeps as it is — with that single exclusion named in the
  test — DoD: the three assertions fail if any of those properties is broken,
  and the word boundary does not make the ten `mctl-agents` files a false
  positive.

- [ ] 10. Update `test/work.test.ts` (depends on 7): delete the test
  `T3: pfeifenpatenschaft-backend has neither repo: nor links:, and is marked private: true, in either language file`;
  derive T4's per-language count from `EXPECTED_SLUGS.length` (14 -> 10) so the
  list and the count cannot drift; leave the source-level T3 assertions on
  `hasLinks`, `project-metrics` and `en.data.private` in place — DoD: the file
  names none of the four removed slugs and `node --test test/work.test.ts`
  passes.

- [ ] 11. Add `test/project-card-private.test.ts` (depends on 1) and register
  it in the `test` script of `package.json`, modelled on
  `test/journal-build.test.ts`: a `makeProjectFixtureTree(cardSource?)` that
  copies the committed `src/`, replaces `src/content/projects/` with the four
  fixture slugs below (`en` and `ru` each, chips restricted to ones
  `chipIsKnown` already accepts, two slugs in `platform` and two in `product`
  so neither group heading renders empty), optionally overwrites
  `src/components/ProjectCard.astro`, copies `astro.config.mjs`,
  `package.json` and `tsconfig.json`, symlinks `node_modules` and `public`,
  and runs `node node_modules/astro/bin/astro.mjs build` via `spawnSync`
  (never `npm run build`, whose `prebuild` would recurse) — DoD: the helper
  builds a fixture tree successfully and the test asserts the build exited zero
  with its stderr included in the failure message.

- [ ] 12. Assert the honest card in that file (depends on 11) from a single
  `dist/work/index.html`, slicing each card out by its
  `<article class="project" id="<fixture-slug>">`:

  | fixture slug | `repo:` | `private:` | `links:` | asserted markup |
  |---|---|---|---|---|
  | `fixture-private-no-repo` | absent | `true` | absent | private chip present; no repository `<li>`; no metrics line |
  | `fixture-public-repo` | present | absent | one entry | repository `<li>` and service `<li>`, in that order; no private chip |
  | `fixture-no-repo-no-private` | absent | absent | absent | no private chip and no `project-links` list |
  | `fixture-private-with-repo` | present | `true` | absent | private chip and repository `<li>` together |

  — DoD: all four hold against the committed `ProjectCard.astro`, proving the
  private chip renders from the `private` field and that a card renders a
  repository link and a service link side by side.

- [ ] 13. Add the mutation control to the same file (depends on 12): a
  `mutantCard()` helper that reads the committed
  `src/components/ProjectCard.astro`, asserts the token `{en.data.private && (`
  occurs exactly once (failing loudly if the source has drifted), replaces it
  with `{!en.data.repo && (`, builds a second fixture tree with that card, and
  asserts the mutant output violates the two discriminating expectations —
  `fixture-no-repo-no-private` gains the private chip and
  `fixture-private-with-repo` loses it — DoD: the mutation evidence is
  re-derived on every run and lives in the test file; nothing about it is
  written into the pull request description.

- [ ] 14. Write this cycle's journal entry (depends on 1-13):
  `src/content/journal/2026-09-13-q14-ten-projects-and-service-links.md` with
  `service: portfolio`, `issue: https://github.com/mctlhq/portfolio/issues/89`,
  `proposal_slug: issue-89-q14-ten-projects-on-work-service-links-t`,
  `status: in_progress`, `visibility: public`, `indexing: noindex`, a
  `seoTitle` inside the length budget `src/lib/seo.ts` enforces, bilingual
  `title` and `decided`, a single-quoted `issue_opened_at`, and
  `interventions: []`. The previous cycle's entry
  (`2026-09-13-q13-link-hit-areas-titles-indexing-and-share-image-alt.md`) is
  already `status: complete`; complete it only if that is no longer true at
  implementation time — DoD: exactly one entry in the collection is
  `in_progress`, and `test/journal*.test.ts` and `test/colophon.test.ts` pass.

- [ ] 15. Run the full gate (depends on 1-14): `npm run vendor && npm test`,
  `npm run build`, `node scripts/check-dist.mjs`, `node scripts/check-links.mjs`
  — DoD: all four pass; the six new service addresses appear in
  `check-links.mjs`'s *skipped* list (it opens no socket by design) and nothing
  appears in its broken list.

## Tests

- [ ] T1. `test/projects.test.ts`: exactly twenty files, ten slugs, one `en`
  and one `ru` each, every count derived from `EXPECTED_PROJECTS` rather than
  hand-typed.
- [ ] T2. `test/projects.test.ts`: `order` is 1..10 once per language and each
  file's `order` and `group` match its `EXPECTED_PROJECTS` row; five platform
  and five product per language.
- [ ] T3. `test/projects.test.ts`: every project that declares a `repo:`
  matches `https://github.com/(mctlhq|mashkoffdmitry)/<slug>` and resolves
  through `repoKey` to a `src/data/metrics.json` per_repo key — no per-slug
  exception list.
- [ ] T4. `test/projects.test.ts`: both `seerrsense` files carry the exact
  `summary` strings from tasks 3 and 4 and the exact new bullet; neither
  `summary` matches `/radarr|sonarr/i`; each `summary` is a single line.
- [ ] T5. `test/projects.test.ts`: the six service links carry the exact `url`
  and the exact EN and RU label; `mctl-api` still carries `Docs` /
  `Документация` and nothing more; `mctl-gitops` and
  `pelican-libertex-social` carry no `links:` line.
- [ ] T6. `test/projects.test.ts`: no word-bounded occurrence of the four
  removed slugs anywhere under `src/` or `test/`, excluding
  `src/data/metrics.json`, that exclusion named in the test.
- [ ] T7. `test/work.test.ts`: ten distinct project names per language, the
  count derived from `EXPECTED_SLUGS.length`; the source-level assertions that
  `ProjectCard.astro` gates the private chip on `en.data.private` still hold.
- [ ] T8. `test/project-card-private.test.ts`: over a built fixture tree, a
  `private: true` entry with no `repo:` renders the private chip and no
  repository link; a `private`-less entry with a `repo:` renders the link and
  no chip.
- [ ] T9. `test/project-card-private.test.ts`: the same build proves the two
  discriminating cases — an entry with neither `repo:` nor `private:` renders
  no chip, and an entry with both renders the chip alongside the repository
  link.
- [ ] T10. `test/project-card-private.test.ts` (mutation control): a card
  mutated from `{en.data.private && (` to `{!en.data.repo && (` fails T9's two
  cases; the helper fails loudly if the token is not found exactly once.
- [ ] T11. `test/project-card-private.test.ts`: a fixture carrying both a
  `repo:` and a `links` entry renders two `<li>` in `project-links`, the
  repository first — the rendering half of criterion 7.
- [ ] T12. `test/ui.test.ts` (existing, unchanged): both
  `colophonChainItems` arrays are non-empty, all-string and equal in length,
  now at six items each.
- [ ] T13. `test/chain.test.ts` (existing, unchanged): the two linkified
  identifiers still resolve; the removed item carried neither.
- [ ] T14. `npm run build` then `node scripts/check-dist.mjs` and
  `node scripts/check-links.mjs`: `/work/` emits ten cards in both languages,
  `class="l en"` / `class="l ru"` parity holds on every page, and no internal
  link is broken.

Reviewer step, not a test: open `/work/` at 390px and at 1440px in both
languages and confirm the two group headings still read correctly with five
entries each.

## Rollback

Every change is content, dictionary text and tests in one repository, released
through release-please, so rollback is ordinary:

1. Before release — revert the merge commit of the implementation PR on `main`.
   The eight deleted content files, the two chain items, the six `links`
   arrays, the two `seerrsense` summaries and the test rework all come back
   together; no state outside git changes, because nothing here touches
   `src/data/metrics.json`, DNS, certificates or gitops values.
2. After release — `mctl_rollback_service` to the previously deployed image tag
   for the `portfolio` service, then revert on `main` and let the next release
   carry the reverted content. No data migration is involved and no URL is
   created or destroyed beyond the four in-page anchors on `/work/`.
3. Partial rollback is safe and independent: the chain-item deletion
   (`src/i18n/ui.ts`), the `seerrsense` correction, the six service links and
   the removal/renumbering can each be reverted on their own, as long as
   `test/support/expected-projects.ts` and the counts derived from it are
   reverted together with the content set they describe.
4. If only the fixture test proves unstable, it can be reverted on its own,
   but the `pfeifenpatenschaft-backend`-keyed tests must not come back with it:
   their subject no longer exists. The correct fallback is to fix the fixture,
   not to restore a test keyed to a removed entry.
