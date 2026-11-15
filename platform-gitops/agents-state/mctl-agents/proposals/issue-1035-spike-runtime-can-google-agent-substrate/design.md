# Design: issue-1035-spike-runtime-can-google-agent-substrate

## Current state

This proposal changes no runtime. It delivers one research report, the same kind as the existing spikes. The relevant current state:

**Spike convention in this repo.** Each research spike lands as `docs/spikes/<n>-<slug>.md`, optionally with a `docs/spikes/<n>/` evidence directory, and a report-guard test `tests/test_spike_<n>_report.py`. Examples:
- `docs/spikes/881-pod-sandbox-runtime.md` has a single `STATUS:` line, a feasibility matrix with `measured|infeasible-no-kvm|not-exercised`, a threat-to-control map, a scorecard, and section 8 Decision with the 2026-10-29 owner decision not to install `runsc`.
- `tests/test_spike_881_report.py` parses the tables through `_rows(heading)` and asserts the token set, row shape and non-empty evidence.
- `docs/spikes/757-duet-sessions.md` has a "D8 ownership map" and the `AttentionDecision v1` boundary that never grants approval.
- `docs/spikes/746-portable-runtime.md` shows the duplicate-check and GO-checklist pattern.

Phase B harnesses live under `experiments/` (for example `experiments/sandbox-runtime-881/`) and are dispatched by `.github/workflows/spike-881-sandbox.yml` on GitHub-hosted runners with single-node k3s. No production node is involved.

**MCTL state/identity owners a hypothetical Actor would have to map onto (read in the clone):**
- DevLoop durable work: Temporal `DevLoopWorkflow` on the queues split by `docs/adr/008-worker-queue-split-and-capacity.md` (`orchestrator/temporal/constants.py`, `orchestrator/temporal/workflows/`). Steps execute as Argo CWFT pods with `activeDeadlineSeconds=7200` (cited in `orchestrator/temporal/constants.py`). Each pod starts cold and reconstructs context from the repo and gitops.
- Execution correlation and context: `docs/adr/009-context-snapshot-contract.md` (`orchestrator/context_snapshot.py`) and `docs/adr/011-work-item-resume-contract.md` (`orchestrator/work_context/`). A resume seals a new immutable ContextSnapshot, so durable, reconstructable state already exists at the logical level.
- Ownership and fencing: `docs/adr/010-lifecycle-ownership-contract.md`, implemented in `orchestrator/lifecycle/` (`claim.py`, `contract.py`, `reconciler.py`). Epochs, the dead/stuck distinction and handoff live here. Any actor placement or restore fencing would duplicate this layer.
- Execution identity and budgets: `docs/adr/011-execution-identity-contract.md` (`orchestrator/execution_identity.py`, `orchestrator/run_token.py`) and `docs/adr/011-execution-budget-contract.md` (`orchestrator/exec_budget.py`).
- Policy and approval: `docs/adr/014-policy-checkpoint.md` (`orchestrator/policy_checkpoint.py`, `orchestrator/action_approvals.py`).
- Isolation precedent: `docs/spikes/807-agent-isolation-k8s.md`, `docs/spikes/852-sandbox-isolation-delta.md`, `docs/spikes/881-pod-sandbox-runtime.md`. Agent pods run on hardened runc, and no RuntimeClass exists.

