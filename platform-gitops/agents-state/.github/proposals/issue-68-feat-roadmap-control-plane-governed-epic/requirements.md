# Governed EpicDefinition apply and RoadmapProposal integration

## Context

`roadmap/` in `mctlhq/.github` is already a working read-only control plane. `roadmap/scripts/validate.py`
enforces the `roadmap.mctl.ai/v1alpha1` `EpicDefinition` contract (`roadmap/schemas/epic-definition.schema.json`),
`roadmap/scripts/github_graph.py` observes the live GitHub graph through a GET-only adapter that raises
`WriteAttempted` before transmission on any non-GET method or request body, `roadmap/scripts/reconcile.py`
produces a deterministic `RoadmapDiff` carrying the SHA-256 of the exact manifest bytes, and
`roadmap/scripts/health.py` derives `RoadmapHealth` and `allRequired` completion. `roadmap/README.md` calls the
missing piece the *Planned write boundary*: "Write reconciliation comes later and must be deterministic: no LLM is
allowed in the apply path. The exact manifest revision/hash must be carried into audit/evidence."

Issue #68 is that write boundary, and it is `governed-apply` in `roadmap/epics/roadmap-control-plane.yaml` — the
only required work item still blocking `allRequired` completion of epic #66. Today a human converges the graph by
hand: the first live run against #66 reported three `DependencyMissing` entries whose dependencies existed only as
prose in issue bodies, and someone had to create the native `blocked_by` relations manually. This proposal turns
that manual convergence into a deterministic, hash-bound, replay-safe apply engine, and connects the authoring end
of the flow — intent, `RoadmapProposal`, `roadmap-decompose`, `EpicDefinition` draft, exact-hash approval, PR into
`roadmap/epics/` — so that a reviewed manifest, and nothing else, decides which GitHub mutations may happen.

## User stories

- AS a roadmap owner I WANT a merged `EpicDefinition` to converge the real GitHub graph automatically SO THAT
  parent, sub-issue and dependency edges stop being hand-maintained prose that drifts.
- AS a reviewer I WANT the set of GitHub mutations to be computable and readable before anything is written SO
  THAT approving a manifest PR is the same decision as approving the mutations.
- AS a platform operator I WANT apply to fail closed on any binding that is missing, ambiguous or externally
  changed SO THAT a transferred or deleted issue can never be "fixed" by writing over somebody else's graph.
- AS an auditor I WANT every applied operation to name the actor, the proposal, the exact manifest content hash
  and git revision, and the GitHub targets SO THAT the write is attributable without copying issue prose into the
  audit record.
- AS a security reviewer I WANT no model output anywhere in the apply path SO THAT an LLM cannot choose GitHub
  mutation targets at apply time.
- AS an agent author I WANT `roadmap-decompose` to end in a reviewable `EpicDefinition` PR SO THAT a
  `RoadmapProposal` produces one reviewed artifact instead of a sequence of generic GitHub mutations.

## Acceptance criteria (EARS)

Planning

- WHEN `plan.py` is given a validated manifest and an observed snapshot THE SYSTEM SHALL emit a
  `RoadmapApplyPlan` that is a pure function of the manifest bytes and the snapshot bytes, carrying no timestamp,
  no random value and no absolute path, so identical inputs produce byte-identical output on any machine.
- WHEN a `RoadmapDiff` entry of type `HierarchyMissingParent`, `HierarchyWrongParent`, `DependencyMissing` or
  `DependencyUnexpected` is present THE SYSTEM SHALL emit exactly one corresponding plan operation
  (`AddSubIssue`, `MoveSubIssue`, `AddDependency`, `RemoveDependency`).
- WHILE a plan is being built THE SYSTEM SHALL restrict every operation target to an identity in
  `DesiredGraph.authored_keys()` for the manifest being applied, and SHALL raise rather than emit an operation
  whose target is not authored.
