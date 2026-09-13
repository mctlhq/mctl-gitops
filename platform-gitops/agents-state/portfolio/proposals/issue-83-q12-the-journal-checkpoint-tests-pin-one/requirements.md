# Q12: the journal test suite asserts invariants, not a checkpoint

## Context

Two tests merged in PR #80 (`test/journal-status.test.ts`, on `main` at
`b2e46cc4` and later) froze a migration-time checkpoint into permanent
assertions over the committed journal tree: one asserts that the number of
`in_progress` journal entries is **exactly** one, the other asserts that
`src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`
carries `status: in_progress`. The invariant the schema
(`src/content.config.ts`) and the loader guard (`checkJournalCollection` in
`src/lib/journal.ts`) actually enforce is *at most* one, and `docs/journal.md`
states that zero is valid. Because of the two pinned tests, the first real
closure pull request the journal-closure workflow opened (#82,
`fix(journal): close cycle 79`) — correct, approved, changing only the five
allowed fields of that one entry — has a red `test` job:

```
✖ at most one journal entry is in_progress -- at this implementation-PR checkpoint, exactly one
    actual: 0, expected: 1
✖ this cycle's own entry is in_progress with no invented evidence
    actual: 'complete', expected: 'in_progress'
```

So the very act of closing a cycle fails the suite, and the lifecycle shipped
by issue #79 cannot complete a single loop. Issue #79's own acceptance
criterion 4 had said that the checkpoint numbers "SHALL NOT become permanent
hard-coded assertions that block future cycles"; the review verdict on #80
checked the schema, loader and UI and never compared these two tests against
that criterion, and nothing mechanical distinguishes a migration checkpoint
from an invariant.

