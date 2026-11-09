# Add the Agent trailer check to portfolio

## Context

The organisation rolled out a warn-only `Agent:` commit trailer check
(mctlhq/.github#316) to 18 repositories. Each one has a thin caller workflow,
`.github/workflows/agent-trailer-check.yml`, that invokes the shared reusable
workflow `mctlhq/.github/.github/workflows/agent-trailer.yml` pinned at
`afb232838c79279141d293e6ce311f3ec664bfbc`. The reusable workflow reads every
commit of a pull request, classifies its `Agent:` trailer (`claude`, `codex`,
`agy`, `none`; missing or malformed is `unknown`), and sets exactly one
`agent:*` label on the pull request. With `enforce` left at its default
`false` it never fails on an unknown commit.

`portfolio` was left out because its bootstrap boundary (ADR-0001, AGENTS.md)
means a non-reserved workflow has to arrive through a DevLoop cycle rather
than a human commit. This proposal adds the same caller through the DevLoop,
makes the implementer's own commits carry an `Agent: claude` trailer, brings
the ADR-0001 Decision text in line with the narrowed reservation list that
AGENTS.md already states, pins the caller with a structural test in
`npm test`, and opens this cycle's journal entry. Everything the issue wants
reported is placed in committed files, not in the pull request description.

## User stories

- AS the platform owner I WANT `portfolio` to run the same Agent trailer
  check as the other 18 repositories SO THAT the rollout of
  mctlhq/.github#316 covers the whole organisation before enforcement is
  decided.
- AS a reviewer I WANT each portfolio pull request to carry an `agent:*`
  label SO THAT I can see which assistant the commits declare.
- AS a reader of the site I WANT ADR-0001 to describe the boundary that is
  actually enforced SO THAT the published decision does not contradict the
  repository it governs.

## Acceptance criteria (EARS)

- THE SYSTEM SHALL contain `.github/workflows/agent-trailer-check.yml` whose
  content is byte-identical to the caller currently on `main` of
  `mctlhq/mctl-web` (reproduced verbatim in design.md, including its two-line
  comment), triggered on `pull_request` types `opened`, `reopened`,
  `synchronize`, `ready_for_review`, with top-level `permissions: {}` and job
  `agent-trailer` granted only `issues: write` and `pull-requests: write`,
  calling `mctlhq/.github/.github/workflows/agent-trailer.yml@afb232838c79279141d293e6ce311f3ec664bfbc`.
- WHILE enforcement has not been decided in mctlhq/.github#316 THE SYSTEM
  SHALL run the check in warn-only mode: the caller SHALL contain no `with:`
  block and no `enforce` key.
- WHEN `npm test` runs THE SYSTEM SHALL execute a new
  `test/agent-trailer-workflow.test.ts` that fails if the caller file is
  missing, sets `enforce`, carries a `with:` block, references the reusable
  workflow at any ref other than the pinned 40-hex SHA, triggers on anything
  other than the four `pull_request` types, or grants any permission beyond
  `permissions: {}` at top level and `issues: write` / `pull-requests: write`
  on the job.
- WHEN the implementer commits for this cycle THE SYSTEM SHALL end every
  commit message with a final trailer paragraph that contains the line
  `Agent: claude` (alongside any `Co-Authored-By:` line, every line of that
  final paragraph being a `Key: value` trailer).
- WHEN the pull request adding the caller is opened from a branch of
  `mctlhq/portfolio` THE SYSTEM SHALL run the "Agent trailers" check, which
  sets an `agent:*` label on that pull request (expected `agent:claude` when
  every non-merge commit carries `Agent: claude`). Observing the label is a
  reviewer step, not a committed artefact.
- THE SYSTEM SHALL amend the Decision section of
  `src/content/adr/0001-bootstrap-boundary.md` in both languages with the
  exact copy given in design.md, so that the ADR reserves for humans only
  the three loop-gating files AGENTS.md reserves
  (`.github/workflows/claude-review.yml`,
  `.github/workflows/release-please.yml`, `.github/dependabot.yml`) instead
  of all of `.github/**`, and names `agent-trailer-check.yml` among the
  workflows that arrive through a DevLoop cycle.
- WHILE the ADR is amended THE SYSTEM SHALL keep `adrBodyProblems`
  (`src/lib/adr.ts`) returning no problems for ADR-0001: all five sections
  in order, each with English and Russian blocks.
- WHEN this cycle's implementation commit lands THE SYSTEM SHALL add
  `src/content/journal/2026-11-06-q25-agent-trailer-check.md` with
  `status: in_progress`, `issue_opened_at: '2026-11-06T15:00:45Z'`, no
  `pr`, `release`, `merged_at`, `released_at` or `deployed_at`, and the exact
  title, seoTitle and decided copy given in design.md.
- IF any other journal entry is `status: in_progress` when the implementer
  starts THEN THE SYSTEM SHALL fail `npm test` / the journal loader rather
  than add a second open entry (existing invariant, unchanged).
- THE SYSTEM SHALL leave `AGENTS.md`, `.github/workflows/claude-review.yml`,
  `.github/workflows/release-please.yml`, `.github/dependabot.yml` and
  `.github/workflows/build.yml` unchanged.

## Out of scope

- Turning on enforcement (`enforce: true`). That is decided in
  mctlhq/.github#316 no earlier than 2026-11-13.
- Any change to the reusable workflow in `mctlhq/.github` or to its pinned
  SHA.
- Editing `AGENTS.md` (human-reserved), including deciding whether
  `agent-trailer-check.yml` should join its reserved-workflow list (see Open
  questions).
- Creating the `agent:*` labels by hand; the reusable workflow creates them.
- Changing how the implementer pipeline itself formats commits for other
  repositories or future cycles.
- Any deployment, image, nginx or site-content change beyond the ADR and
  journal copy above.

## Open questions

- The issue's YAML snippet omits a two-line comment that the live callers in
  `mctlhq/mctl-web`, `mctlhq/mctl-api` and `mctlhq/mctl-agents` all carry
  (the three files hash identically). The issue says the existing caller
  wins, so the proposal copies the comment too.
- ADR-0001 is amended in place rather than superseded by a new ADR. AGENTS.md
  already narrowed the reservation after #21 without a new ADR, so the ADR
  text is brought in line with it. If the owner prefers a superseding
  ADR-0007, send the proposal back.
- Should `agent-trailer-check.yml` be added to the human-reserved list in
  AGENTS.md? Once `enforce: true` is on, it is a check on the agent's own
  commits, which is the reason `claude-review.yml` is reserved. AGENTS.md is
  human-only, so this proposal does not change it and leaves the file
  implementer-owned, consistent with the current text. If the owner reserves
  it later, the ADR-0001 copy must be updated in the same move.
- Implementer commits in earlier cycles (for example PR #196) carried no
  `Agent:` trailer. This proposal requires the trailer for this cycle's
  commits. Whether commits added later by the shepherd or review-fix runs
  also carry it depends on the pipeline, not this repository; a missing
  trailer there would turn the label into `agent:mixed` or `agent:unknown`
  without failing the check.
- The `agent:*` label exists only once the workflow has run on the pull
  request, so it cannot be proven by a committed file; it is a reviewer
  check.
