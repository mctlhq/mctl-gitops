# Domain 4 content expansion: 20 new evidence-backed questions

## Context

Issue #42 asks for 20 published questions for "Domain 4 (Evaluation, Safety &
Production Deployment)" with source citations and per-option feedback. The
actual `domain-4` defined in `content/branding.yaml` is **"Production
operations"** (weight 25, 8 mock questions), with seven objectives:
`dedicated-endpoints`, `endpoint-lifecycle`, `capacity-and-scaling`,
`rate-limits`, `observability`, `billing-and-consumption`, `team-access`.
There is no "Evaluation, Safety" domain anywhere in this repository's course
outline — see "Open questions" below.

Today `content/questions/` holds 5 published `domain-4` items, all citing
just two of the seven objectives (`endpoint-lifecycle`: 2 items,
`rate-limits`: 3 items — confirmed via `grep -l "domain: domain-4"
content/questions/*.yaml`). The other five objectives have zero questions
and, more fundamentally, zero source records: `content/sources/` contains
`src-endpoint-lifecycle.yaml` and `src-rate-limits.yaml` for domain-4, and
nothing for `dedicated-endpoints`, `capacity-and-scaling`, `observability`,
`billing-and-consumption`, or `team-access`. Per `SOURCES.md`, "an objective
with no approved source stays unpublished rather than being covered from
general knowledge" — so closing that gap is a precondition for broad
domain-4 coverage, not an optional nice-to-have.

Per `CONTENT-POLICY.md`, item text must be authored by an agent from
allowlisted documentation excerpts (`docs.tokenfactory.nebius.com` primary,
`docs.nebius.com` secondary) with the maintainer approving, never authoring.
Publication additionally requires a verbatim-citation check against a
private R2 snapshot (`content-evidence.yml`, needs `R2_*` secrets — same-repo
only, never available on a fork) and a `reviewed` block added by the
CODEOWNER (`@mashkovd`) once they approve the PR. This proposal scopes the
work an automated agent can actually perform under those constraints, and
draws the line at the point where only the human reviewer can proceed.

## User stories

- AS a learner practicing for the Production operations domain I WANT a
  question bank that covers all seven domain-4 objectives, not just two, SO
  THAT Practice and Mock selection reflect the full scope the domain weight
  promises.
- AS the content maintainer (CODEOWNER) I WANT every new item schema-valid,
  lint-clean, and citation-verifiable before I review it SO THAT my review
  time goes to the two criteria in `CONTENT-POLICY.md` (evidence supports the
  claim; exactly one best option), not to formatting or missing sources.
- AS the mctl-academy project I WANT new domain-4 source records captured
  with an R2 snapshot SO THAT CI's verbatim citation check
  (`verify-evidence.mjs`) can pass, and the weekly drift job
  (`source-drift.yml`) can track them going forward.

## Acceptance criteria (EARS)

- WHEN the agent drafts a domain-4 question THE SYSTEM SHALL set
  `authored.by` to `agent:<name>` (never a human name), matching the
  `AGENT_AUTHOR` pattern enforced in `scripts/validate-content.mjs`.
- WHEN the agent drafts a domain-4 question THE SYSTEM SHALL write it with
  `status: draft` — publication (`status: published` plus a `reviewed`
  block) is a human CODEOWNER action per `CODEOWNERS` and is out of this
  proposal's automated scope.
- WHEN a domain-4 objective has no `content/sources/*.yaml` record THE
  SYSTEM SHALL capture one via `npm run snapshot:capture -- <url> --id
  <src-id> --objective domain-4/<objective>` (or an equivalent script run
  with `R2_ACCOUNT_ID`/`R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY` populated)
  before any question cites that objective, matching the pattern in
  `src-endpoint-lifecycle.yaml` / `src-rate-limits.yaml`.
- WHILE authoring an item THE SYSTEM SHALL keep every evidence excerpt at
  most 25 whitespace-separated words and verbatim in the cited source's
  retrieved text, matching `question.schema.json`'s
  `evidence.items.excerpt.pattern` and the `verify-evidence.mjs` check.
- WHILE authoring an item THE SYSTEM SHALL give every option (including the
  three wrong ones) a non-empty `explanation` of at least 12 characters, per
  `question.schema.json`.
