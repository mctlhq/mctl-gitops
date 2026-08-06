# Question Report form and intake API

## Context

Issue #22 asks for two things: a "Report Question" action on each question
item in the UI, and an Express endpoint `POST /api/reports` that inserts the
report into a `question_reports` table.

The repository is currently Phase 0 (`CLAUDE.md`: "the application does not
exist yet — Phase 0 is content pipeline and policy"; `README.md`: "the
application is not built yet, and there is nothing to sign in to";
`CONTRIBUTING.md`: "The application does not exist yet. This section will be
filled in when there is something to run."). There is no `client/` or
`server/` directory, no `express`/`react`/`vite`/`pg` dependency in
`package.json`, and no database migration tooling anywhere in the repo. The
only thing that renders a question today is `scripts/build-preview.mjs`, a
static-HTML generator explicitly scoped as "No application, no database, no
login" (its own header comment).

`PLAN.md` section 3 lists "per-question report action" as in-scope product
scope, and section 7 names `question_reports` as one of the core application
tables, in a single TypeScript container (React/Vite client + Express API,
Postgres on the shared CNPG cluster). So the feature is on the roadmap, but
this issue is the first piece of application code to land — there is no
existing client/server scaffold to attach it to, no OAuth (`AUTH_ENABLED`
starts `false` per `PLAN.md` section 8 bootstrap step 1), and no publish
pipeline that turns `content/questions/*.yaml` into a queryable `questions`
table (`PLAN.md` section 4, "Publication" — not yet implemented). This
proposal therefore scopes the minimal vertical slice that makes "Report
Question on each item" real and buildable today, without pretending the rest
of the application (Learn/Practice/Mock modes, GitHub OAuth, attempts,
content-versions publish pipeline) already exists.

This matters because a wrong-or-ambiguous published question is exactly the
kind of defect the clean-room content pipeline (`CONTENT-POLICY.md`) cannot
catch by itself — evidence CI verifies a citation is verbatim, not that the
item reads correctly to a learner. `README.md` already advertises "Issues,
bug reports, and question reports are welcome from anyone" as the primary
outside-contributor path; this proposal is what makes that literally true
inside the app instead of routing everyone to GitHub Issues.

## User stories

- AS a learner viewing a question I WANT a visible "Report" action on the
  item SO THAT I can flag a question that is wrong, ambiguous, or whose
  citation does not support it, without leaving the app.
- AS a learner who reports a question I WANT to pick a reason and optionally
  add details SO THAT the maintainer has enough context to triage without a
  back-and-forth.
- AS the maintainer I WANT every report persisted with the question id,
  reason, optional details, and a timestamp SO THAT I can review and action
  them later (this proposal does not build the review UI — see Out of
  scope).
- AS the platform I WANT the report endpoint to be abuse-resistant SO THAT
  an anonymous, unauthenticated endpoint cannot be used to flood the
  database (`PLAN.md` section 7 lists "rate limits on submission and report
  endpoints" as a required control).

## Acceptance criteria (EARS)

- WHEN a learner activates the Report action on a question item THE SYSTEM
  SHALL open a form capturing a reason (from a fixed set of categories) and
  an optional free-text detail field, pre-filled with the question id.
- WHEN the learner submits the report form THE SYSTEM SHALL send
  `POST /api/reports` with the question id, reason, and optional details.
- WHEN `POST /api/reports` receives a request with a known reason value and
  a `question_id` matching an existing content question THE SYSTEM SHALL
  insert one row into `question_reports` and respond `201` with the created
  report's id.
- IF the request body is missing `question_id` or `reason`, or `reason` is
  not one of the allowed categories, THEN THE SYSTEM SHALL respond `400`
  and SHALL NOT insert a row.
- IF `question_id` does not match any question known to the content set
  THEN THE SYSTEM SHALL respond `404` and SHALL NOT insert a row.
- IF `details` exceeds the configured maximum length THEN THE SYSTEM SHALL
  respond `400` and SHALL NOT insert a row.
- WHEN a report is successfully submitted THE SYSTEM SHALL show the learner
  a confirmation and SHALL close the form without requiring navigation away
  from the item.
- WHILE the report request is in flight THE SYSTEM SHALL disable the submit
  control to prevent duplicate submissions from a single click sequence.
- IF the client-side submission fails (network error or non-2xx response)
  THEN THE SYSTEM SHALL show an inline error and SHALL leave the form open
  with the learner's input intact so they can retry.
- WHEN more than the configured number of report requests arrive from the
  same client within the configured window THE SYSTEM SHALL respond `429`
  and SHALL NOT insert a row, per `PLAN.md` section 7's rate-limit
  requirement.
- THE SYSTEM SHALL NOT require authentication to submit a report, because
  `AUTH_ENABLED` is `false` at initial bootstrap (`PLAN.md` section 8) and
  the issue does not request gating this action behind login.
- THE SYSTEM SHALL record only the GitHub numeric id when a report is
  submitted by an authenticated learner (once auth exists) and SHALL NOT
  collect email, IP-derived identity, or analytics beyond what
  `PRIVACY.md` already allows.

## Out of scope

- The React/Vite Learn, Practice, Mock, and Review-mistakes modes described
  in `PLAN.md` section 3. This proposal adds only the minimal client scaffold
  and question-item view needed to host the Report action.
- GitHub OAuth, sessions, and the `users` table (`PLAN.md` section 7). The
  report endpoint is unauthenticated at this stage.
- The content-versions publish pipeline that turns `content/*.yaml` into an
  immutable manifest and a queryable `questions`/`content_versions` table
  (`PLAN.md` section 4). This proposal reads question ids directly from
  `content/questions/*.yaml` at request time (see design.md) rather than
  waiting on that pipeline.
- A maintainer-facing UI to view, triage, or resolve reports. Reports land
  in Postgres only; triage is a follow-up.
- Notifications (email, Slack, GitHub issue creation) when a report is
  filed.
- Deduplicating repeated reports of the same question by the same learner.
- Actually running `mctl_deploy_service` / `mctl_provision_database` —
  deployment execution is a separate, later step per `PLAN.md` section 8;
  this proposal only specifies the migration and config needs those calls
  must satisfy.

## Open questions

- The issue does not say where "each item" is rendered. The only existing
  question-rendering surface is the static, no-database Phase 0 preview
  (`scripts/build-preview.mjs`), which is explicitly out of scope for a
  live database write. Interpretation taken: build the minimal real
  application entry point (client + server, per `PLAN.md` section 7) with a
  single read-only question-browsing view, and attach the Report action
  there, rather than wiring a database call into the static preview
  generator.
- The issue does not define report reason categories. Interpretation taken:
  a small fixed enum (`incorrect_answer`, `ambiguous_wording`,
  `citation_mismatch`, `typo_or_formatting`, `other`) mirroring the two
  review criteria in `CONTENT-POLICY.md` (evidence supports the claim;
  exactly one option is best) plus a general catch-all.
- The issue does not say whether `question_id` should validate against the
  live content set (`content/questions/*.yaml`, any status) or only
  `published` questions. Interpretation taken: validate against any known
  question id regardless of status, since a `needs_review` item (already
  withdrawn from selection after source drift) can still legitimately
  receive a report referencing a past attempt.
- Rate limit thresholds are unspecified. Interpretation taken: a
  conservative default (10 requests per IP per 10 minutes) applied in code,
  documented as a starting point for the maintainer to tune after launch,
  not a value taken from any external spec.
- Whether report rows should FK to a `questions` table does not apply yet,
  since that table does not exist. Interpretation taken: store
  `question_id` as free text validated against the content set at request
  time, not a foreign key; revisit once the publish pipeline lands (see
  design.md Alternatives).
