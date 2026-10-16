# Design: issue-655-spike-devloop-evaluate-openspec-compatib

## Current state

Proposal artifacts and their consumers, as read in the clone:

- **Producer.** `orchestrator/run_issue_investigator.py` defines
  `TRIPLET = ("requirements.md", "design.md", "tasks.md")` (line 451) and
  `STATUS_FILENAME = ".status.yaml"`. The investigator prompt (around lines
  2171-2221) fixes the section skeleton: requirements.md has Context, User
  stories, Acceptance criteria (EARS), Out of scope and Open questions;
  design.md has Current state (with a `Deployed state checked:` list),
  Proposed solution, Alternatives and Platform impact; tasks.md has numbered
  `- [ ] N.` tasks with `depends on` and `DoD:`, then Tests and Rollback. The
  only structural validation is step 4 (around line 3865): each file must
  exist in staging and be a plain file. Headings, EARS form and task
  numbering are never checked. Published files are recorded by sha256 as
  evidence (`_note_investigation_evidence`, `evidence.note_artifact_file`).
- **Context.** `orchestrator/context_assembly.py:148` has its own
  `TRIPLET_FILENAMES`. A prior proposal's triplet is a context source
  (`collect_prior_proposal`, around line 904).
- **Consumer.** `orchestrator/run_implementer.py` `_build_prompt` (line 1821)
  tells the implementer sub-agent to read
  "requirements.md, design.md, tasks.md" from `$PROPOSAL_DIR` (around line
  2083). The review-fix prompt (around line 1969) does the same, and adopted
  PRs use `.prref.yaml` instead.
- **Execution state.** `.status.yaml` (helpers in
  `orchestrator/proposal_state.py`) holds `status`, `source` (issue
  linkage), `control.requires_human_approval`, `context` (ContextSnapshot id
  and hash), `approval.approved_by/approved_at`, `attempt`, `pr`, `github`,
  `merged_at` and `merge_commit`. The approval gate refuses anonymous
  approvers (`_ANONYMOUS_APPROVERS`) and defaults to required (`_FALSEY`
  denylist). Note: no field binds the approval to a digest of the triplet's
  content.
- **Identity and lifecycle.** `orchestrator/proposal_identity.py` resolves
  the one `issue-<N>-*` directory for an issue. `DevLoopWorkflow`
  (`orchestrator/temporal/workflows/dev_loop.py`) parks on approval and then
  submits the `mctl-agents-approve` CWFT, which flips `.status.yaml`.
  `orchestrator/run_shepherd.py` drives P1/P2 findings
  (`CodexFinding`, severity P1/P2) and CI through remediation to merge.
- **Conventions.** Contracts are written as ADRs under `docs/adr/` (latest
  `020-capability-commerce-contract.md`). Dev tools live in `tools/`.
  Fixtures live in `tests/fixtures/<area>/`. Nothing in the repo references
  OpenSpec today.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/`: 92 proposal
  directories, of which 57 `.status.yaml` files read `status: merged`.
- `.../issue-623-tracing-record-cache-read-write-token-us/`: triplet of
  5617 + 8402 + 3704 = 17723 bytes, standard section skeleton, `status:
  merged`, PR mctl-agents#628. This is a good small round-trip candidate.
- `.../issue-542-fix-work-context-a-resume-onto-a-closed/`: triplet of
  50337 bytes, `status: merged`, PR #545. This is the large candidate.
- `.../issue-601-feat-devloop-register-mctl-claude-remote/`: 12217 bytes,
  merged.
- `.status.yaml` samples above confirm `approval` carries only
  `approved_by`/`approved_at`.
- No mctl MCP service or tenant tools were called. The spike changes no
  deployed service, and nothing in this design asserts a tenant, hostname or
  runtime setting.

## Proposed solution

A self-contained, reversible prototype with no production wiring. It has
four parts.

### 1. Artifact contract (draft ADR 021)

`docs/adr/021-sdd-artifact-contract.md` (status: proposed) defines a change
package that follows the OpenSpec file format:

```text
<change-root>/<slug>/
  proposal.md                 # intent: Why, What Changes, Impact + Source line
  specs/<capability>/spec.md  # deltas: ## ADDED|MODIFIED|REMOVED|RENAMED Requirements
  design.md                   # decisions (optional for trivial/normal)
  tasks.md                    # ## N. Group / - [ ] N.M task
<canonical-root>/<capability>/spec.md   # ## Purpose, ## Requirements
```

Requirement grammar: `### Requirement: <name>`, a body containing SHALL or
MUST, and one or more `#### Scenario: <name>` blocks with `- **WHEN**` /
`- **THEN**` bullets. A `MODIFIED` requirement carries the full new text.

MCTL rules on top of the format:

