# Design: issue-19-feat-ui-implement-practice-mode-screen-w

## Current state

Verified by reading the clone:

- `package.json` has no `react`, `vite`, or any frontend dependency —
  `dependencies` is only `ajv`, `ajv-formats`, `yaml`; `scripts` only cover
  `lint:content`, `verify:evidence`, `snapshot:capture`, `test:content`,
  `build:preview`. There is no `client/`, `src/`, `server/`, or `app/`
  directory anywhere in the repo.
- `git log` shows a single merge commit on `main` — this repo is at the
  state `CLAUDE.md` describes: "The application does not exist yet."
- `scripts/build-preview.mjs` is the one existing artifact that renders
  `content/` into a browsable form. It:
  - loads `content/branding.yaml`, `content/questions/*.yaml`,
    `content/sources/*.yaml` via `yaml`'s `parse`,
  - escapes all text (`esc()`) and interprets only backtick code spans
    (`md()`) — "a preview that interpreted arbitrary markup would be a
    script-injection surface for content nobody has reviewed yet",
  - deliberately renders options in authored order, "which is exactly how
    the all-answers-in-position-a problem was caught" — i.e. shuffling is
    explicitly an application-layer concern, not a content-layer one,
  - is static HTML with no interactivity and no client-side JavaScript
    beyond inline CSS.
  - is wired into `.github/workflows/ci.yml`'s `content` job as
    `npm run build:preview`, uploaded as a build artifact.
- `content/schemas/question.schema.json` defines the exact shape Practice
  mode needs: `status` (`draft|needs_review|published|retired`), `domain`,
  `objective`, `stem` (restricted Markdown), and `options` — exactly 4,
  exactly one `correct: true` (enforced by `minContains`/`maxContains`),
  each with `id` (`a|b|c|d`), `text`, `correct`, and a required
  `explanation` (12-1200 chars) on every option, not just the correct one.
  This is already shaped for per-option feedback; nothing in the content
  model needs to change.
- `content/branding.yaml` defines `domains[].id/title/weight/objectives[]`
  and `mock.question_count`/`time_limit_minutes` — domain/objective
  metadata Practice mode can use later for filtering, even though this
  proposal does not build that filter yet (see requirements.md Open
  questions).
- `PLAN.md` section 7 describes the eventual full application (Express
  host, PostgreSQL `attempts`, GitHub OAuth) as future work; section 8
  describes MCP-only deployment to the `labs` tenant, not yet done — there
  is no live `mctl-academy` service to affect.
- `.github/workflows/ci.yml` has one job, `content`, running on
  `actions/setup-node` with Node 22, `npm ci`, then lint/test/build-preview.
  There is no lint/build/test step for any client code because none exists.

## Proposed solution

Add a new, self-contained `client/` workspace inside this repo:

1. **Content bundle build step** — `scripts/build-content-bundle.mjs`,
   sibling to `build-preview.mjs` and reusing the same load/parse pattern
   (`yaml.parse` over `content/questions/*.yaml` and
   `content/branding.yaml`). It filters to `status: published` only (the
   same filter `build-preview.mjs` computes via `questions.filter(q =>
   q.status === "published")` for its stats line, made the primary
   selection criterion here instead of a side statistic) and writes a JSON
   bundle (question `id`, `domain`, `objective`, `stem`, `options` with
   `id`/`text`/`correct`/`explanation`) to `client/src/content-bundle.json`.
   Wired into `client/package.json` as a `prebuild`/`pretest` step so the
   bundle is never stale relative to `content/`.

   Bundling at build time (not fetching `content/*.yaml` at runtime) keeps
   this proposal server-free: the compiled output is static assets that
   need no `content/` filesystem access once built, consistent with
   "no backend" being the deliberate scope boundary here.

2. **React/Vite app** — `client/` gets its own `package.json`
   (`react`, `react-dom`, `vite`, `@vitejs/plugin-react`, `typescript`,
   `vitest`, `@testing-library/react`), `vite.config.ts`, `tsconfig.json`.
   Kept as an independent npm workspace rather than merged into the root
   `package.json`, so the existing content-lint dependency set
   (`ajv`, `ajv-formats`, `yaml`) stays untouched and `npm run lint:content`
   / `npm run test:content` at the root keep working exactly as they do
   today with no risk of a frontend dependency bump breaking the content
   gate.

