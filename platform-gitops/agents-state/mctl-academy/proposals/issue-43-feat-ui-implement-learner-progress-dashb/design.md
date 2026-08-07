# Design: issue-43-feat-ui-implement-learner-progress-dashb

## Current state

Two independent, non-persistent session mechanisms exist today, and nothing
aggregates across them:

- **Practice mode** (`client/src/practice/usePracticeSession.ts`): loads the
  full published bundle from `client/src/content-bundle.json` (built by
  `scripts/build-content-bundle.mjs`), shuffles it once per mount via a lazy
  `useState` initializer, and tracks `revealedByQuestion` /
  `firstCorrectByQuestion` in `useRef<Map<...>>`. These maps are pure
  in-memory state: nothing survives unmount, reload, or navigating to Mock
  mode and back. `PracticeScreen.tsx` renders a summary
  (`{score} / {attempted} correct on first try`) but has no concept of
  domain, and no persistence.
- **Mock exam** (`client/src/exam/`): `session.ts` is a pure state machine
  (`startSession` / `answerQuestion` / `submitSession` / `scoreSession`) with
  no side effects. `persistence.ts` saves/loads the whole `ExamSessionState`
  to `sessionStorage` under `academy.mock.session.v1`, explicitly scoped to
  one browser tab/session and explicitly "not the server-side session
  authority." `MockFlow.tsx` calls `clearSession()` on "Start a new mock
  exam," discarding the previous attempt entirely. `MockResultsScreen.tsx`
  renders full per-question review (every option, correct/incorrect,
  explanation) but only for the session in hand — nothing is kept once the
  learner starts over.
- **Domain metadata** already flows from `content/branding.yaml` into the
  client bundle: `content-bundle.json`'s `mock.domains` is a
  `DomainConfig[]` (`id`, `title`, `weight`, `mockQuestions`), and each
  `Question` (`client/src/exam/types.ts`) carries a `domain` field. Nothing
  today aggregates attempt outcomes by that `domain` field.
- **No backend persistence exists.** `server/app.mjs` implements only
  `/healthz` and `/api/reports` (the latter backed by an in-memory array,
  not a database). `PLAN.md` section 7's planned tables (`users`,
  `attempts`, `attempt_items`) are not implemented, and per `CLAUDE.md`'s
  Deployment section `mctl-academy` is "Not yet onboarded" to the platform —
  there is no provisioned database and no auth. Building the dashboard on
  that unbuilt backend is not viable for this issue.

## Proposed solution