- WHEN a `RoadmapDiff` carries an entry of severity `informational` (`BindingUnbound`, `HierarchyUnexpectedChild`)
  THE SYSTEM SHALL record it in the plan as a non-actionable note and SHALL NOT emit an operation for it.
- IF a `RoadmapDiff` carries `BindingIssueNotFound`, `BindingAmbiguous` or `BindingRedirected` THEN THE SYSTEM
  SHALL refuse the entire plan for that manifest with a `PlanRefused` reason naming the offending bindings, and
  SHALL emit zero operations.
- IF any authored endpoint of the manifest was not observed, or the snapshot is invalid, or the corpus fails
  validation THEN THE SYSTEM SHALL refuse the plan and SHALL make no network call.
- WHEN a plan is emitted THE SYSTEM SHALL give every operation a stable `opId` derived only from the manifest
  SHA-256, the operation type and its canonical endpoints, so the same operation has the same id across runs.

Applying

- WHILE applying THE SYSTEM SHALL use a write client whose allowed requests are a closed allow-list of
  (method, path template) pairs covering only sub-issue add, sub-issue remove, dependency add and dependency
  remove, and SHALL raise before transmission on any request outside that list.
- WHEN an operation is about to be executed THE SYSTEM SHALL re-read that operation's endpoints and compare the
  live state with the precondition recorded in the plan.
- IF the re-read precondition is already satisfied THEN THE SYSTEM SHALL record the operation as
  `alreadySatisfied` and SHALL issue no write, so retry and replay converge to the same graph with zero
  additional mutations.
- IF the re-read state differs from the precondition recorded in the plan in any other way THEN THE SYSTEM SHALL
  record the operation as `skipped` with reason `PreconditionChanged` and SHALL issue no write.
- IF a write returns a non-success status THEN THE SYSTEM SHALL record the operation as `failed`, SHALL continue
  with the remaining independent operations, and SHALL exit non-zero.
- WHILE applying THE SYSTEM SHALL re-assert, immediately before each write, that both endpoints of the operation
  are authored identities of the manifest being applied.
- WHEN `apply.py` is invoked without an explicit execute flag THE SYSTEM SHALL perform the plan and precondition
  re-read only, write nothing, and report what would change.
- IF the manifest's checkout is dirty, or the manifest bytes on disk do not match the bytes committed at the
  recorded git revision THEN THE SYSTEM SHALL refuse to apply.

Audit and evidence

- WHEN an apply run completes THE SYSTEM SHALL emit a `RoadmapApplyResult` whose audit block names the actor, the
  proposal reference (or explicit null), the manifest repository-relative path, the manifest content SHA-256, the
  full 40-character git revision the manifest was read at, the plan id, and the GitHub targets touched.
- WHILE building audit or evidence output THE SYSTEM SHALL record GitHub targets only as `{repository, number}`
  refs and SHALL NOT copy issue titles, bodies or comment text into the record.
- WHEN a `RoadmapApplyResult` is emitted THE SYSTEM SHALL validate it against
  `roadmap/schemas/roadmap-apply-result.schema.json` before returning it.

Approval and proposal integration

- WHEN `roadmap-decompose` finishes THE SYSTEM SHALL produce an `EpicDefinition` draft that passes schema,
  semantic and corpus validation against the existing `roadmap/epics` corpus, and SHALL publish it as a pull
  request adding or updating a file under `roadmap/epics/` in `mctlhq/.github`.
- WHILE a `RoadmapProposal` is being approved THE SYSTEM SHALL bind the approval to the SHA-256 of the exact
  draft manifest bytes.
- IF the manifest bytes change after approval THEN THE SYSTEM SHALL treat the approval as invalid
  (`ApprovalHashMismatch`) and SHALL NOT apply.
- WHILE the apply path runs THE SYSTEM SHALL take its mutation targets only from the validated manifest corpus
  and SHALL accept no free-form target argument, so no model output can select a GitHub mutation target.
