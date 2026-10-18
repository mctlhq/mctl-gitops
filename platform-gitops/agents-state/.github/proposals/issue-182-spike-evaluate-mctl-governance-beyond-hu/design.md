# Design: issue-182-spike-evaluate-mctl-governance-beyond-hu

## Current state

### This repository (mctlhq/.github)

- `roadmap/epics/agent-governance-decision-assurance.yaml` is the provisional
  EpicDefinition for parent #181. It is written as JSON inside a `.yaml` file and
  sets `lifecycle: proposed`, owner `mctl-api`, one phase `discovery`, and one
  required work item `decision-assurance-spike` that points to
  mctlhq/.github#182. Its header comments say "Discovery-only graph; revise
  required work or archive before epic completion". The last successCriteria
  entry already says "spike closure alone is not evidence of delivered runtime
  guarantees".
- `roadmap/schemas/epic-definition.schema.json` allows `lifecycle` to be one of
  `proposed | active | paused | completed | archived`.
  `.github/workflows/roadmap-validate.yml` runs
  `python3 roadmap/scripts/validate.py roadmap/epics` and the `roadmap/tests`
  suite on every change under `roadmap/`.
- Related owner epics that can absorb gaps: `unified-identity.yaml` (#91,
  completed), `agent-platform.yaml` (#18, completed), `agent-commerce.yaml`
  (#173), `observability.yaml` (#55, active), `agent-runtime-assurance.yaml`
  (#151, active), `human-input.yaml` (#42, completed) and
  `lifecycle-ownership.yaml` (#57, completed).
- `docs/plans/agent-commerce.md` sets the house convention for audit documents:
  a "Live audit and evidence" section, a table of pinned source revisions per
  repository, existing work items with their live state and reuse limits, and
  scoped negative results ("a scoped negative result, not proof that no
  unpublished design exists"). `AGENTS.md` lists active plans. No `docs/spikes/`
  directory exists yet.
- This repository holds no runtime code for approvals, policy or execution. The
  report will cite mctl-api, mctl-agents and mctl-gitops at pinned revisions.

### Governance seams already visible (evidence the report must deepen)

- `agent-platform/policy.yaml` in mctl-gitops: `knownMutationScopes` maps
  mutating scopes to approval gates (`code-authoring`, `merge`,
  `gitops-main-write`). `incident-resolve`, `proposal-status`,
  `proposal-directory-write`, `issue-comment`, `agents-state-inbox-write` and
  `mentor-digest-write` have `requiresApproval: null`. The file's own comment
  says that for `incident-resolve` (a state change in mctl-api that a revert
  cannot undo) "Whether it should have a gate is undecided". `knownPolicies`
  is a registry of policy *names* only: "not their content". This bears
  directly on the D2 "policy evidence" row, because a name is not a version.
- `argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml`: the
  `expected_content_digest` parameter is *optional*. When it is set, the flip
  refuses drift (mctl-agents#681, mctl-gitops#1953). When it is empty, it
  "keeps the #658 behaviour: record the digest of whatever is there at flip
  time". `approver` is a free-form parameter that defaults to `"unknown"`.
  Taken together: binding is enforced only when the caller is mctl-api with a
  digest-carrying grant, and approver identity at this boundary is a string,
  not a verified principal. Which callers reach this CWFT without a digest
  (for example the direct `mctl-agents-approve` operation) is a D3 F1/F5 question.
- The incident responder auto-accepts proposals (MCP tool description:
  "write auto-accepted proposals ... then resolve the incident"). The policy
  `incident-response` names this explicitly. This is a governed path with no
  human gate at all, so it is a D1 path and an input to F10 (bypass).

### Deployed state checked

- `$MCTL_GITOPS_ROOT/bootstrap/templates/mctl-platform/mctl-api.yaml`: mctl-api
  image tag `4.102.0` (the issue's #681 E2E baseline was `4.97.0`).
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker{,-exec,-implement}/values.yaml`:
  image tag `1.84.0`, the same as the #681 E2E baseline.
- `$MCTL_GITOPS_ROOT/agent-platform/policy.yaml`: the mutation scopes, approval
  gates, policy-name registry and approved sandbox CWFTs described above.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml`:
  optional `expected_content_digest`, free-form `approver`, the digest
  computation over requirements/design/tasks/proposed-content.
- `$MCTL_GITOPS_ROOT/agent-platform/execution-profiles/`: profiles exist for
  issue-investigator, implementer, shepherd, incident-responder, mentor,
  service-agent and authoring-canary. Their contents were not read in detail.
- mctl MCP read tools were not called. The values above come from gitops
  desired state, not from live ArgoCD sync or health status, and no live
  approval or audit record was inspected. This is a gap the implementer must
  close (see Open questions in requirements.md).
- mctl-api and mctl-agents source trees: not available in this run. Nothing in
  this design asserts their internal behaviour beyond what the issue and the
  gitops comments state.

## Proposed solution

Deliver the spike as one durable report plus a roadmap manifest edit that
matches its disposition. Make no runtime changes.

### 1. Report: `docs/spikes/agent-governance-decision-assurance.md`

Structure:

1. **Status and non-claims.** A banner stating that this is an audit, that it
   delivers no runtime assurance, and that it authorizes no bypass.
2. **Audit method and pinned revisions.** The same table format as
   `docs/plans/agent-commerce.md`, giving the main SHA of each repository and
   the deployed tags (mctl-api `4.102.0` and mctl-agents `1.84.0` from gitops,
   re-verified at writing time with `mctl_get_service_config` /
   `mctl_get_service_status` where they are available).
3. **Path inventory.** The governed paths audited: P1 DevLoop proposal-content
   approval (Temporal approve signal, then mctl-api grant, then approve CWFT,
   then implementer digest check); P2 the direct `mctl-agents-approve`
   operation; P3 capability gateway invoke (sealed set, then PolicyCheckpoint,
   then provider, then InvocationRecord); P4 incident-responder auto-accept and
   `incident-resolve`; P5 commerce invocation (quote, approval, receipt); P6 MCP
   platform operation through mctl-api (for example deploy or rollback with
   `confirm`); P7 delegated sub-agent or WorkItem execution request
   (mctl-api#428 delegation grants, execution requests with leases and
   fencing). Every path the report leaves out is listed with the reason.
4. **D1 sequence diagrams.** One Mermaid `sequenceDiagram` per path. Trust
   boundaries are drawn as boxes (human client, mctl-api, Temporal worker, Argo
   CWFT, gitops, provider). Every arrow is annotated with the identity it
   carries and the evidence it persists. Implemented and planned steps are
   marked separately.
5. **Dimension evaluations (scope sections 1-8).** Intent provenance, identity
   and authority, policy evidence, decision context (the minimum envelope fields
   classified as present, missing or UX-only for each path), approval integrity
   and execution binding, end-to-end trace (actual evaluation order, durable IDs
   compared with sampled spans), reject, override and escalation, and
   governance observability.
6. **D2 capability matrix.** Columns Capability | Status | Owner/component |
   Gap | Evidence. There is one row per minimum capability. Where status
   differs between paths, the row is split per path, or the Status cell lists
   paths, for example `implemented (P1) / missing (P2, P4) / unknown (P5)`.
   The allowed statuses are implemented, partial, missing,
   owned-by-another-epic and `unknown (not observed: <reason>)`.
7. **D3 F1-F10 table.** Columns ID | Path(s) | Current behaviour | Desired
   invariant | Evidence (test path@SHA or bounded reproduction) | Gap | Owner.
   Reproductions are limited to unit tests, local runs or dry-run modes (for
   example `mctl_trigger_shepherd dry_run`, or CWFT logic run against a scratch
   checkout). Nothing runs against production. Each row may name a candidate
   AssuranceScenario for #151.
8. **D4 candidate Decision Envelope.** Each field of the illustrative
   `GovernedDecision` is mapped to an existing contract: actor and subject to
   mctl-api#572 identity evidence; operation hash to `ActionApprovalRequest.artifact_hash`
   / `intent_hash`; execution to WorkItem execution, InvocationRecord and the
   commerce receipt; usage to the usage ledger; trace to the #55 trace id. The
   envelope is append-only references (decision, then N policy evaluations, N
   approvals, N attempts), not singletons. The section also covers retention,
   access and redaction: hashes plus references to access-controlled artifacts
   instead of payload copies.
9. **D5 disposition.** Exactly one of the three. Every gap appears in a routing
   table: Gap | Owner repo/component | Owner epic (existing or proposed) |
   Draft follow-up (evidence, scope, acceptance criteria). The working
   hypothesis is EXTEND EXISTING. The report must justify it, or switch to one
   of the other two if a coherent capability boundary remains that no existing
   epic owns (for example a cross-path append-only decision record, if
   neither #18 nor #55 can own it).
10. **Parent disposition and non-claims.** What happens to #181 and why.

### 2. Roadmap manifest

- EXTEND EXISTING or NO NEW EPIC: set `lifecycle` to `archived` in
  `roadmap/epics/agent-governance-decision-assurance.yaml`, add a header comment
  that names the report and the routing table, and keep the spike work item
  (it is still the completed required item). No new work items are added here.
  Routed gaps belong to their owner epics' manifests, which are changed only
  once their issues exist.
- CREATE NEW EPIC: keep `proposed` (activation is a separate decision). Add
  phases (for example `binding`, `evidence`, `observability`, `proof`), add
  work items only for issues that exist, and record the rest as proposed
  follow-ups in the report. Set the `dependsOn` DAG and keep the non-claim in
  successCriteria.
- In either case, `validate.py` and `roadmap/tests` must pass.

### 3. `AGENTS.md`

Add a "Spikes" (or active plans) entry that links the report, so that later
agents in this repository find it.

### Why this shape

The issue asks for a durable report in this repository, and the house
convention for cross-repository audits (`docs/plans/agent-commerce.md`) already
covers pinned revisions and scoped negative results. Splitting the matrix per
path is the only way to keep the #681 evidence from being generalized, which
the issue forbids. Changing the manifest in the same PR keeps the roadmap
control plane consistent with the disposition, so that closing #182 cannot
leave a `proposed` epic whose only required item is done and which therefore
looks "complete".

## Alternatives

1. **Put the report in `docs/plans/`.** This is consistent with the existing
   docs, but a plan implies execution. The report is an audit result that
   routes work elsewhere. Rejected as the default; see the open question.
2. **Implement quick fixes during the spike** (for example making
   `expected_content_digest` mandatory in the approve CWFT, or gating
   `incident-resolve`). Rejected. It is out of scope, it changes runtime
   behaviour in mctl-gitops from a `.github` PR, and it would pre-empt the D5
   routing. These become draft follow-ups instead.
3. **One aggregate status per capability.** Simpler, but it would mark
   "execution binding: implemented" on the strength of #681 alone, which the
   issue explicitly forbids. Rejected in favour of per-path status.
4. **Create the follow-up GitHub issues in the same change.** Rejected. Issue
   creation is a separate governed step. The report drafts them with evidence
   and acceptance criteria.

## Platform impact

- Migrations: none. The change touches documentation, one roadmap manifest
  `lifecycle` value (or a refinement of it), and `AGENTS.md`.
- Backward compatibility: the roadmap publication will show epic #181 as
  `archived` (or refined). `roadmap-publish.yml` picks this up on merge, and
  no consumer depends on #181 staying `proposed`. The workflows that
  `roadmap-validate.yml` runs guard the schema.
- Resource impact: none at runtime.
- Risks and mitigations:
  - *Overclaiming coverage from #681.* Mitigation: per-path status, plus the
    `unknown (not observed)` status.
  - *Stale evidence* (the deployed tags already moved from the baseline).
    Mitigation: a pinned SHA and deployed tag for every claim, and the audit
    date in the header.
  - *Sensitive detail in a public-facing org repository* (describing bypass
    gaps). Mitigation: describe gaps at the contract level, with no secrets,
    tokens, tenant data or exploit steps. Reproductions name tests, not
    payloads.
  - *Spike closure misread as delivered assurance.* Mitigation: the non-claim
    banner, the manifest successCriteria, and the archived or refined epic
    lifecycle.