3. **Practice mode components**, under `client/src/practice/`:
   - `usePracticeSession.ts` — loads the bundle, shuffles the question
     order and, per question, the option order (Fisher-Yates, seeded per
     session so a re-render mid-question does not re-shuffle under the
     user), and exposes `{ current, index, total, selectOption, revealed,
     score, next }`.
   - `PracticeScreen.tsx` — renders the current question's `stem` through a
     small `renderInlineMarkdown()` helper that ports `build-preview.mjs`'s
     `esc()`/`md()` pair (escape everything, then linkify only backtick
     spans) so the same restricted-Markdown contract holds in the
     interactive app as in the static preview — the two renderers must
     agree, since they read the same schema-validated `stem`/`text` fields.
     Each option is a button; clicking one adds it to a per-question
     `revealed` set (not a single "answered" flag), which satisfies the
     "explore all four" acceptance criterion — the correctness state and
     the `explanation` text for a *revealed* option only, not the whole
     answer key, are shown; unrevealed options stay inert.
   - A summary view once `index === total`, showing count correct out of
     attempted.
   - An empty state (`content-bundle.json` has zero published questions)
     rendered instead of the question view.

4. **CI** — extend `.github/workflows/ci.yml` with a second job,
   `client`, mirroring the `content` job's checkout/setup-node steps,
   running `npm ci`, `npm run build`, and `npm test` inside `client/`
   (which itself runs `build-content-bundle.mjs` first). Kept as a
   separate job rather than folded into `content` so a client-only
   dependency failure never blocks the fork-safe content-lint gate
   `CLAUDE.md` describes, and vice versa.

## Alternatives

1. **Wait for the full Express/PostgreSQL/OAuth application from `PLAN.md`
   section 7 before building any screen.** Dropped: that is an
   open-ended, multi-proposal effort (auth, database schema, deployment)
   with no dependency from Practice mode's core UX on any of it — per-option
   feedback needs only the content bundle, not attempt persistence or
   login. Blocking #19 on all of Phase 1 landing first would leave a
   concrete, scoped issue unaddressed for an unbounded time.

2. **Extend `build-preview.mjs`'s static HTML generation directly, with
   hand-written vanilla JS for the click interactions, instead of
   React.** Dropped: the issue explicitly asks for a "React UI component",
   and per-option reveal state, shuffle-once-per-session, and a running
   score are exactly the kind of local component state React manages well;
   hand-rolled DOM event wiring on top of a server-rendered HTML dump would
   duplicate that logic without any of the tooling (component tests,
   typed props) this proposal adds.

3. **Serve questions from a new Express endpoint reading `content/`
   directly at request time, instead of a build-time static bundle.**
   Dropped: there is no server in this repo yet, and standing one up
   (routing, hosting, health checks) only to serve read-only content that
   already lives in Git is premature — `PLAN.md` section 4 describes the
   eventual target as "Git content compiles to an immutable manifest";
   `scripts/build-content-bundle.mjs` is a small, direct step toward that
   manifest, whereas a live filesystem-reading endpoint is not on that
   path and would need to be replaced anyway once the real
   attempts-snapshotting manifest exists.

## Platform impact

- **Migrations:** none. No database exists or is touched; `content/` YAML
  is read-only input to a build step.
- **Backward compatibility:** none to break — this is new functionality in
  a repo with no prior client code and no deployed service
  (`mctl_list_services` would show no `mctl-academy` entry; not queried
  live for this proposal, but `PLAN.md` section 8 states onboarding has not
  happened).
- **Resource impact:** none in production — nothing is deployed by this
  proposal. CI gains one additional job (`client`) with its own
  `npm ci`/build/test cost, comparable to the existing `content` job.
- **Risks and mitigations:**
  - *Answer-key exposure.* The compiled bundle embeds every option's
    `correct` flag and `explanation` in client-shippable JSON, which is
    fully inspectable by anyone with browser devtools. `PLAN.md` already
    reclassifies "correct answers not returned before submission" as
    anti-spoiler UX, not a security control, given the repo (and therefore
    the answer key) is public either way — so this is consistent with
    documented policy, not a new exposure. Mitigation for the *UX* concern
    specifically: the screen reveals an option's correctness/explanation
    only once the user clicks that option, never all four up front, so the
    interaction still reads as "practice," not "answer key dump."
  - *Divergence from the eventual full app.* Building a server-free client
    now risks assumptions (no auth, no attempt IDs) that the later
    Express/Postgres integration has to unwind. Mitigation: `usePractice
    Session` is the single seam between data and UI — swapping a
    build-time JSON bundle for a fetched API response later is a change
    localized to that one hook, not to `PracticeScreen.tsx` or the
    shuffle/reveal logic.
  - *Two Markdown renderers drifting apart* (`build-preview.mjs`'s `md()`
    vs. the new `renderInlineMarkdown()`). Mitigation: both implement the
    same "escape, then backtick-only" contract; keeping the logic in two
    places is a deliberate cost of not sharing a module between the root
    Node scripts and the `client/` Vite app (different build targets), but
    a shared unit test asserting identical output for the same input
    string exists in this proposal's task list.
  - *CI runtime growth.* A new job adds wall-clock time to every PR.
    Mitigation: it is independent of and parallel to the existing
    `content` job, so it does not lengthen the critical path for
    content-only PRs, which `CLAUDE.md` states are not LLM-reviewed and
    should stay fast.
