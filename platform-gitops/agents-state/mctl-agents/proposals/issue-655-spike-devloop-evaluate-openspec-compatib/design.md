# Design: issue-655-spike-devloop-evaluate-openspec-compatib

## Current state

### How the planning triplet is produced

- `orchestrator/run_issue_investigator.py` defines
  `TRIPLET = ("requirements.md", "design.md", "tasks.md")` and
  `STATUS_FILENAME = ".status.yaml"`.
- The investigator prompt is an f-string in the same file, near the
  `## What to produce` block. It specifies the required section structure:
  EARS acceptance criteria, `## Current state`, `## Tests` and
  `## Rollback`.
- The only structural validation is that the three files exist. The check
  `missing = [name for name in TRIPLET if not _is_plain_file(staging / name)]`
  refuses a missing file or a symlink, with outcome reason
  `agent-output-missing`. No validation of section structure, EARS form,
  task numbering or dependency references exists today. This gap is the
  baseline for the "validation errors caught" measurement.
- Evidence and tracing record each triplet file as a `proposal` artifact
  (`evidence.note_artifact_file`, `tracing.record_artifact`).

### How the triplet is consumed

- `orchestrator/run_implementer.py`, prompt step 1, tells the sub-agent:
  "Read spec files from `$PROPOSAL_DIR` ... requirements.md, design.md,
  tasks.md". For mctl-docs it also reads `proposed-content.md`, an extra
  file that appears in 40 proposals in gitops today.
- The review-fix prompt (around `context_spec_line`) points at the same
  triplet. Adopted PRs instead carry a `.prref.yaml` with no triplet.
- `orchestrator/context_assembly.py` defines `TRIPLET_FILENAMES` and
  `collect_prior_proposal`. These load each file as a `proposal-dir`
  candidate source with the locator
  `gitops://agents-state/<service>/proposals/<slug>/<name>`.
- `orchestrator/run_shepherd.py` `decide()` is a pure function over PR,
  review and CI state. It returns `flip-to-merged`, `flip-to-rejected`,
  `wait`, `address-review`, `defer-merge` and similar values. It does not
  read the triplet. Spec content plays no part in the merge decision today.

### Execution state: what must stay outside the contract

- `orchestrator/proposal_state.py` (`load_status`,
  `human_approval_satisfied`, `execution_authorization`,
  `BLOCKED_APPROVAL_MISSING`) treats `.status.yaml` as the durable
  projection. It holds `status`, `control.requires_human_approval`,
  `approval.approved_by/approved_at`, `attempt`, `pr`, `github`,
  `execution`, `context` and `source`.
- `orchestrator/temporal/workflows/dev_loop.py`: the `approve` signal sets
  `_approved`. `_is_approved(needs_grant=...)` gates `wait_condition` until
  the implementer runs.
- `orchestrator/proposal_identity.py`: a proposal's identity is the
  `issue-<N>-` slug prefix. A `rejected` status is the only one a candidate
  may be retired for.
- Approval records who approved and when. It records no digest of the
  content that was approved.

### Representative proposal (read from gitops)

