# Design: issue-57-feat-api-implement-attempt-sync-api-and

## Current state

- **Server** (`server/app.mjs`): a single Hono `app`, with `initDb()` called
  fire-and-forget at import time, `authRouter` mounted at `/api/auth`
  (`server/routes/auth.mjs`), a `/healthz` endpoint, an in-memory-only
  `/api/reports` (POST + GET), and a static-file fallback serving
  `client/dist`. There is no `/api/attempts` route.
- **DB layer** (`server/db.mjs`): `initDb()` creates `users`, `sessions`, and
  `attempts` tables when `DATABASE_URL` is set (`CREATE TABLE IF NOT EXISTS
  attempts (id UUID PK, user_id UUID FK -> users, question_id VARCHAR,
  domain VARCHAR, correct BOOLEAN, attempted_at TIMESTAMPTZ DEFAULT NOW())`),
  and falls back to an in-memory `memAttempts` array otherwise. Two functions
  already implement everything the API needs:
  - `recordUserAttempt({ userId, questionId, domain, correct })` — inserts one
    row (Postgres) or pushes one object (memory), returns the stored record.
  - `getUserAttempts(userId)` — Postgres: `SELECT DISTINCT ON (question_id) ...
    ORDER BY question_id, attempted_at DESC` (latest attempt per question);
    memory: filters `memAttempts` by `userId` and keeps the last-inserted entry
    per `questionId` via a `Map`. Both paths return the same shape:
    `{ questionId, domain, correct, attemptedAt }`.
  Both functions are exported but currently unused outside `tests/`.
- **Auth** (`server/routes/auth.mjs`, `server/db.mjs`): GitHub OAuth issues an
  httpOnly `mctl_session` cookie; `getSessionUser(token)` resolves it to
  `{ id, githubId, githubLogin, avatarUrl }` or `null`. `GET /api/auth/me`
  is the existing pattern for "am I logged in" checks and is already polled by
  `client/src/components/UserNav.tsx` on mount.
- **Client progress** (`client/src/services/progressStore.ts`): a plain
  (non-React) module backed by `localStorage` key `mctl_academy_progress_v1`,
  with an in-memory fallback (`memoryFallback`) for environments without
  `localStorage` (tests). `recordAttempt(questionId, domain, correct)`
  replace-or-appends into a flat `QuestionAttempt[]` array — always latest-wins
  per `questionId`, mirroring the server's `DISTINCT ON` semantics exactly.
  `getStoredAttempts`, `getMistakeQuestionIds`, `calculateProgressStats`,
  `clearProgress` all read/write the same array synchronously.
- **Only call site of `recordAttempt`**: `client/src/practice/
  usePracticeSession.ts:102`, inside `selectOption`, on the learner's first
  option selection for a question. Mock Exam (`client/src/exam/`) does not
  touch `progressStore` at all — it has its own `sessionStorage`-backed
  `persistence.ts` for in-progress exam state only.
- **Consumers of local progress**: `DashboardScreen.tsx` (via
  `calculateProgressStats`) and `App.tsx` (via `getMistakeQuestionIds`, for the
  Review Mistakes bundle and the nav badge count).

## Proposed solution

### Server: `server/routes/attempts.mjs` (new)

A new Hono sub-router, mounted the same way `authRouter` is:

```js
// server/app.mjs
import { attemptsRouter } from "./routes/attempts.mjs";
...
app.route("/api/attempts", attemptsRouter);
```

`attemptsRouter` defines two routes matching `/api/attempts` exactly (Hono
`app.route(prefix, router)` + `router.post("/", ...)` composes to that path,
the same pattern already used for `/api/auth/me`, `/api/auth/logout`):

