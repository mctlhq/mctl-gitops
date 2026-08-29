# docs: add dev-loop E2E verification record

## Context

Issue #212 asks for a small, permanent record in `mctl-academy` documenting
that the Temporal dev-loop pipeline (`investigate` → atomic `approve` →
`implement`, as described in `PLAN.md` section 5, "Agents and PR flow
(Temporal dev-loop)") was exercised end-to-end against this repository on
2026-08-29. The issue itself is the E2E test drive for the atomic-approve
stage shipped in `mctlhq/mctl-agents` (referenced in the issue as
`mctlhq/mctl-agents#212`).

This matters because the dev-loop's two-step approval (a Temporal `approve`
signal plus a `.status.yaml` flip to `accepted`, per `PLAN.md` lines 197-215)
is documented as "the sharpest edge in the whole pipeline" — either step
alone silently no-ops or hangs. A living, append-only record of verified
runs gives future maintainers and agents a citable data point that the full
chain (issue -> proposal -> approval -> merged PR) actually completed against
this specific service, distinct from the general pipeline documentation that
already lives in `mctl-agents`. The file is a record, not new pipeline
behavior: it does not change how the dev-loop runs, only how a successful run
against this repo is remembered.

## User stories

- AS a maintainer reviewing the mctl-agents pipeline I WANT a durable,
  append-only record of E2E-verified dev-loop runs against mctl-academy
  SO THAT I can confirm the atomic-approve stage (and any future pipeline
  change) has been proven against a real service without re-deriving it from
  scattered issue/PR history.
- AS an agent (issue-investigator, implementer, or shepherd) operating on a
  future mctl-academy issue I WANT to know the dev-loop has previously
  completed successfully against this repo SO THAT I can trust the pipeline
  mechanics described in `PLAN.md` are current and proven, not aspirational.
- AS a future contributor reading repo docs I WANT a one-paragraph
  explanation of what the dev-loop is and a link to its ADR SO THAT I do not
  need to read all of `PLAN.md` to understand the term "dev-loop".

## Acceptance criteria (EARS)

- WHEN this proposal is implemented THE SYSTEM SHALL contain a new file
  `docs/dev-loop-e2e.md` in the `mctl-academy` repository.
- WHEN `docs/dev-loop-e2e.md` is read THE SYSTEM SHALL present exactly one
  introductory paragraph describing the dev-loop as
  issue -> spec proposal -> human approval -> PR, including a link to
  `mctlhq/mctl-agents` ADR-006.
- WHEN `docs/dev-loop-e2e.md` is read THE SYSTEM SHALL present a
  "Verified runs" section containing a Markdown table with columns for date,
  issue link, and pipeline version.
- WHEN `docs/dev-loop-e2e.md` is created THE SYSTEM SHALL populate the
  "Verified runs" table with exactly one row: date `2026-08-29`, issue link
  to `https://github.com/mctlhq/mctl-academy/issues/212`, and pipeline
  version `mctl-agents 1.30.0`.
- WHILE this proposal is being implemented THE SYSTEM SHALL NOT modify any
  file other than `docs/dev-loop-e2e.md`.
- IF a future dev-loop run against `mctl-academy` is E2E-verified THEN THE
  SYSTEM SHALL support appending a new row to the same table rather than
  replacing or restructuring the file (this proposal only need establish
  that shape; appending future rows is a separate, later change).

## Out of scope

- Any change to the dev-loop pipeline itself (Temporal workflows, CWFTs,
  `mctl-agents` code) — this proposal only records that a run happened.
- Any change to `PLAN.md`, `README.md`, `CONTRIBUTING.md`, or any other
  existing documentation file.
- Automating the append of future "Verified runs" rows (e.g. via a CI job or
  agent step) — the issue asks only for the initial record; future rows are
  described as a manual/future action ("future E2E runs append rows to the
  table"), not something this proposal must automate.
- Adding `docs/dev-loop-e2e.md` to any build, lint, or CI pipeline (e.g.
  `scripts/validate-content.mjs`) — it is a plain Markdown record, not
  `content/` in the schema-governed sense, and nothing in the repo's
  tooling references a `docs/` directory today.
- Verifying or re-deriving ADR-006's content itself — this proposal only
  links to it.

## Open questions

- The exact ADR-006 URL is not given in the issue. Interpretation: link to
  `https://github.com/mctlhq/mctl-agents/blob/main/docs/adr/ADR-006-*.md`
  is not resolvable from this read-only `mctl-academy` clone (no access to
  the `mctl-agents` repo to confirm the file's exact path/slug). Proceeding
  with a best-effort, conventionally-named link
  (`https://github.com/mctlhq/mctl-agents` repo root, with a note pointing at
  "ADR-006" by name) so the file ships; the human reviewer should confirm
  or correct the precise ADR-006 path before merge.
- Whether `docs/dev-loop-e2e.md` should be linked from `README.md` is not
  stated. Interpretation: the issue says "no other files should change", so
  README is left untouched; the file is discoverable by path/convention only.
- Pipeline version is given as "mctl-agents 1.30.0" in the issue; this is
  taken as authoritative and not re-verified against any live deployment
  manifest (the read-only clone has no access to `mctl-agents`'
  `values.yaml` or image tags).
