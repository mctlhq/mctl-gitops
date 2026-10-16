# Design: issue-655-spike-devloop-evaluate-openspec-compatib

## Current state

### How a proposal is produced
- `orchestrator/run_issue_investigator.py` defines
  `TRIPLET = ("requirements.md", "design.md", "tasks.md")`. The prompt template
  fixes the section layout: EARS `requirements.md`, then `design.md` with
  `## Current state` / `## Proposed solution` / `## Alternatives` /
  `## Platform impact`, then `tasks.md` with tasks, `## Tests` and
  `## Rollback`. That layout is enforced only by the prompt. After the agent
  runs, step 4 of `_investigate` checks just two things:
  `missing = [name for name in TRIPLET if not _is_plain_file(staging / name)]`.
  Every file must exist, and every file must be a regular file and not a
  symlink. Nothing checks the structure.
- The orchestrator writes `.status.yaml` into staging next to the triplet,
  then publishes both with a swap. `_note_investigation_evidence` records each
  triplet file by sha256 as a `proposal` artifact (ADR 018 envelope,
  `orchestrator/execution_evidence.py`). `_trace_published` emits one
  `mctl.artifact.write` per file.
- `orchestrator/proposal_identity.py` resolves which `issue-<N>-*` directory
  owns an issue number. The slug, not the file format, is the identity key.

### How a proposal is consumed
- `orchestrator/run_implementer.py` tells the sub-agent to "Read spec files
  from `$PROPOSAL_DIR` ...: requirements.md, design.md, tasks.md" (mctl-docs
  also reads `proposed-content.md`). Review-fix runs say the same thing. The
  implementer treats the files as free-form prose for the model. No code
  parses them.
- `orchestrator/context_assembly.py` has
  `TRIPLET_FILENAMES = ("requirements.md", "design.md", "tasks.md")` and
  collects a prior proposal's triplet as context, under byte ceilings.
- `orchestrator/run_shepherd.py` reads only `.status.yaml` and PR/CI/review
  state. It never reads the triplet, so the Shepherd decision has no spec
  input today.

### Execution state and approval
- `orchestrator/proposal_state.py` owns the execution state:
  - `human_approval_satisfied` checks the write-time gate, `control.requires_human_approval`.
  - `execution_authorization` is fail-closed. Only a non-anonymous
    `approval.approved_by` authorizes; `AUTHORIZATION_AUTONOMY_POLICY` is
    reserved and unused.
  - `unrunnable_reason` names a proposal that can never run.
- `orchestrator/temporal/workflows/dev_loop.py` `DevLoopWorkflow.approve` sets
  `_approved`/`_approver`, and the atomic approve CWFT flips `.status.yaml`.
  The approval is bound to the proposal identity (service/slug, workflow id
  `dev-loop-mctlhq-{repo}-{issue}`). It is **not** bound to a content digest
  of the triplet: `.status.yaml` `approval` holds only `approved_by` and
  `approved_at`. By contrast, `orchestrator/action_approvals.py` binds action
  approvals to `intent_hash`. This spike must not weaken the current binding.
  It records digest-binding as a follow-up.
- Example `.status.yaml` (issue-516) has these blocks: `status`, `updated_*`,
  `execution`, `source` (repo/issue/url), `control`, `context`
  (snapshot_id/content_hash), `approval`, `attempt`, `pr`, `notes`, `github`,
  `merged_at`, `merge_commit`. Only `source` is planning-relevant. All the
  rest is execution state.

### What the corpus looks like
These numbers come from the gitops checkout at
`$MCTL_GITOPS_ROOT/agents-state`:
- 855 proposal directories across services, all with a `requirements.md`.
  Of these, 174 are `incident-*`.
- The 93 `mctl-agents` entries together hold about 2.57 MB of triplet text,
  about 28 KB per proposal. The issue-516 triplet is 35,780 bytes
  (requirements 10,684, design 16,359, tasks 8,737).
- 29 `mctl-agents` `requirements.md` files have no `## Acceptance criteria`
  heading. This is drift that a structural validator would catch and the
  current existence check does not.