Add a new client-side feature area, `client/src/progress/`, that persists a
per-question "last known outcome" map to `localStorage` (not
`sessionStorage` — progress must survive across sessions, unlike the mock
exam's intentionally session-scoped state), and two new screens that read
from it.

**`client/src/progress/progressStore.ts`** — pure functions, mirroring the
existing split between `exam/session.ts` (pure logic) and
`exam/persistence.ts` (storage side effects):

```ts
export interface AttemptRecord {
  questionId: string;
  domain: string;
  correct: boolean;
  recordedAt: number; // epoch ms
}
// keyed by questionId -> AttemptRecord; last write wins
export type ProgressState = Record<string, AttemptRecord>;

export function recordAttempt(state: ProgressState, record: AttemptRecord): ProgressState;
export function loadProgress(): ProgressState;   // localStorage read, try/catch-swallow like persistence.ts
export function saveProgress(state: ProgressState): void;
export function clearProgress(): void;
```

Storage key: `academy.progress.v1` (same versioning convention as
`academy.mock.session.v1`), so a future shape change can be detected and
migrated/discarded rather than crash on parse.

**`client/src/progress/useLearnerProgress.ts`** — a hook that loads
`ProgressState` once, exposes it plus derived aggregates computed against
the *current* published bundle (so retired/unpublished questions drop out of
counts per the requirements' EARS item), and a `recordAttempt` /
`resetProgress` action pair that writes through to storage and updates
local React state:

```ts
export interface DomainProgress {
  domain: string; title: string; weight: number;
  attempted: number; correct: number;
}
export interface LearnerProgress {
  totalAttempted: number;
  totalCorrect: number;
  publishedBankSize: number;      // from content-bundle.json
  byDomain: DomainProgress[];     // one entry per branding.yaml domain, in declared order
  mistakes: BundleQuestion[];     // questions whose latest recorded outcome is incorrect
  recordAttempt: (questionId: string, correct: boolean) => void;
  resetProgress: () => void;
}
```

Domain metadata comes from `rawBundle.mock.domains` (already present in
`content-bundle.json`), not a new file — this keeps `branding.yaml` the
single source of truth for domain titles/weights, matching the existing
convention documented at the top of `branding.yaml` and in
`client/src/exam/types.ts`'s `DomainConfig`.

**Wiring attempts in:**

- `usePracticeSession.ts` gains an optional `onFirstAnswer?: (questionId, domain, correct) => void`
  callback invoked from inside `selectOption` exactly when
  `isFirstSelection` is true (the same point that already updates
  `firstCorrectByQuestion`) — this is an additive, backward-compatible
  parameter; existing callers/tests that omit it are unaffected.
- `PracticeScreen.tsx` obtains `recordAttempt` from `useLearnerProgress()`
  and passes it as `usePracticeSession`'s `onFirstAnswer`.
- `MockFlow.tsx`'s `handleSubmit` computes `scoreSession(session)` (already
  available) and, for each `perQuestion` entry, calls `recordAttempt` with
  that question's `domain` (from `session.questions`), once, at submit time
  — mirroring how `MockResultsScreen` already derives correctness from
  `scoreSession`.

**New screens:**

- `client/src/progress/components/ProgressDashboard.tsx` — total
  attempted/bank size, overall accuracy, a per-domain breakdown table/bars
  driven by `byDomain`, a "Review mistakes" call-to-action (disabled/empty
  state when `mistakes.length === 0`), and a "Reset progress" button that
  calls `resetProgress()` behind a confirmation.
- `client/src/progress/components/ReviewMistakesScreen.tsx` — thin
  wrapper that renders the existing `PracticeScreen` with
  `bundle={mistakes}` (reusing `PracticeScreen`'s already-present `bundle`
  override prop, currently only exercised by tests) and an explicit empty
  state when there are no mistakes, per the EARS "IF a learner has no
  recorded mistakes" criterion. This reuses Practice mode's entire
  option-reveal/feedback UI instead of duplicating it, and questions
  answered correctly here naturally fall out of `mistakes` the next time
  the dashboard/hook recomputes (satisfying the "gets it right -> removed
  from mistakes" criterion), since `PracticeScreen`'s own `onFirstAnswer`
  wiring records the new outcome the same way Practice mode does.

**Nav:** `client/src/App.tsx`'s `mode` state grows a third value
(`"progress"`), with a third nav button, following the exact pattern of the
existing two buttons. Review Mistakes is reached from the dashboard's
call-to-action rather than being a fourth top-level tab, keeping the nav
flat while avoiding a route a learner would land on with nothing to review.

## Alternatives

1. **Build the full server-side schema now** (`users`, `attempts`,
   `attempt_items` per `PLAN.md` section 7) with GitHub OAuth. Rejected for
   this issue: `mctl-academy` is not yet onboarded (no DB, no OAuth app -
   both are separate, later steps in `PLAN.md` section 8's bootstrap
   order), and pulling that forward turns a `feat(ui)` issue into standing
   up auth and a database. This is real future work and is called out in
   Platform impact below, not discarded.
2. **Log every attempt (append-only) in `localStorage`** instead of
   last-outcome-per-question. Rejected: unbounded growth for a client-side
   store with no eviction strategy, and neither the dashboard nor
   review-mistakes needs history — both only need current standing. An
   immutable audit log is explicitly the server-side `attempts` table's job
   per `PLAN.md`; duplicating it client-side pre-empts that design without
   its durability guarantees.
3. **Derive progress purely in-memory, scoped to one page load**, with no
   new storage (extend today's `useRef` approach). Rejected: fails the
   requirement that progress "survive a page reload or switching between
   Practice and Mock modes" — the entire point of the issue is that today's
   in-memory-only tracking is insufficient.
4. **A single flat `ReviewMistakesScreen` reimplementing option-reveal UI**
   instead of reusing `PracticeScreen` with a filtered `bundle`. Rejected:
   `PracticeScreen` already accepts a `bundle` override
   (`PracticeScreenProps.bundle`), already renders the exact interaction
   (immediate per-option feedback, markdown rendering via
   `renderInlineMarkdown`, report-issue modal) the issue asks for in
   "review mistakes mode," and duplicating it would drift from Practice
   mode's behavior over time for no benefit.

## Platform impact

- **Migrations:** none. No database exists for this service yet; this
  proposal adds no server code and no schema.
- **Backward compatibility:** additive only. `usePracticeSession`'s new
  `onFirstAnswer` parameter is optional; existing tests
  (`usePracticeSession.test.ts`, `PracticeScreen.test.tsx`) are unaffected
  since they don't pass it. No change to `content-bundle.json`'s shape,
  `content/schemas/`, or the server API.
- **Resource impact:** negligible. No new server endpoints, no new runtime
  dependencies (React is already a `client/package.json` dependency).
  `localStorage` usage is bounded by published bank size (currently well
  under a thousand questions; each record is a question id, domain string,
  boolean, and timestamp).
- **Risks and mitigations:**
  - Progress is per-browser, not per-account — it will not follow a
    learner across devices, and clearing site data silently resets it. This
    is an accepted limitation matching the product's current phase (no
    auth deployed yet); the dashboard should say so plainly and expose an
    explicit "reset progress" action rather than have that happen only by
    surprise.
  - `localStorage` can throw (quota, private browsing, disabled storage).
    Mitigated by reusing the same try/catch-and-swallow pattern already
    established in `client/src/exam/persistence.ts`, so a failure degrades
    to "nothing recorded this session" instead of crashing the app.
  - Stored question ids can go stale if content is retired/unpublished.
    Mitigated by filtering `ProgressState` against the current bundle's
    question ids when computing `byDomain`/`mistakes`, so stale entries are
    inert rather than rendered broken.
  - Future server-side `attempts` work (per `PLAN.md`) will need a
    migration/merge story for existing `localStorage` progress once
    accounts exist. Not solved here; flagged for that future proposal since
    it depends on OAuth/DB work not yet built.
