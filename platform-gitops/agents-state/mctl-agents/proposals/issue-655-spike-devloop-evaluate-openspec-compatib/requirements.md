# Spike: evaluate an OpenSpec-compatible artifact contract for MCTL DevLoop proposals

## Context

Each DevLoop proposal is three Markdown files today, `requirements.md`, `design.md`
and `tasks.md`, plus a `.status.yaml`. They sit under
`platform-gitops/agents-state/<service>/proposals/<slug>/`. The issue investigator
writes them (`orchestrator/run_issue_investigator.py`, `TRIPLET`). The
implementer reads them (`orchestrator/run_implementer.py`, the prompt step that
says "Read spec files from `$PROPOSAL_DIR`"). Context assembly carries them
forward (`orchestrator/context_assembly.py`, `TRIPLET_FILENAMES`). Evidence is
sealed over them by sha256 (`_note_investigation_evidence`).

Nothing checks the files' structure, apart from the investigator confirming that
they exist and are regular files. No requirement says "what is true today" about
a capability. Each proposal only describes its own change, so a reader cannot
work out what a capability currently promises without reading every merged
proposal.

Issue mctl-agents#655 asks a bounded question. Should MCTL take on an
OpenSpec-compatible planning layer while keeping execution MCTL-native? That
layer means a change package: proposal, per-capability delta specs with
`ADDED`/`MODIFIED`/`REMOVED` requirements, design and tasks. It also means
canonical current-state capability specs. Execution would stay with
DevLoopWorkflow, `.status.yaml`, approval, authorization, Temporal, Shepherd,
CI and merge. The spike must answer the issue's ten questions using a
reversible prototype, fixtures and historical proposals only. It must end with
exactly one recommendation: `ADOPT_CONTRACT`, `ADAPTER_ONLY` or `NO_GO`. It
does not change production behaviour.

## User stories

- AS a platform maintainer I WANT a written mapping from today's proposal
  triplet to an OpenSpec-compatible change package SO THAT I know what would be
  lost, duplicated or gained before committing to a format.
- AS a platform maintainer I WANT a canonical capability spec, plus a change
  delta, plus a simulated merge/archive for one real DevLoop capability SO THAT
  I can judge whether a current-state spec is worth keeping up to date.
- AS the issue investigator I WANT a machine-checkable artifact contract SO THAT
  structural defects in my output (missing acceptance criteria, a delta naming
  an unknown requirement) are caught before publication, not by the implementer.
- AS the implementer I WANT to receive at least the information I receive today
  SO THAT a format change never lowers implementation success.
- AS the shepherd owner I WANT spec verification defined as one more input
  signal SO THAT it never replaces CI, review policy (P1/P2), merge policy or
  authorization.
- AS an operator I WANT trivial changes (typo, dependency bump, flake fix) to
  stay cheap SO THAT the contract does not add ceremony where it adds no value,
  and I still have a single DevLoop lifecycle.
- AS a reviewer of the spike I WANT exactly one recommendation, with evidence
  and follow-up issues SO THAT the decision can be acted on.

## Acceptance criteria (EARS)

### Contract definition
- WHEN the spike is complete THE SYSTEM SHALL provide a written artifact
  contract, `docs/spikes/655-sdd-artifact-contract.md`. The contract SHALL
  define `proposal.md`, `specs/<capability>/spec.md` (delta form),
  `design.md` and `tasks.md`, and the canonical spec form. It SHALL also
  define the grammar of `### Requirement:` and `#### Scenario:` blocks.
- THE SYSTEM SHALL define the contract so that it separates: proposal
  intent/context; behavioural requirements; design decisions; the executable
  task breakdown; delta semantics (`ADDED`, `MODIFIED`, `REMOVED`, `RENAMED`);
  and a source-issue reference.
- THE SYSTEM SHALL keep every execution-state field out of the artifact
  contract. Those fields are `status`, `approval`, `attempt`, `execution`,
  `pr`, `github`, `merge_commit` and `control`, as written to `.status.yaml`.
  The validator SHALL reject any artifact whose front matter or body carries
  one of these keys as structured data.

### Mapping and round-trip
- WHEN the spike is complete THE SYSTEM SHALL publish a mapping table from
  each current artifact and section to its candidate artifact and section.
  Current artifacts and sections include: `requirements.md` `## Context`,
  `## User stories`, `## Acceptance criteria (EARS)`, `## Out of scope` and
  `## Open questions`; `design.md` `## Current state` (including
  `Deployed state checked:`), `## Proposed solution`, `## Alternatives` and
  `## Platform impact`; `tasks.md` tasks, `## Tests` and `## Rollback`;
  `.status.yaml` `source`. Each row SHALL be marked lossless, lossy (with what
  is lost) or duplicated.
- WHEN at least two historical proposals are converted THE SYSTEM SHALL check
  each converted package for information loss. One of them SHALL be
  `mctl-agents/issue-516-fix-devloop-end-devloopworkflow-when-its`. The loss
  check SHALL be mechanical: every EARS line, task line, test line and
  section heading in the original appears in exactly one place in the
  converted package.
- WHEN a converted package is exported back to the triplet THE SYSTEM SHALL
  either produce byte-identical files after whitespace normalisation, or
  document why a one-way migration is preferable.

### Canonical spec and delta
- WHEN the spike is complete THE SYSTEM SHALL contain a canonical spec for
  exactly one bounded capability, written from the current code. The default
  is "DevLoop approval", grounded in `orchestrator/proposal_state.py`
  (`human_approval_satisfied`, `execution_authorization`) and the
  `DevLoopWorkflow.approve` signal in
  `orchestrator/temporal/workflows/dev_loop.py`.
