# Spike: evaluate an OpenSpec-compatible artifact contract for DevLoop proposals

## Context

Every DevLoop proposal is a triplet today: `requirements.md`, `design.md`
and `tasks.md`, plus `.status.yaml`, under
`platform-gitops/agents-state/<service>/proposals/<slug>/`. The
issue-investigator writes the triplet (`TRIPLET` in
`orchestrator/run_issue_investigator.py`). The implementer reads it
(`run_implementer.py`, prompt step 1). Context assembly reads it again as
prior context (`TRIPLET_FILENAMES` in `orchestrator/context_assembly.py`).
`.status.yaml` holds the execution state: status, approval, attempt, PR,
GitHub projection, execution and context ids. MCTL owns that state
(`orchestrator/proposal_state.py`). Issue #655 asks whether the planning half
of this, meaning the triplet, should become an OpenSpec-compatible change
artifact: `proposal.md`, `specs/<capability>/spec.md` with
`ADDED`/`MODIFIED`/`REMOVED` deltas, `design.md` and `tasks.md`. Under that
model, canonical current-state capability specs are synced after a merge.
Execution, approval, authorization, Temporal state, review and merge would
all stay MCTL-native.

This is a spike. It produces evidence and exactly one recommendation:
`ADOPT_CONTRACT`, `ADAPTER_ONLY` or `NO_GO`. It does not change how
production proposals are written or consumed. Everything it adds is inert:
a draft contract document, a stand-alone dev tool, fixtures, tests and a
report. No runtime module under `orchestrator/` imports any of it.

## User stories

- AS a platform maintainer I WANT a written, testable mapping from the current proposal triplet to an OpenSpec-compatible change package SO THAT I can decide on the planning contract from evidence instead of opinion.
- AS a platform maintainer I WANT one bounded DevLoop capability expressed as a canonical spec, a change delta and the resulting canonical spec SO THAT I can judge whether brownfield deltas are worth having.
- AS an implementer-agent operator I WANT proof that nothing the implementer reads today is lost in the candidate form SO THAT adopting it cannot silently degrade implementation quality.
- AS the owner of Shepherd and the approval gate I WANT the spec-verification boundary written down SO THAT spec conformance never becomes a merge, approval or authorization signal.
- AS a contributor fixing a typo or bumping a dependency I WANT a trivial change class SO THAT small fixes do not pay for the full spec ceremony, and there is still only one DevLoop lifecycle.

## Acceptance criteria (EARS)

Contract and mapping
- WHEN the spike is complete THE SYSTEM SHALL provide a draft contract document (`docs/adr/021-sdd-artifact-contract.md`, status `proposed`) that defines the change package `proposal.md`, `specs/<capability>/spec.md`, `design.md` and `tasks.md`. It SHALL define which section of each file carries proposal intent, behavioral requirements, design decisions, task decomposition, delta semantics and the source-issue reference.
- WHEN the spike is complete THE SYSTEM SHALL provide a mapping table from every current artifact and section to a candidate artifact and section, covering every `requirements.md` section (`Context`, `User stories`, `Acceptance criteria (EARS)`, `Out of scope`, `Open questions`), every `design.md` section, every `tasks.md` section (numbered tasks with DoD and dependencies, `Tests`, `Rollback`) and the `.status.yaml` `source` block. Each row SHALL be classified as `preserved`, `moved`, `duplicated` or `lost`.
- THE SYSTEM SHALL keep every `.status.yaml` field out of the candidate artifact. This covers `status`, `approval`, `attempt`, `pr`, `github`, `execution`, `context` and `control`. The only exception is a read-only source-issue reference (`repo`, `issue`, `url`), which MAY be copied into `proposal.md` front matter.
- IF a candidate package contains any execution-state key (the keys listed above) THEN THE SYSTEM SHALL report it as a validation error.

Canonical and delta specs
- WHEN the spike is complete THE SYSTEM SHALL include one canonical capability spec fixture for `devloop-approval`, derived from `human_approval_satisfied` / `execution_authorization` in `orchestrator/proposal_state.py` and the `approve` signal in `orchestrator/temporal/workflows/dev_loop.py`. It SHALL also include a change-delta fixture that contains at least one `ADDED` requirement and at least one `MODIFIED` or `REMOVED` requirement.
- WHEN the delta is applied to the canonical spec THE SYSTEM SHALL produce a new canonical spec that is byte-identical to a committed expected fixture, and SHALL write an archived copy of the change to a temporary directory.
- IF a delta refers to a requirement that is missing from the canonical spec (`MODIFIED`/`REMOVED`), or adds one that already exists (`ADDED`), THEN THE SYSTEM SHALL refuse the apply with a named conflict and SHALL write nothing.

