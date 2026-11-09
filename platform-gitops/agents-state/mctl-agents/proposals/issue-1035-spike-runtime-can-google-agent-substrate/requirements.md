# Spike #1035: can Google Agent Substrate improve MCTL session lifecycle without replacing its control plane?

## Context

Issue mctlhq/mctl-agents#1035 asks a comparative research question. Could Google Agent Substrate (Actor/ActorTemplate, WorkerPool, request parking, snapshot/restore) improve the measured lifecycle, recovery, density or cost of MCTL's existing agent execution paths through an optional adapter? It must not become a second source of truth for execution, authorization, approval, tenancy or durable work. The three paths are (a) Telegram managed conversations (`agent-worker`, `agent_jobs`, cold `claude -p` plus database context), (b) long-lived Bridge/claude-remote/Codex coding sessions, and (c) short-lived DevLoop investigator/implementer jobs (Temporal plus Argo CWFT pods). The spike must end with exactly one outcome token: `REUSE_CURRENT_RUNTIME`, `ADOPT_SUBSTRATE_ADAPTER` or `DEFER`.

Earlier decisions bind this spike. #760 chose `REUSE_CURRENT_RUNTIME_WITH_SESSION_ROUTER` for the conversation plane. #757 chose `EXTEND_DEVLOOP_SESSION` (attention routing). #881/#883 reached a conditional `ADOPT_GVISOR`, but the owner decided on 2026-10-29 not to install `runsc` on MCTL workers, and no KVM host exists. #885, mctl-telegram#1088 and mctl-gitops#2438 are still open. This proposal covers Phase A only: a read-only discovery report committed to the repo in the same shape as the existing spike reports (`docs/spikes/881-pod-sandbox-runtime.md`, `docs/spikes/757-duet-sessions.md`), plus a report-guard test. Phase B, the disposable experiment, is described as a gated plan and is not executed.

## User stories

- AS the platform owner I WANT a pinned, evidence-based comparison of Agent Substrate against the current runtimes SO THAT I can decide whether any workload justifies a separately approved adapter.
- AS a reviewer of #760/#757/#881 I WANT every Substrate capability already handled by MCTL marked `covered` with its owning issue or commit SO THAT settled decisions are not reopened without a materially better measured result.
- AS a security reviewer I WANT the adapter boundary and the tenancy and governance invariants written down explicitly SO THAT an actor lifecycle never grants approval, routes across tenants or replays an aborted action.
- AS an operator I WANT a per-workload Phase B feasibility verdict on current k3s/containerd/Hetzner hosts SO THAT infeasible prerequisites (runsc, KVM, GKE-only features) are recorded and not worked around.

## Acceptance criteria (EARS)

- WHEN the report is written THE SYSTEM SHALL pin the upstream `agent-substrate/substrate` tag or commit SHA, license, installation requirements, supported runtimes (including whether gVisor/`runsc` or KVM is mandatory for snapshot/restore) and API maturity, each with a source link to code or docs, not only the announcement.
- WHEN the report is written THE SYSTEM SHALL contain an ownership/identity map that relates each MCTL identity (Telegram conversation ID, `agent_jobs` job ID, WorkItem/Temporal workflow ID, Argo workflow name, Bridge/claude-remote slot identity, approval refs) to a hypothetical Actor ID. Each row SHALL say whether the state is canonical/durable in MCTL or ephemeral execution state.
- WHEN the report is written THE SYSTEM SHALL contain a capability gap matrix whose every row has exactly one status in {`covered`, `gap`, `not-applicable`, `unknown`}. A `covered` row SHALL cite the owning issue, ADR, file or commit.
- WHEN the report is written THE SYSTEM SHALL score the three workloads (Telegram managed, Bridge/coding sessions, DevLoop jobs) independently, each with its own Phase B feasibility token from {`FEASIBLE_DISPOSABLE`, `NOT_FEASIBLE_ON_CURRENT_HOSTS`, `NOT_WORTH_TESTING`}.
- WHEN a performance, cost, density or security value has not been measured in an MCTL-controlled run THE SYSTEM SHALL label it `unknown` or `vendor-claim`, and SHALL NOT present it as a result.
- WHEN the report is written THE SYSTEM SHALL contain exactly one line `STATUS: <token>` with a token from {`DRAFT`, `REUSE_CURRENT_RUNTIME`, `ADOPT_SUBSTRATE_ADAPTER`, `DEFER`}.
- IF the outcome is `DEFER` THEN THE SYSTEM SHALL record an explicit revisit trigger and a named owner role.
- IF the outcome is `ADOPT_SUBSTRATE_ADAPTER` THEN THE SYSTEM SHALL name exactly one workload, link a reproducible measured run, and state that the outcome is a recommendation that needs a separately approved implementation issue.
- IF a Substrate prerequisite requires `runsc` on MCTL workers, KVM, GKE-only features, new paid infrastructure or cluster privilege changes THEN THE SYSTEM SHALL record `NOT_FEASIBLE_ON_CURRENT_HOSTS` for the affected workload and SHALL NOT weaken any guard to make a test possible.
- WHILE this spike is open THE SYSTEM SHALL NOT change production clusters, RuntimeClass, node pools, Bridge slots, managed workers, feature flags, secrets, deployments or billing, and SHALL NOT add runtime code under `orchestrator/`.
- WHILE an adapter boundary is described THE SYSTEM SHALL keep MCTL authoritative for identity, approvals, job state, quotas/budgets and evidence. The boundary SHALL be written as `MCTL execution/session identity -> governed lifecycle request -> Substrate Actor/Worker`, and actor lifecycle events SHALL NOT approve a tool call or decide owner authority.
- WHEN the report-guard test runs THE SYSTEM SHALL fail if the STATUS token is invalid, a matrix row has an invalid status or no evidence, a workload lacks a feasibility token, or a `measured` cell lacks a run link.

## Out of scope

- Executing Phase B. Any disposable environment, Substrate install or benchmark needs a separate owner approval, recorded on #1035 or a child issue.
- Installing `runsc`, adding a RuntimeClass, KVM hosts, GKE clusters or any paid infrastructure.
- Replacing or changing Temporal, Argo, `agent_jobs`, WorkItem, ADR 010 lifecycle ownership, policy/approval/budget, or the tenancy model.
- Reopening #760 without a representative, measured and materially better result.
- Folding the mctl-telegram#1088 managed pool into a new runtime.
- Creating implementation issues for technology parity.

## Open questions

- mctl-bridge does not appear under `platform-gitops/services/` in the gitops checkout available to this run. Its deployed slot lifecycle, pause/resume and fencing could not be observed. The report must read the mctl-bridge repository HEAD directly, or record the gap as `unknown`.
- The upstream Substrate repository was not fetched during investigation, so its runtime prerequisites are unverified. The working hypothesis, to be confirmed in Phase A, is that process/filesystem snapshot-restore depends on gVisor checkpoint/restore. Under the 2026-10-29 owner decision, that would make every in-cluster workload `NOT_FEASIBLE_ON_CURRENT_HOSTS`.
- It is not decided where Phase B could run without production nodes, tokens or paid/KVM provisioning. A GitHub-hosted runner with single-node k3s, as used by #881 (`.github/workflows/spike-881-sandbox.yml`), is the assumed candidate. Whether it is acceptable is an owner decision.
- Which owner role holds a `DEFER` revisit trigger? Assumed: the mctl-agents runtime owner who decided #881.
