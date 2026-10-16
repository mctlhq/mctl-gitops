# Design: issue-655-spike-devloop-evaluate-openspec-compatib

## Current state

This section covers the proposal artifacts and their consumers, as read in
the clone.

- **Producer.** `orchestrator/run_issue_investigator.py` defines
  `TRIPLET = ("requirements.md", "design.md", "tasks.md")` (line 451) and
  `STATUS_FILENAME = ".status.yaml"`.
  - The `_build_prompt` template (line 2072, sections around lines
    2167-2225) fixes the section skeleton:
    - requirements.md: Context, User stories, Acceptance criteria (EARS),
      Out of scope, Open questions.
    - design.md: Current state (with a `Deployed state checked:` list),
      Proposed solution, Alternatives, Platform impact.
    - tasks.md: numbered `- [ ] N.` tasks with `depends on` and `DoD:`,
      then Tests and Rollback.
  - The only structural validation is step 4 (around line 3865): each file
    must exist in staging as a plain file (`_is_plain_file`). Headings, EARS
    form and task numbering are never checked.
  - Published files are recorded by sha256 as evidence
    (`_note_investigation_evidence` -> `evidence.note_artifact_file`, around
    line 3223).
- **Context.** `orchestrator/context_assembly.py:148` declares its own
  `TRIPLET_FILENAMES`. A prior proposal's triplet becomes a context source
  through `collect_prior_proposal` (around line 879).
- **Consumer.** `orchestrator/run_implementer.py` `_build_prompt` (line 1821)
  tells the implementer sub-agent to read
  "requirements.md, design.md, tasks.md" from `$PROPOSAL_DIR` (around line
  2083). The review-fix prompt does the same (around line 1969). Adopted PRs
  carry a `.prref.yaml` instead of a triplet.
- **Execution state.** `.status.yaml` (helpers in
  `orchestrator/proposal_state.py`) holds the following fields: `status`,
  `source` (issue linkage), `control.requires_human_approval`, `context`
  (ContextSnapshot id and hash), `approval.approved_by`/`approved_at`,
  `attempt`, `pr`, `github`, `merged_at`, `merge_commit`.
  - `human_approval_satisfied` refuses anonymous approvers
    (`_ANONYMOUS_APPROVERS`) and defaults to required (`_FALSEY` denylist).
  - `execution_authorization` fails closed with
    `UNAUTHORIZED_ANONYMOUS_APPROVER`.
- **Approval identity.** `orchestrator/temporal/workflows/dev_loop.py` parks
  on approval. Under `CANONICAL_APPROVAL_PATCH`, an `aar_` grant is bound to
  the loop's `we_`.
  - `orchestrator/temporal/activities/delegated_approval.py`
    `approval_intent` computes `args_digest` over
    `{"service": ..., "slug": ...}` only.
  - Approval is therefore bound to the proposal's identity, not to its
    content.
- **Proposal identity.** `orchestrator/proposal_identity.py` resolves the one
  `issue-<N>-*` directory for an issue.
- **Review loop.** `orchestrator/run_shepherd.py` `decide()` (around line
  2630) is a pure function over `PullRequest`, `CodexReview` and an optional
  `CIStatus`.
  - Its outcomes are `flip-to-merged`, `flip-to-rejected`, `wait`,
    `address-review` (P1/P2 findings plus CI `Blockers`), `ci-infra`,
    `ci-unknown`, merge and `defer-merge`.
  - Remediation goes through the implementer with review feedback.
- **Conventions.** Contracts are ADRs under `docs/adr/`. The latest is
  `020-capability-commerce-contract.md`, and number 011 is used twice. Dev
  tools live in `tools/`, and fixtures in `tests/fixtures/<area>/`.
  `tests/test_worker_isolation.py` is the existing pattern for
  import-isolation tests. Nothing in the repo references OpenSpec today
  (grep).

Deployed state checked:

- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/` has 93 directory
  entries. These include `tier3-pr-shepherd` and an earlier `proposed`
  triplet for this same issue
  (`issue-655-spike-devloop-evaluate-openspec-compatib`, 30766 bytes). This
  design refines that earlier triplet.
- `.../issue-623-tracing-record-cache-read-write-token-us/`: the triplet is
  5617 + 8402 + 3704 = 17723 bytes, uses the standard section skeleton, and
  is merged. It is the small round-trip candidate.
- `.../issue-596-test-agent-platform-add-an-inert-authori/`: the triplet is
  24865 bytes and merged. Its `.status.yaml` shows that `approval` carries
  only `approved_by`/`approved_at`, and that `source`, `execution`,
  `context`, `attempt`, `github` and `merge_commit` all live in
  `.status.yaml`, never in the triplet.
- Average triplet size across the proposals directory: about 27.6 KB
  (computed with `wc -c`).
- No mctl MCP service or tenant tools were called. This spike changes no
  deployed service, and nothing in this design asserts a tenant, hostname or
  runtime setting.

## Proposed solution

The prototype is self-contained and reversible, with no production wiring. It
has four parts.

### 1. Artifact contract (draft ADR 021)

`docs/adr/021-sdd-artifact-contract.md` (status: proposed) defines a change
package that follows the OpenSpec file format:

```text
<change-root>/<slug>/
  proposal.md                 # intent: Why, What Changes, Impact + Source line
  specs/<capability>/spec.md  # deltas: ## ADDED|MODIFIED|REMOVED|RENAMED Requirements
  design.md                   # decisions (required only for governed)
  tasks.md                    # ## N. Group / - [ ] N.M task
<canonical-root>/<capability>/spec.md   # ## Purpose, ## Requirements
```

Requirement grammar:

- `### Requirement: <name>`;
- a body containing SHALL or MUST;
- one or more `#### Scenario: <name>` blocks with `- **WHEN**` and
  `- **THEN**` bullets.

A `MODIFIED` requirement carries the full new text, never a partial patch.

MCTL rules on top of the format:

- `proposal.md` carries `Source: mctlhq/<repo>#<n>` and
  `Change-Class: trivial|normal|governed`.
  - The Source line is a reference only. Canonical identity stays in
    `.status.yaml` `source` and in the slug.
  - A mismatch between the Source line and the slug's issue number is a
    validation error.
- Forbidden content: any `.status.yaml` key at top level or in front matter
  (`status`, `approval`, `attempt`, `execution`, `github`, `pr`,
  `merged_at`, `merge_commit`, `control`, `context`). A spec is intent,
  never authority.
- MCTL extension sections are kept verbatim under fixed headings:
  `## User stories`, `## Out of scope`, `## Deployed state checked`,
  `## Rollback`. OpenSpec readers ignore unknown sections, so these do not
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
| design.md Proposed solution | design.md `## Decisions`; summary in proposal.md `## What Changes` |
| design.md Alternatives | design.md `## Decisions` > `### Alternatives considered` |
| design.md Platform impact | design.md `## Risks / Trade-offs` + `## Migration Plan`; proposal.md `## Impact` |
| tasks.md `- [ ] N.` with depends on / DoD | tasks.md `## 1. Implementation` / `- [ ] 1.N` (dependency and DoD text kept inline) |
| tasks.md Tests | tasks.md `## 2. Tests` |
| tasks.md Rollback | tasks.md `## Rollback` (extension) |
| source issue (`.status.yaml` source, slug) | proposal.md `Source:` line (reference only) |
| `.status.yaml` (all of it) | not mapped; stays MCTL execution state |
| (no equivalent) | capability name per requirement: new information |

Lossless rule:

- Every section body is carried verbatim.
- `import` rebuilds the legacy triplet from the extension headings plus the
  mapped sections.
- The capability assignment and the derived scenarios are the only new data,
  and `import` drops them because they are derived.
- Grouping EARS lines under capabilities is the step most likely to be
  ambiguous. The report measures how ambiguous it is.

### 3. Library and dev tool

`orchestrator/spec_contract.py` is pure stdlib: no yaml, no network. It
defines the dataclasses `Requirement`, `Scenario`, `CapabilitySpec`,
`Delta`, `ChangePackage`, `LegacyProposal` and `Diagnostic`, and these
functions:

