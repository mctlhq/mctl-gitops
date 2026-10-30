# SpikeDefinition v1alpha1 contract, validation and pilot manifests (slice 1)

## Context

Spikes are the organisation's main decision instrument, but they have no
machine-readable contract. Their lifecycle (running in DevLoop, parked behind a
prose trigger, measured without a recorded verdict, or abandoned) and their
verdicts (free text in closing comments, e.g. `ADAPTER_ONLY` on
`mctlhq/mctl-agents#655`) can only be read by a human. `EpicDefinition`
(`roadmap/schemas/epic-definition.schema.json`, `roadmap/scripts/validate.py`)
already solved this for epics: authored desired state in Git, observed state kept
separate, deterministic offline validation.

This proposal adds `kind: SpikeDefinition` (`roadmap.mctl.ai/v1alpha1`) under
`roadmap/` with the same discipline: a JSON Schema sharing `issueRef` / `localId`
with the epic schema, kind dispatch plus spike semantics and cross-kind corpus
invariants in `validate.py`, five pilot manifests in `roadmap/spikes/`, tests, a
README section and CI coverage. It is slice 1 of issue mctlhq/.github#210; the
`spike` drift family in `reconcile.py` / `health.py` (and its diff/health schema
enums and snapshot mutators) is slice 2 and is not built here.

## User stories

- AS a spike owner I WANT to declare a spike's question, lifecycle, allowed
  outcomes and timebox in Git SO THAT its state and decision vocabulary are fixed
  and reviewable before the result is known.
- AS a spike owner I WANT to record the verdict in an authored `decision` block
  SO THAT the decision is machine-readable instead of buried in a closing comment.
- AS a roadmap maintainer I WANT the validator to reject a spike whose epic
  binding, verdict or lifecycle fields are inconsistent SO THAT a broken manifest
  never reaches `main`.
- AS the later drift detector (slice 2) I WANT a validated corpus of spikes with
  real `active`, `parked`, `proposed` and `decided` subjects SO THAT every drift
  type has a real subject in both directions.

## Acceptance criteria (EARS)

Schema and kind dispatch

- WHEN `validate.py` loads a manifest THE SYSTEM SHALL select the schema by the
  document's `kind`: `EpicDefinition` uses `roadmap/schemas/epic-definition.schema.json`,
  `SpikeDefinition` uses `roadmap/schemas/spike-definition.schema.json`.
- IF a manifest's `kind` is missing or is not one of those two THEN THE SYSTEM
  SHALL fail that manifest with a `$.kind:` message naming the supported kinds.
- THE SYSTEM SHALL define `issueRef` and `localId` once, in
  `roadmap/schemas/common.schema.json`, and both the epic and spike schemas SHALL
  reference those definitions.
- WHILE an EpicDefinition manifest is valid today THE SYSTEM SHALL keep it valid,
  and every existing epic validation message SHALL be unchanged.
- IF a SpikeDefinition carries a field not declared by the schema (for example an
  authored issue `state`, `status`, `prs` or `comments`) THEN THE SYSTEM SHALL
  reject it, because observed state is never copied into the manifest.
- WHEN a SpikeDefinition authors a date (`activation.reviewBy`,
  `timebox.decisionBy`, `decision.decidedAt`) THE SYSTEM SHALL accept it quoted or
  unquoted in YAML and SHALL validate it as an ISO `YYYY-MM-DD` calendar date.

Spike semantics (per manifest)

- IF `spec.lifecycle` is `decided` and `spec.decision` is absent THEN THE SYSTEM
  SHALL fail with a path under `$.spec`.
- IF `spec.decision` is present and `spec.lifecycle` is not `decided` THEN THE
  SYSTEM SHALL fail with a path under `$.spec` (this includes `archived`, which
  means the question stopped mattering without a verdict).
- IF `spec.decision.verdict` is not one of `spec.outcomes` THEN THE SYSTEM SHALL
  fail with `$.spec.decision.verdict:` naming the verdict and the allowed outcomes.
- IF `spec.lifecycle` is `parked` and `spec.activation.trigger` is absent THEN THE
  SYSTEM SHALL fail with a path under `$.spec`.
- IF `spec.lifecycle` is `active` and `spec.timebox.decisionBy` is absent THEN THE
  SYSTEM SHALL fail with a path under `$.spec`.
- IF `spec.outcomes` contains a duplicate value THEN THE SYSTEM SHALL fail.
- IF `spec.decision.followUps` lists the same issue twice (case-insensitive
  repository) or lists the spike's own `spec.github.issue` THEN THE SYSTEM SHALL
  fail with a path under `$.spec.decision.followUps`.
- IF `spec.evidence.report` is absolute or contains a `..` segment THEN THE SYSTEM
  SHALL fail.

Corpus and cross-kind invariants

- IF two SpikeDefinition manifests share `metadata.name` THEN THE SYSTEM SHALL
  fail both.
- IF two SpikeDefinition manifests bind the same GitHub issue (canonical,
  case-insensitive repository identity via `validate.issue_key`) THEN THE SYSTEM
  SHALL fail both.
- WHEN a SpikeDefinition declares `spec.epic` THE SYSTEM SHALL require that an
  EpicDefinition named `spec.epic.name` exists in the validated corpus, that it has
  a work item with id `spec.epic.workItem`, and that this work item's `issue` is the
  same issue as the spike's `spec.github.issue`; otherwise it SHALL fail with a
  `$.spec.epic` message saying which of the three does not hold.
