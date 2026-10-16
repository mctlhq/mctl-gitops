# Spike: evaluate an OpenSpec-compatible artifact contract for DevLoop proposals

## Context

mctlhq/mctl-agents#655 asks whether MCTL should stop owning a bespoke
planning format (`requirements.md` + `design.md` + `tasks.md`, the `TRIPLET`
constant in `orchestrator/run_issue_investigator.py:451` and
`TRIPLET_FILENAMES` in `orchestrator/context_assembly.py:148`) and adopt an
OpenSpec-compatible, OpenSpec-runtime-independent artifact layer. Execution
semantics stay MCTL-native: `.status.yaml`, approval
(`orchestrator/proposal_state.py`), Temporal (`DevLoopWorkflow`), Shepherd,
CI and merge policy are not part of the contract.

The positioning goal is "MCTL executes SDD workflows". The spike must produce
evidence, not a rollout: an explicit artifact mapping, a lossless (or
explicitly one-way) conversion of real proposals, a canonical capability spec
plus a delta applied by a simulated merge/archive, a documented spec
verification versus Shepherd boundary, a change-class strategy, cost
estimates, and exactly one recommendation: `ADOPT_CONTRACT`, `ADAPTER_ONLY`
or `NO_GO`. Everything ships as an isolated library, fixtures, a dev-only
tool, a draft ADR and a report. No production code path imports any of it.

## User stories

- AS a platform maintainer I WANT a written mapping from every section of
  the current triplet to an OpenSpec-style change package SO THAT I can see
  exactly what is gained, lost or duplicated.
- AS a platform maintainer I WANT a canonical capability spec plus an
  `ADDED`/`MODIFIED`/`REMOVED` delta that is applied deterministically SO THAT
  I can judge whether current-state specs are worth maintaining.
- AS an Implementer agent operator I WANT evidence that a converted artifact
  carries everything `requirements.md`/`design.md`/`tasks.md` carry today SO
  THAT a format change cannot silently degrade implementation input.
- AS a reviewer of the Shepherd I WANT the spec-verification boundary written
  down SO THAT spec conformance can never replace CI, P1/P2 review policy,
  approval or authorization.
- AS the DevLoop owner I WANT one evidence-backed recommendation with
  follow-up issue drafts SO THAT the decision does not have to be argued
  again from scratch.

## Acceptance criteria (EARS)

Artifact contract and mapping

- WHEN the spike is complete THE SYSTEM SHALL provide a mapping table that
  assigns every section of the current triplet (`requirements.md`: title,
  Context, User stories, Acceptance criteria (EARS), Out of scope, Open
  questions; `design.md`: Current state incl. `Deployed state checked:`,
  Proposed solution, Alternatives, Platform impact; `tasks.md`: numbered
  tasks with `depends on` and `DoD:`, Tests, Rollback) and the source-issue
  linkage to exactly one location in the candidate change package
  (`proposal.md`, `specs/<capability>/spec.md`, `design.md`, `tasks.md`), or
  marks it as an MCTL extension section with no OpenSpec equivalent.
- THE SYSTEM SHALL define the candidate change package so that it separates
  proposal intent, behavioral requirements, design decisions, task
  decomposition, per-capability delta semantics and the source-issue
  reference.
- IF a candidate artifact contains any `.status.yaml` field (status,
  approval, attempt, execution, github, pr, merge_commit, control) THEN the
  validator SHALL reject it with an error that names the field.

Conversion and round trip

- WHEN `export` converts a current triplet into a change package and `import`
  converts it back THE SYSTEM SHALL reproduce each original file byte for byte
  after a documented normalization (line endings, trailing whitespace, final
  newline), or report every section it could not reproduce.
- THE SYSTEM SHALL run that round trip on at least two real proposals: this
  proposal's own triplet (always readable by the Implementer at
  `$PROPOSAL_DIR`) and at least one merged historical proposal (preferred:
  `agents-state/mctl-agents/proposals/issue-623-tracing-record-cache-read-write-token-us/`).
- IF a lossless round trip cannot be achieved for a section THEN the report
  SHALL document a one-way migration for it and explain why a round trip is
  undesirable.

Canonical spec and delta

- THE SYSTEM SHALL include one canonical capability spec, `devloop-approval`,
  whose requirements are derived from code that exists today
  (`orchestrator/proposal_state.py`: non-anonymous `approval.approved_by`,
  the `_FALSEY` waiver denylist for `control.requires_human_approval`; the
  approval flow in `orchestrator/temporal/workflows/dev_loop.py`), with each
  requirement citing the file it was derived from.
- WHEN a delta containing at least one `ADDED` and one `MODIFIED` requirement
  is applied to the canonical spec THE SYSTEM SHALL produce a new canonical
  spec deterministically, in the order RENAMED, REMOVED, MODIFIED, ADDED.