- WHEN `mctl-api` and `mctl-agents` are wired to this contract THE SYSTEM SHALL keep `mctl-api` as the
  `RoadmapProposal` persistence and authorization boundary and `mctl-agents` as the deterministic GitHub
  mutation boundary, with no model invocation inside the apply activity.

Proof

- WHEN the converged `human-input` fixture is planned THE SYSTEM SHALL emit an empty operation list.
- WHEN a single mutation from `roadmap/tests/mutations.py` is applied to that fixture THE SYSTEM SHALL emit
  exactly one operation of the matching type and SHALL NOT emit operations in a neighbouring family.
- WHEN that operation is executed against the offline fake graph and the fixture is reconciled again THE SYSTEM
  SHALL report zero drift, proving a merged manifest reconciles Human Input with no duplicate hand-maintained
  graph declarations.
- WHILE running in `.github/workflows/roadmap-validate.yml` THE SYSTEM SHALL exercise plan and apply only
  offline against fixtures, with `permissions: {}` and no token.

## Out of scope

- Automatic merge of the manifest PR. A human merges; apply only ever runs on merged, reviewed bytes.
- Replacing the GitHub Issues/Projects UI. GitHub stays the human planning surface.
- Migrating every existing epic in the first write-enabled release. `human-input` and `roadmap-control-plane` are
  the pilots.
- Creating GitHub issues for unbound work items (`BindingUnbound`). Creation is not idempotent without an
  external idempotency key and forces a write-back of the new issue number into the manifest, which would make
  the apply path author desired state. It stays a follow-up.
- Projects v2 field mutation. There is no observed representation of project fields in
  `roadmap/schemas/github-graph-snapshot.schema.json` and no `RoadmapDiff` family for them, so there is nothing
  deterministic to converge; the read side must gain projects first, and the read adapter is deliberately
  REST-only while Projects v2 is GraphQL-only.
- Removing `HierarchyUnexpectedChild` children. The manifest does not claim exclusive ownership of a parent's
  child set; deleting a child nobody authored would destroy state the manifest never described.
- `UNEXPECTED_SILENCE` / temporal health (#85), which needs a notion of "now" and is deliberately excluded from
  deterministic evaluation.

## Open questions

- **Which repository hosts the apply engine.** The reconciler, schemas and fixtures live in `mctlhq/.github`, so
  this proposal places `plan.py`, `apply.py`, `github_apply.py` and the two new schemas there beside them, and
  treats the Temporal/Argo workflow and the `RoadmapProposal` persistence changes as follow-up work in
  `mctl-agents` and `mctl-api` against the published contracts. If the platform prefers the engine to live in
  `mctl-agents` from the start, the module layout is unchanged but the pilot fixtures must be vendored there.
- **Credential and identity for writes.** A GitHub App installation token scoped to `issues: write` on
  `mctlhq/*` is assumed, with the app slug recorded as `audit.actor`. Whether that is the existing
  `mctl-agents[bot]` app or a separate roadmap app with a narrower scope is a platform decision. Proceeding with
  the narrower-scope assumption and making the actor a required audit field either way.
- **`MoveSubIssue` atomicity.** GitHub has no single call that reparents an issue, so a move is a remove followed
  by an add. If the add fails, the child is left orphaned. Proceeding with: perform the add-side first where the
  API permits re-parenting in one call, otherwise record the intermediate state in the result and mark the
  operation `failed` with the orphaned child named, so the next replay finishes it.
- **`RoadmapProposal` shape in `mctl-api`.** The existing resource is not visible from this repository. Assuming
  it already carries an id, an actor and an approval record, and that adding `manifestSha256` plus an
  `epicDefinitionPullRequest` reference is additive.
- **Whether apply should run on a schedule or only on merge.** Proceeding with merge-triggered plus manual
  re-run; a periodic drift-correcting cron is deliberately not proposed, because unattended continuous writes
  would make a bad merge converge the whole graph before anyone reads the diff.
