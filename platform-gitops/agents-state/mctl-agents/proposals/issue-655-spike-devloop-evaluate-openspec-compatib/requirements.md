# Spike: evaluate an OpenSpec-compatible artifact contract for DevLoop proposals

## Context

mctlhq/mctl-agents#655 asks whether MCTL should stop owning a bespoke
planning format and adopt an OpenSpec-compatible artifact layer that does not
depend on the OpenSpec runtime. Today that format is the proposal triplet:
`requirements.md` + `design.md` + `tasks.md` (`TRIPLET` in
`orchestrator/run_issue_investigator.py:451`, `TRIPLET_FILENAMES` in
`orchestrator/context_assembly.py:148`). Execution semantics stay
MCTL-native: `.status.yaml` (`orchestrator/proposal_state.py`), approval
(`orchestrator/temporal/workflows/dev_loop.py`,
`orchestrator/temporal/activities/delegated_approval.py`), Temporal, Shepherd
(`orchestrator/run_shepherd.py`), CI and merge policy are not part of the
contract.

The goal is to make "MCTL executes SDD workflows" technically true, or show
with evidence that it is not worth it. The spike produces evidence, not a
rollout:

- an explicit artifact mapping;
- a lossless (or explicitly one-way) conversion of real proposals;
- a canonical capability spec plus a delta, applied by a simulated
  merge/archive;
- a documented boundary between spec verification and Shepherd;
- a strategy for change classes;
- cost estimates;
- exactly one recommendation: `ADOPT_CONTRACT`, `ADAPTER_ONLY` or `NO_GO`.

Everything ships as an isolated library, fixtures, a dev-only tool, a draft
ADR and a report. No production code path imports any of it.

## User stories

- AS a platform maintainer I WANT a written mapping from every section of
  the current triplet to an OpenSpec-style change package SO THAT I can see
  exactly what is gained, lost or duplicated.
- AS a platform maintainer I WANT a canonical capability spec plus an
  `ADDED`/`MODIFIED`/`REMOVED` delta that is applied deterministically SO THAT
  I can judge whether current-state specs are worth maintaining in brownfield
  repos.
- AS an operator of the Implementer agent I WANT evidence that a converted
  artifact carries everything the triplet carries today SO THAT a format
  change cannot silently degrade the implementer's input.
- AS a reviewer of the Shepherd I WANT the spec-verification boundary written
  down SO THAT spec conformance can never replace CI, P1/P2 review policy,
  approval or authorization.
- AS the DevLoop owner I WANT one recommendation backed by evidence, plus
  drafts of the follow-up issues, SO THAT nobody has to re-argue the decision
  from scratch.

## Acceptance criteria (EARS)

Artifact contract and mapping

- WHEN the spike is complete THE SYSTEM SHALL provide a mapping table that
  assigns every section of the current triplet, plus the source-issue
  linkage, to exactly one location in the candidate change package
  (`proposal.md`, `specs/<capability>/spec.md`, `design.md`, `tasks.md`), or
  marks it as an MCTL extension section with no OpenSpec equivalent. The
  sections to cover are:
  - `requirements.md`: title, Context, User stories, Acceptance criteria
    (EARS), Out of scope, Open questions;
  - `design.md`: Current state including `Deployed state checked:`, Proposed
    solution, Alternatives, Platform impact;
  - `tasks.md`: numbered tasks with `depends on` and `DoD:`, Tests, Rollback.
- THE SYSTEM SHALL define the candidate change package so that each of these
  has its own place: proposal intent, behavioral requirements, design
  decisions, task decomposition, per-capability delta semantics, and the
  source-issue reference.
- IF a candidate artifact contains a `.status.yaml` key at top level or in
  front matter (`status`, `approval`, `attempt`, `execution`, `github`, `pr`,
  `merged_at`, `merge_commit`, `control`, `context`) THEN the validator SHALL
  reject it with an error that names the key.

Conversion and round trip

