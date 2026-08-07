# Tasks: issue-57-feat-api-implement-attempt-sync-api-and

- [ ] 1. Create `server/routes/attempts.mjs` with a Hono router exporting
      `attemptsRouter`, implementing `POST /` and `GET /` as described in
      `design.md` (cookie-based session resolution via `getCookie` +
      `getSessionUser`, 401 when unauthenticated, 400 on invalid
      `POST` body, calling `recordUserAttempt` / `getUserAttempts` from
      `server/db.mjs`) — DoD: file exists, exports `attemptsRouter`, no
      changes to `server/db.mjs` required (verify by grep — both helper
      functions are unchanged).
- [ ] 2. Mount the router in `server/app.mjs`: `import { attemptsRouter } from
      "./routes/attempts.mjs"` and `app.route("/api/attempts",
      attemptsRouter)`, placed next to the existing `app.route("/api/auth",
      authRouter)` line (depends on 1) — DoD: `POST /api/attempts` and
      `GET /api/attempts` are reachable; `/api/reports`, `/api/auth/*`,
      `/healthz` still respond exactly as before.
- [ ] 3. Add `client/src/services/progressStore.ts` exports `setSyncEnabled`
      and `syncFromServer`, and extend `recordAttempt` with the
      fire-and-forget `POST /api/attempts` side effect, per `design.md`
      (depends on 2) — DoD: all existing exports keep their current
      signatures; when `setSyncEnabled` is never called, behavior is
      byte-for-byte identical to today (no `fetch` call is made).
- [ ] 4. Wire auth-awareness into `client/src/App.tsx`: resolve
      `GET /api/auth/me` once on mount, call
      `progressStore.setSyncEnabled(...)` accordingly, and on authenticated
      mount run the merge-then-backfill sequence from `design.md`
      (`syncFromServer()` then POST only `questionId`s missing from the
      server's response) (depends on 3) — DoD: signed-out app behavior is
      pixel- and network-identical to pre-change `App.tsx`; signed-in app
      makes exactly one `GET /api/auth/me`, one `GET /api/attempts`, and at
      most `N` backfill `POST /api/attempts` calls (`N` = local attempts not
      already on the server) on mount.
- [ ] 5. Refactor `client/src/components/UserNav.tsx` to accept the resolved
      user (and loading state) as props instead of fetching
      `/api/auth/me` itself, since `App.tsx` now owns that fetch (depends on
      4) — DoD: no duplicate `/api/auth/me` request fires on app load;
      `UserNav`'s rendered output and sign-in/sign-out behavior are
      unchanged.

## Tests

- [ ] T1. `tests/server.test.mjs` or a new `tests/attempts.test.mjs`:
      `POST /api/attempts` without a session cookie returns `401`.
- [ ] T2. Same file: `POST /api/attempts` with a valid session cookie (create
      a user + session via `upsertUser` / `createSession` as
      `tests/auth.test.mjs` already does) and a valid body returns `201` and
      the stored attempt; a subsequent `GET /api/attempts` with the same
      cookie includes it.
- [ ] T3. `POST /api/attempts` with a valid session but a missing/invalid
      field (`questionId` absent, `correct` not boolean) returns `400` and
      does not appear in a following `GET /api/attempts`.
- [ ] T4. `GET /api/attempts` without a session cookie returns `401`.
- [ ] T5. Re-recording an attempt for the same `questionId` (two `POST`s,
      different `correct` values) and then `GET /api/attempts` returns only
      the latest one for that `questionId` (exercises `getUserAttempts`'s
      `DISTINCT ON` / in-memory last-wins behavior through the new HTTP
      layer, not just at the `db.mjs` unit level).
- [ ] T6. `client/src/services/__tests__/progressStore.test.ts`: with sync
      disabled (default), `recordAttempt` makes no `fetch` call (spy on
      global `fetch`, assert not called) — proves existing behavior is
      unchanged.
- [ ] T7. New client test: with `setSyncEnabled(true)`, `recordAttempt` calls
      `fetch("/api/attempts", ...)` with the expected method/body, and a
      rejected/failed fetch does not throw out of `recordAttempt` and does
      not remove the already-written local entry.
- [ ] T8. New client test: `syncFromServer()` merges a mocked
      `GET /api/attempts` response into local storage, keeping the
      later-`attemptedAt` record per `questionId` in both directions
      (server-newer-than-local and local-newer-than-server cases).
- [ ] T9. Confirm `npm run test:server` (CI's `client` job, no
      `DATABASE_URL` set) still passes end to end against the in-memory
      fallback — no test in T1-T5 may assume a live Postgres connection.

## Rollback

- Server: revert the two-line mount in `server/app.mjs` and delete
  `server/routes/attempts.mjs`; `server/db.mjs` is never modified by this
  change, so no data-layer rollback is needed. The `attempts` table and its
  rows are harmless to leave in place (or in the in-memory store, which is
  process-lifetime only) even if the routes are removed.
- Client: revert `progressStore.ts`, `App.tsx`, and `UserNav.tsx` to their
  pre-change versions (single commit revert, since task 3-5 touch only these
  three files plus new tests). Because sync is fully additive and gated
  behind `setSyncEnabled`, reverting the client alone (leaving the server
  routes live) is also a safe intermediate state — signed-in learners simply
  stop syncing and fall back to local-only progress, identical to today's
  behavior.
- No feature flag beyond the code path itself is introduced; if a partial
  rollback is needed under time pressure, disabling sync client-side (task
  3-4 revert) while leaving the server endpoints live is non-destructive and
  is the recommended first step over a full revert.