This cycle makes the journal test suite assert invariants only, closes cycle
79's entry with its verified GitHub evidence and its one recorded manual
intervention (superseding #82), and writes this cycle's own entry as the single
`in_progress` one.

## User stories

- AS the release owner I WANT the journal test suite to assert only what the
  schema and loader actually guarantee SO THAT a closure pull request that
  correctly closes a cycle turns nothing red.
- AS a future DevLoop cycle in `portfolio` I WANT no test keyed to one
  journal filename or to one point-in-time count SO THAT starting, closing or
  abandoning a cycle never requires editing a test that has nothing to do with
  the change.
- AS a reader of the public colophon I WANT cycle 79's entry to carry its real
  pull request, release, merge time, release time and the one manual
  intervention it required SO THAT the published record matches what happened.

## Acceptance criteria (EARS)

### A. Tests

- WHEN the implementer edits `test/journal-status.test.ts` THE SYSTEM SHALL
  contain no assertion that the number of `in_progress` entries under
  `src/content/journal/` equals one, and no assertion keyed to the status of
  `2026-09-13-journal-lifecycle-and-release-closure.md`.
- WHEN the test suite runs THE SYSTEM SHALL assert, over every `*.md` file in
  `src/content/journal/`, that the count of entries whose frontmatter `status`
  is `in_progress` is less than or equal to 1, failing with a message that
  names every offending file.
- WHILE that invariant test exists THE SYSTEM SHALL keep its name honest:
  `at most one journal entry is in_progress` (no "at this checkpoint,
  exactly one" tail).
- WHEN the test suite runs THE SYSTEM SHALL carry mutation evidence in
  `test/journal-status.test.ts` itself — not in the pull request description —
  proving that the at-most-one check fails for a fixture set of two
  `in_progress` entries (naming both) and passes for a fixture set of zero.
- WHEN the old `this cycle's own entry is in_progress with no invented
  evidence` test is removed THE SYSTEM SHALL either add no replacement or add a
  status-driven replacement that iterates over every journal file and, for
  each file whose `status` is `in_progress`, asserts that `release`,
  `released_at` and `deployed_at` are absent. IF a replacement guard is added
  THEN THE SYSTEM SHALL NOT key it to any filename, and SHALL NOT assert the
  absence of `pr` or `merged_at`, which `docs/journal.md` explicitly permits on
  an in-progress entry.
- WHEN `grep -n "exactly one" test/journal-status.test.ts
  test/journal-build.test.ts` is run after the change THE SYSTEM SHALL return
  only fixture-level cases — cases whose subject is a synthetic entry list or a
  fixture content tree, never the committed `src/content/journal/` tree. The
  two that qualify and stay are `checkJournalCollection accepts exactly one
  in_progress entry` (`test/journal-status.test.ts`, a pure-function call over
  two literal objects) and `astro sync passes with exactly one in_progress
  entry, even when it belongs to an older backlog issue than a completed entry`
  (`test/journal-build.test.ts`, which builds its own fixture tree).
- WHILE the header comment of `test/journal-status.test.ts` describes the
  source-level assertions THE SYSTEM SHALL describe them as they are after this
  change (at most one entry is `in_progress`), with no wording that implies a
  fixed checkpoint count.

### B. Close cycle 79's entry (supersedes PR #82)

- WHEN the implementer edits
  `src/content/journal/2026-09-13-journal-lifecycle-and-release-closure.md`
  THE SYSTEM SHALL set exactly these values, character for character (source:
  GitHub REST `pulls/80` `merged_at`, and the `0.1.21` release's
  `published_at`; identical to what the closure workflow computed in #82):
  - `pr: https://github.com/mctlhq/portfolio/pull/80`
  - `merged_at: '2026-09-13T07:23:38Z'`
  - `release: 0.1.21`
  - `released_at: '2026-09-13T07:33:33Z'`
  - `status: complete`
  - no `deployed_at`
- WHEN that entry is edited THE SYSTEM SHALL replace its `interventions: []`
  with exactly one intervention, character for character:
  - `what: "Merged pull request #80 by hand (merge commit) after the review had approved it with no P1/P2 findings and CI was green."`
  - `why: "The deployed shepherd (mctl-agents 1.42.0) re-fed a round-1 P2 that GitHub had re-anchored to the new head and the reviewer had already confirmed closed; the implementer correctly refused (exit 42) and review_attempts reached 3. The fix (mctl-agents#359, merge on the head's verdict) was on mctl-agents main but unreleased."`
  - `at: '2026-09-13T07:23:38Z'`
- WHILE that entry is edited THE SYSTEM SHALL change nothing else in it: its
  `service`, `issue`, `proposal_slug`, `visibility`, `title`, `decided` and
  `issue_opened_at` values stay byte-identical.
- WHEN the colophon is built THE SYSTEM SHALL compute `data-intervention-count`
  on `/colophon/` as 22 (21 recorded today plus the one added above); the
  number is computed by `totalInterventions()` in
  `src/pages/colophon/index.astro` and SHALL NOT be typed anywhere.
- IF the diff of pull request #82 were applied on top of this branch THEN THE
  SYSTEM SHALL produce a no-op or a conflict, never a second closure of the
  same entry.

### C. This cycle's own entry

- WHEN the implementer adds this cycle's entry THE SYSTEM SHALL create
  `src/content/journal/2026-09-13-journal-tests-assert-invariants-only.md`
  with exactly this frontmatter (body empty, as every other entry):

```yaml
---
service: portfolio
issue: https://github.com/mctlhq/portfolio/issues/83
proposal_slug: issue-83-q12-the-journal-checkpoint-tests-pin-one
visibility: public
status: in_progress
title:
  en: "Q12: the journal tests assert invariants, not a checkpoint"
  ru: "Q12: тесты журнала проверяют инварианты, а не контрольную точку"
decided:
  en: "Two tests merged with the journal lifecycle pinned a migration checkpoint as a permanent fact: one asserted that exactly one entry is in_progress, the other asserted that one named file carries status in_progress. The invariant the schema and the loader enforce is at most one, and zero is valid, so the first real closure pull request the workflow opened was correct and red. The suite now asserts the invariant instead, with mutation evidence committed beside it: the same check fails for a fixture of two in-progress entries, naming both, and passes for a fixture of zero. The filename-keyed test is gone; what it wanted -- an in-progress entry carries no release evidence -- is now a status-driven guard over every file. Cycle 79's entry is closed in this pull request with the pull request, release, merge time and release time the closure workflow had computed, and with the one manual intervention that cycle required recorded rather than dropped."
  ru: "Два теста, влитые вместе с жизненным циклом журнала, закрепили контрольную точку миграции как постоянный факт: один утверждал, что ровно одна запись имеет статус in_progress, другой — что именно указанный по имени файл несёт статус in_progress. Инвариант, который обеспечивают схема и загрузчик, — «не более одной», и ноль допустим, поэтому первый настоящий closure pull request, открытый воркфлоу, был верным и красным. Теперь набор тестов проверяет именно инвариант, а рядом зафиксировано мутационное доказательство: та же проверка падает на наборе из двух незавершённых записей, называя обе, и проходит на наборе из нуля. Тест, привязанный к имени файла, удалён; то, что он проверял, — незавершённая запись не несёт данных о релизе — теперь выражено проверкой по статусу для всех файлов. Запись цикла 79 закрывается в этом же pull request теми pull request, релизом, временем мержа и временем релиза, которые вычислил воркфлоу закрытия, и с записанным, а не потерянным единственным ручным вмешательством того цикла."
issue_opened_at: '2026-09-13T07:37:51Z'
interventions: []
---
```

- WHILE this cycle's entry is `in_progress` THE SYSTEM SHALL NOT give it `pr`,
  `merged_at`, `release`, `released_at` or `deployed_at`. The journal-closure
  workflow closes it after this cycle's release.
- WHEN the change is complete THE SYSTEM SHALL leave exactly one entry
  `in_progress` across `src/content/journal/`: this cycle's own.

### D. Gates

- WHEN `npm run vendor && npm test` is run THE SYSTEM SHALL pass.
- WHEN `npm run build` is run THE SYSTEM SHALL pass.
- WHEN `node scripts/check-links.mjs` is run after a build THE SYSTEM SHALL
  pass.

## Out of scope

- Any change to `scripts/close-journal.mjs`, `.github/workflows/` (the
  journal-closure workflow), the journal schema in `src/content.config.ts`, or
  the loader/helpers in `src/lib/journal.ts`.
- The five P3 findings left open on #80 (pagination, null issue guard, 422 body
  check, error message wording). These belong to a separate hygiene issue.
- Touching pull request #82 in any way from this cycle. It becomes redundant
  once this lands; the release owner closes it unmerged.
- Recording the release-PR merges as interventions: merging release-please pull
  requests is the release owner's documented step in `AGENTS.md`, not an
  intervention.
- Any change to the colophon markup, the cycle table, the journal detail route
  or the i18n strings. The intervention total changes because the data changed,
  not because a template did.
- Any `deployed_at` value for cycle 79's entry — no deployment evidence was
  collected for it.

## Open questions

- The issue's A.3 asks that `grep -n "exactly one" test/*.ts` return only
  fixture-level cases. Taken literally over all of `test/`, that sweep also
  matches unrelated suites — `test/approach.test.ts`, `test/home.test.ts`,
  `test/chain.test.ts`, `test/check-dist.test.ts`, `test/nginx.test.ts`,
  `test/vendor-assets.test.ts` — whose "exactly one" is about `<Details>`
  elements, anchors and font-face blocks, not about journal status. Reading the
  intent as scoped to the journal suites, this proposal requires the sweep over
  `test/journal-status.test.ts` and `test/journal-build.test.ts` and leaves the
  unrelated files untouched.
- The slug of this cycle's entry is not fixed by the issue
  (`2026-09-13-<slug>.md`). This proposal fixes it as
  `2026-09-13-journal-tests-assert-invariants-only.md` so the implementer has
  no choice to make.
- `proposal_approved_at` is omitted from this cycle's entry: the implementer
  cannot know its own approval timestamp, the schema marks the field optional,
  and cycle 79's entry was written the same way. A later backfill cycle may add
  it, exactly as #72 backfilled two earlier stamps.
- The issue leaves the status-driven replacement guard optional ("if the
  implementer wants a content-level guard"). This proposal requires it, in the
  mandated status-driven shape, so that the coverage the deleted test intended
  is not silently lost.
