# Fix: Review Mistakes nav badge doesn't refresh in-place after progress-affecting attempts

## Context

`AppNav.vue` renders a "Review Mistakes (N)" badge whose count is a local
`ref` (`mistakeCount`, `AppNav.vue:23`) seeded once from
`getMistakeQuestionIds().length`. It is only re-read on two triggers:
`router.afterEach()` (`AppNav.vue:24-26`) and a `watch()` on the
`syncVersion` ref injected from `App.vue` (`AppNav.vue:27-32`), which is
bumped only after a server `syncFromServer()` completes
(`App.vue:31-40`).

Neither trigger fires when `MockFlow.vue`'s `handleSubmit()` calls
`recordAttempt(...)` directly against `progressStore.ts`
(`MockFlow.vue:42-47`) while the learner stays on `/mock` viewing exam
results. The badge shows a stale count until the next route change. The
same gap exists in Practice mode: `usePracticeSession.ts:104` also calls
`recordAttempt()` in place while the learner stays on `/practice`,
answering further questions — a first-selection wrong answer there will
not update the nav badge either, for the identical reason.

This is a cosmetic, low-priority UI-staleness bug (confirmed non-data-loss:
the underlying `progressStore` localStorage data is always correct; only
the nav badge's cached display lags). It matters for trust in the "Review
Mistakes" count as a live indicator during a single session, and it will
recur at every future call site that writes an attempt unless the fix
lives in the write path itself rather than in each caller.

## User stories

- AS a learner taking a mock exam I WANT the "Review Mistakes" badge to
  update immediately after I submit SO THAT the nav accurately reflects my
  mistake count without requiring an unrelated navigation.
- AS a learner practicing in the Practice Bank I WANT the same immediate
  badge update after an incorrect first answer SO THAT the badge is never
  visibly stale during a session, regardless of which mode produced the
  mistake.
- AS a future contributor adding a new call site that records progress
  attempts I WANT the nav badge to refresh automatically SO THAT I do not
  need to remember to wire up a manual refresh trigger.

## Acceptance criteria (EARS)

- WHEN `recordAttempt()` in `progressStore.ts` is called and completes its
  local-storage write THE SYSTEM SHALL make that change observable to any
  currently-mounted subscriber without requiring a route change.
- WHEN a learner submits a mock exam via `MockFlow.vue` and stays on
  `/mock` THE SYSTEM SHALL update the "Review Mistakes (N)" badge in
  `AppNav.vue` to the new count without any navigation occurring.
- WHEN a learner answers a question incorrectly for the first time in
  Practice mode via `usePracticeSession.ts` and stays on `/practice` THE
  SYSTEM SHALL update the "Review Mistakes (N)" badge to the new count
  without any navigation occurring.
- WHILE the existing `router.afterEach()` and `syncVersion`-driven refresh
  triggers in `AppNav.vue` continue to fire on route change and post-sync
  merge THE SYSTEM SHALL continue producing the same correct badge count
  as before this change (no regression to the two existing triggers).
- IF `recordAttempt()` throws or the local-storage write fails (existing
  try/catch at `progressStore.ts:116-128`) THEN THE SYSTEM SHALL NOT emit a
  refresh signal for that failed write (the badge must not advance past
  data that was never actually persisted).
- WHEN the badge-refresh mechanism is exercised THE SYSTEM SHALL NOT force
  a remount of the currently-routed view component (i.e. it must not go
  through `App.vue`'s `syncVersion`-keyed `RouterView`, which would discard
  in-progress local UI state such as the mounted `MockResultsScreen`).

## Out of scope

- Re-architecting `progressStore.ts` into a full pub/sub or state-management
  library; the fix is additive and minimal (a single reactive counter).
- Changing what counts as a "mistake" or any scoring/attempt-recording
  logic — `recordAttempt`'s data semantics are unchanged and confirmed
  correct by the issue reporter.
- Server-side `/api/attempts` behavior or `syncFromServer()` merge logic.
- Refreshing other progress-derived UI (e.g. `DashboardScreen.vue` stats)
  that is not the nav badge — those views already recompute on their own
  mount/route-change cycle and are not reported stale in this issue.
- Debouncing or batching rapid repeated `recordAttempt()` calls; existing
  call sites invoke it at most once per submitted answer, which is not a
  performance concern at this scale.

## Open questions

- The issue proposes two alternative fixes (reuse `syncVersion`, or a
  dedicated ref/event bumped from `recordAttempt()` itself). This proposal
  selects the dedicated-ref approach because reusing `syncVersion` would
  force-remount the currently-routed view (via `App.vue`'s
  `:key="${route.fullPath}-${syncVersion}"`), which would discard the
  mounted `MockResultsScreen` right after submit — a worse regression than
  the bug being fixed. Recorded here for reviewer visibility; proceeding
  with the dedicated-ref interpretation as the most reasonable one.
- Whether to also refresh `DashboardScreen.vue` reactively through the same
  mechanism is left open; the issue only reports the nav badge as stale, so
  this proposal does not extend scope there. A follow-up issue can widen
  the new counter's consumers if desired.
