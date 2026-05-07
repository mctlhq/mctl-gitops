# mcp-agent-runs-cron-source: Document cron+operator merge in mctl_list_recent_agent_runs

## Context
Two commits landed in mctl-api on 2026-05-07:

- `41b6d4d` — `feat(agent-runs): include cron-driven workflows in mctl_list_recent_agent_runs`
- `b73a825` — `fix(agent-runs): normalize operator timestamp to RFC3339 string`

Together they change the behavior of the `mctl_list_recent_agent_runs` MCP tool
significantly:

1. **Before:** The tool returned only operator-initiated runs (REST POST → audit log).
   Cron-driven runs of `mctl-agents-daily`, `mctl-agents-shepherd`, and
   `mctl-agents-implement` were invisible. During incident triage this produced false
   "agent system idle" readings when the operator saw "last activity 6 days ago" while
   daily crons had fired every morning.

2. **After:** The tool merges cron-driven workflow runs (Argo Workflows labelled
   `workflows.argoproj.io/cron-workflow`) with operator runs, sorts the combined list
   by timestamp descending, and caps at 10 items. Each item now carries a `source`
   field — either `"operator"` or `"cron"` — so callers can distinguish how a run
   was triggered.

The response schema is now richer. Any AI agent or human operator calling
`mctl_list_recent_agent_runs` today will receive the new shape. The existing
`docs/mcp/tools-reference.md` documents only the pre-merge, operator-only view.

**version-status: unverified — see commits `41b6d4d`, `b73a825`. Committed
2026-05-07 but not yet confirmed in a mctl-gitops image bump as of scan time.**

## User stories
- AS a **platform admin** I WANT to see all recent agent activity (both scheduled
  cron runs and manually triggered runs) in one list SO THAT I can quickly assess
  whether the agent system is healthy without cross-referencing Argo Workflows UI.
- AS an **AI coding assistant** using the mctl MCP server I WANT the `mctl_list_recent_agent_runs`
  tool documentation to accurately describe the response schema (including the `source`
  field) SO THAT I can correctly interpret and filter the results in automation.
- AS a **developer** integrating with the mctl MCP server I WANT an example response
  showing both `"source": "cron"` and `"source": "operator"` items SO THAT I know
  what fields to expect and how to differentiate run types.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/mcp/tools-reference.md` and navigates to
  `mctl_list_recent_agent_runs` THE SYSTEM SHALL describe that the tool returns a merged
  list of both cron-driven and operator-triggered runs.
- WHEN a reader consults the tool reference THE SYSTEM SHALL explain the `source` field
  with valid values (`"operator"`, `"cron"`) and their meaning.
- WHEN a reader wants to understand the response shape THE SYSTEM SHALL provide an
  example JSON response containing at least one `"source": "cron"` item and one
  `"source": "operator"` item.
- WHILE the production deployment is unverified THE SYSTEM SHALL include a note
  referencing commits `41b6d4d` and `b73a825` and tagging the section
  "version-status: unverified".
- IF a reader wants to know the list cap and sort order THE SYSTEM SHALL state that
  the list is sorted by timestamp descending and capped at 10 items.

## Out of scope
- Documenting the internal `ListCronAgentRuns` Go interface (private implementation).
- Changes to the REST endpoint (only the MCP tool surface is documented here).
- Pagination (the tool currently caps at 10; no pagination mechanism exists).
- Documenting the `fakeExecutor` test double (internal).
