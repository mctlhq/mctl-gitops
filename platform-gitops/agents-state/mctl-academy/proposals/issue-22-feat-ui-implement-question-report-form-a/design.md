# Design: issue-22-feat-ui-implement-question-report-form-a

## Current state

Verified by reading the clone directly:

- `package.json` has exactly three runtime dependencies: `ajv`,
  `ajv-formats`, `yaml`. No `express`, `react`, `vite`, `pg`, or any HTTP
  framework. Scripts are `lint:content`, `verify:evidence`,
  `snapshot:capture`, `test:content`, `build:preview` — all content-pipeline
  tooling, none of them an app server.
- `Dockerfile` builds `npm run build:preview` (the static HTML preview) and
  then runs a literal inline `node -e "..."` HTTP server whose only two
  routes are `/healthz` and a hardcoded landing-page string. This is the
  entire "application" that exists today.
- `scripts/build-preview.mjs` renders each question from
  `content/questions/*.yaml` as a static `<article class="q">` block. Its
  own header comment: "No application, no database, no login... Phase 0
  exists to prove the content pipeline produces something coherent." It is
  explicitly not meant to carry live interactivity.
- There is no `client/`, `server/`, `src/`, `migrations/`, or `db/`
  directory anywhere in the repo (confirmed via a full non-node_modules
  directory listing).
- `content/questions/*.yaml` is the only source of question data, validated
  against `content/schemas/question.schema.json` (2020-12, ajv). Each
  question has a stable `id` matching `^q-[a-z0-9]{12}$`, a `status` enum
  (`draft|needs_review|published|retired`), and no runtime database
  representation — `PLAN.md` section 4's "Publication" step (content ->
  immutable manifest -> `content_versions`/`questions` tables) is documented
  but not implemented anywhere in this repo.
- `PLAN.md` section 7 specifies the target shape once built: "Single
  TypeScript container: React/Vite client built to static assets, served by
  Express alongside the API. PostgreSQL on the shared CNPG cluster," with
  `question_reports` as one of the core tables, and "rate limits on
  submission and report endpoints" as a required control.
- `PLAN.md` section 8 documents the deployment bootstrap order: onboard with
  `AUTH_ENABLED=false` / `PUBLIC_ROUTES_ENABLED=false` first, provision the
  database as a separate `mctl_provision_database` call, then flip auth on
  later. No `secret_env_vars`/`env_vars` have been configured for this
  service yet (`mctl_get_service_config` would 404 — the service is not
  onboarded).
- CI (`.github/workflows/ci.yml`) currently only runs content lint, content
  tests, and the preview build. There is no build/test job for application
  code, and no `claude-review.yml` trigger has been exercised against app
  code in this repo yet — per `CLAUDE.md`, `claude-review.yml` covers
  "everything else (code, schemas, CI, deployment)".

## Proposed solution

This proposal is the first application code in the repo. It bootstraps the
minimal vertical slice PLAN.md section 7 describes, scoped tightly to what
issue #22 needs, and nothing else:

**1. `server/` — Express API, TypeScript, replacing the Dockerfile's inline
stub.**
- `server/app.ts`: Express app factory. Keeps `/healthz` (moved out of the
  inline `node -e` string). Mounts `GET /api/questions` (read-only, returns
  `{ id, status }` for every question under `content/questions/*.yaml` —
  enough for the client to validate a `question_id` and populate a picker;
  full question rendering stays out of scope) and `POST /api/reports`.
  Serves the built client's static assets (`dist/client`) for everything
  else, matching "served by Express alongside the API" in `PLAN.md`.
