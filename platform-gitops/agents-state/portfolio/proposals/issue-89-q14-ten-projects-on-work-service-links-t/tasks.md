# Tasks: issue-89-q14-ten-projects-on-work-service-links-t

- [ ] 1. Delete the eight content files for the four removed slugs:
      `src/content/projects/mctl-agent.en.md`,
      `src/content/projects/mctl-agent.ru.md`,
      `src/content/projects/mctl-pairdesk.en.md`,
      `src/content/projects/mctl-pairdesk.ru.md`,
      `src/content/projects/pfeifenpatenschaft-backend.en.md`,
      `src/content/projects/pfeifenpatenschaft-backend.ru.md`,
      `src/content/projects/mctl-openclaw.en.md`,
      `src/content/projects/mctl-openclaw.ru.md` — DoD:
      `src/content/projects/` holds exactly twenty `.md` files, ten slugs with
      one `en` and one `ru` each.

- [ ] 2. Renumber the `order:` line of the remaining twenty files (depends on
      1) so both language files of a slug carry the same value and the result
      is exactly:

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

      DoD: `order` runs 1..10 once per language, five `group: platform` and
      five `group: product` per language, relative order inside each group
      unchanged from today, platform before product. Nothing else in these
      files is edited by this task.

- [ ] 3. Correct `src/content/projects/seerrsense.en.md` (depends on 2).
      Replace its `summary` line with exactly:

      ```
      summary: "Natural-language media requests for Seerr over MCP: the model interprets intent, provider IDs stay the source of truth."
      ```

      and append, as the last body bullet, exactly:

      ```
      - one upstream: Seerr, which is what drives Radarr and Sonarr
      ```

      DoD: the file's `stack`, `repo`, `group`, `slug`, `lang`, `name`, the
      three existing bullets and the `order: 7` set in task 2 are unchanged;
      `summary` is a single line; the `summary` mentions neither Radarr nor
      Sonarr.

- [ ] 4. Correct `src/content/projects/seerrsense.ru.md` (depends on 2).
      Replace its `summary` line with exactly:

      ```
      summary: "Запросы медиа на естественном языке для Seerr через MCP: модель интерпретирует намерение, идентификаторы провайдеров остаются источником истины."
      ```

      and append, as the last body bullet, exactly:

      ```
      - один апстрим — Seerr, и уже он управляет Radarr и Sonarr
      ```

      DoD: as task 3, for the Russian file; `order: 7`; `summary` is a single
      line and mentions neither Radarr nor Sonarr.

- [ ] 5. Add a `links` array to both language files of six projects (depends
      on 2), after the `summary:` line, in the shape `mctl-api` already uses
      (`- label: "..."` then `url: ...`), with exactly these values:

      | slug | `url` | EN label | RU label |
      |---|---|---|---|
      | `mctl-portal` | `https://app.mctl.ai` | `Portal` | `Портал` |
      | `mctl-design` | `https://ui.mctl.ai` | `Storybook` | `Storybook` |
      | `mctl-telegram` | `https://tg.mctl.ai` | `Service` | `Сервис` |
      | `seerrsense` | `https://seerrsense.mctl.ai` | `Service` | `Сервис` |
      | `mctl-academy` | `https://academy.mctl.ai` | `Service` | `Сервис` |
      | `mctl-loyalty` | `https://labs-mctl-loyalty.mctl.ai` | `Service` | `Сервис` |

      DoD: each of the twelve files carries one `links` entry; `url` is
      byte-identical between the `en` and `ru` file of a slug; no trailing
      slash on any `url`; `Storybook` is untranslated in both `mctl-design`
      files; `mctl-api` still carries exactly its existing `Docs` /
      `Документация` entry and nothing more; `mctl-gitops` and
      `pelican-libertex-social` carry no `links` array; `astro sync` passes,
      so `checkProjectParity` accepts the ordered `links[].url` lists.

- [ ] 6. Remove the rehearsal-host item from both `colophonChainItems` arrays
      in `src/i18n/ui.ts`. Delete exactly this string from `.en`:

      ```
      Rehearsal host preview.dmitriimashkov.com shares the same certificate and stays until the apex has been observed
      ```

      and exactly this string from `.ru`:

      ```
      Репетиционный хост preview.dmitriimashkov.com делит тот же сертификат и остаётся, пока апекс не будет отнаблюдён
      ```

      DoD: both arrays are one item shorter and equal in length (six each);
      every other item is byte-identical to before, including `Live at
      dmitriimashkov.com; www redirects to it with a 301` and `Работает на
      dmitriimashkov.com; www перенаправляется на него с кодом 301`;
      `grep -rn "preview.dmitriimashkov.com" src/i18n/ui.ts` returns nothing;
      `src/lib/chain.ts` and `CHAIN_LINKS` are untouched;
      `src/content/journal/2026-09-11-production-cutover.md` keeps its own
      mentions of the rehearsal host and is not edited.