- WHEN a change delta containing at least one `ADDED` and one `MODIFIED` or
  `REMOVED` requirement is applied to that canonical spec THE SYSTEM SHALL
  produce a new canonical spec deterministically. Applying the same delta to
  the same base twice SHALL produce byte-identical output.
- IF a delta names, for `MODIFIED`, `REMOVED` or `RENAMED`, a requirement that
  does not exist in the base canonical spec THEN THE SYSTEM SHALL fail
  validation with an error naming the requirement and capability.
- IF a delta `ADDED` requirement collides with an existing requirement name THEN
  THE SYSTEM SHALL fail validation.
- WHEN a simulated merge is run against fixtures THE SYSTEM SHALL demonstrate
  three things: verify, then sync canonical spec, then archive change. Archive
  means the change package moves under an archive path. The real
  `agents-state` tree SHALL never be written.

### Agent fit
- WHEN the investigator simulation is run THE SYSTEM SHALL record the following
  for current versus candidate representation on the same issue(s):
  requirement clarity; task completeness; artifact byte size and estimated
  token count; ambiguity observations; whether the changed capability is
  identifiable. The issue(s) SHALL be historical and already investigated.
- WHEN the implementer simulation is run THE SYSTEM SHALL show that every
  implementation-relevant item in the original triplet is present in the
  prompt-visible candidate artifact(s).
- WHILE the spike is in progress THE SYSTEM SHALL NOT change the investigator
  prompt in `run_issue_investigator.py`, the implementer prompt in
  `run_implementer.py`, or `TRIPLET` / `TRIPLET_FILENAMES`.

### Verification boundary
- THE SYSTEM SHALL document spec verification as one more, separately reported
  input to the Shepherd decision, alongside CI/required checks and P1/P2 review
  findings. It SHALL never be a replacement for any of them.
- IF a candidate design lets a spec-verification pass merge, approve or
  authorize anything THEN THE SYSTEM SHALL reject that design in the spike
  report.

### Interop boundary
- THE SYSTEM SHALL implement the contract with no runtime dependency on the
  OpenSpec CLI or its Node package. The validator, diff, import and export SHALL
  be pure Python inside `mctl-agents`.
- WHEN an OpenSpec-layout change directory (`changes/<id>/...`) is imported THE
  SYSTEM SHALL produce a candidate package. When a candidate package is
  exported THE SYSTEM SHALL produce an OpenSpec-layout directory. Both SHALL be
  shown on fixtures.

### Change classes
- THE SYSTEM SHALL propose a `trivial` / `normal` / `governed` classification.
  All three SHALL use the same proposal directory, the same `.status.yaml`
  state machine and the same approval path. `trivial` SHALL waive only the
  delta-spec artifacts, never approval or authorization.

### Invariants
- WHILE any part of this spike exists THE SYSTEM SHALL leave unchanged the
  semantics of `.status.yaml`, `human_approval_satisfied`,
  `execution_authorization`, `DevLoopWorkflow` and the Shepherd decision
  function.
- THE SYSTEM SHALL keep exactly one source of truth for requirements in any
  recommended end state. A permanent model where `requirements.md` and
  `specs/**` are both authored is not an acceptable recommendation.

### Decision
- WHEN the spike report is complete THE SYSTEM SHALL state exactly one of
  `ADOPT_CONTRACT`, `ADAPTER_ONLY` or `NO_GO`. It SHALL justify that choice
  against the decision criteria written down in the report before the
  measurements were taken.
- IF the recommendation is `ADOPT_CONTRACT` THEN THE SYSTEM SHALL include a
  staged migration plan and a list of follow-up issues with titles and scope.

## Out of scope

- Replacing DevLoopWorkflow, Temporal, Shepherd, MCTL approval or
  authorization.
- Changing what the investigator or implementer produce or consume in
  production.
- Writing to `platform-gitops/agents-state/**` in mctl-gitops, and bulk
  migration of historical proposals.
- A public `mctl spec` CLI in mctl-api or the MCTL MCP server. The spike
  ships a repo-local `tools/spec_contract.py` only.
- Installing or invoking the OpenSpec CLI at runtime or in CI.
- Binding approval to an artifact content digest. This is noted as a
  follow-up, not done here.
- Incident-responder proposals (`incident-*`) and the mctl-docs
  `proposed-content.md` extension. Both are recorded in the mapping as
  "not covered".

## Open questions

- Which OpenSpec version is the compatibility target? The grammar used here is
  the publicly documented one: `## ADDED|MODIFIED|REMOVED|RENAMED
  Requirements`, `### Requirement:`, `#### Scenario:` with WHEN/THEN bullets,
  `changes/archive/YYYY-MM-DD-<id>/`. It was not checked against a pinned
  release during this investigation. The spike should pin a version, or a
  commit of the published docs, in its fixtures.
- Which capability to model canonically? DevLoop approval is the default
  because its rules are compact and already fail-closed in code. The
  review/remediation loop is larger and may give a more representative signal.
- Where would canonical specs live if the recommendation were
  `ADOPT_CONTRACT`? Options: per target repo, or per service under
  `agents-state/<service>/specs/`. The spike decides only for fixtures.
- How should EARS `WHILE`/`IF` lines that are not behaviour of one capability
  (for example cross-cutting invariants) map onto per-capability requirements?
- There are 29 of the current `mctl-agents` proposals' `requirements.md` files
  that have no `## Acceptance criteria` heading (observed in the gitops
  checkout). Should the validator treat this as an error or a warning when
  converting history?
- Should approval in a future contract bind to a digest of the change package?
  Today `.status.yaml` `approval` records only `approved_by`/`approved_at`. This
  is out of scope here and recorded for the follow-up list.
