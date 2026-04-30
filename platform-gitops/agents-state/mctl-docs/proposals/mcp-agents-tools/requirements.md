# MCP Tools Reference: mctl-agents Pipeline Controls

## Context

Between 2026-04-27 and 2026-04-29, `mctl-api` shipped **five new admin-only MCP tools**
that expose the mctl-agents autonomous pipeline to any admin user connected via Claude/MCP:

- `mctl_trigger_agents_run` — full pipeline run (all service-agents + mentor digest)
- `mctl_trigger_mentor_only` — mentor-only digest run
- `mctl_trigger_single_service` — run one service-agent's researcher → analyst → spec-writer cycle
- `mctl_list_recent_agent_runs` — list the last ≤10 agent-pipeline runs from the audit log
- `mctl_trigger_implementer` — Tier 2 implementer: turn accepted proposals into pull requests

These tools were added in commits `016b3c8` (first four + REST endpoint `GET /api/v1/agent-runs`)
and `f41590e` (fifth tool), shipping in mctl-api 4.15.0 and 4.16.0 respectively.

The existing `docs/mcp/tools-reference.md` page documents the pre-existing tool set but has
no mention of these five tools. An admin user querying `tools/list` today would discover them
with no documentation to consult.

## User stories

- AS a **platform admin** I WANT to find all five mctl-agents MCP tools documented on
  docs.mctl.ai SO THAT I can learn their parameters and expected outputs without reading
  source code.
- AS a **platform admin** I WANT to understand the cost and duration of each trigger tool
  SO THAT I can make informed decisions before starting a run.
- AS a **platform admin** I WANT to know how to poll for run status after triggering
  SO THAT I can track pipeline progress without guessing.
- AS a **developer** reviewing the tool list I WANT to understand why these tools are
  admin-only SO THAT I know what permissions are required.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/mcp/tools-reference.md` THE SYSTEM SHALL show a dedicated
  section titled "mctl-agents pipeline controls" that lists all five tools.
- WHEN the section describes each tool THE SYSTEM SHALL include: tool name, short purpose,
  parameters (name / type / required / description), return value, and estimated cost/duration.
- IF a reader wants to trigger the full pipeline THEN THE SYSTEM SHALL provide a complete
  `mcp` call example using `mctl_trigger_agents_run`.
- IF a reader wants to implement accepted proposals THEN THE SYSTEM SHALL explain the
  `mctl_trigger_implementer` workflow including the optional `service`, `slug`, and `force`
  parameters.
- WHEN the section describes status polling THE SYSTEM SHALL cross-link to the
  `mctl_get_workflow_status` tool (pre-existing) and explain the `workflow_name` return value.
- WHILE version-status is unverified (no mcp__mctl__* confirmation available) THE SYSTEM
  SHALL tag the section with source commit SHAs so a reviewer can verify against production.

## Out of scope

- Documentation of the Argo Workflows ClusterWorkflowTemplate internals.
- Guide on how to write or review proposals (that belongs in a separate how-to guide).
- Non-admin access to the tools (they are gated to admin group membership; no user-level
  equivalent exists).
- Localisation / i18n.