- `proposal.md` carries `Source: mctlhq/<repo>#<n>` and
  `Change-Class: trivial|normal|governed`. The Source line is informational.
  Canonical identity stays in `.status.yaml` `source` and the slug, and a
  mismatch between the two is a validation error.
- Forbidden content: any `.status.yaml` key at top level or in front matter
  (`status`, `approval`, `attempt`, `execution`, `github`, `pr`,
  `merge_commit`, `control`). A spec is intent, never authority.
- MCTL extension sections are kept verbatim under fixed headings:
  `## User stories`, `## Out of scope`, `## Deployed state checked`,
  `## Rollback`. OpenSpec readers ignore unknown sections, so they do not
  break compatibility.

### 2. Mapping (to be completed with evidence in the report)

| Current | Candidate |
|---|---|
| requirements.md `#` title | proposal.md `#` title |
| requirements.md Context | proposal.md `## Why` |
| requirements.md User stories | proposal.md `## User stories` (extension) |
| requirements.md Acceptance criteria (EARS) | specs/<cap>/spec.md `### Requirement:` (EARS sentence verbatim as body) + derived `#### Scenario:` |
| requirements.md Out of scope | proposal.md `## Out of scope` (extension) |
| requirements.md Open questions | design.md `## Open Questions` |
| design.md Current state + Deployed state checked | design.md `## Context` + `## Deployed state checked` (extension) |
| design.md Proposed solution | design.md `## Decisions`; summary into proposal.md `## What Changes` |
| design.md Alternatives | design.md `## Decisions` > `### Alternatives considered` |
| design.md Platform impact | design.md `## Risks / Trade-offs` + `## Migration Plan`; proposal.md `## Impact` |
| tasks.md `- [ ] N.` with depends on / DoD | tasks.md `## 1. Implementation` / `- [ ] 1.N` (dependency and DoD text kept inline) |
| tasks.md Tests | tasks.md `## 2. Tests` |
| tasks.md Rollback | tasks.md `## Rollback` (extension) |
| source issue (`.status.yaml` source, slug) | proposal.md `Source:` line (reference only) |
| `.status.yaml` (all of it) | not mapped, stays MCTL execution state |
| (no equivalent) | capability name per requirement, which is new information |

Lossless rule: every section body is carried verbatim. `import` rebuilds the
legacy triplet from the extension headings plus the mapped sections. Only
the capability assignment and the derived scenarios are new, and `import`
drops them because they are derived. Grouping several EARS lines under one
capability is the step most likely to be ambiguous. The report measures it.

### 3. Library and dev tool

- `orchestrator/spec_contract.py`: pure stdlib (no yaml, no network), with
  dataclasses `Requirement`, `Scenario`, `CapabilitySpec`, `Delta`,
  `ChangePackage` and functions:
  - `parse_legacy_triplet(dir) -> LegacyProposal`, keyed on the exact
    headings the investigator prompt emits;
  - `export_change(legacy, capability_map) -> ChangePackage` and
    `render_change(pkg) -> dict[path, str]`;
  - `import_change(pkg) -> LegacyProposal` and `render_legacy`;
  - `parse_canonical`, `parse_delta`, and
    `apply_delta(canonical, delta) -> CapabilitySpec` (order RENAMED,
    REMOVED, MODIFIED, ADDED; any missing target or duplicate raises
    `DeltaConflict`, all or nothing);
  - `validate(pkg, canonical=None) -> list[Diagnostic]`, which implements the
    rules in requirements.md;
  - `archive(change_dir, canonical_root, archive_root)`, the simulated
    post-merge step. It only writes inside the paths it is given.
- `tools/spec_contract.py`: argparse CLI with `validate`, `diff`, `export`,
  `import`, `apply` and `measure`. `measure` prints bytes and
  `ceil(chars/4)` token estimates. The method is stated because no
  tokenizer dependency is added. The tool exists only to produce evidence.
  It is not packaged as a console script.

### 4. Fixtures, demonstration and report

- `tests/fixtures/spec_contract/canonical/devloop-approval/spec.md`: the
  canonical spec derived from today's code. Requirements include: approval
  requires a non-anonymous approver (`proposal_state._ANONYMOUS_APPROVERS`);
  the approval requirement defaults on and only explicit denylist values
  waive it (`_FALSEY`); approval applies to exactly this issue's proposal
  (`dev_loop.py` module docstring); an accepted proposal with no verified
  approver is reported unrunnable (`UNAUTHORIZED_ANONYMOUS_APPROVER`).
- `tests/fixtures/spec_contract/changes/approval-content-binding/`: a
  simulated change with `ADDED` "Approval binds to proposal content digest"
  and `MODIFIED` "Approval requires a non-anonymous approver" (records the
  digest alongside the approver). It is fixture only and does not change
  behaviour.
