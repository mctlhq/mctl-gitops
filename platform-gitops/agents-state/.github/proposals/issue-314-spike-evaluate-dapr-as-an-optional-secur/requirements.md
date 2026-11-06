# Spike: Dapr as an optional secure MCP boundary and agent execution adapter for MCTL

## Context

mctlhq/.github#314 asks whether selected Dapr capabilities measurably improve
MCTL's governed agent-to-tool security boundary (H1: Dapr service invocation
with App-ID/mTLS and ACL/middleware in front of trusted MCP backends) or its
framework-agnostic agent execution (H2: Dapr Agents as an optional executor
behind MCTL's execution contract), and whether Virtual Actors are worth more
than a design reference (H3). The hard constraint is that Dapr must never become
a second orchestration, approval, tenant-authorization or state authority. MCTL
already owns those through mctl-api (principal/tenant authz, single-use
approvals, budgets), Temporal plus Argo (DevLoop, CWFTs), Valkey Streams plus
the transactional outbox, and the bridge state machine.

The deliverable is research only. It is a decision report
`docs/spikes/dapr-mctl.md` in this repository, plus the roadmap
`SpikeDefinition` manifest and an index entry, in the same shape as the existing
spikes (`docs/spikes/mcp-gateway-g0.md`, `docs/spikes/edge-config-kv-instant.md`,
`docs/spikes/journey-intent-correlation.md`). It matters for two reasons. First,
the current service-to-service boundary is K8s NetworkPolicy only: no service
mesh or workload identity is declared in mctl-gitops, and the Temporal frontend
has no client authentication. Second, the accepted MCP gateway design
(`docs/plans/mcp-gateway.md`) already puts per-tool policy in an mctl-owned
gateway. A clear answer, including a well-founded NO_GO, prevents the platform
from drifting into Dapr without evidence.

## User stories

- AS the platform owner I WANT a source-linked current-state matrix of MCTL trust boundaries and the exact Dapr overlap SO THAT I can decide on Dapr from MCTL facts rather than from a generic feature list.
- AS a security reviewer I WANT a threat model whose every allow assertion has a paired deny test SO THAT no adoption can weaken MCTL's tenant, approval or spend controls.
- AS the agent-platform maintainer I WANT a minimal optional executor adapter contract with explicit unsupported cases SO THAT I know what Dapr Agents could not preserve (lease, fencing, cancel, evidence lineage).
- AS the operator I WANT a baseline-first benchmark plan with thresholds agreed before execution SO THAT later measurements can falsify the adoption case.
- AS the decision owner I WANT independent H1, H2 and H3 verdicts and one overall recommendation SO THAT I can accept, revise or reject each one without being bound by the agent's recommendation.

## Acceptance criteria (EARS)

- WHEN the spike report is written THE SYSTEM SHALL place it at `docs/spikes/dapr-mctl.md` with an evidence-pin table that gives a 40-hex commit for every MCTL repository read and a version/date for every Dapr document cited.
- WHEN a statement is made in the report THE SYSTEM SHALL tag it `[CODE]`, `[CONFIG]`, `[LIVE]`, `[DOC]` or `[DAPR-DOC]`, and SHALL write `unknown (not observed)` for anything not read, never "absent".
- WHEN the current-state matrix is produced THE SYSTEM SHALL list, for each MCTL boundary (MCP client to mctl-api `/mcp`, mctl-api to Temporal, Temporal workers to Argo CWFTs, agent pods to egress proxy, producers to Valkey, managed-runtime worker to mctl-telegram agent API, planned mcp-gateway to downstreams), its current control and owner, the cited file, the Dapr capability that overlaps, and a gap classification: `closed-by-existing`, `gap-dapr-could-close`, `gap-better-closed-otherwise`, or `out-of-scope`.
- WHEN H1 is evaluated THE SYSTEM SHALL state explicitly that a Dapr App-ID ACL decides on caller App-ID, HTTP verb and path, not on the MCP JSON-RPC `params.name` or arguments in the body, and SHALL name the component (MCTL gateway, or body-aware middleware/OPA) that makes per-tool decisions in each option.
- WHEN the threat model is written THE SYSTEM SHALL pair every allow case with deny tests for: cross-app caller, cross-tenant replay, revoked grant, direct endpoint bypass (sidecar skipped), unauthorized tool on an allowed App-ID, replayed request, malformed or forged tenant/identity context, sidecar outage, retry with duplicate delivery, and a compromised caller sidecar.
- WHEN the refusal-test plan is written THE SYSTEM SHALL include both mandatory proofs: (a) an MCTL approval/tenant-policy denial of a forbidden write even when Dapr App-ID invocation is permitted, and (b) a Dapr denial of an unapproved caller before the application handler runs, observed as zero handler invocations.
- WHEN H2 is evaluated THE SYSTEM SHALL provide an adapter contract sketch covering submit, status/stream, cancel, retry/idempotency, tenant and principal propagation, approval check, resource and budget caps and evidence references, and a state mapping table from MCTL execution states to Dapr Agents/workflow states, with every unmappable state listed as an unsupported case plus an abort condition.
- WHEN H3 is evaluated THE SYSTEM SHALL classify Virtual Actors as reference-only unless the report cites evidence that they preserve the bridge's atomic state transitions, and SHALL state that an actor is not an OS or process security boundary.
- WHEN the benchmark plan is written THE SYSTEM SHALL define the baseline (direct MCTL path) first, give falsifiable thresholds for p50/p95/p99 latency, sidecar CPU/memory and operability before any run, and SHALL NOT present any unmeasured number as evidence.
- WHEN the report concludes THE SYSTEM SHALL give separate verdicts for H1, H2 and H3 and one overall recommendation from `ADOPT_BOUNDARY`, `ADOPT_ADAPTER`, `ADOPT_BOTH_OPTIONAL`, `REFERENCE_ONLY`, `NO_GO`, each with its prerequisites and no-go conditions, and SHALL label it a recommendation that is not approval.
- WHEN the roadmap manifest is added THE SYSTEM SHALL write `roadmap/spikes/dapr-mctl.yaml` with `lifecycle: proposed`, those five outcomes, `github.issue` = mctlhq/.github#314, `execution.devloop: true`, `evidence.report: docs/spikes/dapr-mctl.md` and no `decision` block, and `python roadmap/scripts/validate.py` SHALL pass.
- WHEN the report is merged THE SYSTEM SHALL add a one-entry link to it under `# Spikes` in `AGENTS.md`.
- WHILE the spike is open THE SYSTEM SHALL NOT deploy Dapr, inject sidecars, write to mctl-gitops or any other repository, open implementation issues, or invoke a mutating production tool.
- IF an MCTL source repository cannot be read at a pin THEN THE SYSTEM SHALL mark the affected matrix rows `unknown (not observed)` and record the gap under Limitations, rather than inferring behaviour from plans.
- IF the evidence shows a Dapr option needs a second policy store, tool catalogue, approval decision or canonical execution state THEN THE SYSTEM SHALL record that option as `NO_GO` for that hypothesis.

## Out of scope

- Any Dapr installation, control plane, sidecar injection, component definition or traffic change in any environment, including preview. The disposable proof is designed, not run.
- Replacing or wrapping Temporal, Argo, Valkey Streams, the outbox, the bridge state machine or Vault/ExternalSecrets.
- A new public MCP edge, second tool catalogue, second approval or authorization authority, or grants to agent subprocesses.
- Implementation issues, PRs in other repositories, and edits to `docs/plans/mcp-gateway.md` or any epic manifest.
- Recording the owner's decision: the `decision` block is added only by the human owner.

## Open questions

- The issue's `Outcomes:` line names `GO/REVISE/REFERENCE_ONLY/NO_GO`, while its acceptance criteria name `ADOPT_BOUNDARY/ADOPT_ADAPTER/ADOPT_BOTH_OPTIONAL/REFERENCE_ONLY/NO_GO`. This proposal uses the acceptance-criteria set as manifest outcomes, because it is more specific and maps 1:1 to options B/C/D/E/A. Per-hypothesis verdicts use the same vocabulary restricted to the hypothesis.
- Source access: this clone contains only `mctlhq/.github` and a read-only mctl-gitops checkout. Whether the implementing run can read mctl-api, mctl-agents and mctl-telegram source at pinned commits is not known. Without it, rows for the execution contract (lease/fencing in mctl-api#366/#368), the bridge state machine and managed-runtime claim path become `unknown (not observed)`.
- Deployed mctl-api configuration (for example `TENANT_AUTHZ_MODE`, token audience enforcement after mctl-api#805) was not observed in this investigation. The report must re-check it or mark it unknown.
- Whether the owner wants the disposable experiment run later as a separate approved issue, or wants no follow-up at all. This spike only designs it and opens nothing.
- Temporal frontend client authentication is a real gap (see design). Dapr does not front Temporal gRPC, so the report will classify it `gap-better-closed-otherwise`. Whether the owner wants that recorded as a separate follow-up is a decision outside this spike.
