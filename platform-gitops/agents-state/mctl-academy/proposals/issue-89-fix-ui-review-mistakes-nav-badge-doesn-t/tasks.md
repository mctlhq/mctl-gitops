# Tasks: issue-89-fix-ui-review-mistakes-nav-badge-doesn-t

- [ ] 1. Add `attemptsVersion` reactive counter to `client/src/services/progressStore.ts`:
      import `ref` from `vue`, export `export const attemptsVersion = ref(0);`,
      and bump it (`attemptsVersion.value += 1;`) inside `recordAttempt()`'s
      `try` block, immediately after the `setItem(STORAGE_KEY, ...)` call
      succeeds — not inside `catch`, not in a `finally`. — DoD: `recordAttempt()`
      increments `attemptsVersion.value` by exactly 1 on a successful write and
      leaves it unchanged when `setItem` throws.

- [ ] 2. Wire the new counter into `client/src/components/AppNav.vue`
      (depends on 1): import `attemptsVersion` alongside the existing
      `getMistakeQuestionIds` import, and add
      `watch(attemptsVersion, () => { mistakeCount.value = getMistakeQuestionIds().length; })`
      next to the existing `syncVersion` watch, leaving `router.afterEach`
      and the `syncVersion` watch untouched. — DoD: badge count updates
      when `attemptsVersion` changes, with no change to existing
      navigation- or sync-triggered refresh behavior.

- [ ] 3. Verify no other consumer relies on `recordAttempt()` having zero
      side effects beyond the localStorage/sync write (depends on 1) —
      grep the codebase for `recordAttempt` call sites and confirm
      `MockFlow.vue:46` and `usePracticeSession.ts:104` are the only two,
      and that neither asserts on `progressStore` internals in a way the
      new export would break. — DoD: confirmed by inspection, noted in the
      PR description; no code change expected from this task.

## Tests

- [ ] T1. `client/src/services/__tests__/progressStore.test.ts`: add a case
      asserting `recordAttempt()` increments `attemptsVersion.value` by 1
      per call (mirroring the existing "stores and retrieves question
      attempts" test's setup/teardown via `resetMemoryFallback()`).

- [ ] T2. `client/src/services/__tests__/progressStore.test.ts`: add a case
      that forces `setItem`'s underlying `localStorage.setItem` to throw
      (e.g. `vi.stubGlobal("localStorage", { setItem: () => { throw new Error("full"); }, getItem: () => null, ... })`,
      matching the file's existing `vi.unstubAllGlobals()` teardown in
      `afterEach`) and asserts `attemptsVersion.value` does NOT change.

- [ ] T3. New `client/src/components/__tests__/AppNav.test.ts`: mount
      `AppNav.vue` with a `vue-router` memory-history router instance
      (`createRouter({ history: createMemoryHistory(), routes: [...] })`,
      mirroring the route table in `client/src/router/index.ts`) and, if
      needed, a `syncVersion` provide stub (`App.vue:17-18`'s shape) so the
      component mounts cleanly. Assert: (a) initial badge text reflects
      `getMistakeQuestionIds().length` at mount time; (b) calling
      `recordAttempt(...)` with a wrong answer after mount updates the
      badge text without any router navigation, proving the new trigger
      works end-to-end through the real `progressStore` module (not a
      mock).

- [ ] T4. Extend `client/src/exam/components/__tests__/MockFlow.test.ts`'s
      existing "records a progress attempt for every question on submit"
      test, or add a sibling case, asserting that after `handleSubmit()`
      runs, `attemptsVersion.value` has increased — a regression guard tying
      the exact bug's repro scenario (submit a mock exam, stay on
      `/mock`) to the new mechanism.

- [ ] T5. Run `npm run lint:content` and the existing full test suite
      (`bun test` / `vitest` per `client/package.json` scripts) to confirm
      no unrelated regressions — this change touches no content files, so
      `lint:content` is expected to be a no-op pass, included here only as
      the repo's standard pre-merge check per `CLAUDE.md`.

## Rollback

This is a small, additive, client-only diff (one new export, one bump
call, one new watcher, plus tests). If it needs to be reverted:

1. `git revert` the merge commit on the feature branch's target (per
   `CLAUDE.md`: never squash, so the merge commit is a single revertible
   unit).
2. Reverting drops the `attemptsVersion` export, its bump in
   `recordAttempt()`, and the `AppNav.vue` watcher — `AppNav.vue` falls
   back to exactly its current (pre-fix) two-trigger behavior, with no
   data migration or state cleanup required, since `attemptsVersion` is an
   in-memory-only counter (not persisted to `localStorage` or the server).
3. No feature flag is needed given the change's small blast radius and the
   fact that `mctl-academy` is not yet deployed to the platform (per
   `CLAUDE.md`/`PLAN.md`) — rollback is purely a source-control operation.