- `POST /` — reads the `mctl_session` cookie with `getCookie` (as
  `auth.mjs` does), resolves it via `getSessionUser`. `401` if no user.
  Parses the JSON body defensively (try/catch, `400` on parse failure, mirroring
  `POST /api/reports`'s `catch` block in `app.mjs`). Validates `questionId`
  (non-empty string), `domain` (non-empty string), `correct` (boolean) — `400`
  with a descriptive `error` message on any failure, mirroring `/api/reports`'s
  `VALID_REASONS` check. On success, calls `recordUserAttempt({ userId: user.id,
  questionId, domain, correct })` and responds `201` with `{ success: true,
  attempt }`.
- `GET /` — same cookie/session resolution, `401` if no user. Calls
  `getUserAttempts(user.id)` and responds `200` with `{ attempts }` (an array,
  matching the `{ reports, count }`-style envelope already used by
  `GET /api/reports`, but attempts doesn't need a count since the array length
  suffices client-side).

This keeps `server/app.mjs` a thin composition root (mirrors how `authRouter`
was split out already) rather than growing the reports-style inline handlers
further. `server/db.mjs` needs no changes — both helpers already match this
shape exactly, including the in-memory fallback that CI's `test:server` job
exercises (no `DATABASE_URL` in `.github/workflows/ci.yml`'s `client` job).

### Client: `progressStore.ts` gains a server-sync layer

Three additions, keeping every existing export's signature and synchronous
local behavior unchanged (existing tests in
`client/src/services/__tests__/progressStore.test.ts` must keep passing
unmodified):

1. **`setSyncEnabled(enabled: boolean): void`** — a module-level flag,
   default `false`. The app flips it once, from wherever it already knows
   auth state.
2. **`recordAttempt` gains a side effect**: after writing to local storage as
   today, if the sync flag is on, fire `fetch("/api/attempts", { method:
   "POST", headers: {"Content-Type": "application/json"}, credentials:
   "same-origin", body: JSON.stringify({ questionId, domain, correct }) })`
   without `await`-ing it in the caller's path — attach a `.catch(() => {})`
   so a failed sync never throws into `usePracticeSession.selectOption`,
   matching the "local write always succeeds, network is best-effort" rule in
   `requirements.md`.
3. **`syncFromServer(): Promise<void>`** (new export) — when sync is enabled,
   `GET /api/attempts`, then for each returned attempt, compare
   `attemptedAt` against the matching local entry (if any) and keep whichever
   is newer; entries that exist only on one side are kept as-is. Writes the
   merged array back with the existing `setItem`. On any fetch failure,
   no-ops (local data is untouched) — same silent-failure posture as the rest
   of the module.

Auth wiring lives in `App.tsx`, which already owns top-level state and is the
natural place to make the one `GET /api/auth/me` call currently duplicated
implicitly by `UserNav`:

- On mount, `App.tsx` calls `GET /api/auth/me` once. `UserNav` is refactored to
  accept the resolved user as a prop instead of fetching it itself, removing
  the duplicate request. (Alternative considered and rejected below.)
- If `authenticated`, call `progressStore.setSyncEnabled(true)` then
  `await progressStore.syncFromServer()` before rendering; also loop the
  attempts already in `getStoredAttempts()` at that point through individual
  `POST /api/attempts` calls for any not already present server-side (the
  "push pre-existing local history on first sign-in" backfill from
  `requirements.md`) — simplest correct implementation is: after
  `syncFromServer()` merges server-into-local, POST every locally-stored
  attempt again. `recordUserAttempt` is a plain insert (not idempotent), so a
  naive full replay on every login would grow the table unboundedly; the
  implementation must instead only replay attempts whose `questionId` was
  *not* present in the server's `GET /api/attempts` response (i.e. genuinely
  new local history), which is bounded by bank size (~80-100 rows) and only
  fires for ids the server didn't already have.
- If not authenticated, `setSyncEnabled(false)` (already the default) and skip
  the fetch — Practice, Dashboard, and Review Mistakes behave exactly as
  today.

## Alternatives

1. **Sync check inside `progressStore.ts` itself** (module calls
   `/api/auth/me` internally on first use). Rejected: couples a
   `localStorage`-only module to network/auth concerns and to React's mount
   lifecycle, complicates the existing synchronous test suite (which
   currently needs no `fetch` mocking at all), and duplicates the auth check
   `UserNav` already makes. Keeping `progressStore.ts` sync-agnostic except
   for the explicit `setSyncEnabled`/`syncFromServer` seam keeps it testable
   with plain `fetch` mocks only in new tests, not existing ones.
2. **Bulk sync endpoint (`POST /api/attempts/bulk` taking an array)** instead
   of looping single `POST /api/attempts` calls for backfill. Rejected for
   this issue: adds a second server code path and a second shape of
   `recordUserAttempt` (batch insert) for a one-time, bounded-size (~100 rows)
   operation; the individual-call loop reuses the exact same endpoint and
   validation the issue asks for ("POST /api/attempts"), and bank size makes
   the N-request cost negligible. Can be revisited if bank size grows well
   past MVP's 80-100 question target in `PLAN.md`.
3. **Store the full attempt history server-side and let the client always
   trust the server as authoritative** (no local/server merge, server always
   wins). Rejected: breaks the "signed out still fully works, sign-in is
   optional" requirement, and discards a learner's local history on their
   first sign-in if the merge is not symmetric — the "later `attemptedAt`
   wins" rule handles both directions (local-only history predating sign-in,
   and server-only history from a different device) without a special case
   for first login.
