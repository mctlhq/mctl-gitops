# Tasks: issue-22-feat-ui-implement-question-report-form-a

- [ ] 1. Add `question_reports` table schema to PostgreSQL migration or initial setup in `server/db.mjs` — DoD: `question_reports` table exists in PostgreSQL with columns `id`, `question_id`, `reason`, `details`, `user_id`, `created_at`.
- [ ] 2. Update Hono `POST /api/reports` endpoint in `server/app.mjs`:
      - Validate `question_id` against existing questions (loaded from `content/questions/` or content bundle).
      - Reconcile reason enum (`typo`, `factual_error`, `unclear_stem`, `bad_distractor`, `other`).
      - Support optional `details` string up to 2000 chars.
      - Save valid report to PostgreSQL `question_reports` table.
      - Add IP/User rate limiting on `POST /api/reports`.
      - DoD: valid request inserts row into DB and returns 201; invalid `question_id` returns 404; invalid payload or details > 2000 chars returns 400.
- [ ] 3. Enhance `client/src/components/ReportModal.tsx` to handle the report flow gracefully (error messages, loading state, 2000 char details limit).
- [ ] 4. Add integration unit tests for `POST /api/reports` endpoint in `server/`.

## Tests

- [ ] T1. `POST /api/reports` with valid `question_id` and `reason` inserts row into `question_reports` table and returns 201.
- [ ] T2. `POST /api/reports` with unknown `question_id` returns 404 and does not insert row.
- [ ] T3. `POST /api/reports` with `details` > 2000 chars returns 400.
- [ ] T4. `npm run test` in server & client passes.

## Rollback

- Revert the merge commit on `main`.