- IF a spike's `spec.github.issue` is bound as an EpicDefinition work item and the
  spike does not declare `spec.epic` pointing at exactly that work item THEN THE
  SYSTEM SHALL fail the spike (duplicate binding across kinds).
- IF a spike's `spec.github.issue` is an EpicDefinition root issue THEN THE SYSTEM
  SHALL fail the spike.
- WHILE validating a corpus that contains only EpicDefinition manifests THE SYSTEM
  SHALL produce exactly the corpus diagnostics it produces today, so
  `reconcile.validate_corpus` and every consumer of `validate.corpus_errors` are
  unaffected.

CLI, corpus and CI

- WHEN `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` runs on the
  committed corpus THE SYSTEM SHALL exit 0 and print `PASS` for every manifest.
- WHEN any single rule above is violated by a mutation of one pilot manifest THE
  SYSTEM SHALL print `FAIL <path>` with the precise message and exit non-zero
  (exit 1, the existing "invalid manifest" code; exit 2 stays reserved for usage
  and schema-load errors, see Open questions).
- WHEN `validate.py` is run with no path arguments THE SYSTEM SHALL validate both
  `roadmap/epics` and `roadmap/spikes`.
- THE SYSTEM SHALL ship five pilot manifests in `roadmap/spikes/`:
  `portable-runtime.yaml` (`mctlhq/mctl-agents#746`, active),
  `agent-scale-coordination.yaml` (`mctlhq/mctl-agents#747`, parked with trigger),
  `duet-sessions.yaml` (`mctlhq/mctl-agents#757`, proposed),
  `security-finding-lifecycle.yaml` (`mctlhq/.github#209`, active) and
  `openspec-contract.yaml` (`mctlhq/mctl-agents#655`, decided, verdict
  `ADAPTER_ONLY`, report `docs/spikes/655-openspec-contract.md`).
- WHEN `.github/workflows/roadmap-validate.yml` runs THE SYSTEM SHALL validate
  `roadmap/epics` and `roadmap/spikes` together in one invocation.
- WHEN `python -m unittest discover -s roadmap/tests -p 'test_*.py'` runs THE
  SYSTEM SHALL be green, with one test per rule above.
- THE SYSTEM SHALL perform no GitHub reads or writes during validation.

## Out of scope

- The `spike` diff family (`SpikeClosedWithoutVerdict`, `SpikeDecidedButOpen`,
  `SpikeTimeboxExceeded`, `SpikeParkedReviewDue`, `SpikeReportMissing`) in
  `reconcile.py` / `health.py`, its enums in `roadmap-diff.schema.json` /
  `roadmap-health.schema.json`, the contents GET adapter, and the snapshot
  mutators in `roadmap/tests/mutations.py` for those diff types: slice 2.
- Any change to `reconcile.py`, `health.py`, `ready.py`, `plan.py`, `apply.py`,
  `publish.py` or the RoadmapPublication: spikes are not published in this slice.
- A GitHub `Spike` issue type or `spike` label.
- Back-filling manifests for spikes other than the five pilots.
- DevLoop / investigator reading `SpikeDefinition`.
- `mctl-api/internal/roadmap` and the `mctl_roadmap_*` MCP tools.
- Any change to the epic completion rule: a spike bound inside an epic stays an
  ordinary work item.

## Open questions

- Exit code. The issue's acceptance says the validator "exits 2" on each mutation,
  but `validate.main` returns 1 for invalid manifests and 2 for usage/schema-load
  errors, and `roadmap/tests/test_validate.py` asserts both. This proposal keeps 1
  for invalid manifests; switching to 2 would conflate the two classes and break
  existing callers.
- "mutations.py entries for every new diff type" is listed under slice 1, but the
  diff types themselves are slice 2. This proposal adds pure manifest mutators for
  the validation rules in slice 1 and leaves snapshot mutators for diff types to
  slice 2, where the detectors exist.
- Pilot authored values not stated by the issue: `outcomes` for #746 (the issue
  gives them), #747, #757 and `.github#209`; `timebox.decisionBy` for #746 and
  #209; `activation.trigger` / `reviewBy` for #747. The implementer derives them
  from each issue's own body (decision rule / outcome section) and flags them in
  the PR for owner confirmation. Choosing a `decisionBy` already earlier than
  today would make slice 2 report `SpikeTimeboxExceeded` immediately, which is a
  true observation, not a reason to pick a later date.
- `openspec-contract.yaml` is authored after the fact, so its `outcomes`
  (`ADAPTER_ONLY`, `ADOPT_CONTRACT`, taken from the report
  `docs/spikes/655-openspec-contract.md` in `mctlhq/mctl-agents`) were not "fixed
  before the spike started" by this manifest. That is accepted for the pilot; the
  decision fields come from the owner's 2026-10-17 closing comment
  (`decidedBy: mashkovd`).
- None of the five pilots is bound as a work item in any `roadmap/epics/*.yaml`
  today, so no pilot declares `spec.epic`; the epic-binding rule is exercised by
  tests, not by the corpus. "The decided one resolves its epic binding where it
  has one" is therefore vacuous for #655.
- Whether `evidence.report` should be required when `lifecycle: decided`. The
  issue does not list it as a rule; this proposal keeps it optional so a decided
  spike without a write-up stays valid (slice 2's `SpikeReportMissing` then only
  checks authored paths).
- `outcomes` minimum size: this proposal requires at least two (one allowed
  verdict is not a decision). The issue does not state a minimum.
- Whether any consumer outside this repository (for example
  `mctl-api/internal/roadmap`) loads `epic-definition.schema.json` standalone. If
  it does, the `$ref` into `common.schema.json` needs that file too. Not
  observable from this clone.