- `server/routes/reports.ts`: `POST /api/reports`. Validates body against a
  small schema (reusing `ajv` — already a dependency, keeps the "no new
  validation library" pattern the content pipeline already established):
  `question_id` (string, must match an id present in the content set
  loaded at startup/watched — see Alternatives for why not a DB FK yet),
  `reason` (enum: `incorrect_answer`, `ambiguous_wording`,
  `citation_mismatch`, `typo_or_formatting`, `other`), `details` (optional
  string, capped at 2000 chars — same order of magnitude as the question
  `stem` cap in `question.schema.json`). Inserts a row via `server/db.ts`
  and returns `201 { id }`.
- `server/db.ts`: a thin `pg` `Pool` wrapper reading `DATABASE_URL` from the
  environment. No ORM introduced — the existing project has zero ORM/query
  builder precedent, and one table with one insert path does not justify
  adding one.
- `server/middleware/rate-limit.ts`: a small in-memory token-bucket keyed by
  client IP, applied only to `POST /api/reports` (and left ready to apply
  to the future submission endpoint, per `PLAN.md` section 7). In-memory is
  an explicit, documented limitation for a single-replica service — see
  Platform impact.
- Migration: `server/migrations/0001_question_reports.sql`, applied by a
  new `scripts/migrate.mjs` (same style as the existing `scripts/*.mjs`
  content tools — plain Node, no migration framework) run once at container
  start before the HTTP listener binds. Schema:
  ```sql
  CREATE TABLE IF NOT EXISTS question_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    details TEXT,
    reporter_user_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  CREATE INDEX IF NOT EXISTS question_reports_question_id_idx
    ON question_reports (question_id);
  ```
  `reporter_user_id` is nullable and unused until GitHub OAuth exists;
  included now so the column does not require a later migration plus a
  backfill decision.

**2. `client/` — minimal React/Vite scaffold, one view.**
- `client/src/main.tsx`, `client/src/App.tsx`: Vite-built React app,
  matching `PLAN.md` section 7's "React/Vite client built to static
  assets."
- `client/src/pages/QuestionBrowser.tsx`: fetches `GET /api/questions`,
  renders a plain list of question ids and statuses — a stand-in for the
  not-yet-built Practice/Learn views, existing only so the Report action has
  somewhere real to attach in a running app (as opposed to the static,
  database-less preview).
- `client/src/components/ReportQuestionButton.tsx` +
  `ReportQuestionForm.tsx`: the action from the issue title. Button opens a
  form (reason select, optional details textarea, pre-filled hidden
  `question_id`); submit calls `POST /api/reports`; success shows a
  confirmation and closes the form; failure shows an inline error and keeps
  the input (per requirements.md's EARS criteria); submit is disabled while
  the request is in flight.
- Build wiring: `vite build` outputs to `dist/client`; `Dockerfile` builds
  both the existing content preview (`build:preview`, unchanged — still the
  Phase 0 artifact) and the new client build, and the runner stage serves
  `dist/client` via the new Express app instead of the inline `node -e`
  stub.

**3. Config, per the two platform gotchas in `CLAUDE.md`.**
- `DATABASE_URL` arrives via `mctl_provision_database`'s own `envFrom`
  secret (already colon-safe, per `PLAN.md` section 8) — no manual
  `secret_env_vars` needed for it.
- `RATE_LIMIT_MAX` / `RATE_LIMIT_WINDOW_MS` (colon-free scalars) go in the
  plain `env:` block if they need to be tunable without a rebuild;
  otherwise they default in code and no config entry is needed at all,
  which is the safer choice given `env:` has been wiped by
  `action=deploy` before.

## Alternatives

1. **Attach the Report action to the existing static preview
   (`scripts/build-preview.mjs`) instead of building a new client.**
   Rejected: that script's own comment states it is deliberately
   database-less and login-less as a Phase 0 proof artifact; wiring a live
   `fetch()` to a stateful API into it conflates two things `PLAN.md`
   treats as separate phases (static content proof vs. the real
   application), and the preview is `noindex` and rebuilt fresh on every CI
   run, so anything stateful bolted onto it would be fighting the grain of
   the file.
2. **Make `question_reports.question_id` a foreign key into a `questions`
   table.** Rejected for now: no `questions` table exists because the
   content-versions publish pipeline (`PLAN.md` section 4) that would
   populate it is unbuilt. Forcing that table into existence as a
   side-effect of a report-form issue would be scope creep disguised as
   correctness. Validating `question_id` against `content/questions/*.yaml`
   at request time gets the same practical guarantee (`404` on an unknown
   id) without inventing the publish pipeline's schema ahead of the work
   that is supposed to define it. Flagged as an explicit follow-up once
   that pipeline lands.
3. **Use an ORM/query builder (Prisma, Drizzle, Knex) instead of raw `pg` +
   hand-written SQL migrations.** Rejected: the repo has zero precedent for
   one, the entire schema surface this proposal touches is a single table,
   and `scripts/*.mjs` already establishes "plain Node script, no
   framework" as the house style for anything not content-schema
   validation. Revisit if/when `users`, `attempts`, and `attempt_items`
   arrive and the schema surface actually justifies the dependency.
4. **Skip rate limiting in this proposal and add it later.** Rejected:
   `PLAN.md` section 7 lists it as a named requirement for exactly this
   endpoint, and an unauthenticated public POST endpoint with no rate limit
   is a concrete abuse vector from day one, not a hardening pass to defer.

## Platform impact

- **Migrations.** New: `server/migrations/0001_question_reports.sql`,
  applied by `scripts/migrate.mjs` at container start. Idempotent
  (`CREATE TABLE IF NOT EXISTS`), safe to run on every boot including
  scaled-to-N-replica restarts.
- **Backward compatibility.** N/A — first application code; nothing to
  break. The Dockerfile's replacement of the inline stub server is a
  behavior change (real Express app instead of a literal string), but the
  `/healthz` contract is preserved.
- **Resource impact.** `PLAN.md` section 8 already reserved capacity for
  this service (`50m`/`128Mi` request, `200m`/`512Mi` limit) — this
  proposal's endpoint count (three: `/healthz`, `GET /api/questions`,
  `POST /api/reports`) fits comfortably; no quota change needed.
- **New dependency surface.** `express`, `pg`, `react`, `react-dom`, `vite`,
  `@vitejs/plugin-react`, plus TypeScript build tooling for both
  `server/` and `client/`. All are mainstream, widely-audited packages;
  none overlaps with anything already in `package.json`.
- **Risk: in-memory rate limiting does not survive a restart or scale past
  one replica.** Acceptable at MVP scale (single replica, `PLAN.md`
  capacity section implies no autoscaling configured for this service yet)
  but explicitly not a durable control. Mitigation: document the limitation
  in code comments and revisit with a shared store (e.g. Postgres-backed
  counter, since Redis is not established platform infrastructure here) if
  the service scales beyond one replica.
- **Risk: unauthenticated endpoint accepting arbitrary `details` text.**
  Mitigated by length cap (2000 chars) and by the fact that reports are
  never rendered back as HTML anywhere in this proposal (no report-viewing
  UI is built) — output-side XSS is not reachable from this change. Input
  is still parameterized via `pg`'s prepared statements, not
  string-concatenated SQL.
- **Risk: `question_id` validated against a YAML file read at request time
  or process start.** `content/questions/*.yaml` only changes via a content
  PR merge and a redeploy (no publish pipeline exists to update it live),
  so a snapshot loaded at process start is acceptable; document that a
  report against a question id added after the process started requires a
  restart to validate, consistent with how `content/branding.yaml` is
  already treated as build-time data by `scripts/build-preview.mjs`.
- **Deployment sequencing.** This proposal is code only. Actually exposing
  it requires, in order (per `PLAN.md` section 8, not executed by this
  proposal): `mctl_deploy_service action=onboard` for `mctl-academy` in
  `labs` (does not exist yet — `mctl_get_service_config` would 404 today),
  then `mctl_provision_database`, then a config update setting
  `PUBLIC_ROUTES_ENABLED=true` (or equivalent) so the question browser and
  report form are reachable. Onboarding itself is out of scope for this
  proposal but is a hard prerequisite the implementer/reviewer should be
  aware of — merging this PR does not make the feature live.
