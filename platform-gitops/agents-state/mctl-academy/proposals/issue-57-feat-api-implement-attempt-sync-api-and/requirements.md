# Attempt sync API and persistent progress backend

## Context

`mctl-academy` today tracks practice progress entirely client-side: every time a
learner selects an option in Practice mode, `usePracticeSession` (in
`client/src/practice/usePracticeSession.ts`) calls
`recordAttempt(questionId, domain, correct)` in
`client/src/services/progressStore.ts`, which writes to `localStorage` under the
key `mctl_academy_progress_v1`. The Progress Dashboard
(`client/src/dashboard/DashboardScreen.tsx`) and the Review Mistakes flow
(`client/src/App.tsx`, via `getMistakeQuestionIds`) both read exclusively from that
local store. There is no server persistence: progress is lost on a new device, a
cleared browser, or a new browser profile.

The server (`server/`) already has GitHub OAuth (`server/routes/auth.mjs`,
mounted at `/api/auth`) producing an httpOnly `mctl_session` cookie, and
`server/db.mjs` already defines a PostgreSQL `attempts` table (id, user_id,
question_id, domain, correct, attempted_at) plus two helper functions,
`recordUserAttempt({ userId, questionId, domain, correct })` and
`getUserAttempts(userId)`, complete with an in-memory fallback path for when
`DATABASE_URL` is unset. Neither helper is wired to an HTTP route — `server/app.mjs`
only mounts `/api/auth`, `/healthz`, and `/api/reports`. This issue is the wiring:
expose `POST /api/attempts` and `GET /api/attempts` in the Hono app, and make the
client's `progressStore` sync with them for signed-in learners, so progress
survives across devices and sessions while remaining fully usable signed out.

## User stories

- AS a signed-in learner I WANT my practice attempts saved to the server SO THAT
  my progress and mistake history survive a browser change or a cleared cache.
- AS a signed-in learner who has practiced before signing in I WANT my existing
  local progress pushed to the server on first sign-in SO THAT I do not lose
  history I already built up anonymously.
- AS a signed-in learner opening the app on a new device I WANT my server-recorded
  attempts pulled down and merged into my local progress SO THAT the Dashboard and
  Review Mistakes screens reflect my full history, not just this device's.
- AS an anonymous (signed-out) learner I WANT Practice mode and the Dashboard to
  keep working exactly as they do today SO THAT sign-in is optional, not required.

## Acceptance criteria (EARS)

- WHEN an authenticated request (valid `mctl_session` cookie) sends
  `POST /api/attempts` with a JSON body `{ questionId, domain, correct }` THE
  SYSTEM SHALL persist the attempt via `recordUserAttempt` and respond `201` with
  the stored attempt.
- IF `POST /api/attempts` is called without a valid session cookie THEN THE SYSTEM
  SHALL respond `401` and SHALL NOT write an attempt.
- IF `POST /api/attempts`'s body is missing `questionId`, `domain`, or a boolean
  `correct` THEN THE SYSTEM SHALL respond `400` and SHALL NOT write an attempt,
  matching the existing validation style of `POST /api/reports` in
  `server/app.mjs`.
- WHEN an authenticated request sends `GET /api/attempts` THE SYSTEM SHALL return
  `200` with the latest attempt per `question_id` for that user (i.e. exactly
  `getUserAttempts(userId)`'s existing `DISTINCT ON (question_id) ... ORDER BY
  attempted_at DESC` semantics), each with `questionId`, `domain`, `correct`,
  `attemptedAt`.
- IF `GET /api/attempts` is called without a valid session cookie THEN THE SYSTEM
  SHALL respond `401`.
- WHILE `DATABASE_URL` is not configured THE SYSTEM SHALL continue serving both
  endpoints correctly against `server/db.mjs`'s existing in-memory fallback
  (`memAttempts`), matching how `test:server` already runs in CI without a
  database (`.github/workflows/ci.yml`, `client` job).
- WHEN the client app loads and the learner is authenticated (per the existing
  `GET /api/auth/me` check already used by `UserNav`) THE SYSTEM SHALL fetch
  `GET /api/attempts` and merge the results into local progress, keeping, per
  `questionId`, whichever of the local or server record has the later
  `attemptedAt`.
- WHEN a learner who is authenticated answers a practice question (the existing
  `recordAttempt` call site in `usePracticeSession.ts`) THE SYSTEM SHALL also send
  that attempt to `POST /api/attempts`, in addition to the existing local
  `localStorage` write, without blocking the UI on the network call.
- IF the learner is not authenticated THEN THE SYSTEM SHALL behave exactly as it
  does today: `recordAttempt` writes to `localStorage` only, no network call is
  made, and `calculateProgressStats` / `getMistakeQuestionIds` read local data
  only.
- IF a `POST /api/attempts` sync call fails (network error, 401 from an expired
  session, 5xx) THEN THE SYSTEM SHALL leave the already-written local
  `localStorage` copy intact and SHALL NOT surface an error to the learner
  (matches the existing silent-catch pattern in `progressStore.ts`'s `getItem` /
  `setItem` / `recordAttempt`).

## Out of scope

- Mock Exam attempts (`client/src/exam/`). `MockFlow` / `MockResultsScreen` do not
  call `progressStore.recordAttempt` today and this proposal does not add that —
  mock-exam persistence is the richer `attempts` (immutable) / `attempt_items` /
  `question_reports` schema described in `PLAN.md` (around line 278), a separate,
  larger design (server-side timing/expiry, immutable snapshots of rendered
  questions) that this issue's scaffolding does not attempt to satisfy.
- Any change to the `attempts` table schema in `server/db.mjs`'s `initDb()` — the
  table, columns, and both helper functions already exist and match what this
  issue needs.
- A bulk/batch sync endpoint. First-sign-in backfill of pre-existing local
  attempts is handled by looping individual `POST /api/attempts` calls
  client-side (bank size is on the order of 80-100 questions per `PLAN.md`
  Phase 1 exit criteria, so this is cheap).
- Conflict resolution UI or manual merge review — the "later `attemptedAt` wins"
  rule is silent and automatic.
- Deployment / onboarding of the service (`mctl_deploy_service`,
  `mctl_provision_database`) — `PLAN.md` section 8 already documents this and the
  service is not yet onboarded; this issue only prepares the code.
- Rate limiting or abuse protection on `/api/attempts` beyond requiring a valid
  session, consistent with `/api/reports` having none today.

## Open questions

- Should `GET /api/attempts` responses include attempts for retired/unpublished
  questions? The issue does not say. Resolved as: yes, return everything recorded
  for the user — filtering by current publication status is a Dashboard/client
  concern (`calculateProgressStats` already joins against the live bundle and
  silently ignores attempts for question ids not present in it), not an API
  concern.
- Should the server reject an attempt whose `questionId` is not in the current
  published content bundle? The issue does not say, and `recordUserAttempt` has no
  such check today (it takes `questionId` as an opaque string, same as
  `POST /api/reports`'s `question_id`). Resolved as: no server-side bundle
  validation, matching existing `/api/reports` behavior — keeps the API stateless
  with respect to content and avoids a content-bundle import in `server/`.
- Exact wire shape of the sync merge (whether the client does a full local
  overwrite-with-server-if-newer, or a real per-record merge) is an implementation
  detail left to `design.md` rather than the issue; captured there.
