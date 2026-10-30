# Spike: evaluate AG-UI 1.0 as MCTL's canonical agent-to-user protocol (Phase A report)

## Context

mctlhq/.github#258 asks for a bounded architecture spike. The question: should
AG-UI 1.0 become the standard northbound presentation and event adapter between
user-facing applications and MCTL agent executions? MCP stays the agent-to-tools
protocol and Temporal/Argo stay the durable execution plane. The spike must end with
exactly one Phase A verdict (`ADOPT_AG_UI_ADAPTER`, `ADOPT_LIMITED_EVENT_SUBSET`,
`REJECT_KEEP_CUSTOM`) and one roadmap disposition (`KEEP_AS_AGENT_PLATFORM_FOLLOWUP`,
`CREATE_AGENT_UI_EPIC`, `NO_FOLLOWUP`). It must not authorize a new runtime, a
production UI, or a second approval, tool or authentication path.

This proposal covers the Phase A deliverables D1-D6, D8 (as a recommendation) and
the D5 experiment design. The implementer writes them into `mctlhq/.github` the same
way earlier spikes were written: a report under `docs/spikes/`, a `SpikeDefinition`
under `roadmap/spikes/`, and an index line in `AGENTS.md`. Like
`docs/spikes/mcp-gateway-g0.md`, the report pins every repository it reads and tags
every claim. Phase B (the AG-UI DevLoop Run Inspector) writes to other repositories
(`mctl-api`, `mctl-portal`, possibly `mctl-agents`). It only goes ahead after the
owner accepts a GO verdict, so this proposal does not include it.

## User stories

- AS the platform owner I WANT an evidence-backed verdict on AG-UI 1.0 SO THAT MCTL
  adopts a northbound protocol only if it fits the existing governance, identity and
  execution contracts.
- AS a governance reviewer (.github#181) I WANT the AG-UI interrupt/resume boundary
  proven against the canonical `aar_` action-approval path SO THAT a UI event can
  never grant authority or replay an approval.
- AS an operator-UI developer (mctl-portal) I WANT a concrete mapping of MCTL run,
  step, tool, approval and usage facts to AG-UI events SO THAT I know which views a
  standard client can render and which it cannot.
- AS a Phase B implementer I WANT repository-level experiment slices with named owners
  and negative tests SO THAT the experiment is bounded and removable.

## Acceptance criteria (EARS)

- WHEN the report is written THE SYSTEM SHALL pin each repository it read by 40-hex
  commit and read date, plus the AG-UI 1.0 spec/schema by tag or commit of
  `ag-ui-protocol/ag-ui`.
- WHEN a claim is made in the report THE SYSTEM SHALL tag it `[CODE]` (read at a
  pinned commit), `[DEPLOYED]` (observed through mctl tools or gitops), `[DOC]`
  (issue or plan text) or `unknown (not observed)`.
- WHEN D1 is produced THE SYSTEM SHALL list every fact in Q1 as a row
  `fact | source of truth | API/event surface | durable? | user-authoritative? | correlation id`.
  Every fact MCTL cannot observe today SHALL be recorded as "not observable". No event
  is invented for it.
- WHEN D2 is produced THE SYSTEM SHALL cover at least these MCTL concepts: execution
  start/end, workflow phase, streamed response, MCP invocation, execution state,
  role/subagent transitions, approval/human input, cancel, token usage,
  evidence/proposal refs and audit/trace refs. Each SHALL be classified exact, lossy or
  no mapping, and each SHALL state where authority stays.
- WHEN D3 analyses interrupt/resume THE SYSTEM SHALL show the path from a canonical
  approval or human-input request through an AG-UI interrupt and a resume payload to
  server-side validation in mctl-api (`DecideActionApproval`, `ConsumeActionApproval`)
  or to the human-input API. The path SHALL show that a resume payload alone carries
  no authority.
- IF a resume is stale, duplicate, from the wrong actor or for the wrong tenant THEN
  THE SYSTEM SHALL fail closed in the design. The report SHALL name the existing
  server check that refuses it, or mark the gap as a required new check.
- WHILE an execution has a consequential action pending THE SYSTEM SHALL keep its
  authorization in the governed operation and exact-action gate, never in a frontend
  tool.
- THE SYSTEM SHALL classify every AG-UI reasoning-related event as "not emitted",
  "safe summary only" or "pass-through of explicitly safe provider output". Raw private
  chain-of-thought SHALL NOT be a product requirement.
- WHEN D4 is decided THE SYSTEM SHALL compare at least three ownership shapes (adapter
  in mctl-agents behind mctl-api, adapter in mctl-api, library-only). For the shape
  chosen it SHALL define actor/tenant resolution, authorization before
  subscribe/run/resume/cancel, CORS/CSRF/session semantics, SSE reconnect/replay,
  retention bounds, backpressure, correlation and horizontal scaling.
- IF a design option requires public ingress on an mctl-agents worker THEN THE
  SYSTEM SHALL reject that option. Workers deploy today with `ingress.enabled: false`.
- THE SYSTEM SHALL state the non-overlap of AG-UI, MCP Apps, MCP and Temporal, and
  SHALL include one coexistence scenario with a single source of truth.
- THE SYSTEM SHALL define version advertisement, unknown-event handling, the schema
  source, the compatibility policy and the rules for namespaced `CUSTOM`/metadata
  fields.
- WHEN the report concludes THE SYSTEM SHALL select exactly one D6 verdict and exactly
  one D8 disposition, each with cited evidence.
- WHEN the verdict is `REJECT_KEEP_CUSTOM` THE SYSTEM SHALL omit the experiment build
  plan and record `NO_FOLLOWUP`.
- WHEN the roadmap manifest is added THE SYSTEM SHALL pass
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` and the existing
  roadmap unit tests.

## Out of scope

- Phase B implementation in any repository (mctl-api adapter, mctl-portal inspector,
  mctl-agents event emission). It is designed here and built only after the owner
  accepts GO.
- Any production change, new public endpoint, new auth boundary, new tool registry or
  new workflow engine.
- Selecting CopilotKit or any frontend framework as a runtime dependency.
- Replacing MCP, MCP Apps, Temporal/Argo, or the approval, identity or audit contracts.
- A2A.
- Creating a new roadmap epic.
- Closing #258. The owner reviews the verdict and records `decision` later.

## Open questions

- The AG-UI 1.0 event names the issue lists (subagents, interrupts/resume, usage,
  activity) must be confirmed against the pinned upstream schema. Wherever the 1.0
  schema differs from the issue's description, the report follows the schema.
- This run could not observe whether mctl-api or mctl-portal stream anything (SSE or
  websocket) for agent runs today. `mctl_get_dev_loop` and `mctl_list_agent_executions`
  were refused as outside the investigate scope, and mctl-api/mctl-portal are not
  catalogue services. The implementer must read the code at pinned commits. Until that
  read happens, "no streaming surface" is unknown, not established.
- Token-level model output streaming from the Claude Code CLI inside Argo pods is
  unknown (not observed). If it cannot be sourced, message events map to coarse step
  summaries only. That pushes the verdict toward `ADOPT_LIMITED_EVENT_SUBSET`.
- `timebox.decisionBy` is not stated in the issue. This proposal uses 2026-11-30, the
  same as other active `.github` spikes. The owner may change it.
- Owner of the spike manifest: `mctlhq/.github`, as for #195 and #222. Owner of a
  future adapter: proposed `mctl-api`, decided in D4.