- WHEN the full batch of 20 items is drafted THE SYSTEM SHALL distribute
  them across all seven domain-4 objectives rather than concentrating on the
  two already sourced, so coverage tracks the objective map rather than
  authoring convenience (`CONTENT-POLICY.md`: "coverage is allocated from
  the published domain weights only").
- WHEN opening pull requests THE SYSTEM SHALL cap each PR at 10 questions,
  per `CONTRIBUTING.md` ("Content pull requests are capped at 10
  questions") — 20 items requires at least two PRs.
- WHEN opening a content PR THE SYSTEM SHALL include the content
  attestation checklist from `.github/pull_request_template.md` fully
  checked, and SHALL NOT touch any file outside `content/questions/` and
  (if new sources are needed) `content/sources/`.
- IF `npm run lint:content` or `npm run test:content` fails locally THEN THE
  SYSTEM SHALL fix the violation before opening the PR — CI runs the same
  two commands (`ci.yml`) and a red run blocks merge.
- IF an objective's source cannot be captured (fetch fails, or the R2 store
  is unavailable) THEN THE SYSTEM SHALL leave that objective's planned
  questions undrafted for this batch and note the gap in the PR description,
  rather than authoring from memory or general knowledge (`SOURCES.md`).
- WHILE the bank has 12 or more total questions THE SYSTEM SHALL keep the
  correct-answer position roughly balanced (no single position exceeding 50%
  bank-wide), matching the answer-position-bias check in
  `scripts/validate-content.mjs`.
- IF two options on the same item would have identical text THEN THE SYSTEM
  SHALL reword one — `scripts/validate-content.mjs` rejects duplicate option
  text as unanswerable.

## Out of scope

- Flipping any item's `status` to `published` or writing a `reviewed` block
  — that is the CODEOWNER's action after PR review, mechanically separated
  from authorship by `CONTENT-POLICY.md` and enforced by `CODEOWNERS`.
- Renaming or reinterpreting `domain-4` to match the issue's "Evaluation,
  Safety & Production Deployment" title. The course outline in
  `content/branding.yaml` is the source of truth; changing it is a
  deliberate, separately-reviewed decision (the file's own header: "READ
  THIS BEFORE CHANGING THE MAP"), not a side effect of a content batch.
- Adding new source hosts beyond the `SOURCES.md` allowlist
  (`docs.tokenfactory.nebius.com`, `docs.nebius.com`).
- Lessons content (`content/lessons/` — schema exists, directory does not
  yet). This proposal is questions-only, matching the issue.
- Client/UI changes. No app code is touched.
- Deployment — the app is not yet onboarded (`CLAUDE.md`: "The application
  does not exist yet — Phase 0 is content pipeline and policy").

## Open questions

1. The issue's parenthetical "(Evaluation, Safety & Production Deployment)"
   does not match `content/branding.yaml`'s domain-4 title ("Production
   operations") or its objectives, none of which mention evaluation or
   safety. Interpretation adopted: the issue means the repository's actual
   `domain-4`, and the parenthetical is either stale or refers to a
   different (e.g. vendor-published) domain list that this project
   deliberately does not use — see `branding.yaml`'s own comment on why the
   vendor's official domain list is out of bounds. Proceeding on that basis;
   a human should confirm domain-4 is indeed the intended target before
   merging any PR.
2. "20 published questions" — does this mean 20 *new* items (bank grows from
   5 to 25 domain-4 items) or 20 *total* domain-4 items (15 new)? This
   proposal assumes 20 new, since the existing 5 only cover 2 of 7
   objectives and 20 total would leave several objectives thin or empty.
3. Should the 20 items be weighted evenly across the seven objectives
   (~3 each) or weighted toward objectives more central to daily operation
   (e.g. `dedicated-endpoints`, `rate-limits`)? No sub-objective weights
   exist in `branding.yaml`. This proposal defaults to roughly even
   distribution and leaves rebalancing to reviewer feedback.
4. Whether the executing agent has `R2_*` credentials available outside of
   GitHub Actions to run `snapshot:capture` before opening a PR, or whether
   source capture must happen as a same-repo CI/maintainer step. Tasks below
   assume the agent can run the capture script directly; if it cannot, the
   fallback is documented in `tasks.md`.
