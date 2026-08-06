# Design: issue-20-feat-ui-implement-mock-exam-screen-30-qu

## Current state

Verified by reading the clone, not assumed:

- `package.json` (root, only manifest in the repo) lists exactly three runtime
  dependencies: `ajv`, `ajv-formats`, `yaml`. No `react`, `react-dom`, `vite`,
  `express`, or any test/build tool for a client app. Scripts are
  `lint:content`, `verify:evidence`, `snapshot:capture`, `test:content`,
  `build:preview` — all content-pipeline tooling, none of them a dev server.
- There is no `client/`, `src/`, `app/`, `tsconfig.json`, or `vite.config.*`
  anywhere in the tree (`find . -iname '*.tsx' -o -iname 'tsconfig*' -o -iname
  'vite.config*'` returns nothing).
- `Dockerfile`'s runner stage `CMD` is a single inline Node `http.createServer`
  call that serves a hardcoded HTML string on `/` and a JSON health payload on
  `/healthz`. It runs `npm run build:preview` in the builder stage and copies
  `dist/` (the static preview) and `content/` into the final image, but the
  runtime never serves `dist/` or does any routing. There is no Express
  instance anywhere.
- `scripts/build-preview.mjs` is the only rendering code in the repo. It reads
  `content/branding.yaml`, `content/questions/*.yaml`, `content/sources/*.yaml`
  with the `yaml` package, and emits one static, unauthenticated HTML file
  showing every question with its correct answer already visible (deliberately
  unshuffled, per its own comment, to catch authoring bias). It has no
  interactivity, no timer, no session, and is explicitly documented as "No
  application, no database, no login."