- [ ] 7. Write `test/project-card-private.test.ts` (depends on 1) — the
      fixture proof of the private-repository capability, modelled on
      `test/journal-build.test.ts`'s `makeFixtureTree` / `runAstro` /
      `cleanup`: copy the committed `src/` into an `mkdtemp` tree, replace
      `src/content/projects` with the fixture set, copy `astro.config.mjs`,
      `package.json` and `tsconfig.json`, symlink `node_modules` and
      `public`, spawn `node_modules/astro/bin/astro.mjs build`, read
      `dist/work/index.html`. Fixture set, each as an `en` and a `ru` file so
      `checkProjectParity` passes, using stack chips already known to
      `stackChipRu` / `stackChipUntranslated`:

      | fixture slug | `repo:` | `private:` | expected markup |
      |---|---|---|---|
      | `fixture-private` | absent | `true` | private chip, no repository link |
      | `fixture-public` | present | absent | repository link, no private chip |
      | `fixture-neither` | absent | absent | neither chip nor repository link |
      | `fixture-both` | present | `true` | repository link and private chip |

      DoD: the test asserts all four rows against the rendered HTML; it reads
      no file from the committed `src/content/projects/`; it names none of the
      four removed slugs; the temporary tree is removed in a `finally`.

- [ ] 8. Add the mutation case to `test/project-card-private.test.ts`
      (depends on 7): build a second fixture tree in which the copied (never
      the committed) `src/components/ProjectCard.astro` has
      `{en.data.private && (` textually replaced by `{!en.data.repo && (`,
      run the same build, and assert the mutant's `dist/work/index.html`
      violates at least one assertion the unmutated build satisfies —
      concretely, that `fixture-neither` gains a private chip or
      `fixture-both` loses one. DoD: the mutation string, why those two
      fixture rows are the discriminators, and the expected kill are written
      as comments in the test file; the test fails if the mutation is ever
      made to the real component; no evidence of any kind is placed in the
      pull request description.

- [ ] 9. Register the new test file in `package.json` (depends on 7) by
      adding `test/project-card-private.test.ts` to the `node --test` file
      list of the `test` script. DoD: `npm test` runs the new file; its name
      appears in the run output.

- [ ] 10. Update `test/projects.test.ts` (depends on 1, 2). DoD:
      `EXPECTED_SLUGS` is the ten survivors in the order of the task 2 table;
      `NO_REPO_SLUGS` is empty or removed entirely, with the two assertions it
      gated restated as "every project that declares a `repo:` matches the
      repository pattern and resolves to a `metrics.json` key" and no
      per-slug exception list; the file count and slug count derive from
      `EXPECTED_SLUGS.length` rather than the literals 28 and 14; the order
      range derives from `EXPECTED_SLUGS.length` rather than the literal 14;
      the group counts are 5 and 5 and their sum is asserted against
      `EXPECTED_SLUGS.length`; the `pfeifenpatenschaft-backend has no repo:`
      test is deleted; the file names none of the four removed slugs.

- [ ] 11. Update `test/work.test.ts` (depends on 1, 2). DoD: the T3 case that
      reads `pfeifenpatenschaft-backend.{en,ru}.md` is deleted; T3's
      source-text assertions on `hasLinks`, the `en.data.repo` metrics gate
      and the `{en.data.private && (` branch remain unchanged; T4's fourteen
      becomes ten, read from the directory listing where practical rather
      than typed twice; the file names none of the four removed slugs.

- [ ] 12. Write this cycle's journal entry under `src/content/journal/`
      (depends on 1-11) with `service: portfolio`, `issue:
      https://github.com/mctlhq/portfolio/issues/89`, `proposal_slug:
      issue-89-q14-ten-projects-on-work-service-links-t`, `status:
      in_progress`, `visibility: public`, bilingual `title` and `decided`,
      and `issue_opened_at`. Verify the previous cycle's entry,
      `src/content/journal/2026-09-13-q13-link-hit-areas-titles-indexing-and-share-image-alt.md`,
      is already `status: complete` with `pr`, `release`, `merged_at` and
      `released_at` recorded; complete it only if the closure workflow has not
      already done so. DoD: exactly one entry in the collection is
      `in_progress`, as `docs/journal.md` and the journal loader require; the
      new entry carries no release, release time or deployment time; an
      explicit `seoTitle` is present if the English `title` exceeds 65
      characters, so `test/title.test.ts` passes.