- `parse_legacy_triplet(dir) -> LegacyProposal`, keyed on the exact headings
  the investigator prompt emits;
- `export_change(legacy, capability_map) -> ChangePackage` and
  `render_change(pkg) -> dict[str, str]`;
- `import_change(pkg) -> LegacyProposal` and `render_legacy`;
- `parse_canonical`, `parse_delta`, and
  `apply_delta(canonical, delta) -> CapabilitySpec`:
  - operations run in the order RENAMED, REMOVED, MODIFIED, ADDED;
  - a missing target or a duplicate raises `DeltaConflict`;
  - the apply is all or nothing;
- `validate(pkg, canonical=None) -> list[Diagnostic]`, which implements the
  rules in requirements.md;
- `archive(change_dir, canonical_root, archive_root)`, the simulated
  post-merge step. It writes only inside the paths it is given.

`tools/spec_contract.py` is an argparse CLI with the subcommands `validate`,
`diff`, `export`, `import`, `apply` and `measure`.

- `measure` prints bytes and a `ceil(chars/4)` token estimate. The method is
  stated in the report, because no tokenizer dependency is added.
- The tool exists only to produce evidence. It is not registered as a
  console script.

### 4. Fixtures, demonstration and report

All fixtures live under `tests/fixtures/spec_contract/`:

- `canonical/devloop-approval/spec.md`: the canonical spec, derived from
  today's code. Each requirement cites its source:
  - approval requires a non-anonymous approver
    (`proposal_state._ANONYMOUS_APPROVERS`);
  - the approval requirement defaults on, and only explicit denylist values
    waive it (`_FALSEY`);
  - approval applies to exactly one `<service>/<slug>`
    (`delegated_approval.approval_intent`);
  - an accepted proposal with no verified approver is unrunnable
    (`UNAUTHORIZED_ANONYMOUS_APPROVER`).
- `changes/approval-content-binding/`: a simulated `normal` change with two
  deltas:
  - `ADDED` "Approval binds to the proposal content digest";
  - `MODIFIED` "Approval applies to exactly one proposal", which now also
    names the digest.

  This is a fixture only and does not change behavior.
- `expected/devloop-approval.spec.md`: the canonical spec after `apply`, and
  the archive layout after `archive`.
- `legacy/issue-655/` and `legacy/issue-623/`, with their exported
  `expected/` packages:
  - `issue-655` is this proposal's own triplet, copied from `$PROPOSAL_DIR`;
  - `issue-623` is copied from the mctl-gitops checkout when it is readable.
    If it is not, a second in-repo proposal is used instead and the gap is
    recorded in the report.
- `invalid/`: one negative fixture per validation rule, including one that
  carries a `status:` front-matter key.

The report goes in
`docs/spikes/655-openspec-compatible-artifact-contract.md`. It contains:

- the mapping table, filled in with measured results;
- the loss and duplication findings;
- the size and token table;
- the validator findings;
- the sync/archive demonstration, with the canonical spec before and after;
- the simulated Investigator and Implementer evaluation;
- the Shepherd boundary;
- the change classes;
- the coupling statement;
- the migration cost;
- the effect on the state machine and APIs (expected: none);
- the single recommendation and the follow-up issue drafts.

### Spec verification and the Shepherd boundary

```text
spec verification (validate + "PR diff touches declared capability")
        +
CI / required checks (ci_checks.read_required_checks -> CIStatus)
        +
review findings P1/P2 (CodexReview.fresh_findings_p1_p2)
        |
        v
Shepherd decide() -> address-review / wait / merge (authority unchanged)
```

Spec verification produces findings in the same shape as a review finding.
A failure is P2 and goes through the existing `address-review` remediation
path; no new `decide()` outcome and no new `.status.yaml` value is added.

Spec verification:

- never gates a merge on its own;
- never approves or authorizes anything;
- grants nothing when it is absent or errors, which is treated the way
  `ci-unknown` is treated today.

The report checks this design against the existing states (`implementing`,
`review-fixing`, `merged`). Any design in which a spec `verify` step
replaces Shepherd, CI, review policy or authorization is explicitly
rejected.

