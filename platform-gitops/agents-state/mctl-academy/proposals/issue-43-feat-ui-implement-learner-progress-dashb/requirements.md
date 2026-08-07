# Learner Progress Dashboard and Review Mistakes mode

## Context

Issue #43 asks for three related pieces of UI: a learner stats overview, a
domain-by-domain progress breakdown, and a dedicated "review mistakes" mode.
`PLAN.md` (section 3, "Product scope") already lists "Review-mistakes" and
"progress dashboard" as in-scope MVP features alongside Practice and Mock —
this proposal is the first implementation of that line item.

Today, `client/src/practice/usePracticeSession.ts` tracks per-question
correctness only in `useRef` maps that live for the lifetime of the mounted
component: a reload, a tab close, or switching to Mock mode and back loses
everything. `client/src/exam/persistence.ts` persists the in-progress mock
session, but deliberately to `sessionStorage` ("tab/session-scoped"), and only
for the duration of one mock attempt — it is explicitly "not the server-side
session authority" and is cleared once a new attempt starts
(`clearSession()` in `client/src/exam/components/MockFlow.tsx`). Neither
mechanism records which domain a question belongs to alongside its outcome,
and nothing persists across Practice and Mock modes. There is currently no
way for a learner to see cumulative progress or revisit only what they got
wrong.

`PLAN.md` section 7 describes a future server-side schema
(`users`, `attempts` (immutable), `attempt_items`) gated behind GitHub OAuth,
but section 8's bootstrap order stands the service up with
`AUTH_ENABLED=false` first, and the OAuth app itself is a separate, manual,
later step. `mctl-academy` is not yet onboarded to the platform at all (no
entry in `mctl_list_services`, no `DATABASE_URL`). Building the dashboard and
review-mistakes mode on top of that unbuilt backend would turn a `feat(ui)`
issue into standing up a database, an auth system, and an OAuth app — a much
larger, separate effort. This proposal instead delivers the two learner-facing
features entirely client-side, persisted in the browser, so they work today
without waiting on auth/DB work, and are additive with it later.

## User stories

- AS a learner I WANT to see how many questions I have attempted and how many
  I got right SO THAT I know my overall progress through the bank.
- AS a learner I WANT to see my accuracy broken down by domain SO THAT I know
  which of the four course domains needs more study time.
- AS a learner I WANT a dedicated mode that only re-serves the questions I
  most recently got wrong SO THAT I can focus practice time on my mistakes
  instead of re-running the whole bank.
- AS a learner I WANT my progress to survive a page reload or switching
  between Practice and Mock modes SO THAT casual navigation does not erase my
  standing.
- AS a learner I WANT an explicit way to reset my recorded progress SO THAT I
  am not stuck with stale history I did not ask to keep.

## Acceptance criteria (EARS)

- WHEN a learner selects an option for the first time on a question (in
  Practice mode or in a submitted Mock exam) THE SYSTEM SHALL record that
  question's id, domain, and whether the first selection was correct, in a
  persistent client-side store keyed by question id (last outcome per
  question, not a growing log).
- WHEN a learner opens the Progress Dashboard THE SYSTEM SHALL display: total
  questions attempted vs. the published bank size, overall accuracy (correct
  / attempted), and a per-domain breakdown (attempted, correct, accuracy) for
  every domain declared in `content/branding.yaml`.
- WHEN a learner opens Review Mistakes mode THE SYSTEM SHALL present only
  questions whose most recently recorded outcome was incorrect, using the
  same immediate-feedback option-reveal interaction as Practice mode.
- IF a learner has no recorded mistakes THEN THE SYSTEM SHALL show an
  explicit empty state in Review Mistakes mode instead of an empty question
  list.
- IF a learner re-answers a question that was previously a recorded mistake
  and gets it right THEN THE SYSTEM SHALL remove it from the mistakes set (the
  store reflects current standing, not history of past attempts).
- WHILE the recorded progress store is empty (first visit, or after a reset)
  THE SYSTEM SHALL show the dashboard with zeroed stats rather than an error
  or blank screen.
- WHEN a learner triggers "reset progress" THE SYSTEM SHALL clear all
  recorded attempt outcomes after that action, with the dashboard and Review
  Mistakes mode reflecting the cleared state immediately.
- IF the browser's persistent storage is unavailable (private browsing,
  quota exceeded, storage disabled) THEN THE SYSTEM SHALL degrade to
  recording nothing for that session rather than throwing, matching the
  existing try/catch-and-swallow pattern in `client/src/exam/persistence.ts`.
- WHEN a question referenced in stored progress no longer exists in the
  current published bundle (retired or unpublished since it was recorded)
  THE SYSTEM SHALL exclude it from both the dashboard counts and Review
  Mistakes mode rather than rendering a broken entry.

## Out of scope

- Server-side persistence of attempts (`users`/`attempts`/`attempt_items`
  tables from `PLAN.md` section 7) and GitHub OAuth. Progress in this
  proposal is per-browser, not per-account, and does not follow a learner
  across devices.
- An immutable, full attempt history/audit log. The store keeps only the
  latest outcome per question, matching what "review mistakes" and a
  dashboard actually need; a full log is the server-side `attempts` table's
  job per `PLAN.md`.
- Least-recently-seen question selection for Mock exams using this attempt
  history (`client/src/exam/selectMockQuestions.ts` explicitly defers this:
  "that needs per-learner attempt history this proposal defers" — still
  true here since Mock selection algorithm changes are a separate concern
  from surfacing progress/mistakes).
- Any change to `content/schemas/`, `scripts/validate-content.mjs`, or
  question content itself.
- Cross-device sync, account deletion cascades, or any other
  `PRIVACY.md`/OAuth-era concern.
- Confidence/recency-based Review filters (explicitly out of scope per
  `PLAN.md` section 3, "Out (explicitly)").

## Open questions

- Should Mock exam attempts count toward the same per-question progress
  store as Practice mode, or be tracked separately? This proposal treats them
  as one merged store (a question is a question, regardless of which mode
  last tested it) since the issue does not distinguish, and a merged view is
  the simpler correct default for "review my mistakes."
- Should the dashboard be a new top-level nav mode (a third tab alongside
  "Practice Mode" / "Mock Exam (30 Questions)" in `client/src/App.tsx`), or
  live inside one of the existing modes? This proposal adds it as a third
  nav tab, with Review Mistakes reachable from the dashboard, since that
  matches the flat nav structure already in `App.tsx` and keeps the entry
  point discoverable without nesting.
- Exact visual design (charts vs. bars vs. plain numbers) is left to
  implementation; the acceptance criteria constrain content, not layout.
  None of this blocks the proposal — recorded as the most reasonable
  interpretation, not a blocker.