- [ ] 13. Run the full gate (depends on all of the above): `npm run vendor &&
      npm test`, `npm run build`, `node scripts/check-dist.mjs`, `node
      scripts/check-links.mjs`, and `grep -rn` over `src/` and `test/` for
      `mctl-agent`, `mctl-pairdesk`, `pfeifenpatenschaft-backend` and
      `mctl-openclaw`. DoD: all four commands exit 0; the grep returns
      nothing for all four slugs; `src/pages/work.astro`,
      `src/components/ProjectCard.astro` and `src/content.config.ts` are
      unchanged in the diff, or, if one proved necessary, the change is the
      minimum that keeps the private capability working and is called out in
      the commit message.

## Tests

- [ ] T1. `test/projects.test.ts`: exactly twenty files, ten distinct slugs,
      one `en` and one `ru` per slug, derived from `EXPECTED_SLUGS.length`.
- [ ] T2. `test/projects.test.ts`: `order` values are 1..10 once per
      language, and the ten `(slug, order, group)` triples match the task 2
      table.
- [ ] T3. `test/projects.test.ts`: five `platform` and five `product` entries
      per language, summing to `EXPECTED_SLUGS.length`.
- [ ] T4. `test/projects.test.ts`: every project that declares a `repo:`
      matches `https://github.com/(mctlhq|mashkoffdmitry)/<slug>` and resolves
      through `repoKey` to a `per_repo` key in `src/data/metrics.json`, with
      no per-slug exception list.
- [ ] T5. `test/project-card-private.test.ts`: a `private: true` fixture with
      no `repo:` renders the private chip and no repository link; a fixture
      with a `repo:` and no `private` renders the repository link and no chip.
- [ ] T6. `test/project-card-private.test.ts`: a fixture with neither `repo:`
      nor `private:` renders neither the chip nor a repository link, and a
      fixture with both renders both — the two discriminators the `!repo`
      mutation cannot satisfy.
- [ ] T7. `test/project-card-private.test.ts`: the mutation case — a build of
      a tree whose copied `ProjectCard.astro` reads `!en.data.repo` instead of
      `en.data.private` fails at least one of T5/T6's assertions.
- [ ] T8. `test/work.test.ts`: ten distinct project names per language.
- [ ] T9. `test/ui.test.ts` (existing, must stay green): both
      `colophonChainItems` arrays are non-empty and of equal length after the
      deletion.
- [ ] T10. `test/chain.test.ts` (existing, must stay green): every chain item
      still round-trips through `chainSegments` byte-identically and the two
      `CHAIN_LINKS` identifiers are still found in the items that carry them.
- [ ] T11. Content-level check that neither `seerrsense` file's `summary`
      matches `/radarr|sonarr/i`, that each carries the exact string from task
      3 / task 4, and that each body ends with the exact new bullet. Add it to
      `test/projects.test.ts` if it is not already implied by T1-T4.
- [ ] T12. `npm run build` followed by `node scripts/check-dist.mjs` and
      `node scripts/check-links.mjs`: `/work/` renders ten cards in the task 2
      order in both languages, the six service links appear beside the
      repository links, and the six new off-origin hrefs are reported as
      skipped rather than broken.

## Rollback

Every change in this cycle is a file edit in a single pull request; there is
no migration, no persisted state and no infrastructure action. Reverting the
merge commit restores the eight deleted content files, the fourteen-entry
ordering, the two `seerrsense` summaries, the rehearsal-host chain items and
the old test counts in one step, and deletes the new test file and its
`package.json` registration with them.

If only part of the change proves wrong, the pieces are independent and can be
reverted one at a time: the six `links` additions (task 5) touch twelve files
and nothing else; the chain-item deletion (task 6) touches `src/i18n/ui.ts`
alone; the `seerrsense` correction (tasks 3-4) touches two files. The
removal-and-renumbering (tasks 1-2) is the only change with a dependent
blast radius — reverting it requires reverting the test updates in tasks 10
and 11 as well, or those tests fail against the restored fourteen-entry set.

No release, deployment or DNS action is part of this cycle, so no rollback
through `mctl_rollback_service` is implied. If the change has already been
released and deployed when a defect is found, the release owner rolls the
service back to the previous image tag through `mctl_rollback_service` while
the revert pull request goes through the normal gates; that is an
infrastructure action for the owner, not part of the implementer's work.
