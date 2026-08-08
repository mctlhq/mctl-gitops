# Design: issue-89-fix-ui-review-mistakes-nav-badge-doesn-t

## Current state

`client/src/components/AppNav.vue` is mounted once by `App.vue`
(`App.vue:57`) alongside a `<RouterView>` whose displayed component is
force-remounted on route change or `syncVersion` bump via a composite
`:key` (`App.vue:60-62`: `key="${route.fullPath}-${syncVersion}"`).
`AppNav.vue` itself is *not* part of that keyed subtree, so it is never
remounted — its `mistakeCount` ref (`AppNav.vue:23`) is a long-lived value
that only gets re-read through two explicit triggers already wired in:

1. `router.afterEach(() => { mistakeCount.value = getMistakeQuestionIds().length })`
   (`AppNav.vue:24-26`) — fires on every completed navigation.
2. `watch(syncVersion, () => { ... })` (`AppNav.vue:27-32`), where
   `syncVersion` is a `Ref<number>` provided by `App.vue` (`App.vue:17-18`)
   and bumped only after a successful `syncFromServer()` resolves
   (`App.vue:38-39`).

`progressStore.ts` is a plain (non-Vue-reactive) TypeScript module. Its
`recordAttempt(questionId, domain, correct)` (`progressStore.ts:115-133`)
writes to `localStorage` (or an in-memory fallback) and, if sync is
enabled, best-effort POSTs to the server. It has no notion of subscribers
today — callers just call it and the write is fire-and-forget from the
caller's perspective.

Two call sites invoke `recordAttempt()` while remaining on the same route,
which is exactly the case neither of `AppNav.vue`'s triggers covers:

- `MockFlow.vue:46` — `handleSubmit()` iterates the scored session and
  calls `recordAttempt()` per question, then stays on `/mock` rendering
  `MockResultsScreen` (`MockFlow.vue:67-68`).
- `usePracticeSession.ts:104` — on a learner's first selection for a
  question, calls `recordAttempt()` while `PracticeScreen.vue` stays
  mounted on `/practice`.

`getMistakeQuestionIds()` (`progressStore.ts:184-187`) itself is cheap and
correct — it just filters `getStoredAttempts()` for `!a.correct`. The bug
is purely about *when* `AppNav.vue` re-reads it, not the read itself.

## Proposed solution

Add a small reactive counter owned by `progressStore.ts` and bump it from
inside `recordAttempt()`, after the write succeeds:

- `export const attemptsVersion = ref(0);` in `progressStore.ts` (Vue is
  already a runtime dependency of this module's consumers, and other
  non-`.vue` files in this codebase — e.g. `usePracticeSession.ts` — already
  import `ref`/`computed` from `vue` directly, so this is consistent with
  existing conventions, not a new pattern).
- Inside `recordAttempt()`, move the `attemptsVersion.value += 1` bump to
  execute only after the `setItem(...)` call inside the `try` block
  succeeds (i.e. inside the `try`, right after `setItem`, not in a
  `finally` and not in the `catch`) — this satisfies the acceptance
  criterion that a failed write must not emit a refresh signal.
- In `AppNav.vue`, import `attemptsVersion` alongside the existing
  `getMistakeQuestionIds` import and add a third trigger:
  `watch(attemptsVersion, () => { mistakeCount.value = getMistakeQuestionIds().length; })`.
  This is a plain module-level import, exactly like the existing
  `getMistakeQuestionIds` import — no `provide`/`inject` plumbing needed,
  because `progressStore.ts` is already a shared singleton module, not a
  component-tree-scoped value.

This is additive: `router.afterEach` and the `syncVersion` watch stay
exactly as they are, so behavior on navigation and on post-sync-merge is
unchanged. The new watcher only adds a third, narrower trigger for the
in-place-write case the issue describes.

Because `attemptsVersion` lives in `progressStore.ts` and is bumped
unconditionally by `recordAttempt()`, both current in-place call sites
(`MockFlow.vue` and `usePracticeSession.ts`) are fixed by this one change,
with no per-call-site wiring — matching the issue's stated preference
("every caller gets the refresh for free instead of each call site
remembering to bump a shared ref").

## Alternatives

1. **Have `MockFlow.vue` inject and bump the existing `syncVersion` ref
   after `recordAttempt()` calls** (the issue's first suggested fix).
   Rejected: `syncVersion` is also the key input to `App.vue`'s
   `RouterView` `:key`, so bumping it force-remounts the currently
   displayed routed component. Right after a mock-exam submit, that is
   `MockResultsScreen` — remounting it discards any of its local UI state
   and is a visibly worse regression than the stale badge. `syncVersion`'s
   contract today is "a full routed-view refresh happened", which is too
   coarse for "just re-read the mistake count."

2. **Have `AppNav.vue` poll `getMistakeQuestionIds().length` on an
   interval (e.g. `setInterval`).** Rejected: wastes cycles, adds latency
   before the badge is correct, and is a worse fit than an exact
   write-triggered signal that is already trivial to add at the one choke
   point (`recordAttempt`) all writes pass through.

3. **Introduce a dedicated event-emitter/pub-sub utility (e.g. `mitt`) as a
   new dependency.** Rejected: the codebase has no existing event-bus
   dependency or pattern, and Vue's own `ref`/`watch` — already used for
   exactly this kind of cross-component signal via `syncVersion` — is
   sufficient and keeps the fix idiomatic to the existing code rather than
   introducing a new concept for one narrow case.

## Platform impact

- No migrations, no server/API changes, no schema changes — this is a
  client-only, UI-reactivity fix confined to `client/src/services/progressStore.ts`
  and `client/src/components/AppNav.vue`.
- No backward-compatibility concerns: `attemptsVersion` is a new export,
  additive to `progressStore.ts`'s public surface; no existing exported
  function's signature or behavior changes (`recordAttempt`'s return type,
  `void`, is unchanged — it now also has a side effect of bumping a
  counter, which is invisible to existing callers/tests that don't
  reference the new export).
- No resource/deployment impact — `mctl-academy` is not yet onboarded to
  the platform (per `CLAUDE.md`/`PLAN.md`), so there is nothing to deploy
  for this change beyond the normal PR/CI/merge flow.
- Risk: a stray `watch(attemptsVersion, ...)` firing on initial mount would
  be a no-op re-read of the same value (Vue's `watch` without `immediate:
  true` does not fire on setup, matching the existing `syncVersion` watch's
  behavior), so no double-read-on-mount regression is expected. Mitigation:
  covered by the new AppNav test in tasks.md, which asserts the badge does
  *not* change until `attemptsVersion` is actually bumped.
- Risk: `recordAttempt()`'s `catch` block already swallows storage errors
  silently (`progressStore.ts:126-128`); placing the version bump inside
  the `try`, after `setItem`, means a caught error correctly skips the
  bump — consistent with the acceptance criterion that failed writes must
  not signal a refresh. Mitigation: exercised by a new progressStore test
  that forces `setItem` to throw and asserts `attemptsVersion` is
  unchanged.
