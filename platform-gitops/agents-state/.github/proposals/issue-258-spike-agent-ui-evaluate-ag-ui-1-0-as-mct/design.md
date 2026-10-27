# Design: issue-258-spike-agent-ui-evaluate-ag-ui-1-0-as-mct

## Current state

`mctlhq/.github` (clone head `ad7408b`) is the governance and roadmap repository. It
holds no runtime code for agents. The relevant parts are below.

- Spike conventions. `docs/spikes/mcp-gateway-g0.md` and
  `docs/spikes/agent-governance-decision-assurance.md` set the report format: a
  non-claims header, a table of evidence pins (repository, 40-hex commit, read date,
  what was read), per-claim evidence tags (`[REF]`, `[CODE]`, `[DOC]`,
  `unknown (not observed)`) and numbered deliverables ending in a verdict. `AGENTS.md`
  indexes each spike under `# Spikes`.
- Spike manifests. `roadmap/spikes/*.yaml` are `kind: SpikeDefinition`
  (`roadmap/schemas/spike-definition.schema.json`). `lifecycle: active` requires
  `timebox.decisionBy`. `decision` is allowed only when `lifecycle: decided`.
  `evidence.report` is a repository-relative path. Validation:
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes`, tests in
  `roadmap/tests/test_validate_spike.py`. `roadmap/spikes/mcp-gateway-g0.yaml` is the
  closest precedent (owner `mctlhq/.github`, `execution.devloop: true`). No manifest
  binds #258 yet (`grep -rn 258 roadmap/` finds nothing).
- Related epics. `roadmap/epics/agent-platform.yaml` (#18, `lifecycle: completed`,
  owner mctl-agents) owns the rule of no parallel runtime and includes
  `capability-discovery` (mctl-agents#242). `roadmap/epics/human-input.yaml` (#42,
  completed) defines durable clarification that is "not approval". Its API slice is
  mctl-api#261. `roadmap/epics/agent-governance-decision-assurance.yaml` (#181) owns
  the governance chain.
- Approval path as already audited. `docs/spikes/agent-governance-decision-assurance.md`
  §3.1 (pins `api@57864b5`, `agents@50e703d`) documents the canonical P1 DevLoop
  approval:
  1. `delegated_approval.py#request_devloop_approval` creates an `aar_` grant with
     `artifact_hash`.
  2. `handlers_action_approvals.go#DecideActionApproval` is gated by `#isHumanAdmin`
     and refuses self-decision.
  3. `handlers_approval_grant.go#prepareApprovalGrant` refuses a body-supplied
     approver or digest.
  4. `workitems#ConsumeActionApproval` is a single-use
     `UPDATE ... WHERE state='approved' AND intent_hash=$2 AND expires_at > $3`.
  5. The CWFT recomputes the digest before any edit.

  Q3 is built on this path. A resume becomes a decision on an existing `aar_`, and a
  replay hits the single-use consume.
- Event precedent. `events/README.md` (envelope `mctl.events/v1`) already sets the
  MCTL rule "the event is disposable; the source is canonical". Envelopes carry
  references, never content, and are capped at 4096 bytes. `correlation_id` is carried
  through every stage, with at-least-once delivery and dedupe by `id`. An AG-UI
  adapter should inherit that rule: AG-UI events are a projection, and the client
  re-reads canonical state on reconnect.
- Northbound API surface visible from this run. The mctl MCP tool descriptions expose
  these read/control endpoints (`[DOC]`, from the tool contract, not code):
  - `GET /api/v1/agents/dev-loop/{workflow_id}`: Temporal status only, explicitly
    "does not distinguish which step".
  - `POST .../dev-loop/{id}/approve`: human admins only, service credentials refused.
  - `POST .../dev-loop/{id}/abandon`.
  - Agent executions (`we_`), WorkItems (`wi_`, `state_version`), sealed
    ContextSnapshots (`cs_`) and execution requests (`xr_`).
  - The usage ledger: `GET /api/v1/usage/summary`, grouped by `devloop_stage`.
  - Lifecycle ownership events, workflow step logs from the archive, and incident
    `trace_id`.

  Every one of these is request/response. No streaming or subscription endpoint is
  visible in that contract.

Deployed state checked:

- `mctl_list_services(team=admins)`: the agent runtime is three Temporal workers
  (`mctl-agents-worker`, `-exec`, `-implement`), image
  `ghcr.io/mctlhq/mctl-agents:1.105.1`, all Synced, with no host. `mctl-portal` and
  `mctl-api` are not catalogue services in `admins`, so their deployed config was not
  observed.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: `ingress.enabled:
  false` (line 41), `--role control`,
  `TEMPORAL_ADDRESS: temporal-frontend.temporal.svc.cluster.local:7233`,
  `TEMPORAL_NAMESPACE: mctl-agents`. `-exec` and `-implement` are the same with roles
  `execution` and `implementation`. This confirms that mctl-agents has no public
  ingress today.
