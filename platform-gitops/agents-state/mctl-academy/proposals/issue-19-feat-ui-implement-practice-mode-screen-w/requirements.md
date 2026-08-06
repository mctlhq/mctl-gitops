# Practice mode React screen with instant per-option feedback

## Context

Issue #19 asks for a Practice mode React UI screen on `academy.mctl.ai`: users
select an answer and get immediate per-option feedback and explanations.

The repository is currently Phase 0 (`CLAUDE.md`: "The application does not
exist yet — Phase 0 is content pipeline and policy"). There is no `client/`
directory, no `react`/`vite` dependency anywhere in `package.json`, no Express
server, no database, and no CI job that builds or tests a UI. The only
runtime artifact that exists today is `scripts/build-preview.mjs`, a static,
unshuffled, non-interactive HTML dump of `content/` used to sanity-check the
content pipeline (`npm run build:preview`, wired into `.github/workflows/ci.yml`
as the `content` job).

`PLAN.md` section 7 ("Application") describes the eventual full system: a
single TypeScript container running a React/Vite client built to static
assets and served by Express, PostgreSQL-backed `attempts`/`users` tables,
GitHub OAuth, CSRF protection, server-side deadline enforcement, and MCP-only
deployment to the `labs` tenant (not yet onboarded — `mctl_list_services`
would show no `mctl-academy` entry). That is Phase 1 scope, not this issue.

This proposal treats #19 narrowly: build the Practice mode screen itself, as
a standalone client-side React application that reads a build-time content
bundle generated from `content/questions/` and `content/branding.yaml`
(the same source `build-preview.mjs` already reads), with no server API, no
database, no authentication, and no persistence beyond the current browser
session. That is the largest slice of #19 that is buildable today without
first completing the unrelated backend/auth/deployment work Phase 1
describes elsewhere. The full application (Express host, attempts API,
OAuth, deployment) is out of scope here and belongs to separate proposals
tracked against `PLAN.md` section 7 and section 8.

Per-option instant feedback is well-supported by the existing content model:
`content/schemas/question.schema.json` requires every option (correct or
not) to carry a non-empty `explanation` (12-1200 chars) — the schema was
already designed for exactly this UX, described in the schema itself as
"the part that makes this a study tool rather than a quiz."

## User stories

- AS a certification candidate I WANT to answer a practice question and
  immediately see whether the option I picked was correct SO THAT I learn
  from each choice without waiting for a full submission cycle.
- AS a certification candidate I WANT to read the explanation for any option
  I pick, right or wrong SO THAT I understand why a distractor was wrong, not
  just that it was.
- AS a certification candidate I WANT the four options presented in shuffled
  order SO THAT I do not memorize answer positions instead of content
  (`build-preview.mjs` explicitly calls out authored-order bias as a known
  failure mode it exists to catch; the live app must not reintroduce it).
- AS the maintainer I WANT Practice mode to only ever draw `published`
  questions SO THAT unreviewed or drifted (`needs_review`) content is never
  shown to a learner.

## Acceptance criteria (EARS)

- WHEN the Practice screen loads THE SYSTEM SHALL display one question at a
  time, drawn only from questions with `status: published`.
- WHEN the Practice screen loads a question THE SYSTEM SHALL render its four
  options in a shuffled order that differs, in general, from the authored
  order stored in `content/questions/*.yaml`.
- WHEN a user selects an option THE SYSTEM SHALL immediately show, for that
  option, whether it is correct and its `explanation` text, without a
  network round trip or a separate "submit" step.
- WHEN a user selects an option THE SYSTEM SHALL continue to allow selecting
  the other options of the same question, each independently revealing its
  own correctness and explanation, so the user can inspect all four choices
  before moving on.
- WHEN a user advances past the last question in the current set THE SYSTEM
  SHALL display a summary of how many of the attempted questions were
  answered correctly on the first selection.
- WHILE a question's options have not yet been selected at all THE SYSTEM
  SHALL NOT reveal any option's correctness or explanation.
- IF the compiled content bundle contains zero published questions THEN THE
  SYSTEM SHALL show an explanatory empty state rather than an empty or
  broken screen.
- IF a question's `stem` or option `text` contains the restricted inline
  Markdown the schema allows (backtick code spans) THEN THE SYSTEM SHALL
  render it as code and SHALL NOT interpret any other markup, mirroring the
  sanitization `build-preview.mjs` already performs.

## Out of scope

- Any backend API, Express host, or database (`PLAN.md` section 7). No
  `attempts` persistence, no cross-session history, no server-side scoring.
- GitHub OAuth / authentication (`PLAN.md` section 7). Practice mode is
  anonymous and client-only in this proposal.
- Mock mode (30-question timed exam), Review-mistakes mode, and the progress
  dashboard — separate product modes listed in `PLAN.md` section 3, not part
  of issue #19's request.
- Least-recently-seen question selection across sessions (`PLAN.md` section
  3 describes this for Mock composition specifically; it requires server-side
  attempt history that does not exist yet). This proposal uses a client-side
  random selection/shuffle instead.
- Deployment of `mctl-academy` to the `labs` tenant (`PLAN.md` section 8).
  This proposal only builds the screen and its build tooling; it does not
  onboard or deploy a service.
- Question reporting ("per-question report action", `PLAN.md` section 3).
- Domain/objective filtering UI for choosing which questions to practice
  (see Open questions).

## Open questions

- Should the initial cut let the user pick a domain to practice, or always
  draw from the whole published bank? The issue does not say. Proceeding
  with: whole bank, client-side shuffled, with domain filtering left as a
  natural follow-up once this screen exists (the content bundle already
  carries `domain`/`objective` per question, so this is additive later, not
  a rework).
- Should selecting a wrong option lock the question (no further selection),
  or allow exploring all four options' explanations as stated in the
  acceptance criteria above? The issue's phrasing ("feedback and explanations
  for each choice", plural) reads as explore-all-four; proceeding on that
  interpretation since it maximizes the stated learning goal, but a
  first-guess-only variant is a small, isolated change if rejected in
  review.
- How many questions make up one Practice session, and can the user
  configure it? Proceeding with a fixed default (all published questions,
  in one shuffled pass) since the bank is small at Phase 0 (fewer than 20
  questions per `PLAN.md`'s Phase 0 exit criteria); a session-length control
  is a follow-up once the bank grows past a comfortable single pass.
- Visual design system / component library is unspecified anywhere in the
  repo (no existing UI to match). Proceeding with plain CSS scoped to the
  new `client/` app, reusing the light/dark, system-font approach already
  established in `scripts/build-preview.mjs`'s inline `<style>` for visual
  consistency between the two artifacts, without pulling in a UI framework
  dependency this proposal does not otherwise need.
- Where the built client assets ultimately get served (Express static host
  per `PLAN.md` section 7) is intentionally not decided here — this proposal
  only produces a buildable, testable `client/` app and its `npm run build`
  output; wiring it behind a server is separate, later work.
