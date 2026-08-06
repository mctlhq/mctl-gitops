# Mock exam screen: 30 questions, 60-minute timer, deferred feedback

## Context

Issue #20 asks for the Mock exam React UI: 30 questions distributed by domain
weight (6/10/6/8), a 60-minute countdown timer, and feedback deferred until the
exam is submitted. This is one of the four modes described in `README.md`
("Mock: 30 questions, 60 minutes, weighted 6 / 10 / 6 / 8 across the four
domains") and its composition is already codified in
`content/branding.yaml` (`mock.question_count: 30`, `mock.time_limit_minutes:
60`, and each domain's `mock_questions`: 6/10/6/8, summing to 30).

It matters because it is the flagship practice mode described in `PLAN.md`
section 3 ("Mock composition: 6/10/6/8 across the four domains... Selection is
least-recently-seen with shuffled options") and is one of the Phase 1 exit
criteria ("working mock; 3 complete end-to-end mock runs with zero functional
defects").

However, grounding this in the actual repository state matters just as much as
the issue text: **no application exists yet.** `CLAUDE.md` states plainly "The
application does not exist yet — Phase 0 is content pipeline and policy," and
that is verifiably true of this clone: `package.json` has no React, Vite, or
Express dependency; there is no `client/`, `src/`, `tsconfig.json`, or
`vite.config.*` anywhere in the tree; the `Dockerfile` runner stage serves a
single inline landing-page string and `/healthz`, nothing else. The only
rendering code that exists is `scripts/build-preview.mjs`, a static,
read-only, unauthenticated HTML dump of `content/` with no interactivity, no
timer, and no submission concept.

The content bank is also well short of the Phase 1 minimum: `content/questions/`
holds 20 items (across `draft`/`needs_review`/`published` statuses, unverified
here), against a stated Phase 1 exit bar of "≥80 reviewed published questions
across all four domains." A live Mock screen wired to real content today would
either fail to fill 6/10/6/8 per domain or would have to draw from
insufficiently reviewed items.

Given both facts, this proposal scopes issue #20 to what can be built now
without contradicting `CLAUDE.md`/`PLAN.md`: the Mock exam **UI component and
its client-side exam-session logic**, bootstrapped on a minimal React/Vite
client scaffold (since none exists), driven by a local/mock data adapter whose
shape matches the `content/schemas/question.schema.json` contract and the
future attempt API described in `PLAN.md` section 7. Server-side session
authority (start/expiry timestamps, persisted immutable attempts, GitHub OAuth)
is explicitly deferred — see Out of scope.

## User stories

- AS a learner I WANT to start a 30-question mock exam drawn proportionally
  from the four domains SO THAT my practice mirrors the real exam's weighting.
- AS a learner I WANT a visible 60-minute countdown timer SO THAT I practice
  under the same time pressure as the real exam.
- AS a learner I WANT to move freely between the 30 questions (answer, skip,
  change an answer, jump to any question) before submitting SO THAT I can
  manage my own pacing, as on a real exam.
- AS a learner I WANT no correct/incorrect feedback while the exam is in
  progress SO THAT the mock behaves like a real timed assessment rather than
  Practice mode.
- AS a learner I WANT the exam to submit automatically when the timer reaches
  zero SO THAT running out of time doesn't leave me in an ambiguous state.
- AS a learner I WANT a results/review screen after submission, showing my
  score and, per question, the correct answer and each option's explanation
  SO THAT the mock is a learning tool, not just a score.
- AS a learner I WANT the UI to disclose the current bank size on the mock
  start screen SO THAT I understand a second mock may repeat questions (per
  `content/branding.yaml`'s `disclose_bank_size: true` and `PLAN.md` section 3).

## Acceptance criteria (EARS)

- WHEN a learner starts a mock exam THE SYSTEM SHALL select 30 questions
  distributed 6 from domain-1, 10 from domain-2, 6 from domain-3, and 8 from
  domain-4, matching `content/branding.yaml`'s `mock_questions` values.
- WHEN a mock exam starts THE SYSTEM SHALL start a 60-minute countdown timer
  (`content/branding.yaml`'s `mock.time_limit_minutes`) and display remaining
  time to the learner, updating at least once per second.
- WHILE a mock exam is in progress THE SYSTEM SHALL NOT reveal which option is
  correct, nor show any option's explanation, for any question.
- WHEN a learner selects an option for a question THE SYSTEM SHALL record that
  selection without revealing correctness, and SHALL allow the learner to
  change it before submission.
- WHILE a mock exam is in progress THE SYSTEM SHALL allow navigation to any of
  the 30 questions in any order (not strictly linear/next-only).
- WHILE a mock exam is in progress THE SYSTEM SHALL indicate, per question,
  whether it has been answered.
- WHEN a learner submits the exam (manually, via an explicit submit action)
  THE SYSTEM SHALL stop the timer, lock all answers, and transition to the
  results view.
- IF the countdown timer reaches zero THEN THE SYSTEM SHALL submit the exam
  automatically using whatever answers were recorded at that point, with no
  further input required from the learner.
- WHEN the results view renders THE SYSTEM SHALL show the overall score and,
  for every question, the learner's selected option, the correct option, and
  every option's explanation.
- WHEN the mock start screen renders THE SYSTEM SHALL display the current
  question bank size (per `disclose_bank_size: true`) and SHALL NOT claim that
  a repeat mock draws entirely fresh questions.
- IF the learner navigates away or reloads mid-exam THEN THE SYSTEM SHALL
  preserve in-progress answers and remaining time for the current browser
  session (client-side persistence only, per Out of scope).
- WHERE fewer than the required count of published questions exists for a
  domain THE SYSTEM SHALL degrade visibly (e.g., a clear "not enough content"
  state) rather than silently short-filling the mock or crashing.

## Out of scope

- Any Express/API server work, routing, or deployment wiring. This proposal is
  UI/client-only; there is no server code to extend yet.
- GitHub OAuth, sessions, CSRF, and all authentication described in `PLAN.md`
  section 7 ("Security and session handling").
- Server-side authoritative `started_at`/`expires_at` and post-deadline
  scoring by server receipt time (`PLAN.md` section 7). This proposal's timer
  is client-side only; server-side time authority is a prerequisite the
  PLAN.md security model requires before this mode can be trusted in
  production and must be its own follow-up proposal.
- Persisting attempts to PostgreSQL (`attempts`, `attempt_items` tables) or any
  `content_version` snapshot/versioning mechanics described in `PLAN.md`
  section 4 and 7. This proposal's "results view" is computed and held
  entirely client-side for the duration of the session.
- Review-mistakes mode, Practice mode, Learn mode, and the progress dashboard —
  other modes listed in `README.md`, not part of issue #20.
- Least-recently-seen question selection (`PLAN.md` section 3) — requires
  per-learner attempt history, which requires the backend this proposal defers.
  This proposal uses uniform random selection within each domain instead (see
  design.md Alternatives).
- Wiring the client build into the Docker image / `academy.mctl.ai` deployment.
  The Dockerfile and `mctl_deploy_service` bootstrap sequence in `PLAN.md`
  section 8 explicitly ships the first image with
  `PUBLIC_ROUTES_ENABLED=false`; enabling and deploying learner routes is a
  deployment-phase decision, not this proposal's.
- Rate limiting and abuse controls (`PLAN.md` section 7) — not applicable
  without a server.
- Populating the content bank to the ≥80-question Phase 1 minimum — a content
  pipeline concern (`CONTENT-POLICY.md`), unrelated to UI work.

## Open questions

- The issue does not specify how questions are sourced at runtime (live
  content directory vs. a build-time generated bundle vs. a future API). This
  proposal assumes a build-time generated JSON bundle from `content/questions/`
  and `content/branding.yaml` (see design.md), matching the pattern already
  used by `scripts/build-preview.mjs`, since no API exists.
- The issue does not specify what happens once fewer than 80 questions exist
  and a domain cannot supply its full quota (e.g., domain-1 needs 6 but only
  has fewer published items). This proposal treats it as a degraded/empty
  state (see acceptance criteria) rather than blocking; the actual content gap
  is tracked separately, not by this proposal.
- The issue does not specify whether "deferred feedback" means literally zero
  feedback until final submission (chosen interpretation, matching "Mock" as
  distinct from "Practice" per `README.md`'s mode table) versus some partial
  feedback (e.g., an unanswered-question warning before submit, which this
  proposal does include as a UX nicety, not scoring feedback).
- The issue does not name a design system / component library. This proposal
  assumes no framework is picked yet and specifies plain CSS modules,
  deferring any design-system adoption to a separate decision, since none is
  evidenced anywhere in the repository.
- Whether the client scaffold created here (Vite + React + TypeScript) is the
  scaffold the rest of the application should build on, or whether a future
  proposal should redo it, is left to the maintainer's review — this proposal
  picks the lightest reasonable default (see design.md Alternatives) precisely
  because it is a foundational, hard-to-reverse choice.