### Post-merge behavior (proposed answer to Q7)

The canonical spec lives in the target repo, for example
`specs/<capability>/spec.md`.

- **Sync.** The implementation PR applies the delta, so the spec change is
  reviewed together with the code it describes.
- **Verify.** Verification is the boundary above.
- **Archive.** The proposal reaching `merged` is the archive; `.status.yaml`
  already records that.

No post-merge writer is introduced. The report demonstrates this with the
fixture `archive()` and lists the gitops-side alternative.

### Change classes

There is one lifecycle with three validation shapes:

- `trivial` (typo, dependency bump, flake fix): `proposal.md` and `tasks.md`
  only, with no delta required;
- `normal`: at least one delta;
- `governed`: at least one delta plus `design.md`.

The class never sets or waives approval; `control.requires_human_approval`
remains the only switch. Who decides the class (the investigator, a label, a
heuristic) is a follow-up question. The spike only shows that all three
shapes validate inside one model.

### Decision rubric (applied in the report)

- `ADOPT_CONTRACT` requires all of the following:
  - a lossless round trip on at least 2 proposals;
  - unambiguous capability assignment in the simulation;
  - the candidate package plus the touched canonical spec costs no more than
    125% of the current triplet's tokens;
  - the validator catches at least one real class of defect that the current
    pipeline misses;
  - the migration plan needs no change to `.status.yaml` or the DevLoop
    APIs.
- `NO_GO` applies if the round trip is lossy for implementation-relevant
  sections AND the validator catches nothing the current format misses.
- `ADAPTER_ONLY` applies otherwise.

The investigator's working expectation is `ADAPTER_ONLY`, for two reasons:

- canonical specs add a real maintenance cost to brownfield repos that have
  none today;
- invariant 7 forbids dual authoring.

The rubric decides, not this expectation.

## Alternatives

1. **Adopt the OpenSpec CLI as a runtime dependency** (generate, validate
   and archive with `openspec`). Rejected for three reasons:
   - it violates invariant 6;
   - it adds a Node toolchain to the agent image (`Dockerfile`);
   - it couples the format to CLI behavior before the contract is proven.
2. **Change the investigator and implementer prompts directly and A/B them
   in production.** Rejected for three reasons:
   - it violates invariant 5 (no production migration);
   - each investigator run costs about $3;
   - it would create the dual-authoring state that invariant 7 forbids.
3. **A paper-only evaluation with no code.** Rejected because the issue's
   prototype items B and C require a demonstrated round trip and a delta
   applied to a canonical spec. A deterministic library with tests is the
   cheapest durable proof, and it can be deleted cleanly.
4. **Keep canonical specs in mctl-gitops `agents-state`.** Evaluated in the
   report as the alternative to specs in the target repo. It is not the
   default because sync would need a post-merge writer, which reintroduces a
   race that the merge-time PR avoids.

## Platform impact

- **Migrations.** None. No change to `.status.yaml`, the DevLoop/Temporal
  histories, the approval CWFT, or mctl-gitops.
- **Backward compatibility.** Production behavior is untouched. The new
  module is imported only by `tools/spec_contract.py` and by tests, and a
  test enforces this.
- **Resources.**
  - No runtime cost.
  - The test suite takes a few hundred milliseconds.
  - No new dependencies in `pyproject.toml` / `uv.lock`.
- **Risks and mitigations.**
  - *Format drift against upstream OpenSpec.* The ADR pins the targeted
    grammar, and the tool validates only that grammar.
  - *The simulated agent run biases the conclusion.* The report labels the
    run as simulated and lists a real investigator A/B run as an optional
    follow-up.
  - *The historical fixture is unreadable from the implementer's run.* The
    fallback is this proposal's own triplet plus a second proposal, and the
    gap is recorded.
  - *Scope creep into production wiring.* The tasks forbid edits to the
    listed production files, and an import-isolation test enforces it.
  - *Fixture copies of proposals are themselves duplicated requirements.*
    They are test data under `tests/fixtures/`, not a second source of
    truth, and the report says so.