- `content/branding.yaml` already encodes the mock's shape: `mock.
  question_count: 30`, `mock.time_limit_minutes: 60`, `mock.
  disclose_bank_size: true`, and each of the four domains carries a
  `mock_questions` field (6, 10, 6, 8) that sums to 30 and matches the domain
  `weight` values (20/35/20/25).
- `content/schemas/question.schema.json` defines the published question shape:
  `id`, `status`, `domain`, `objective`, `stem` (restricted Markdown), exactly
  four `options` each with `id`/`text`/`correct`/`explanation`, `evidence`,
  `authored`, optional `reviewed`. This is the natural shape for the mock's
  question payload; the UI must not depend on any field the schema doesn't
  guarantee (e.g., must not assume `reviewed` is present).
- `content/questions/` currently holds 20 YAML files (`ls | wc -l` = 20), well
  under the `PLAN.md` Phase 1 exit minimum of 80 and under the "minimum 3 per
  domain" Phase 0 floor is unverified per-domain here — a real mock today
  cannot reliably fill 6/10/6/8 from `published`-status items alone.
- `PLAN.md` section 7 ("Application") describes the target architecture this
  screen eventually plugs into: a single TypeScript container, React/Vite
  client built to static assets and served by Express alongside the API,
  PostgreSQL-backed `attempts`/`attempt_items` tables, server-side
  `started_at`/`expires_at` as the sole scoring authority, GitHub OAuth. None
  of that exists yet in code — it's the plan, not the state.
- `PLAN.md` section 8 (deployment) confirms the first `mctl_deploy_service
  onboard` image intentionally ships with `AUTH_ENABLED=false` and
  `PUBLIC_ROUTES_ENABLED=false`, i.e. learner-facing routes including any Mock
  screen are gated off until a later, deliberate flip. This is further
  evidence the platform expects the UI to exist and be built before it is
  switched on for real learners.

## Proposed solution

Because no client exists, this proposal bootstraps the minimum viable
React/Vite scaffold and builds the Mock screen inside it, structured so later
proposals (Learn, Practice, Review-mistakes, the real API) extend rather than
replace it.

**1. Client scaffold** — new `client/` directory at repo root:
- Vite + React + TypeScript (`client/package.json` as its own workspace-style
  package, `client/vite.config.ts`, `client/tsconfig.json`), kept separate
  from the root `package.json` so `npm run lint:content` / `test:content` in
  CI remain untouched and fast (they must keep running identically on fork
  PRs per `ci.yml`'s own comment).
- Minimal routing (a lightweight router, e.g. a single-purpose in-app router
  or plain `useState`-driven view switch — see Alternatives) with exactly one
  real route for this proposal: the mock flow. Placeholder entries for
  Learn/Practice/Review-mistakes are explicitly not built.
- `client/src/data/` — a build-time content adapter, mirroring
  `scripts/build-preview.mjs`'s read pattern: a small Node script (or a Vite
  plugin) that reads `content/branding.yaml` and `content/questions/*.yaml`
  at build time and emits a static JSON bundle (`client/src/data/
  mock-bundle.generated.json`) containing only `published`-status questions,
  with `correct`/`explanation` fields *retained* (unlike the public preview)
  because deferred feedback is a UX rule enforced by the UI, not a secrecy
  boundary — `README.md` and `PLAN.md` are explicit that "the answer key is
  public," so there is no security requirement to strip it. This keeps the
  mock screen buildable and demoable with zero backend.
- A typed `ExamDataSource` interface (`client/src/exam/dataSource.ts`) with
  one implementation now (`StaticBundleDataSource`, reading the generated
  JSON) so a future `ApiDataSource` (hitting the real Express API from
  `PLAN.md` section 7) is a drop-in replacement, not a rewrite of the exam
  logic.

**2. Exam domain logic** (`client/src/exam/`), framework-agnostic where
possible so it's unit-testable without a DOM:
- `selectMockQuestions(questions, branding)` — filters to `status ===
  "published"`, groups by `domain`, and draws `mock_questions` count per
  domain uniformly at random (see Alternatives for why not
  least-recently-seen). Returns a clear typed error/empty-state result if a
  domain can't supply its quota, per the "WHERE fewer than the required count"
  acceptance criterion.
- `shuffleOptions(question)` — shuffles the 4 options' display order per
  question per session (branding.yaml documents shuffled options as part of
  mock selection; the schema's `options` array order is authoring order, not
  display order).
- `ExamSession` state machine: `not_started -> in_progress -> submitted`, with
  `answers: Record<questionId, optionId | undefined>`, `startedAt`,
  `expiresAt = startedAt + 60min`, `remainingMs` derived from a ticking clock,
  and an `submitExam()` transition triggered either by explicit learner action
  or by `remainingMs <= 0`.
- Session persistence: serialize `ExamSession` to `sessionStorage` (tab/
  session-scoped, not `localStorage`) keyed by a session id, so a reload
  mid-exam restores answers and recomputes `remainingMs` from the stored
  `expiresAt` (wall-clock based, so backgrounding the tab doesn't grant extra
  time within the session). This is explicitly a client-side convenience, not
  the server-side authority `PLAN.md` requires for production trust — called
  out in requirements.md Out of scope.

**3. UI components** (`client/src/exam/components/`):
- `MockStartScreen` — shows question count (30), time limit (60 min), current
  bank size (`disclose_bank_size`), and a start action.
- `MockExamScreen` — question navigator (30-item grid showing answered/
  unanswered state), current question stem + four options (radio-style,
  single-select), a persistent countdown timer, and a submit action with a
  confirmation step if unanswered questions remain.
- `MockResultsScreen` — overall score, then per-question review: stem, the
  learner's selection, the correct option, and every option's explanation
  (reusing the same rendering approach as `build-preview.mjs`'s restricted
  inline-Markdown `md()` helper, ported to a small React-safe equivalent —
  content is still restricted Markdown, never raw HTML, per `CONTENT-POLICY.md`
  and the schema's own description).
- A visible `not-enough-content` state on `MockStartScreen` if
  `selectMockQuestions` reports a shortfall for any domain, per the acceptance
  criteria — this is expected to trigger today, given the 20-question bank.

**4. Build wiring**: `client/` gets its own `npm run build` producing
`client/dist/`. This proposal does *not* change the root `Dockerfile` or wire
`client/dist/` into the runner stage's `CMD` — that is deployment integration,
explicitly out of scope (see requirements.md), and doing it prematurely risks
exactly the kind of `env:`/`values.yaml` churn `PLAN.md` section 8 warns about
before the OAuth/API pieces exist to make a deployed mock meaningful.

## Alternatives

1. **Wait for a separate "bootstrap the application" proposal before building
   any screen.** Rejected: issue #20 asks specifically for the Mock screen,
   and `CLAUDE.md`/`PLAN.md` don't have an open issue or proposal for a bare
   scaffold. Splitting "create client/" from "build the one screen anyone
   asked for" would produce a scaffold PR with no visible feature, which is
   harder to review meaningfully and harder to justify against the "does this
   solve the issue" bar. Bundling them keeps the scaffold minimal (only what
   the Mock screen needs) instead of speculative.

2. **Build the Mock screen directly against a real Express API and
   PostgreSQL, per the full `PLAN.md` section 7 design, instead of a static
   bundle.** Rejected for this proposal: that requires GitHub OAuth, session
   handling, CSRF, `attempts`/`attempt_items` tables, and server-side
   timestamp authority — a materially larger, security-sensitive surface that
   deserves its own requirements/design/review cycle and is explicitly what
   `PLAN.md` section 7 describes as still-to-build. Building the UI against a
   typed `ExamDataSource` interface now means that work later replaces one
   implementation, not the UI.

3. **Implement least-recently-seen question selection now, per `PLAN.md`
   section 3's stated intent.** Rejected for this proposal: least-recently-
   seen requires per-learner history, which requires the `attempts` table and
   auth this proposal defers. Uniform random selection within each domain
   quota is used instead, isolated behind `selectMockQuestions` so swapping in
   least-recently-seen later is a single-function change, not a UI rewrite.

4. **Pull in a full component/design-system library (e.g. an existing React
   UI kit) for the screens.** Rejected: no design system is evidenced
   anywhere in the repository, and picking one is a project-wide decision this
   single-issue proposal shouldn't make unilaterally. Plain CSS modules keep
   the choice reversible.

## Platform impact

- **Migrations**: none. No database exists yet in code; this proposal touches
  no schema.
- **Backward compatibility**: none broken — there is no prior client to be
  compatible with. `content/schemas/question.schema.json` is read-only
  consumed, not modified.
- **Resource impact**: build-time only in CI (client build added to `ci.yml`
  as a new job/step, analogous to the existing `build:preview` step); no
  runtime resource change, since `client/dist/` is not wired into the
  deployed image or `Dockerfile` by this proposal.
- **Risks**:
  - *Risk*: a reviewer expects a deployed, working `academy.mctl.ai/mock` from
    this PR, given the issue's "on academy.mctl.ai" phrasing. *Mitigation*:
    requirements.md Out of scope states plainly that deployment wiring is
    excluded and why (`PUBLIC_ROUTES_ENABLED=false` by platform design at
    first onboard); tasks.md's DoD is demoable via local `npm run dev`/`npm
    run build` + a static preview artifact, not a live URL.
  - *Risk*: the static content bundle embeds full answer keys and
    explanations client-side, which could read as a security concern.
    *Mitigation*: `README.md` and `PLAN.md` both state explicitly that "the
    repository is public, so the answer key is public with it" and that
    withholding answers pre-submission is anti-spoiler UX, not a security
    control — this proposal's approach (hide via UI state, not via omitting
    data from the client) matches that stated posture exactly.
  - *Risk*: building against only 20 questions means `selectMockQuestions`
    will almost certainly hit the "not enough content" degraded state in
    practice today. *Mitigation*: that degraded state is a first-class,
    tested acceptance criterion, not a bug — it is expected to be exercised
    now and stop being hit once content grows past 80 items.
  - *Risk*: introducing a second `package.json` (`client/`) could confuse the
    existing CI, which assumes one root manifest. *Mitigation*: tasks.md
    includes an explicit CI update as its own task with its own DoD (root
    `lint:content`/`test:content` jobs continue to run unchanged; a new job
    runs `npm ci`/`npm run build` inside `client/`).