4. **Add attempts handling as more inline routes in `app.mjs`** (like
   `/api/reports`) instead of a new `server/routes/attempts.mjs` router.
   Rejected: `auth.mjs` already established the "one router file per
   resource" convention for anything needing session lookup; `/api/reports`
   predates that convention and doesn't need auth, so it isn't a precedent to
   extend.

## Platform impact

- **Migrations**: none. The `attempts` table, its columns, and both DB helper
  functions already exist in `server/db.mjs`'s `initDb()` and are exercised by
  `tests/server.test.mjs` / `tests/auth.test.mjs` patterns today (though not
  yet through HTTP). No `ALTER TABLE`, no new table.
- **Backward compatibility**: purely additive. `/api/reports`, `/api/auth/*`,
  `/healthz`, and the static-file fallback are untouched. `progressStore.ts`'s
  existing exports keep their current signatures and fully synchronous,
  network-free behavior when `setSyncEnabled` is never called (i.e. for any
  code path — including all existing tests — that doesn't opt in).
- **Resource impact**: negligible. One new small router file; `GET
  /api/attempts` is a single indexed-ish query (`user_id` foreign key) with
  `DISTINCT ON` over a per-user row count bounded by bank size (~80-100
  questions since re-attempts overwrite the "latest" view but the table itself
  grows with every attempt — retention/pruning is not addressed by this
  issue and is out of scope).
- **Risks + mitigations**:
  - *Risk*: a broken or slow `/api/attempts` call blocking or breaking
    Practice mode. *Mitigation*: `recordAttempt`'s server POST is
    fire-and-forget with a swallowed `.catch`; `syncFromServer` failures
    no-op and leave local data intact — matches `requirements.md`'s explicit
    acceptance criterion.
  - *Risk*: double-counting or unbounded growth of the `attempts` table from
    the backfill-on-login replay. *Mitigation*: backfill only POSTs
    `questionId`s absent from the server's own `GET /api/attempts` response,
    not a full replay every login (see Proposed solution above).
  - *Risk*: this service is not yet deployed (`PLAN.md` section 8, "Not yet
    onboarded"), so there is no live `DATABASE_URL` / Vault wiring yet to
    verify against in production. *Mitigation*: none needed for this issue —
    the in-memory fallback path is what CI exercises today and is what this
    design is built and tested against; wiring `mctl_provision_database` and
    `secret_env_vars` remains tracked separately in `PLAN.md`.
  - *Risk*: `server/routes/auth.mjs`'s cookie-reading pattern
    (`getCookie(c, "mctl_session")` then `getSessionUser`) is duplicated in
    the new router. *Mitigation*: acceptable duplication for two call sites;
    if a third authenticated route appears, extract a small
    `requireSession` Hono middleware then — not warranted for this issue
    alone (kept as a task note, not done preemptively).
