# Tasks: issue-43-feat-ui-implement-learner-progress-dashb

- [ ] 1. Add `client/src/progress/progressStore.ts`: `AttemptRecord`,
      `ProgressState`, `recordAttempt` (pure reducer, last-write-wins by
      `questionId`), `loadProgress`/`saveProgress`/`clearProgress`
      (`localStorage`, key `academy.progress.v1`, try/catch-swallow
      matching `client/src/exam/persistence.ts`) — DoD: module has no React
      dependency, all functions exported and typed, `loadProgress()` on a
      fresh/corrupt/absent key returns `{}` without throwing.

- [ ] 2. Add `client/src/progress/useLearnerProgress.ts` (depends on 1): a
      hook that loads `ProgressState` once on mount, computes
      `totalAttempted`, `totalCorrect`, `publishedBankSize` (from
      `content-bundle.json`), `byDomain` (one entry per
      `rawBundle.mock.domains`, in declared order, counts filtered to
      question ids present in the current bundle), `mistakes` (bundle
      questions whose latest recorded outcome is incorrect, also filtered
      to currently-published ids), and exposes `recordAttempt(questionId,
      correct)` / `resetProgress()` that write through via `progressStore`
      and update local state — DoD: hook returns zeroed/empty aggregates
      when storage is empty; a stale question id in storage that is absent
      from the current bundle affects neither `byDomain` counts nor
      `mistakes`.

- [ ] 3. Wire Practice mode into progress recording (depends on 2): add an
      optional `onFirstAnswer?: (questionId: string, domain: string,
      correct: boolean) => void` parameter to
      `client/src/practice/usePracticeSession.ts`, invoked inside
      `selectOption` exactly where `isFirstSelection` is computed; have
      `client/src/practice/PracticeScreen.tsx` obtain `recordAttempt` from
      `useLearnerProgress()` and pass it through — DoD: existing
      `usePracticeSession.test.ts` and `PracticeScreen.test.tsx` still pass
      unmodified (parameter is optional, omitted in those tests); a new
      test confirms `onFirstAnswer` fires once per question on first
      selection only, with the question's `domain` and correctness.

- [ ] 4. Wire Mock exam submission into progress recording (depends on 2):
      in `client/src/exam/components/MockFlow.tsx`'s `handleSubmit`, after
      `scoreSession(submitted)`, call `recordAttempt` for every
      `perQuestion` entry using that question's `domain` looked up from
      `submitted.questions` — DoD: submitting a mock exam updates the
      progress store for every question in that mock, verified by a test
      that submits a session and then reads back `loadProgress()`.

- [ ] 5. Add `client/src/progress/components/ProgressDashboard.tsx`
      (depends on 2): renders total attempted vs. `publishedBankSize`,
      overall accuracy, a per-domain breakdown (`byDomain`: attempted /
      correct / accuracy per domain title), a "Review mistakes"
      call-to-action, and a "Reset progress" control that calls
      `resetProgress()` — DoD: renders a sane zero-state when
      `totalAttempted === 0`; the mistakes call-to-action is disabled or
      hidden when `mistakes.length === 0`.

- [ ] 6. Add `client/src/progress/components/ReviewMistakesScreen.tsx`
      (depends on 2, 3): renders `PracticeScreen` with
      `bundle={mistakes}` when `mistakes.length > 0`, and an explicit empty
      state ("No mistakes to review") otherwise — DoD: a question answered
      correctly inside this screen no longer appears in `mistakes` on the
      next render (verified through `useLearnerProgress`'s recompute, not a
      manual filter duplicated in this component).

- [ ] 7. Wire navigation (depends on 5, 6): add a third `mode` value
      (`"progress"`) to `client/src/App.tsx` with a third nav button
      alongside "Practice Mode" / "Mock Exam (30 Questions)", rendering
      `ProgressDashboard`; dashboard's "Review mistakes" action switches to
      rendering `ReviewMistakesScreen` — DoD: all three modes are reachable
      from the nav without a full page reload, matching the existing
      `useState`-driven mode switch.

## Tests

- [ ] T1. `progressStore.test.ts`: `recordAttempt` overwrites a prior
      record for the same `questionId` (last-write-wins, not append);
      `loadProgress`/`saveProgress` round-trip; `loadProgress` on absent or
      corrupt (non-JSON) storage returns `{}` without throwing;
      `clearProgress` empties subsequent `loadProgress()` calls.
- [ ] T2. `useLearnerProgress.test.ts`: zero-state aggregates when storage
      is empty; `byDomain` totals match a hand-constructed `ProgressState`
      fixture with a known bundle; a recorded question id absent from the
      supplied bundle is excluded from both `byDomain` and `mistakes`; a
      question recorded incorrect then re-recorded correct leaves
      `mistakes` without it.
- [ ] T3. `usePracticeSession.test.ts` (extend existing file): a new test
      asserts `onFirstAnswer` is called exactly once per question, only on
      the first `selectOption` call for that question, with the correct
      `domain`/`correct` values; existing tests continue to pass with the
      parameter omitted.
- [ ] T4. `MockFlow` submission test (extend existing exam component
      tests): submitting a mock session with a mix of correct/incorrect
      answers results in matching entries via `loadProgress()` after
      submit, keyed by the submitted questions' ids and domains.
- [ ] T5. `ProgressDashboard.test.tsx`: renders zero-state with empty
      storage; renders correct totals/per-domain breakdown given a
      `useLearnerProgress` fixture; "Review mistakes" is disabled/hidden
      when there are no mistakes and enabled when there are.
- [ ] T6. `ReviewMistakesScreen.test.tsx`: renders the empty state with no
      mistakes; renders `PracticeScreen` scoped to only the mistake
      questions when present; answering a mistake question correctly
      removes it from the set on next read (integration-style, following
      `PracticeScreen.test.tsx`'s existing `userEvent` pattern).

## Rollback

All changes are additive, client-only, and contained to a new
`client/src/progress/` directory plus small, optional-parameter extensions
to `usePracticeSession.ts` and `MockFlow.tsx`'s `handleSubmit`. To roll
back:

1. Revert the commit(s) introducing `client/src/progress/`, the
   `onFirstAnswer` parameter in `usePracticeSession.ts`, the
   `recordAttempt` call in `MockFlow.tsx`, and the third nav mode in
   `App.tsx`.
2. No database, server, or content-schema changes exist to unwind — there
   is nothing to migrate down.
3. End users' `localStorage` entries under `academy.progress.v1` become
   inert (unread) once the feature is reverted; no cleanup action is
   required, and no other stored key (`academy.mock.session.v1`) is
   touched by this proposal.