- WHEN `export` converts a current triplet into a change package and `import`
  converts it back THE SYSTEM SHALL reproduce each original file byte for
  byte after a documented normalization (line endings, trailing whitespace,
  final newline), or SHALL report every section it could not reproduce.
- THE SYSTEM SHALL run that round trip on at least two real proposals:
  - this proposal's own triplet, which the Implementer can always read at
    `$PROPOSAL_DIR`;
  - at least one merged historical proposal. The preferred one is
    `agents-state/mctl-agents/proposals/issue-623-tracing-record-cache-read-write-token-us/`.
- IF a section cannot be round-tripped losslessly THEN the report SHALL
  document a one-way migration for that section and explain why a round trip
  is undesirable.

Canonical spec and delta

- THE SYSTEM SHALL include one canonical capability spec, `devloop-approval`,
  whose requirements are derived from code that exists today. Each
  requirement SHALL cite the file it was derived from. The sources are:
  - `orchestrator/proposal_state.py`: `human_approval_satisfied`,
    `execution_authorization`, `_ANONYMOUS_APPROVERS`, `_FALSEY`;
  - `orchestrator/temporal/activities/delegated_approval.py`:
    `approval_intent`, which binds the approval to `<service>/<slug>`.
- WHEN a delta containing at least one `ADDED` and one `MODIFIED` requirement
  is applied to the canonical spec THE SYSTEM SHALL produce a new canonical
  spec deterministically, applying operations in the order RENAMED, REMOVED,
  MODIFIED, ADDED.
- IF a delta modifies, removes or renames a requirement that is absent from
  the canonical spec, or adds one that already exists, THEN the apply step
  SHALL fail without writing any output.
- WHEN the simulated archive runs THE SYSTEM SHALL write the new canonical
  spec and move the change package under an `archive/` path. Both writes
  SHALL stay inside the temporary or fixture directory it was given.

Validation

- THE SYSTEM SHALL validate at least the following:
  - each requirement has a `SHALL` or `MUST` statement and at least one
    scenario;
  - requirement names are unique per capability;
  - a `normal` or `governed` change has at least one delta;
  - a `governed` change has a `design.md`;
  - the source-issue reference has the form `mctlhq/<repo>#<n>`.
- WHEN the validator runs over the converted proposals THE SYSTEM SHALL
  record every defect it finds that the current pipeline does not detect.
  Today the investigator only checks that the three files exist as plain
  files (`run_issue_investigator.py`, step 4, around line 3865).

Agent fit and measurements

- THE SYSTEM SHALL record, for each converted proposal, the byte size and an
  approximate token count, with the counting method stated in the report, for
  each of the following:
  - the current triplet;
  - the candidate package;
  - the candidate package plus the canonical spec it touches.
- THE SYSTEM SHALL record a simulated Investigator result for one historical
  issue (issue, code and canonical spec in; change package out) and a
  simulated Implementer reading of that package.
- The simulated results SHALL be scored on requirement clarity, task
  completeness, context size, ambiguity, and whether the changed capability
  is identified exactly.
- The simulation SHALL be labeled as such and SHALL NOT be presented as a
  production agent run.

Boundaries and invariants

- THE SYSTEM SHALL document spec verification as one input to the Shepherd
  decision, alongside CI/required checks and P1/P2 review findings.
- THE SYSTEM SHALL state that spec verification never merges, approves,
  authorizes or overrides a Shepherd `decide()` outcome.
- IF spec verification is absent or errors THEN the documented design SHALL
  grant nothing. A missing signal never counts as a pass.
- IF spec verification fails THEN the result SHALL route through the
  existing remediation path as a finding, never as a new lifecycle status.
- WHILE the spike is in progress THE SYSTEM SHALL NOT change any of the
  following:
  - `run_issue_investigator.py`, `run_implementer.py`, `run_shepherd.py`;
  - `orchestrator/temporal/**`, `proposal_state.py`;
  - any `.status.yaml`, or any mctl-gitops content.
