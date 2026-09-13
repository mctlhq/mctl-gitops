# Q12: the journal test suite asserts invariants, not one cycle's checkpoint

## Context

Issue #79 gave the journal an explicit `status` enum (`in_progress` /
`complete` / `abandoned`), a loader guard for the one-cycle-at-a-time rule
(`checkJournalCollection` in `src/lib/journal.ts`, wired into `journalLoader()`
in `src/content.config.ts`), and a release-triggered closure workflow
(`.github/workflows/journal-closure.yml` + `scripts/close-journal.mjs`). Two
source-level tests that merged with it in pull request #80 froze the state of
the tree at that moment instead of stating the rule. In
`test/journal-status.test.ts` at `b2e46cc4`, line 288-291 asserts that the
number of `in_progress` journal entries is **exactly one**, and line 348-356
asserts that the single file
`src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md` has
`status: in_progress` and carries no `pr`, `release`, `merged_at`,
`released_at` or `deployed_at`.

The invariant the schema and the loader actually enforce is *at most one*, and
zero is valid (`docs/journal.md`: "At most one entry is `in_progress`,
including private entries; zero is valid"). Because the two tests assert more
than the invariant, the first real closure pull request the workflow opened
(#82, `fix(journal): close cycle 79`) turned the `test` job red by doing
exactly what it was built to do -- it set `status: complete`, `pr`,
`release: 0.1.21`, `merged_at` and `released_at` on that one entry, and CI
reported `actual: 0, expected: 1` and `actual: 'complete', expected:
'in_progress'`. Issue #79 acceptance criterion 4 had said in so many words
that the checkpoint numbers "SHALL NOT become permanent hard-coded assertions
that block future cycles". This cycle makes the suite assert invariants only,
closes cycle 79's entry with its verified evidence and its one recorded manual
intervention, and writes this cycle's own entry.

## User stories

- AS the release owner I WANT the journal test suite to assert only the rules
  the schema and loader enforce SO THAT merging a closure pull request, or
  starting a new cycle, never turns the suite red for having changed data the
  lifecycle allows to change.
- AS a reader of the public colophon I WANT cycle 79's entry to carry its
  verified pull request, release and timestamps and its one manual
  intervention SO THAT the published record of the cycle matches what actually
  happened.
- AS the next DevLoop cycle I WANT exactly one `in_progress` entry -- this
  cycle's own -- after this pull request SO THAT the journal-closure workflow
  has an unambiguous entry to close after this cycle's release.
- AS a reviewer I WANT the new invariant test to carry its own fixture
  evidence in the test file SO THAT I can see the assertion fails on a
  two-in-progress tree rather than trusting that it would.

## Acceptance criteria (EARS)

Tests -- `test/journal-status.test.ts`:

- WHEN the implementer finishes, THE SYSTEM SHALL contain, in
  `test/journal-status.test.ts`, no assertion that the number of `in_progress`
  entries under `src/content/journal/` equals one, and no assertion keyed to
  the status of `2026-09-13-journal-lifecycle-and-release-closure.md`.
  (Issue acceptance criterion 1.)
- WHEN `test/journal-status.test.ts` runs, THE SYSTEM SHALL assert that the
  number of files under `src/content/journal/` whose frontmatter `status` is
  `in_progress` is less than or equal to one, with a failure message that
  names the offending files. (Issue scope item A.1; keep the test name honest:
  `at most one journal entry is in_progress`.)
- WHEN `test/journal-status.test.ts` runs, THE SYSTEM SHALL prove that
  assertion has something real to fail on, from fixtures inside the test file:
  a fixture journal directory holding two `in_progress` entries SHALL fail it,
  and a fixture journal directory holding zero `in_progress` entries SHALL
  pass it. (Issue acceptance criterion 2. The evidence lives in the test file,
  never in the pull request description -- the implementer cannot edit its
  pull request body.)
- WHEN the implementer removes the test that pinned
  `2026-09-13-journal-lifecycle-and-release-closure.md` to `in_progress`, THE
  SYSTEM SHALL NOT replace it with any other filename-keyed status assertion.
  (Issue scope item A.2.)
- IF the implementer wants to keep a content-level guard for the rule that
  test wanted ("an in-progress entry carries no evidence"), THEN THE SYSTEM
  SHALL express it status-driven over all files -- for every file under
  `src/content/journal/` whose `status` is `in_progress`, assert it carries no
  `release`, no `released_at` and no `deployed_at` -- and never key it to one
  filename. (Issue scope item A.2. The rule is already enforced by the schema
  via `statusEvidenceProblems` in `src/lib/journal.ts` and covered by the
  `journalEntryProblems` / `statusEvidenceProblems` tests, so this guard is
  optional; if added, it must take the status-driven form.)
- WHEN `grep -n "exactly one" test/*.ts` is run after the change, THE SYSTEM
  SHALL return only fixture-level cases. (Issue scope item A.3. The fixture
  case `astro sync passes with exactly one in_progress entry, even when it
  belongs to an older backlog issue than a completed entry` in
  `test/journal-build.test.ts` line 264 is fine: it builds its own tree. The
  in-memory unit case `checkJournalCollection accepts exactly one in_progress
  entry` in `test/journal-status.test.ts` line 231 is likewise a fixture-level
  case over a hand-built list and stays. The unrelated hits in
  `test/approach.test.ts`, `test/chain.test.ts`, `test/check-dist.test.ts`,
  `test/home.test.ts`, `test/nginx.test.ts` and
  `test/vendor-assets.test.ts` are not about the journal and stay.)

Closing cycle 79's entry -- `src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`:

- WHEN the implementer edits that file, THE SYSTEM SHALL set exactly these
  values in its frontmatter, character for character (source: GitHub REST
  `pulls/80` `merged_at`, `releases` tag `0.1.21` `published_at`; identical to
  what the closure workflow computed in #82):

  ```
  pr: https://github.com/mctlhq/portfolio/pull/80
  release: 0.1.21
  status: complete
  merged_at: '2026-09-13T07:23:38Z'
  released_at: '2026-09-13T07:33:33Z'
  ```

  (Issue scope item B.4.)
- WHILE that entry is `complete`, THE SYSTEM SHALL NOT carry a `deployed_at`
  field on it. (Issue scope item B.4: "no `deployed_at`".)
- WHEN the implementer edits that file, THE SYSTEM SHALL record the one manual
  intervention of cycle 79 in its `interventions` array, exactly, character
  for character:

  ```yaml
  interventions:
    - what: "Merged pull request #80 by hand (merge commit) after the review had approved it with no P1/P2 findings and CI was green."
      why: "The deployed shepherd (mctl-agents 1.42.0) re-fed a round-1 P2 that GitHub had re-anchored to the new head and the reviewer had already confirmed closed; the implementer correctly refused (exit 42) and review_attempts reached 3. The fix (mctl-agents#359, merge on the head's verdict) was on mctl-agents main but unreleased."
      at: '2026-09-13T07:23:38Z'
  ```

  (Issue scope item B.5. `interventions[].what` and `interventions[].why` are
  single English strings in the schema -- `src/content.config.ts` -- and the
  detail page renders them inside `<ol class="interventions" lang="en">`, so
  no Russian counterpart exists or is wanted.)
- WHILE editing that entry, THE SYSTEM SHALL change nothing in it other than
  the five closure fields above and the `interventions` array -- no new
  `proposal_approved_at`, no edit to `service`, `issue`, `proposal_slug`,
  `visibility`, `title`, `decided`, `issue_opened_at` or the markdown body.
- WHEN this pull request lands, THE SYSTEM SHALL make closure pull request #82
  redundant, and THE SYSTEM SHALL NOT touch #82 from this cycle -- neither
  closing it, commenting on it, nor merging it. The release owner closes it
  unmerged. (Issue scope item B.6.)

This cycle's own entry -- `src/content/journal/2026-09-13-<slug>.md`:

- WHEN the implementer finishes, THE SYSTEM SHALL contain a new journal entry
  file `src/content/journal/2026-09-13-journal-tests-assert-invariants-only.md`
  with `service: portfolio`,
  `issue: https://github.com/mctlhq/portfolio/issues/83`,
  `proposal_slug: issue-83-q12-the-journal-checkpoint-tests-pin-one`,
  `visibility: public`, `status: in_progress`,
  `issue_opened_at: '2026-09-13T07:37:51Z'`, `interventions: []`, and the
  bilingual `title` and `decided` copy given verbatim below. (Issue scope item
  C.7. `issue_opened_at` is this issue's GitHub `created_at`.)
- WHILE this cycle's own entry is `in_progress`, THE SYSTEM SHALL NOT give it
  a `pr`, `merged_at`, `release`, `released_at` or `deployed_at` field. The
  journal-closure workflow closes it after this cycle's release. (Issue scope
  item C.7.)
- WHEN the implementer writes that entry, THE SYSTEM SHALL use this copy
  character for character:

  ```yaml
  title:
    en: "Q12: the journal test suite asserts invariants, not one cycle's checkpoint"
    ru: "Q12: набор тестов журнала проверяет инварианты, а не контрольную точку одного цикла"
  ```

  ```yaml
  decided:
    en: "Two source-level tests that merged with issue 79 pinned the implementation-PR checkpoint of that cycle as a permanent fact: one asserted that the number of in_progress journal entries is exactly one, the other asserted that 2026-09-13-journal-lifecycle-and-release-closure.md is in_progress and carries no evidence. The invariant the schema and the journal loader actually enforce is at most one, and zero is valid, so the first closure pull request the release-triggered workflow opened turned its own test job red by doing precisely what it was built to do -- CI reported an in_progress count of 0 against an expected 1, and a status of complete against an expected in_progress. The exactly-one assertion is now an at-most-one assertion that names the offending files when it fails, and the filename-keyed test is gone, replaced by a status-driven guard that holds for every file rather than one: whichever entries are in_progress carry no release, released_at or deployed_at. Both assertions carry their own fixture evidence inside the test file -- a fixture journal directory with two in-progress entries fails the invariant, one passes, zero passes -- so each is proven to have something real to fail on instead of passing by accident on the committed tree. Cycle 79's entry is closed in the same commit with the evidence the workflow had computed: pull request 80, merged at 07:23:38Z, release 0.1.21 published at 07:33:33Z, no deployment timestamp collected. It also records the one manual intervention of that cycle, the hand merge of pull request 80 after the deployed shepherd re-fed a review finding the reviewer had already confirmed closed. The closure pull request itself becomes redundant and is closed unmerged by the release owner."
    ru: "Два теста уровня исходников, попавшие в main вместе с задачей 79, закрепили контрольную точку того цикла на этапе implementation-PR как постоянный факт: один утверждал, что число записей журнала со статусом in_progress равно ровно одному, другой -- что файл 2026-09-13-journal-lifecycle-and-release-closure.md имеет статус in_progress и не несёт доказательств. Инвариант, который на самом деле обеспечивают схема и загрузчик журнала, -- не более одной, и ноль допустим, поэтому первый closure pull request, открытый воркфлоу по релизу, сделал свою же job test красной ровно тем, ради чего был создан: CI сообщил о количестве in_progress 0 против ожидаемого 1 и о статусе complete против ожидаемого in_progress. Проверка «ровно одна» стала проверкой «не более одной», называющей нарушившие файлы при падении, а тест, привязанный к имени файла, удалён и заменён проверкой по статусу, которая действует для всех файлов, а не для одного: те записи, что находятся в in_progress, не несут release, released_at и deployed_at. Обе проверки несут собственные фикстуры прямо в файле теста -- каталог журнала с двумя записями in_progress роняет инвариант, с одной проходит, с нулём проходит, -- так что у каждой доказуемо есть на чём упасть, а не случайное прохождение на закоммиченном дереве. Запись цикла 79 закрыта тем же коммитом с доказательствами, которые вычислил воркфлоу: pull request 80, смержен в 07:23:38Z, релиз 0.1.21 опубликован в 07:33:33Z, отметка о деплое не собиралась. В ней же записано единственное ручное вмешательство того цикла -- ручной мерж pull request 80 после того, как развёрнутый shepherd повторно подал замечание ревью, которое ревьюер уже подтвердил как закрытое. Сам closure pull request становится избыточным, и владелец релиза закрывает его без мержа."
  ```

Collection state and gates:

- WHEN this pull request lands, THE SYSTEM SHALL have exactly one journal
  entry with `status: in_progress` -- this cycle's own,
  `2026-09-13-journal-tests-assert-invariants-only.md`. Applying #82's diff on
  top of this branch would be a no-op or a conflict, never a second closure.
  (Issue acceptance criterion 4.)
- WHEN the site is built, THE SYSTEM SHALL render `data-intervention-count`
  on `/colophon/` as the computed value 22 (21 interventions recorded across
  the existing 23 public entries, plus the one added in B.5), and
  `data-cycle-count` as 24, `data-complete-count` as 23,
  `data-in-progress-count` as 1, `data-abandoned-count` as 0. (Issue
  acceptance criterion 3, plus the release owner's verification list.) These
  numbers SHALL be computed by `totalInterventions` / `statusCounts` in
  `src/pages/colophon/index.astro` as they already are; THE SYSTEM SHALL NOT
  add a test that hard-codes any of them against the committed content tree --
  that is the same defect this issue exists to remove.
- WHEN the implementer finishes, THE SYSTEM SHALL pass `npm run vendor && npm
  test`, `npm run build` and `node scripts/check-links.mjs`. (Issue acceptance
  criterion 5.)

## Out of scope

- Any change to `scripts/close-journal.mjs`, `.github/workflows/journal-closure.yml`,
  the journal schema in `src/content.config.ts` or the loader / helpers in
  `src/lib/journal.ts`.
- The five P3 findings left open on #80 (pagination, null issue guard, 422
  body check, error message wording). Those belong to a separate hygiene
  issue.
- Recording the release-PR merges as interventions: merging release-please
  pull requests is the release owner's documented step in `AGENTS.md`, not an
  intervention.
- Touching pull request #82 in any way from this cycle -- closing it,
  commenting on it or merging it. The release owner closes it unmerged after
  this lands.
- Adding `proposal_approved_at` to cycle 79's entry, or any other field beyond
  the five closure fields and the `interventions` array.
- Changing any other journal entry's content, the colophon page, the cycle
  table or the journal detail page.

## Open questions

- The issue names this cycle's own entry as
  `src/content/journal/2026-09-13-<slug>.md` without fixing the slug. This
  proposal fixes it as
  `2026-09-13-journal-tests-assert-invariants-only.md` so the filename is
  unambiguous for the implementer and for review.
- The issue leaves the status-driven content guard of scope item A.2 optional
  ("if the implementer wants a content-level guard"). This proposal makes it
  required in the status-driven form, because deleting the filename-keyed test
  without a replacement would drop the only source-level check that an
  in-progress entry carries no release evidence, and the required form cannot
  pin any cycle. If a reviewer prefers to rely on the schema alone, dropping
  task 3 leaves every other acceptance criterion satisfied.
- The issue does not supply the bilingual `title` and `decided` copy for this
  cycle's own entry. Per `AGENTS.md` ("the copy is the contract"), this
  proposal supplies it verbatim above; the implementer copies it rather than
  inventing prose.