- `mctl_get_dev_loop(dev-loop-mctlhq-.github-258)` and
  `mctl_list_agent_executions(workflow_id=...)`: both refused with "outside the
  investigate scope of this agent run". Nothing is known about live execution records
  from this run. This is a gap, not an absence.
- Source code of mctl-api, mctl-agents and mctl-portal was not readable from this
  run, apart from the citations already pinned in the governance spike. Task 1 pins
  and reads it.

## Proposed solution

Deliver Phase A as one report plus one manifest in `mctlhq/.github`. Do not build
Phase B in this proposal.

### Files

1. `docs/spikes/agent-ui-ag-ui.md`: the report, in the `mcp-gateway-g0.md` style,
   with these sections:
   - Header and non-claims: no production change, AG-UI is not authority, Phase B is
     not started.
   - Evidence pins: mctl-api, mctl-agents, mctl-portal, mctl-gitops and
     `ag-ui-protocol/ag-ui` at the 1.0 tag commit.
   - **D1 inventory**: one row per Q1 fact. The minimum code to read (pinned):
     - mctl-api: `internal/api/router.go` (routes under `/api/v1/agents/`, executions,
       work-items, usage, human-input), `handlers_action_approvals.go` and any
       SSE/stream handler, if one exists. Search for `text/event-stream` and `Flusher`.
     - mctl-agents: `orchestrator/temporal/workflows/dev_loop.py` (signals, queries,
       phase fields such as `_canonical_pending_phase`), the activities that record
       executions and usage, and how the Claude CLI output is captured in Argo pods.
     - mctl-portal: plugins that render DevLoop or proposals, and their transport
       (polling or streaming).
     - Temporal: queries and signals defined on `DevLoopWorkflow`.

     Each fact is tagged durable / user-authoritative / correlation id (`we_`, `wi_`,
     `aar_`, `xr_`, `cs_`, Temporal workflow and run id, Argo workflow name,
     `trace_id`). Facts with no observable source are recorded as such.
   - **D2 mapping matrix**: the issue's table, filled in. Expected shape, to be
     confirmed by D1 and the pinned schema:
     - `RUN_STARTED`/`RUN_FINISHED`/`RUN_ERROR` map exactly to the `we_` execution
       lifecycle.
     - `STEP_*` maps lossily to DevLoop stages (investigate, approve, implement,
       shepherd), sourced from records rather than from live Temporal state.
     - `TOOL_CALL_*` maps exactly for policy-checkpointed MCP calls that are already
       recorded, carrying the server-qualified capability name from mctl-agents#242.
       `TOOL_CALL_ARGS` carries no argument bodies, only a digest or reference.
     - `STATE_SNAPSHOT`/`STATE_DELTA` carry a bounded, reference-only projection.
     - Subagents: role transitions map to `SUBAGENT_*` only where a real execution
       boundary exists. Otherwise they become step metadata.
     - The interrupt maps to `aar_` or a human-input request.
     - Cancel maps to the existing abandon/cancel API and ends as
       `RUN_FINISHED`/`RUN_ERROR` with the recorded outcome.
     - Usage maps from the ledger. Costs keep three distinct fields and are never
       summed.
     - Proposal, evidence, audit and trace references go into namespaced metadata.
     - Text message streaming: exact only if D1 finds a token stream. Otherwise there
       is no mapping and it degrades to step summaries.
   - **D3 threat and governance boundary**: a sequence diagram of interrupt to resume
     to `DecideActionApproval`, then a refusal table covering:
     - a stale `state_version` or digest;
     - a duplicate (consume is single-use);
     - the wrong actor (`isHumanAdmin`, self-decision refusal);
     - the wrong tenant (the principal's tenant authorization);
     - an edited action (an edit supersedes the pending grant and needs a new
       decision, as the `mctl_approve_dev_loop` contract already states);
     - a reconnect replay (resume is idempotent on the `aar_` id and the consume
       refuses a second spend);
     - an injected frontend event (the adapter accepts only a closed resume schema;
       anything else is refused).

     It also covers prompt or tool-output injection (output is data, rendered
     escaped, and never parsed into control) and the reasoning policy:
     `REASONING_*` is not emitted, only step-status summaries.
   - **D4 ownership**: compare the three shapes from Q6. Recommended: the adapter in
     **mctl-api**. mctl-api already owns identity, tenant authorization, approvals and
     the execution read model. The workers have no ingress and must not get one. The
     adapter translates canonical records into AG-UI over SSE. It is authenticated by
     the existing mctl-api session or bearer, with no new cookie scope; CSRF is
     covered by bearer-only or the existing portal session's protections. Event ids
     are derived from the canonical record (execution id plus sequence), so
     `Last-Event-ID` resumes from canonical records rather than from an adapter
     buffer. History is bounded to N events or KB per run, then a fresh
     `STATE_SNAPSHOT`. A slow consumer is dropped and reconnects to a snapshot. The
     adapter is stateless and can scale horizontally because state lives in Postgres
     or Temporal. The schema owner is `mctlhq/.github` (the pinned version file). The
     client owner is mctl-portal.
   - **D5 experiment design**: the AG-UI DevLoop Run Inspector, as slices.
     - mctl-api: an SSE endpoint, read-only, plus a resume endpoint that only
       forwards to the existing decision handler.
     - mctl-portal: a minimal operator view using the plain `@ag-ui/client`, with no
       CopilotKit unless the measured effort justifies it.
     - mctl-agents: no change, unless D1 shows that a needed fact is not recorded
       anywhere.
     - The fixture is an owner-controlled test issue on a throwaway repository.
     - The ten required proofs and the measurement list from the issue, each with a
       named test.
   - Q8 non-overlap: one scenario. An `mctl_get_service_logs` MCP result is rendered as
     a `TOOL_CALL_RESULT` reference. Its MCP App UI, if any, stays in the MCP host. The
     single source is the MCP result recorded by the policy checkpoint.
   - Q9 versioning: pin `1.0.x`. Advertise the version in run metadata and an HTTP
     header. Unknown event types and fields are ignored by the client and never
     emitted by the server. Generate types from the upstream schema at the pinned
     commit. MCTL custom data is allowed only under a documented `mctl.*` namespace
     listed in the report, closed, with a cap on field count. Each field is a
     reference, never a control.
   - **D6 verdict and D8 disposition**, with evidence.
2. `roadmap/spikes/agent-ui-ag-ui.yaml`:
   - `kind: SpikeDefinition`, `name: agent-ui-ag-ui`, `owner: mctlhq/.github`;
   - `lifecycle: active`, `timebox.decisionBy: "2026-11-30"`;
   - `github.issue: mctlhq/.github#258`;
   - outcomes `ADOPT_AG_UI_ADAPTER`, `ADOPT_LIMITED_EVENT_SUBSET`,
     `REJECT_KEEP_CUSTOM`;
   - `execution.devloop: true`, `evidence.report: docs/spikes/agent-ui-ag-ui.md`;
   - no `epic` (Agent Platform is completed, and #258 is not a work item there) and no
     `decision`, which the owner adds later.
3. `AGENTS.md`: one bullet under `# Spikes`, in the existing style.

### Verdict guidance

The verdict is decided from D1-D4 evidence, not in advance. The report states this
conditional explicitly:

- **`ADOPT_AG_UI_ADAPTER`** if D1 finds that MCTL records run, step, tool, usage and
  approval facts at event granularity, and that a token or message stream can be
  sourced.
- **`ADOPT_LIMITED_EVENT_SUBSET`** if those facts exist only as coarse records with
  no live message stream. That would match what is visible today: request/response
  APIs, a status-only `GET dev-loop`, and no observed stream.
- **`REJECT_KEEP_CUSTOM`** if the interrupt/resume or reconnect semantics cannot be
  made to fail closed without a second authority.

The D8 default is `KEEP_AS_AGENT_PLATFORM_FOLLOWUP` for either adopt verdict and
`NO_FOLLOWUP` for reject. `CREATE_AGENT_UI_EPIC` is never chosen from Phase A alone.

## Alternatives

- **Write the report only in the issue comment thread.** Dropped: earlier spikes
  (#195, #222, #209) keep the report and manifest in Git, so they get validator
  coverage and a stable `evidence.report` path for the owner's later `decision`.
- **Build Phase B directly (a thin adapter plus a portal view) and report from it.**
  Dropped: the issue requires Phase A first and forbids building the experiment if the
  verdict is reject. Phase B also writes to repositories this DevLoop does not target.
- **Bind the spike under an epic (agent-platform or a new agent-ui epic).** Dropped:
  agent-platform is `completed`, and the issue forbids a new epic before evidence.
  The manifest stays unbound, and D8 decides.

## Platform impact

- Migrations: none. Two new files and one line in `AGENTS.md`. No runtime,
  deployment, API or schema change in any service.
- Backward compatibility: the new manifest must keep `validate.py` green, including
  unique spike names and issue bindings (no existing spike binds #258).
- Resources: none at runtime. Reading pinned clones of mctl-api, mctl-agents and
  mctl-portal is the main cost.
- Risk: the report asserts a streaming or event fact it did not observe. Mitigation:
  mandatory evidence tags, and "unknown (not observed)" is never read as "absent".
- Risk: the AG-UI 1.0 event names differ from the issue text. Mitigation: pin the
  upstream schema commit and follow the schema.
- Risk: the reader treats the report as authorization for Phase B. Mitigation: a
  non-claims header, plus `lifecycle: active` with no `decision` until the owner
  decides.
- Risk: the reader takes the namespaced `mctl.*` metadata as a parallel protocol.
  Mitigation: a closed list in the report, references only, and each field is
  justified against a D1 row.