- A test SHALL assert that no production module imports the new library.
- THE SYSTEM SHALL use no OpenSpec CLI, npm package or other OpenSpec runtime
  dependency, and SHALL add no new entries to `pyproject.toml` / `uv.lock`.
  Compatibility is defined against the published file format only.

Change classes

- THE SYSTEM SHALL define three change classes (`trivial`, `normal`,
  `governed`) as validation shapes inside one artifact model and one DevLoop
  lifecycle. A `trivial` change needs no spec delta.
- IF an artifact declares a change class THEN that declaration SHALL only
  select validation rules. It SHALL NOT waive or alter approval:
  `control.requires_human_approval` in `.status.yaml` stays the only approval
  switch.

Decision output

- WHEN the spike completes THE SYSTEM SHALL publish exactly one
  recommendation, chosen with the decision rubric defined in design.md.
- The report SHALL include a migration and interop cost estimate for the
  existing proposals under `agents-state/*/proposals/`.
- IF the recommendation is `ADOPT_CONTRACT` or `ADAPTER_ONLY` THEN the report
  SHALL include a staged plan and drafts of the follow-up issues.

## Out of scope

- Any change to DevLoopWorkflow, Temporal, approval, authorization, Shepherd
  decision logic, CI or merge policy.
- Changing what the investigator writes or what the implementer reads in
  production. No new proposal directory layout goes live.
- Bulk migration of historical proposals or `.status.yaml`.
- A public `mctl spec` CLI in mctl-api or mctl-telegram. The dev-only
  `tools/spec_contract.py` exists only to produce evidence.
- Installing or invoking the OpenSpec CLI.
- Adapters for Spec Kit, Kiro or other SDD formats.
- Filing GitHub issues. Follow-ups are drafted in the report, and a human
  files them.
- Fixing the gap where approval is not bound to the proposal's content. It is
  only modeled in a fixture delta.

## Open questions

- **OpenSpec format version.** Compatibility targets the published layout:
  - `openspec/specs/<cap>/spec.md`;
  - `openspec/changes/<id>/{proposal.md, design.md, tasks.md, specs/<cap>/spec.md}`;
  - `## ADDED|MODIFIED|REMOVED|RENAMED Requirements`, `### Requirement:`,
    `#### Scenario:`.

  This investigation could not verify that layout against a specific OpenSpec
  release. The implementation pins the targeted grammar in the ADR and does
  not depend on CLI behavior.
- **Where canonical specs live after adoption.** The options are the target
  service repo (proposed: the implementation PR applies the delta, so no
  post-merge writer is needed) or mctl-gitops `agents-state`. The spike
  evaluates the first and records the second as the alternative.
- **Mapping EARS to scenarios.** It is unclear how an EARS `WHILE`/`IF`
  criterion should map to an OpenSpec scenario. Proposed: keep the EARS
  sentence verbatim as the requirement body and derive a `WHEN`/`THEN`
  scenario. Whether reviewers accept that duplication is a finding for the
  report.
- **Approval is not bound to content.** Approval is bound to `<service>/<slug>`,
  not to a digest of the proposal content: `approval_intent` hashes only
  `{"service", "slug"}`, and `.status.yaml` `approval` carries only
  `approved_by`/`approved_at`. A proposal edited after approval is therefore
  still "approved". Invariant 3 of the issue asks that proposal immutability
  not be weakened, and it is already weak today. The fixture delta uses this
  gap as its `ADDED` example. Closing it is a separate follow-up.
- **Simulated Investigator run.** The simulated run is performed by the
  implementer agent's own model inside its run. A real investigator A/B run
  on a candidate prompt would cost about $3. Whether that is worth doing
  before the decision is left to the reviewer.
- **Prior proposal for this issue.** A proposal for this issue already
  existed in `agents-state` (status `proposed`). This investigation refines
  it and does not change its direction.