- 40 mctl-docs proposals carry the extra `proposed-content.md`.
- The repo has no current-state capability specs. ADRs under `docs/adr/`
  (for example 010 lifecycle ownership, 016 shepherd merge approval) are the
  nearest thing to canonical behaviour, written as prose.
- `grep -ri openspec` over the clone returns nothing, so no prior work exists.

Deployed state checked:
- `mctl_get_service_status(team=admins, service=mctl-agents-worker)`: ArgoCD
  `Healthy` / `Synced`, image tag `1.76.0`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`:
  `image.tag: "1.76.0"`. The worker rides the shared
  `ghcr.io/mctlhq/mctl-agents` image. The spike adds no runtime component, so
  this is context only.
- `$MCTL_GITOPS_ROOT/agents-state/*/proposals/*`: listed and measured as
  above. Read-only.
- Not checked: the OpenSpec upstream repository and docs. This run did no web
  fetch, so the grammar below is from published documentation as recalled and
  must be pinned by task 1 (see Open questions in requirements.md).

## Proposed solution

The spike is a set of additive artifacts plus one inert, pure-Python module. No
production code path imports the module. Everything is reversible by deleting
the files.

### 1. Contract document: `docs/spikes/655-sdd-artifact-contract.md`
This document defines the candidate change package. It can live inside the
existing proposal directory, with no directory migration required:

```text
proposals/<slug>/
  proposal.md                 # Why / What changes / Impact / Source
  specs/<capability>/spec.md  # delta: ## ADDED|MODIFIED|REMOVED|RENAMED Requirements
  design.md                   # unchanged sections
  tasks.md                    # unchanged sections
  .status.yaml                # MCTL execution state, NOT part of the contract
```

It also defines the canonical form. The fixtures default to
`specs/<capability>/spec.md` with `## Purpose` and `## Requirements`.

The grammar:
- `### Requirement: <Name>`, whose body holds at least one SHALL or MUST
  sentence.
- One or more `#### Scenario: <name>` blocks, with `- WHEN` / `- THEN`
  (optional `- AND`) bullets.

EARS lines map onto it as follows. A `WHEN x THE SYSTEM SHALL y` line becomes
a requirement with one scenario. `WHILE` and `IF` become scenarios with a
`GIVEN`/`WHEN` precondition.

`proposal.md` carries `Source: <issue URL>`. It is the only identity
reference, and it duplicates `.status.yaml` `source.url` on purpose,
read-only. If the two disagree, `.status.yaml` wins. No other execution field
appears in it.

### 2. Inert module: `orchestrator/spec_contract.py`
This module holds pure functions with no I/O beyond the paths it is given:
- `parse_change(path) -> ChangePackage` and `parse_canonical(path) ->
  CapabilitySpec`: typed dataclasses `Requirement(name, text, scenarios)` and
  `Delta(added, modified, removed, renamed)`.
- `validate_change(pkg, canonical: Mapping[str, CapabilitySpec]) ->
  list[ContractError]`. It reports:
  - a missing `proposal.md` or a missing `Source:` line;
  - a requirement with no SHALL/MUST, or with no scenario;
  - a `MODIFIED`, `REMOVED` or `RENAMED` entry whose target is unknown;
  - an `ADDED` entry that collides with an existing name;
  - a duplicate name within the delta;
  - execution-state keys present (`status:`, `approval:`, `attempt:`, `pr:`,
    `merge_commit:`, `control:` as YAML front matter or as structured blocks);
  - a `trivial` class that carries delta specs, or a `normal` or `governed`
    class that carries none.
- `apply_delta(base, delta) -> CapabilitySpec`: deterministic. The order is
  RENAMED, then REMOVED, then MODIFIED, then ADDED, appending in delta order.
  `MODIFIED` replaces the whole requirement block.
- `render_canonical(spec) -> str`: stable rendering, so that
  `render(apply(base, d))` is byte-stable.
- `from_triplet(dir) -> ChangePackage` and `to_triplet(pkg) -> dict[str, str]`
  for the round-trip, plus `import_openspec(dir)` and `export_openspec(pkg,
  out)`. These are layout transforms only. They never shell out to `openspec`.

There is no YAML schema dependency beyond what `pyproject.toml` already
carries. The module is imported only by tests and by `tools/spec_contract.py`.

### 3. Tool: `tools/spec_contract.py`
This is a repo-local CLI in the same style as `tools/check_binding_hash.py`,
with four subcommands: `validate <dir>`, `diff <base> <change>`,
`import <openspec-change> <out>` and `export <proposal> <out>`. It also has
`archive <change> --canonical <dir> --out <dir>`, which simulates verify, then
sync, then archive into a scratch directory. The CLI is the cheapest way to
show the command surface the issue sketches. It is not a public CLI.

### 4. Fixtures: `tests/fixtures/spec_contract/`
- `canonical/devloop-approval/spec.md` is written from current code. It holds
  about 6 to 8 requirements, for example:
  - "Approval requires a non-anonymous approver" (`execution_authorization`);
  - "Absent control block does not require approval"
    (`human_approval_satisfied`);
  - "Malformed control block fails closed";
  - "Accepted proposal without approval is unrunnable"
    (`unrunnable_reason`, `BLOCKED_APPROVAL_MISSING`);
  - "Approve signal never raises" (`DevLoopWorkflow.approve`);
  - "Autonomy policy authorizes nothing yet".
- `changes/approval-digest-binding/` is a synthetic delta. It ADDS "Approval
  binds a change-package digest", MODIFIES "Approval requires a non-anonymous
  approver" to require a digest match, and REMOVES nothing. A second delta,
  `changes/remove-legacy/`, demonstrates REMOVED.
- `historical/issue-516/` and one smaller proposal are byte copies of the
  triplets plus their `.status.yaml` `source` block only. The smaller one is
  chosen in task 4, for example `issue-623-tracing-record-cache-read-write-token-us`.
- `openspec/` holds a hand-written OpenSpec-layout change, used to test import.
- `expected/` holds golden outputs: the new canonical spec, the exported
  triplet and the archived layout.

### 5. Investigator / implementer simulation (offline, recorded)
These runs are done once by a human or agent and the results are stored in the
spike report. They are not wired into CI.

- **Investigator.** Take two historical issues (516 and the smaller one). Run
  the current investigator prompt and a candidate prompt variant against the
  same clone SHA. The variant is a copy of the template text in the report and
  is not edited into `run_issue_investigator.py`. It adds the canonical
  devloop-approval spec as context and asks for a delta. Then:
  - Run `validate` on the output.
  - Count bytes, and estimate tokens as bytes/4 to stay consistent with
    `context_assembly` ceilings.
  - Count the ambiguities the validator or a reviewer flags.
  - Record whether the changed capability is named.
- **Implementer.** Conceptually, feed the converted package to the implementer
  prompt shape. The concrete evidence is the mechanical loss check from
  requirements.md (every EARS, task, test and heading line appears exactly
  once). Optionally, add one dry implementer run on a sandbox branch of the
  smaller proposal, with no push.

### 6. Verification boundary (documented, not built)
Shepherd's decision gets one new, separately reported input,
`spec_conformance: pass|fail|unknown`. It comes from
`validate_change(pkg, canonical)` and an optional model judgement of whether
the diff satisfies each scenario. It ranks below CI and P1/P2 review findings.
It can block a merge only as a **finding**: a fail becomes a P2-class
remediation input. It can never cause a merge, an approval or an authorization.
`unknown` never blocks, so the current behaviour is preserved.

The report states three explicit rejections:
- "spec verify replaces Shepherd/CI";
- "verify pass authorizes merge";
- "spec artifact implies approval".

### 7. Post-merge behaviour (documented and simulated)
On `merged`, a follow-up step in the reconcile path (not built) would run three
steps:
1. verify, which revalidates the delta against the canonical spec at the merge
   commit;
2. sync, which writes the new canonical spec in its own gitops commit;
3. archive, which moves `specs/**` deltas to `archive/<date>-<slug>/`.

`.status.yaml` stays the record of execution. The spike only simulates this
with `tools/spec_contract.py archive` on fixtures.

### 8. Change classes
`trivial`, `normal` and `governed` are a single planning-only field in
`proposal.md` (`Class:`). The classifier is the investigator. The validator
checks consistency.

| Class | Requires | Waives |
|-------|----------|--------|
| `trivial` | `proposal.md` + `tasks.md` | delta specs and `design.md` |
| `normal` | full package | nothing |
| `governed` | full package + canonical-spec sync on merge | nothing |

Approval, `execution_authorization` and the `.status.yaml` state machine are
identical for all three, so there is no second lifecycle.

### 9. Decision criteria (fixed before measuring)
The report must record these before task 6 runs.

- `ADOPT_CONTRACT` needs all four of the following:
  - lossless or justified-lossy round-trip;
  - candidate size no more than 1.15x current on both proposals;
  - the validator catches at least one real defect class the existence check
    misses (the 29 missing-heading proposals already qualify);
  - the investigator variant names the changed capability in both runs, with no
    new ambiguity.
- `ADAPTER_ONLY` applies if the contract is sound but canonical-spec upkeep or
  investigator reliability fails.
- `NO_GO` applies if the round-trip is lossy in implementation-relevant ways
  or the size and ceremony cost exceeds the criteria.

Invariant 7 (one source of requirements) settles what `ADOPT_CONTRACT` would
mean. `specs/**` deltas plus `proposal.md` replace `requirements.md` for new
proposals. A `to_triplet` view is generated for any legacy consumer, and is
never authored.

## Alternatives

- **Depend on the OpenSpec CLI (Node) for validate/archive.** Dropped. It adds
  a Node runtime to the `ghcr.io/mctlhq/mctl-agents` image, couples the
  contract to a third-party release cadence, and violates invariant 6 without
  enough justification. The grammar is small enough to parse in about 300
  lines of Python.
- **Extend `requirements.md` in place with a structured EARS validator, without
  OpenSpec layout.** This is cheaper, and it catches the missing-heading drift.
  It gives no capability identity, no current-state specs and no interop. It is
  kept as the fallback the `ADAPTER_ONLY` and `NO_GO` outcomes can still
  justify as a follow-up, but it does not answer the issue's question.
- **Prototype directly in the investigator and implementer behind a flag.**
  Dropped for the spike. It touches production prompts and the
  `TRIPLET`/`TRIPLET_FILENAMES` contract, and needs an agent release through
  the registry (ADR 007). That breaks the "no production migration" invariant.
  It is the natural first follow-up if the result is `ADOPT_CONTRACT`.
- **Model canonical specs as ADRs.** Dropped. ADRs record decisions and their
  history, not current-state requirements. Deltas against prose do not apply
  mechanically.

## Platform impact

- **Migrations:** none. No gitops writes, no `.status.yaml` change and no agent
  release. Historical proposals are copied into fixtures, and the originals
  are never touched.
- **Backward compatibility:** total. `orchestrator/spec_contract.py` is
  imported only by `tools/spec_contract.py` and the tests.
  `TRIPLET`, `TRIPLET_FILENAMES`, both prompts and `proposal_state` are
  unchanged.
- **Resources:** the CI suite gains a few fast unit tests. The offline agent
  simulations cost about 2 investigator runs (about $3 each) and optionally one
  implementer dry run. Their results are recorded once.
- **Risks and mitigations:**
  - *Grammar drift from upstream OpenSpec.* Mitigation: pin the targeted
    version in the fixtures, and keep `import`/`export` as layout transforms
    only.
  - *The spike is read as a commitment.* Mitigation: the decision criteria are
    fixed up front, and `ADOPT_CONTRACT` requires follow-up issues rather than
    code in this PR.
  - *Dual authoring sneaks in.* Mitigation: the report must state which file is
    authored and which is generated for any recommended end state.
  - *Approval provenance weakened.* Mitigation: the contract carries no
    approval field. Digest-binding is recorded as a strengthening follow-up,
    not a dependency.
  - *Fixture copies of proposals contain sensitive text.* The proposals are
    already in the mctl-gitops repo with the same visibility tier.
    Mitigation: copy only `mctl-agents` proposals, and only the `source`
    block of `.status.yaml`.