- `tests/fixtures/spec_contract/legacy/issue-655/` (this proposal's triplet,
  copied from `$PROPOSAL_DIR`) and `legacy/issue-623/` (copied from
  mctl-gitops when readable, otherwise recorded as a gap in the report),
  plus their exported `expected/` packages.
- `docs/spikes/655-openspec-compatible-artifact-contract.md`: the report.
  It holds the mapping table filled with measured results, loss and
  duplication findings, size and token table, validator findings, the
  sync/archive demonstration (before and after canonical spec), the
  simulated Investigator and Implementer evaluation, the Shepherd boundary,
  change classes, the coupling statement, migration cost, effect on the
  state machine and APIs (expected: none), the single recommendation and
  follow-up issue drafts.

### Spec verification and the Shepherd boundary

```text
spec verification (validate + "changed code touches declared capability")
        +
CI / required checks (ci_checks.py)
        +
review findings P1/P2 (run_shepherd.py CodexFinding)
        |
        v
Shepherd decide() -> remediation / merge (unchanged authority)
```

Spec verification produces findings in the same shape as a review finding
(a failure is P2, routed to the existing implementer `--review-feedback`
path). It never gates a merge by itself, never approves, never authorizes,
and an absent or errored result grants nothing. The report checks this
against the existing review loop states (`implementing`, `review-fixing`,
`merged`) and shows that no new status value is needed. Any design in which
spec `verify` replaces Shepherd, CI, review policy or authorization is
explicitly rejected.

### Post-merge behaviour (proposed answer to Q7)

The canonical spec lives in the target repo (for example
`specs/<capability>/spec.md`). The implementation PR applies the delta, so
"sync" is reviewed together with the code it describes. "Archive" is just the
proposal reaching `merged`, which `.status.yaml` already records. No
post-merge writer is introduced. The report demonstrates this with the
fixture `archive()` and lists the gitops-side alternative.

### Change classes

One lifecycle, three validation shapes. `trivial` (typo, dependency bump,
flake): `proposal.md` and `tasks.md` only, no delta required. `normal`: at
least one delta. `governed`: delta plus `design.md`. The class never sets
or waives approval, and `control.requires_human_approval` remains the only
switch.

### Decision rubric (applied in the report)

- `ADOPT_CONTRACT` requires all of the following: a lossless round trip on at
  least 2 proposals; capability assignment was unambiguous in the simulation;
  the candidate package plus the touched canonical spec costs no more than
  125% of the current triplet's tokens; the validator caught at least one
  real defect class the current pipeline misses; and the migration plan
  needs no change to `.status.yaml` or the DevLoop APIs.
- `NO_GO` applies if the round trip is lossy for implementation-relevant
  sections AND the validator catches nothing the current format misses.
- Otherwise `ADAPTER_ONLY`.

The investigator's working expectation is `ADAPTER_ONLY`. Canonical specs
add real maintenance cost to brownfield repos that have none today, and
invariant 7 forbids dual authoring. The rubric decides, not this expectation.

## Alternatives

1. **Adopt the OpenSpec CLI as a runtime dependency** (generate, validate and
   archive with `openspec`). Rejected: it violates invariant 6, adds a Node
   toolchain to the agent image (`Dockerfile`), and couples the format to CLI
   behaviour before the contract is proven.
2. **Change the investigator and implementer prompts directly and A/B them in
   production.** Rejected: invariant 5 (no production migration), roughly $3
   per investigator run, and it would create the dual-authoring state that
   invariant 7 forbids.
3. **Paper-only evaluation, no code.** Rejected: acceptance criteria C and B
   require a demonstrated round trip and a delta applied to a canonical spec.
   A deterministic library with tests is the cheapest durable proof and can
   be deleted cleanly.
4. **Keep canonical specs in mctl-gitops `agents-state`.** Evaluated in the
   report as the alternative to target-repo specs. It is not chosen as the
   default because sync would need a post-merge writer, which reintroduces a
   race the merge-time PR avoids.

## Platform impact

- **Migrations.** None. No change to `.status.yaml`, DevLoop or Temporal
  histories, the approval CWFT or mctl-gitops.
- **Backward compatibility.** Production behaviour is untouched. The new
  module is imported only by `tools/spec_contract.py` and tests, and a test
  enforces this.
- **Resources.** None at runtime. A test suite of a few hundred milliseconds.
  No new dependencies in `pyproject.toml` / `uv.lock`.
- **Risks and mitigations.**
  - Format drift against upstream OpenSpec: the ADR pins the targeted grammar
    and the tool validates only that grammar.
  - The spike's conclusion is biased by the simulated agent run: the report
    labels it simulated and lists a real investigator A/B run as an optional
    follow-up.
  - The historical fixture copy may not be readable from the implementer's
    clone: the fallback is this proposal's own triplet, and the gap is
    recorded.
  - Scope creep into production wiring: tasks forbid edits to the listed
    production files, and a test enforces the import isolation.