Round trip
- WHEN the spike is complete THE SYSTEM SHALL convert at least one representative merged proposal, copied as a fixture from `agents-state/mctl-agents/proposals/issue-623-tracing-record-cache-read-write-token-us/`, into the candidate form. A second fixture SHALL come from a different service.
- WHEN a converted package is converted back THE SYSTEM SHALL either reproduce the original triplet byte for byte after a documented normalization (trailing whitespace, final newline), or the report SHALL declare a one-way migration and give the reason.
- THE SYSTEM SHALL report, for each fixture, the byte size and an approximate token count (bytes / 4, labelled as an approximation) for both the current and the candidate representation.

Agent boundaries
- WHEN the spike is complete THE SYSTEM SHALL record a traceability check for each converted fixture. The check SHALL show that every EARS criterion, numbered task with its DoD and dependency, test item and rollback step in the original triplet can be found at a stated location in the candidate package.
- THE SYSTEM SHALL record observations for the Investigator and Implementer boundaries on requirement clarity, task completeness, context size, ambiguity, implementation-success risk and identification of the changed capability. Each observation SHALL be marked `improves`, `preserves` or `worsens`, with the evidence behind it. Any observation not backed by an actual model run SHALL be labelled `simulated`.

Verification boundary
- THE SYSTEM SHALL document spec verification as an input to Shepherd, alongside CI and review findings. It SHALL NOT be a replacement for any of them. The document SHALL state that a spec-verification result never produces a merge, an approval, an authorization grant, or a change to `decide()` in `orchestrator/run_shepherd.py` within this spike.
- IF a proposed design would let spec verification satisfy or bypass `human_approval_satisfied`, the action-approval gate (ADR 016) or required CI checks THEN THE SYSTEM SHALL list that design as rejected.

Interop and change classes
- WHEN the spike is complete THE SYSTEM SHALL provide a dev tool `tools/spec_contract.py` with the sub-commands `validate`, `diff`, `apply`, `import`, `export` and `measure`. The tool SHALL use only the Python standard library and PyYAML, which is already a dependency, and SHALL NOT invoke or import the OpenSpec CLI.
- THE SYSTEM SHALL define the change classes `trivial`, `normal` and `governed` as a single field in `proposal.md`. A `trivial` package SHALL validate without a `specs/` delta. All three classes SHALL map onto the existing `.status.yaml` lifecycle, with no new status values.

Decision
- WHEN the spike is complete THE SYSTEM SHALL publish `docs/spikes/655-openspec-compatible-artifact-contract.md`. The report SHALL contain all the measurements listed in the issue, the answers to questions 1 through 10, a migration and interop cost estimate, and exactly one of `ADOPT_CONTRACT`, `ADAPTER_ONLY` or `NO_GO`, chosen against the rubric in design.md.
- IF the recommendation is `ADOPT_CONTRACT` THEN THE SYSTEM SHALL include a staged migration plan and a list of follow-up issues, each with a title and a scope. Under that plan, after migration there is one canonical requirements source and no permanent dual authoring.

Isolation
- WHILE the spike is unmerged or merged THE SYSTEM SHALL NOT change the investigator prompt, `TRIPLET`, `TRIPLET_FILENAMES`, the implementer prompt, `run_shepherd.decide()`, `dev_loop.py`, `proposal_state.py` or any file under `platform-gitops/`.

## Out of scope

- Changing the proposal layout, the investigator output, or the implementer input in production.
- Replacing or modifying `DevLoopWorkflow`, Temporal, approval, authorization, Shepherd, CI or merge policy.
- Bulk migration of historical proposals under `agents-state/`.
- A public `mctl spec` CLI, or an mctl-api endpoint or MCP tool.
- A runtime or CI dependency on the OpenSpec CLI or npm package.
- Wiring a spec-conformance check into Shepherd. The spike defines this boundary on paper only.

## Open questions

- Which OpenSpec revision counts as "compatible"? Without network access the spike pins the format to what it can document: header conventions such as `## ADDED Requirements`, `### Requirement:` and `#### Scenario:`, plus `SHALL`/`MUST` wording. The report must name the revision it was checked against. If none could be checked, it must record the gap.
- Can EARS acceptance criteria be represented as OpenSpec requirements with scenarios without loss? Assumed: each EARS line becomes one requirement with one scenario, and the EARS keywords are kept verbatim. The traceability check confirms or refutes this.
- Does the spike need real model runs for the Investigator and Implementer boundary? Assumed no: the boundary is simulated through traceability and prompt-size measurement, labelled `simulated`. One real investigator run against a fixture is optional and needs an operator to spend about $3.
- Capability taxonomy: how capabilities are named and scoped per service, for example `devloop-approval` versus `approval`. The spike proposes a naming rule but cannot validate it across all 16 services.
- Approval provenance: `.status.yaml` records `approval.approved_by`/`approved_at`, but it does not record a content digest of the triplet that was approved. Any adoption must decide whether approval binds to a package digest. This is recorded as a follow-up and is not solved here.
- ADR numbering: `docs/adr/` already contains two `011-*` files. The draft uses `021`, which may need renumbering at merge time.