`agents-state/mctl-agents/proposals/issue-623-tracing-record-cache-read-write-token-us/`
has status `merged` (PR #628). Its file sizes are: `requirements.md` 5617 B,
`design.md` 8402 B, `tasks.md` 3704 B, 17723 B in total. Its `.status.yaml`
carries `source`, `control`, `context`, `approval`, `attempt`, `pr`, `github`,
`merged_at` and `merge_commit`. This is the planned primary round-trip
fixture.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/agents-state/` lists 16 service directories with
  proposals. Counts include mctl-agents 93, mctl-gitops 216, mctl-api 89 and
  mctl-telegram 111. There are 2629 `.md` files under `proposals/` in
  total. Non-triplet files: `proposed-content.md` 40, plus single files
  `outcome.md`, `cve-addendum-2026-04-27.md`,
  `contract-hardening-addendum.md` and `chef-review-amendments.md`. These
  are inputs to the migration-cost estimate.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-623-*/.status.yaml`
  is the field inventory used for the execution-state exclusion list (shown
  above).
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-655-*/` is a
  prior investigation of this same issue, with `status: proposed`. This
  proposal supersedes its content. The orchestrator owns
  `.status.yaml`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`:
  `replicaCount: 1`, `image.tag: "1.76.0"`. The spike changes no deployed
  config, so this is recorded only to confirm that no runtime change is
  needed.
- A search for `openspec` across `agents-state/` matched only the existing
  issue-655 proposal. No proposal uses OpenSpec today.
- mctl MCP tools were not called. Nothing in this spike depends on tenant,
  service or runtime state beyond the gitops files above.

## Proposed solution

The spike is a docs-and-fixtures change in `mctl-agents`. Its code lives in
a stand-alone dev tool. Production code paths are untouched.

### 1. Draft contract: `docs/adr/021-sdd-artifact-contract.md` (status `proposed`)

The change package has four files and an optional specs directory:

```
<slug>/
  proposal.md            # front matter: change_class, source{repo,issue,url}, capabilities[]
                         # sections: ## Why, ## What changes, ## Out of scope, ## Open questions
  specs/<capability>/spec.md   # ## ADDED|MODIFIED|REMOVED Requirements
                               #   ### Requirement: <name>   (SHALL/MUST sentence)
                               #   #### Scenario: <name>     (WHEN/THEN, EARS keywords kept)
  design.md              # unchanged section contract (Current state / Proposed / Alternatives / Platform impact)
  tasks.md               # unchanged: numbered tasks, DoD, (depends on N), ## Tests, ## Rollback
```

Canonical specs live in their own tree,
`specs/<service>/<capability>/spec.md`, holding only current-state
requirements. For the spike, this tree exists only as fixtures.

Rules:
- **Content allowed in the package.** Only the read-only `source` triple
  from `.status.yaml` may appear in the package, in `proposal.md` front
  matter. Every other execution key (`status`, `approval`, `attempt`, `pr`,
  `github`, `execution`, `context`, `control`) is a validation error.
- **Change classes.** `change_class: trivial | normal | governed` is
  required in `proposal.md`.
  - `trivial`: the package needs no `specs/` delta, and `tasks.md` may be a
    single task. Allowed only when no behavioral requirement changes.
  - `normal`: the default. A delta is required when a capability's
    behavior changes.
  - `governed`: a delta is required, and `design.md` must contain
    `## Alternatives` and `## Platform impact`.
  - All three classes use the same `.status.yaml` lifecycle and the same
    approval gate. The class selects validation strictness only, never
    authority. `control.requires_human_approval` is still set by the
    investigator exactly as today.
- **Mapping from the current triplet.**
  - `requirements.md` `## Context` maps to `proposal.md` `## Why`.
  - `## User stories` maps to `proposal.md` `## What changes`.
  - Each EARS line maps to one `### Requirement:` with one `#### Scenario:`
    under `## ADDED Requirements`. A requirement that changes existing
    behavior is placed under `MODIFIED` instead.
  - `## Out of scope` and `## Open questions` map to the same-named
    sections in `proposal.md`.
  - `design.md` and `tasks.md` stay byte-identical.
  - The `source` block is copied into front matter.

### 2. Dev tool: `tools/spec_contract.py`

This is a single file that follows the style of the existing `tools/*.py`
scripts (`check_binding_hash.py`, `context_release.py`). It depends only on
the standard library and PyYAML. It has no import from `orchestrator.*`,
and no `orchestrator.*` module imports it.

| Sub-command | Function |
|---|---|
| `validate <pkg>` | Checks structure, the class rules, the execution-key denylist, unique requirement names, a scenario for every requirement, task numbering, and that every `(depends on N)` refers to an existing task. Returns a list of diagnostics, each with a stable code. |
| `diff <canonical> <delta>` | Prints the planned `ADDED`/`MODIFIED`/`REMOVED` operations. |
| `apply <canonical> <delta> --out <dir> --archive <dir>` | Pure merge of the delta into the canonical spec. Raises `DeltaConflict` and writes nothing on conflict. |
| `export <legacy-dir>` | Converts a triplet into a package. |
| `import <pkg>` | Converts a package into a triplet. |
| `measure <legacy-dir>` | Byte and approximate token counts for both forms, plus a traceability matrix. |

### 3. Fixtures: `tests/fixtures/spec_contract/`

- `legacy/issue-623/`: a copy of the triplet and the `.status.yaml`
  `source` block (mctl-agents).
- `legacy/<second>/`: one proposal from another service, preferably one
  with `proposed-content.md` to exercise an extra file.
- `canonical/devloop-approval/spec.md`: current-state requirements written
  from `proposal_state.py` and `dev_loop.py`. Examples: approval required
  unless `control.requires_human_approval` is falsey; anonymous approvers
  (`""`, `unknown`, `none`, `null`) refused; a missing `control` block
  means no approval is required.
- `changes/devloop-approval-digest/`: an example delta.
  - `ADDED`: "approval SHALL record the package content digest".
  - `MODIFIED`: the anonymous-approver requirement, with an extra scenario.
  - `expected/devloop-approval/spec.md`: the canonical spec after the
    delta, used as the golden output.
- `invalid/`: one package per diagnostic code, for example an execution
  key in front matter, a requirement without a scenario, a dangling
  dependency, or a `trivial` class carrying a `MODIFIED` delta.

### 4. Report: `docs/spikes/655-openspec-compatible-artifact-contract.md`

The report contains:
- the mapping table;
- information lost or duplicated;
- size tables;
- the traceability matrix, as Implementer-boundary evidence;
- Investigator-boundary observations, each labelled `simulated` unless a
  real run was made;
- validation errors that the candidate form catches and the current form
  cannot;
- the sync and archive demonstration;
- the OpenSpec coupling, which is zero at runtime;
- the migration cost;
- the effect on the state machine and APIs, which is none for
  `ADAPTER_ONLY` and listed per follow-up for `ADOPT_CONTRACT`;
- answers to questions 1 through 10;
- one recommendation.

### Spec verification and the Shepherd boundary

```
spec verification (advisory finding)  +  CI required checks  +  review P1/P2
                                  \            |               /
                                   Shepherd decide() -> remediation / merge
```

- If spec verification is ever wired in, it produces findings in the same
  shape as a review finding. Those findings can feed `address-review`
  remediation. They can never produce `flip-to-merged` alone, never satisfy
  `human_approval_satisfied`, and never satisfy the ADR 016 merge
  approval.
- Rejected designs:
  - verification replaces review or CI;
  - verification grants or implies approval;
  - verification runs inside the merge path as an authority.
- The spike changes nothing in `run_shepherd.py`.

### Post-merge behavior (answer to Q7)

The proposed order is: merge, then the shepherd flips the status to
`merged`, then a separate sync applies the delta to canonical specs and
archives the change. Sync is never a precondition of `merged`. A sync
conflict leaves canonical specs untouched and raises an operator-visible
diagnostic. The spike only simulates this with `apply --archive`.

### Decision rubric (applied in the report)

Recommend `ADOPT_CONTRACT` only if all of the following hold:
- (a) zero `lost` rows;
- (b) the round trip is stable, or the one-way migration is justified;
- (c) the candidate catches at least one class of defect the current form
  cannot;
- (d) size growth is 15% or less;
- (e) there is a concrete path to a single requirements source with no
  dual authoring.

Recommend `NO_GO` if (a) fails, or if the delta model cannot express the
fixture capability. Otherwise recommend `ADAPTER_ONLY`.

## Alternatives

1. **Adopt the OpenSpec CLI directly** (`openspec validate`/`archive` in
   the worker image). Rejected: it adds a Node runtime dependency and
   couples the contract to CLI internals. That contradicts invariant 6,
   and it is not needed to prove the contract.
2. **Add the conversion logic to `orchestrator/` (for example
   `orchestrator/spec_contract.py`) now.** Rejected for the spike: it puts
   unproven code on the import graph of running workers, and it would
   tempt early wiring into the investigator or implementer. If the result
   is `ADOPT_CONTRACT`, promoting the tool into `orchestrator/` becomes a
   follow-up.
3. **A paper-only spike with no code.** Rejected: the issue requires
   demonstrated round-trip, delta-apply and validation evidence. A small
   tested tool makes the measurements reproducible.

## Platform impact

- **Migrations.** None. No gitops paths are written, and historical
  proposals are only copied into fixtures.
- **Backward compatibility.** Full. The investigator, implementer,
  shepherd, context assembly, Temporal workflows and `.status.yaml` are
  unchanged.
- **Resources.** None at runtime. The tests add a few fixture files and
  run in milliseconds.
- **Risks and mitigations.**
  - Risk: fixtures copied from gitops could contain sensitive text.
    Mitigation: the copies are proposals that are already public in the
    org repo, and they are reviewed in the PR.
  - Risk: format drift from upstream OpenSpec. Mitigation: the report pins
    the revision it checked compatibility against, or records that it
    could not check one.
  - Risk: the spike is read as approval to migrate. Mitigation: the ADR
    status is `proposed`, and the report must name a single
    recommendation. Any follow-up needs its own issues and approvals.
