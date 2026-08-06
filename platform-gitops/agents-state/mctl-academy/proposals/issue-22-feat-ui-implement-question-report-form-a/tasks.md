# Tasks: issue-22-feat-ui-implement-question-report-form-a

- [ ] 1. Add `server/` scaffold: `app.ts` (Express factory), `db.ts` (`pg`
      Pool from `DATABASE_URL`), `/healthz` route moved out of the
      Dockerfile inline stub — DoD: `node --test` or a manual `curl
      localhost:8080/healthz` returns the same `{status:"ok",...}` payload
      the current inline server returns; TypeScript build produces
      `dist/server`.
- [ ] 2. Add `server/migrations/0001_question_reports.sql` and
      `scripts/migrate.mjs` that applies pending migrations against
      `DATABASE_URL` on startup — DoD: running `node scripts/migrate.mjs`
      twice against a fresh Postgres is idempotent (second run is a no-op,
      exits 0); `question_reports` table matches the schema in design.md.
- [ ] 3. Implement `GET /api/questions` (depends on 1) reading
      `content/questions/*.yaml` at process start and returning
      `[{id, status}]` — DoD: endpoint returns every question id present in
      `content/questions/`, matches `question.schema.json`'s `id` pattern
      for each entry, no question body/answer text is exposed by this
      route.
- [ ] 4. Implement `POST /api/reports` (depends on 2, 3) with `ajv`
      validation of `question_id` (must be a known id from task 3's loaded
      set), `reason` (fixed enum), `details` (optional, <=2000 chars) —
      DoD: valid request inserts one row and returns `201 {id}`; missing/
      invalid `question_id` returns `404`; missing/invalid `reason` or
      oversized `details` returns `400`; no partial inserts on any
      rejected path (verified by a row-count assertion in the test in T3).
- [ ] 5. Add IP-keyed in-memory rate limiting middleware on
      `POST /api/reports` (depends on 4) — DoD: exceeding the configured
      threshold within the window returns `429` and does not insert a row;
      threshold/window configurable via `RATE_LIMIT_MAX` /
      `RATE_LIMIT_WINDOW_MS` env vars with sane defaults if unset.
- [ ] 6. Add `client/` Vite+React scaffold: `main.tsx`, `App.tsx`, build
      config producing `dist/client` — DoD: `npm run build` (or equivalent
      new script) produces static assets; `server/app.ts` serves them for
      non-API routes.
- [ ] 7. Implement `QuestionBrowser` page (depends on 3, 6) listing question
      ids/status from `GET /api/questions` — DoD: page renders the full
      list returned by the API with no client-side filtering by status
      (status is shown, not hidden) matching README's stated intent that
      the answer key is public.
- [ ] 8. Implement `ReportQuestionButton` + `ReportQuestionForm` (depends on
      4, 7) attached to each item in `QuestionBrowser` — DoD: all EARS
      criteria in requirements.md are met: form opens pre-filled with
      `question_id`, reason is required, details optional, submit disabled
      while in flight, success shows confirmation and closes the form,
      failure shows inline error and preserves input.
- [ ] 9. Update `Dockerfile`: build both `build:preview` (unchanged) and the
      new client build; runner stage runs the compiled `server/app.ts`
      instead of the inline `node -e` stub (depends on 1, 6) — DoD: `docker
      build` succeeds; running the built image serves `/healthz`, the
      client app at `/`, and both new API routes; the Phase 0 preview
      artifact at `dist/preview` is still produced by CI unchanged.
- [ ] 10. Update `package.json` scripts and add a CI job (or extend
      `ci.yml`) to build and type-check `server/` and `client/` on every PR
      (depends on 1, 6) — DoD: CI fails on a TypeScript error or failed
      build in either workspace; existing content-lint/content-test/preview
      jobs are untouched.
- [ ] 11. Document the deployment prerequisite in `README.md`'s Status
      section or a short note in `PLAN.md`'s bootstrap order — DoD: it is
      written down that merging this PR does not make the feature live;
      `mctl_deploy_service action=onboard`, `mctl_provision_database`, and
      enabling `PUBLIC_ROUTES_ENABLED` are still required (execution is out
      of scope for this proposal).

## Tests

- [ ] T1. `POST /api/reports` with a valid `question_id` (one that exists
      in `content/questions/`), a valid `reason`, and no `details` inserts
      exactly one row and returns `201`.
- [ ] T2. `POST /api/reports` with `details` present and under 2000 chars
      persists `details` verbatim; with `details` over 2000 chars returns
      `400` and inserts no row.
- [ ] T3. `POST /api/reports` with an unknown `question_id` returns `404`
      and inserts no row (assert row count unchanged).
- [ ] T4. `POST /api/reports` with a `reason` outside the fixed enum
      returns `400` and inserts no row.
- [ ] T5. Sending more than `RATE_LIMIT_MAX` requests from the same client
      within `RATE_LIMIT_WINDOW_MS` returns `429` on the excess requests
      and does not insert rows for them.
- [ ] T6. `GET /api/questions` returns an entry for every file under
      `content/questions/*.yaml`, with ids matching the schema's
      `^q-[a-z0-9]{12}$` pattern, and returns no `stem`/`options`/`evidence`
      fields.
- [ ] T7. Client: submitting the report form with the submit button already
      disabled (in-flight) does not fire a second request (simulate a
      double click / rapid Enter).
- [ ] T8. Client: a simulated network failure on submit leaves the form
      open with the previously entered `reason`/`details` still populated,
      and shows an inline error.
- [ ] T9. `scripts/migrate.mjs` run twice against the same database is
      idempotent (no error, no duplicate table/index creation).
- [ ] T10. Existing content-pipeline tests (`npm run test:content`) and
      `npm run lint:content` still pass unmodified — this proposal must not
      touch `content/`, `content/schemas/`, or the lint script.

## Rollback

- All new code lives under `server/`, `client/`, and
  `server/migrations/`, plus edits to `Dockerfile`, `package.json`, and
  `ci.yml`. Reverting the merge commit (per `CLAUDE.md`, merges are never
  squashed, so this is a clean single revert) removes all of it and
  restores the prior inline-stub Dockerfile behavior.
- The migration is additive only (`CREATE TABLE IF NOT EXISTS`) — no
  existing table or column is altered or dropped, so no down-migration is
  required to make a code rollback safe. If the `question_reports` table
  needs to be removed independently of a code revert (e.g. to fully undo a
  bad deploy), that is a manual `DROP TABLE question_reports;` against the
  provisioned database — deliberately not automated, since an automatic
  down-migration on a table that may already hold real learner reports is
  a data-loss risk this proposal should not introduce casually.
- Because this proposal does not itself call `mctl_deploy_service` or
  `mctl_provision_database` (see design.md, Platform impact), there is no
  live deployment to roll back as a consequence of merging this PR alone;
  rollback of the eventual deployment (once onboarded) is the standard
  `mctl_rollback_service` path against the prior image tag.