**Deployed state checked:**
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: image `ghcr.io/mctlhq/mctl-agents:1.117.0`, `replicaCount: 1`, requests 50m/320Mi, limits 500m/576Mi. This is the Temporal worker. Work runs in Argo pods, not here.
- `services/labs/agent-worker-managed-preview/values.yaml`: `AGENT_WORKER_CONCURRENCY: "1"`, `AGENT_MAX_BUDGET_USD: "0.25"`, `AGENT_MAX_TURNS: "12"`, limits 500m/256Mi, a claim-only `aud=agent-pool` pool token. This is the #1088 managed pool, a bounded cold worker with a budget ceiling.
- `services/labs/agent-worker-preview/values.yaml`: `replicaCount: 0` at HEAD, `AGENT_WORKER_CONCURRENCY: "2"`. An in-file comment says it ran with 1 replica from 2026-07-31; the current value is 0. This is the #760 cold `claude -p` plus database context path.
- `services/labs/claude-remote/values.yaml`: image `mctl-claude-remote:0.21.1`, `replicaCount: 0` at HEAD, limits 1500m/2048Mi, and an R2 object-storage endpoint. The operator session resumes the transcript on every relaunch (`CLAUDE_CODE_RESUME_*_THRESHOLD`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW: "140000"`, managed session rotation in image 0.9.0+) and wakes on Valkey events (mctlhq/.github#87). This is the only observed path that keeps per-session state across restarts, and it does so with a file/transcript resume plus object storage, not process-memory snapshots.
- `services/labs/mctl-telegram/values.yaml`: `mctl-telegram:0.130.0`. Its only "bridge" references are the bot-start bridge token, which is unrelated to mctl-bridge.
- `grep -ri "runtimeClass|gvisor|kvm"` over `services/` returned nothing. This is consistent with #881 (no RuntimeClass).
- mctl-bridge: no `services/*/mctl-bridge` directory exists in the available checkout. Its deployment could not be observed. That is a gap, not evidence of absence (see Open questions).
- Not available to this run: the CWFT templates (`cwft-mctl-agents-*.yaml` live outside `services/`/`tenants/`), node kernel/containerd versions, `/dev/kvm` on workers, and the upstream Substrate repository (not fetched). All of these are recorded as `unknown`.

## Proposed solution

Deliver Phase A as a read-only, test-guarded research report. Phase B is specified but gated.

### Artifacts (all additive, docs plus one test)

1. `docs/spikes/1035-agent-substrate.md`, with sections:
   1. **Source and limits.** Pinned upstream tag/commit SHA, license, install requirements, supported runtimes, and whether snapshot/restore requires gVisor `runsc` checkpoint or KVM. Also API maturity (alpha/beta, CRD versions) and the GKE-only features versus generic k8s. Vendor figures (<500ms resume, 10x density, 500+ activations/s) are recorded only as `vendor-claim`.
   2. **Duplicate/ownership map.** Rows for #760, #757, #885, mctl-telegram#1088, #881/#883, mctl-gitops#2438 and mctl-bridge, each with current HEAD/state verified at write time and its relation to Substrate.
   3. **Identity and state map.** Columns `mctl_identity | owner (file/ADR) | durability (canonical|reconstructable|ephemeral) | hypothetical_actor_mapping | must_stay_in_mctl`. It covers conversation ID, `agent_jobs` job ID plus job token, WorkItem ID and ContextSnapshot, Temporal workflow ID, Argo workflow name, ADR-010 claim epoch, claude-remote session/transcript, Bridge slot, and approval ref.
   4. **Capability gap matrix.** Columns `id | substrate_capability | mctl_equivalent | status | evidence`, with status in {`covered`,`gap`,`not-applicable`,`unknown`}. Rows include C1 cold start, C2 warm start, C3 idle suspension, C4 event wakeup (covered by #87 Valkey Channel / #757), C5 placement and affinity (#885), C6 cross-worker restore (ADR 009/011 reconstruct), C7 crash recovery (Temporal/ADR 010), C8 cancellation, C9 version/image upgrade (agent registry/ADR 007), C10 per-session serialization (#760 claim-time coalescing), C11 fencing (ADR 010 epochs), and C12 process-memory snapshot.
   5. **Workload scorecard.** One row each for W1 Telegram managed, W2 Bridge/claude-remote/Codex coding sessions, and W3 DevLoop jobs. Columns `in_process_state_useful (yes|no|unknown) | current_reconstruction_cost | substrate_benefit_hypothesis | prerequisites | phase_b_feasibility | evidence`. Feasibility is in {`FEASIBLE_DISPOSABLE`,`NOT_FEASIBLE_ON_CURRENT_HOSTS`,`NOT_WORTH_TESTING`}. Metrics (p50/p95 wake-to-ready, RSS idle/active, density, snapshot size, cost) stay `unknown` unless a linked MCTL-controlled run measured them.
   6. **Tenancy and governance invariants.** G1 to G8: no cross-tenant routing, credentials never in snapshots, a single writer per session, stale placement fenced, aborted/pending actions never replayed as approved, job-token/tool scopes exact, budget ceilings enforced by `exec_budget`, and auditable evidence (ADR 018). For each, state how an adapter would preserve it or why it cannot.
   7. **Adapter boundary.** Written as `MCTL execution/session identity -> governed lifecycle request -> Substrate Actor/Worker`. MCTL stays authority for identity, approvals, job state, quotas/budgets and evidence. The Actor is a disposable cache of execution state, keyed by an MCTL-issued identity. Restore is only an optimization; on any restore failure the system falls back to the current cold reconstruct path.
   8. **Phase B plan (gated, not executed).** Fixture, A/B arms, metrics, negative cases (A/B tenant crossing, concurrent wake, stale fence, crash mid-checkpoint, no approval replay, no credential in snapshot), and the environment constraint (GitHub-hosted runner, no MCTL tokens or data). It also names the exact approval needed.
   9. **Decision.** Exactly one `STATUS:` token, the rationale, the stop conditions, the rollback concept, and the smallest next step.
2. `tests/test_spike_1035_report.py`, modeled on `tests/test_spike_881_report.py` (`_rows(heading)` parser). It asserts:
   - a single STATUS line in {`DRAFT`,`REUSE_CURRENT_RUNTIME`,`ADOPT_SUBSTRATE_ADAPTER`,`DEFER`}
   - valid gap-matrix statuses, with non-empty evidence on every row and citations on `covered` rows
   - exactly W1 to W3 with valid feasibility tokens
   - no `measured`/numeric metric cell without a run link
   - a revisit trigger and owner when the status is `DEFER`
   - exactly one named workload plus a run link when the status is `ADOPT_SUBSTRATE_ADAPTER`
   - G1 to G8 all present.

### Expected reasoning (to be confirmed by evidence, not assumed)

- W3 DevLoop: each step is a fresh Argo pod with a 2h deadline, and its context is rebuilt from git/gitops. The useful in-process state between steps is probably none, so the likely result is `NOT_WORTH_TESTING`.
- W1 Telegram: #760 deliberately uses cold `claude -p` plus database context. Substrate would need a measured, material win to reopen it, and the bounded worker (`AGENT_WORKER_CONCURRENCY` 1-2) is already small.
- W2 coding sessions: the only plausible beneficiary, since a long-lived CLI process and checkout exist. But claude-remote already restores from a transcript plus object storage. A process-memory restore that depends on `runsc` would hit the 2026-10-29 owner rejection, giving `NOT_FEASIBLE_ON_CURRENT_HOSTS` in-cluster.
- If Phase B stays unapproved or infeasible, the outcome is `REUSE_CURRENT_RUNTIME`, or `DEFER` with a trigger. The trigger would be "owner supersedes the runsc decision, or MCTL acquires KVM/GKE capacity, and a W2 restore benchmark becomes feasible".

## Alternatives

- **Build a disposable Substrate prototype immediately (Phase A plus B together).** Dropped. The issue requires a separate owner gate before any environment mutation, and #881 shows prerequisites can make the benchmark moot. Discovery first avoids spending on an infeasible run.
- **Architecture-only note in the issue comment, with no repo artifact or test.** Dropped. Every prior runtime spike (#746, #757, #881) is committed and test-guarded so the verdict and its `unknown` labels cannot silently drift. The issue also asks for reproducible evidence links.
- **Prototype an adapter module under `orchestrator/` behind a flag.** Dropped. It violates the no-new-control-plane and no-production-code invariants, and it presumes an `ADOPT` outcome.

## Platform impact

- Migrations: none. Backward compatibility: unaffected. The change adds one Markdown file, an optional evidence directory and one pytest file. The test runs in the existing suite with no new dependency.
- Resource impact: none in the cluster. No workflow dispatch, no new infrastructure, no secrets.
- Risks and mitigations:
  - Vendor claims presented as results. Mitigation: the test rejects numeric metric cells without a run link, and the `vendor-claim` label is mandatory.
  - Reopening #760 by stealth. Mitigation: the ownership map row for #760 must state the "materially better measured result" bar, and W1 cannot be `ADOPT` without a linked run.
  - Upstream drift. Mitigation: pin a commit SHA and record the access date.
  - Unobservable Bridge/node facts. Mitigation: record them as `unknown`, never `absent`.