- IF a delta modifies, removes or renames a requirement absent from the
  canonical spec, or adds one that already exists, THEN the apply step SHALL
  fail without writing any output.
- WHEN the simulated archive runs THE SYSTEM SHALL write the new canonical
  spec and move the change package under an `archive/` path inside the
  fixture tree only.

Validation

- THE SYSTEM SHALL validate, at least: each requirement has a `SHALL` or
  `MUST` statement and at least one scenario; requirement names are unique
  per capability; a `normal` or `governed` change has at least one delta; a
  `governed` change has a `design.md`; the source-issue reference has the
  form `mctlhq/<repo>#<n>`.
- WHEN the validator runs over the converted historical proposals THE SYSTEM
  SHALL record every defect it finds that the current pipeline does not
  detect (today the investigator only checks that the three files exist and
  are regular files, `run_issue_investigator.py` step 4, around line 3865).

Agent fit and measurements

- THE SYSTEM SHALL record, for each converted proposal, the byte size and
  approximate token count (method stated in the report) of the current
  triplet, the candidate package, and the candidate package plus the
  canonical spec it touches.
- THE SYSTEM SHALL record a simulated Investigator result (issue, code and
  canonical spec in; change package out) for one historical issue and a
  simulated Implementer reading of that package. The result SHALL be scored
  on requirement clarity, task completeness, context size, ambiguity and
  whether the changed capability is identified exactly. The simulation SHALL
  be labeled as such, never presented as a production agent run.

Boundaries and invariants

- THE SYSTEM SHALL document spec verification as one input to the Shepherd
  decision, alongside CI/required checks and P1/P2 review findings, and SHALL
  state explicitly that it never merges, approves, authorizes or overrides a
  Shepherd decision.
- IF spec verification is absent or errors THEN the documented design SHALL
  grant nothing (a missing signal never counts as a pass). IF it fails THEN
  the result SHALL route through the existing remediation path as a finding,
  never as a new lifecycle state.
- WHILE the spike is in progress THE SYSTEM SHALL NOT change
  `run_issue_investigator.py`, `run_implementer.py`, `run_shepherd.py`,
  `orchestrator/temporal/**`, `proposal_state.py`, any `.status.yaml`, or any
  mctl-gitops content. A test SHALL assert that no production module imports
  the new library.
- THE SYSTEM SHALL use no OpenSpec CLI, npm package or other OpenSpec runtime
  dependency. Compatibility is defined against the published file format only.

Change classes

- THE SYSTEM SHALL define three change classes (`trivial`, `normal`,
  `governed`) as validation shapes inside one artifact model and one DevLoop
  lifecycle. `trivial` needs no spec delta.
- IF an artifact declares a change class THEN that declaration SHALL only
  select validation rules and SHALL NOT waive or alter approval;
  `control.requires_human_approval` in `.status.yaml` stays the only
  approval switch.

Decision output

- WHEN the spike completes THE SYSTEM SHALL publish exactly one
  recommendation, chosen with the decision rubric defined in design.md, plus
  a migration and interop cost estimate for the existing proposals (92 under
  `agents-state/mctl-agents/proposals/` at investigation time). If the
  recommendation is `ADOPT_CONTRACT` or `ADAPTER_ONLY`, the report SHALL
  include a staged plan and follow-up issue drafts.

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
- Filing GitHub issues. Follow-ups are drafted in the report; a human files
  them.

## Open questions

- OpenSpec format version: compatibility targets the published layout
  (`openspec/specs/<cap>/spec.md`, `openspec/changes/<id>/{proposal.md,
  design.md, tasks.md, specs/<cap>/spec.md}`, `## ADDED|MODIFIED|REMOVED|RENAMED
  Requirements`, `### Requirement:`, `#### Scenario:`). This investigation
  could not check that against a specific OpenSpec release. The
  implementation pins the format it targets in the ADR and does not depend
  on CLI behaviour.
- Where canonical specs live after an adoption: in the target service repo
  (the proposed answer, so that the implementation PR applies the delta and
  no post-merge writer exists) or in mctl-gitops `agents-state`. The spike
  evaluates the first and records the second as the alternative.
- How an EARS `WHILE`/`IF` criterion maps to an OpenSpec scenario. The
  proposed answer keeps the EARS sentence verbatim as the requirement body
  and derives a `WHEN`/`THEN` scenario. Whether reviewers accept that
  duplication is a finding for the report.
- Approval is bound to a slug and status today, not to a digest of the triplet
  content (`.status.yaml` `approval` carries only `approved_by` and
  `approved_at`; `context.content_hash` is the ContextSnapshot, not the
  proposal). The `devloop-approval` delta fixture uses this gap as its
  `ADDED` example. Actually closing it is a separate follow-up, not part of
  this spike.
- The simulated Investigator run uses the implementer agent's own model. A
  real investigator run on the candidate prompt would cost about $3, and
  whether that is worth it before a decision is left to the reviewer.
