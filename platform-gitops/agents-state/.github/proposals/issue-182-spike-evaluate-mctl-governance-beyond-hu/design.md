# Design: issue-182-spike-evaluate-mctl-governance-beyond-hu

## Current state

### This repository (`mctlhq/.github` at `6f35424`)
- `docs/plans/` holds durable plan documents (`agent-commerce.md`, `mcp-gateway.md`). `AGENTS.md` lists the active plans. There is no `docs/spikes/` directory yet. The issue names `docs/spikes/agent-governance-decision-assurance.md` as the accepted report location.
- `roadmap/epics/agent-governance-decision-assurance.yaml` is an `EpicDefinition`:
  - `lifecycle: proposed`, parent issue #181;
  - one phase, `discovery`;
  - one required work item, `decision-assurance-spike` (#182, owner `mctl-api`);
  - `completion.mode: allRequired`.
  - Its successCriteria already require that "spike closure alone is not evidence of delivered runtime guarantees".
- The `roadmap/scripts/validate.py` and `roadmap/tests/` checks run on manifests. This proposal does not touch any manifest, so it leaves them unaffected.

### Cross-repository anchors read for this proposal
These are pre-checks only. The implementer must re-pin and read in full (task 1).

| Repo | SHA read | Anchors confirmed |
|---|---|---|
| mctl-api | `5dd4e73d5001271b7ee3adee711b74596ad612a6` | `internal/workitems/action_approvals.go`: states pending/approved/denied/consumed; `expired` derived from `expires_at` (`effectiveState`); `IntentHash` covers `policy_version`, `artifact_hash`, `work_item_id`; `ConsumeActionApproval` is an approved-to-consumed CAS guarded by `intent_hash` (`ErrApprovalIntentMismatch`, `ErrApprovalConsumed`); `MaxApprovalTTL`; `decided_by_principal_id` / `decided_via_principal_id` columns. `internal/api/handlers_action_approvals.go`: `DecideActionApproval` refuses non-`isHumanAdmin` callers (`approval_decider_forbidden`), with comments saying "never the requester". `internal/api/handlers_approval_grant.go`: `prepareApprovalGrant` / `bindApprovalGrant` / `spendApprovalGrant`; approver taken from the grant decider (R8); grant without a digest gives `approval_content_unbound`; `devLoopApprovalPolicyVersion = "v1"`. `internal/operations/registry.go` (`mctl-agents-approve`, optional `expected_content_digest` with `contentDigestPattern`). `internal/mcp/server.go` (`mctl_trigger_approve` posts straight to `/api/v1/operations/mctl-agents-approve/execute`). `internal/audit/` (Postgres audit log, `redact.go`). `internal/evidence/`. `internal/commerce/receipt.go` (`PolicyVersion`). |
| mctl-agents | `50e703dfcf75ce25c674f1151879d6bcc0e1c239` | `orchestrator/policy_checkpoint.py` (`ActionRequest`, `Rule`, `Policy`, `Decision.policy_version`, `args_digest_of`, `decide`, `_redeem`, the closed governed action-kind set). `orchestrator/action_approvals.py`. `orchestrator/temporal/activities/proposals.py` (`read_proposal_content_digest` at a fixed commit). `orchestrator/proposal_state.py` (`PROPOSAL_DIGEST_FILES`, `content_digest_of`). `orchestrator/run_implementer.py`. `orchestrator/run_incident_responder.py` (writes proposals with `status: accepted`; its "Trust boundary" section says the implementer opens a PR "without a human reading them first"; MCP allow-list `_ALLOWED_MUTATIONS = ("resolve_incident", "acknowledge_incident")`). `orchestrator/execution_evidence.py`, `evidence_producer.py`, `commerce_gateway.py`. Tests: `tests/test_proposal_digest*.py`, `tests/test_action_approvals.py`, `tests/test_delegated_approval.py`, `tests/test_execution_evidence.py`. |
| mctl-gitops | `a521f7aec786b2524f3093821733558be4b9d1f3` (local checkout) | `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml`: validates `expected_content_digest` format; recomputes `sha256` over the proposal files; idempotent no-op on an already-`accepted` proposal, which refuses a digest mismatch only when an expected digest is supplied; writes `approval.{approved_by,approved_at,content_digest}`. `cronworkflow-mctl-agents-incidents.yaml`, `cwft-mctl-agents-implement.yaml`. |

### Observations relevant to the paths (to be verified in full by the spike)
- **P1 and P2 share one CWFT** but differ in their binding inputs. On P1 the digest comes from the grant, and mctl-api refuses an unbound grant. On P2 `expected_content_digest` is optional, so the CWFT computes and records whatever content is present at flip time. P2 therefore records a digest, but it does not bind a prior human decision to it. This is a candidate F1/F5 gap for P2 only. The spike must confirm it from the code and tests.
- **P3** (incident responder) produces `accepted` proposals with no human decision. Its governance contract (who authorised the autonomous path, what policy permits it, what the implementer checks) must be read before F10 classifies it.
- **Policy evidence**: `policy_version` exists in the approval intent hash, in mctl-agents `Decision`, and in commerce receipts. The DevLoop grant uses the constant `"v1"`. Whether policy identity/version is persisted on executions that need no approval is a D2 question.
- **Approver authority** is an `isHumanAdmin` check at decision time. Whether authority is re-evaluated at spend/execution time (F3) is a D3 question.

### Deployed state checked
- `mctl_whoami`: authenticated as `mctl-agent`, admin, team `admins`. The MCP tools are read-only in this run.
- `mctl_get_service_config(team=admins, service=mctl-api)`: returned "service not found: admins/mctl-api". mctl-api is not a catalogue tenant service. This does not mean it is not deployed.
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`: image `ghcr.io/mctlhq/mctl-api` tag `4.102.0`. The #681 E2E ran on 4.97.0.
- `platform-gitops/services/admins/mctl-agents-worker{,-exec,-implement}/values.yaml`: image tag `1.84.0` (matches the #681 E2E agents version).
- `platform-gitops/agents-state/.github/proposals/issue-182-spike-evaluate-mctl-governance-beyond-hu/`: the earlier rejected proposal (`status: proposed`). Its design recorded a "working hypothesis", which owner correction 1 forbids. This proposal supersedes it.
- Not observed: live action-approval rows, audit entries and Temporal executions. The spike reads these read-only where they materially validate a claim (task 2).

## Proposed solution

The spike PR adds **one new file**, `docs/spikes/agent-governance-decision-assurance.md`. It may also add a non-semantic link line under a "Spikes" heading in `AGENTS.md`. No code, manifest, schema or lifecycle changes are made.

Report structure:

1. **Header and non-claims.**
   - Scope; date; "spike completion is not delivered runtime assurance".
   - Links to #181, #182, #681, #91, #18, #173, #55 and #151.
2. **Evidence pins.**
   - A table with repo, SHA, read date, and the files/tests read.
   - Deployed versions and their source: a gitops path or a read-only MCTL call.
   - A blockers section, which must be empty for D1-D4 to proceed.
3. **Path inventory.**
   - P1: DevLoop grant approval.
   - P2: standalone/direct GitOps approve.
   - P3: incident-responder autonomous path.
   - P4: orchestrator policy-checkpoint actions (GitHub mutations, work-item writes, MCP tool calls), including delegated approval (`temporal/activities/delegated_approval.py`).
   - P5: Agent Commerce invocation and receipt.
   - Each path lists its entry point and its trust boundaries: caller to mctl-api, mctl-api to Argo/Temporal, worker to GitHub/gitops, and gitops to implementer.
4. **D1.** One Mermaid sequence diagram per path, drawn in the actual evaluation order.
   - Each step is annotated with its code citation (`repo@sha:path#symbol`) and tagged implemented or planned.
5. **Scope sections 1-8** of the issue: intent provenance, identity/authority, policy evidence, decision context (the 11-field minimum envelope, each field marked present/missing per path), approval integrity, end-to-end trace, reject/override/escalation, and governance observability.
   - The observability section proposes metrics that reuse #55's OTLP primitives and the mctl-api audit/usage stores.
   - It states the instrumentation limits, including that sampled traces are not durable audit.
6. **D2.** A capability matrix per path, with the 13 mandatory rows and the five-value status vocabulary. Every row has an owner, even when the status is implemented.
7. **D3.** An F1-F10 table with columns path, current behavior, desired invariant, evidence, gap and owner.
   - Evidence is an existing test name or a safe bounded reproduction: a unit test run locally against a pinned clone, or a CWFT script run in a scratch directory with fixture files. Nothing touches production.
   - F1/F2 use the closest real action kinds. Any `send_message` path not found in source is marked `unknown (not observed)`.
   - Candidate AssuranceScenarios for #151 are listed by name only.
8. **D4.** A field map from the illustrative `GovernedDecision` interface to existing contracts: `ActionApprovalRequest`, `IntentHash`/`ActionIntent`, execution evidence (`ToolCallRef`), WorkItem/execution/snapshot, commerce receipt, audit `Entry`, and principal IDs.
   - Fields with no source are marked as gaps.
   - The section decides where append-only references are needed (multiple approvals, attempts, policy evaluations, workflow steps).
   - It states that stored authority is evidence, not authorization.
9. **D5.**
   - First a gap-to-owner table.
   - Then exactly one disposition, with the reasoning that leads from D2/D3 to it.
   - Then a "Recommended roadmap action (not applied in this PR)" block holding the exact manifest delta or archive action as a fenced snippet, plus the follow-up issue drafts as text (evidence, scope, acceptance criteria, owner). None are filed.

Why this shape: the issue makes cross-repo evidence a hard gate and keeps the lifecycle change in a separate PR. A single docs file gives an owner-reviewable record without affecting the roadmap control plane (`roadmap/scripts/*`, publication). Splitting the analysis by path stops the #681 P1 proof from leaking into P2-P5 conclusions.

## Alternatives

- **Put the report under `docs/plans/`.** Dropped: plans in this repo describe active delivery work (`agent-commerce.md`). A spike's output is an assessment, and the issue names `docs/spikes/` as the accepted location.
- **Update the epic manifest in the same PR, for example to archive it or add required work items.** Dropped: owner correction 2 forbids this explicitly. Doing it would also make D5 self-executing before review.
- **Write the matrix as a machine-readable YAML/JSON artifact checked by `roadmap/scripts/validate.py`.** Dropped for the spike: no schema exists for it, and adding one is runtime/tooling scope. D4 may recommend it as a follow-up if D5 needs it.
- **Build D1-D4 from the issue text and #681 comments only.** Dropped: owner correction 3 makes source reading at pinned SHAs mandatory.

## Platform impact

- **Migrations:** none. **Backward compatibility:** unaffected; this is documentation only.
- **Roadmap control plane:** no manifest change, so `validate.py`, `ready.py`, `health.py` and publication output are unchanged. #182 stays the only required item of a `proposed` epic until the separate lifecycle PR lands.
- **Resource impact:** none at runtime. Source reading needs a shallow clone of the four repositories.
- **Risks and mitigations:**
  - *Risk: the report overstates guarantees, for example by extending #681 to P2.* Mitigation: per-path D2/D3 and mandatory evidence citations; reviewers check every "implemented" cell against a cited test.
  - *Risk: the spike is misreported as delivered assurance.* Mitigation: an explicit non-claims header, plus the existing manifest successCriteria.
  - *Risk: a reproduction causes production side effects.* Mitigation: only local tests and fixture runs; MCTL calls limited to get/list/read.
  - *Risk: the report embeds sensitive payloads.* Mitigation: cite IDs and digests, not payload bodies; reuse the `internal/audit/redact.go` conventions when quoting.
  - *Risk: the evidence goes stale as versions move (api 4.97.0 then 4.102.0).* Mitigation: pin SHAs and deployed tags with dates in the report.
