# Design: mcp-agents-tools

## Source commits

- `mctl-api:016b3c8` — feat(mcp): mctl-agents trigger tools (run / mentor-only / single-service / list)
- `mctl-api:f41590e` — feat(mcp): add mctl_trigger_implementer admin tool

## Current state of documentation

- **Existing page:** `docs/mcp/tools-reference.md` — "MCP Tools Reference"
  - Lists all pre-existing MCP tools grouped by category (tenant management, service ops,
    monitoring, etc.).
  - Has no entry for any of the five new mctl-agents tools.
  - The page is **incomplete** (gap, not stale): the tools exist in production (mctl-api 4.16.0)
    but are simply absent from the page.

## Proposed solution

Add a new **"mctl-agents pipeline controls"** section near the bottom of
`docs/mcp/tools-reference.md`, after existing admin-level sections.

The section should contain:

1. **Brief intro paragraph** — what the mctl-agents pipeline is (proactive platform R&D:
   researcher → analyst → spec-writer per service) and that all five tools are admin-only.

2. **Tool table** with columns: Tool name | Purpose | Admin-only | Returns

3. **Per-tool detail blocks** (sub-headings or definition lists) covering:
   - `mctl_trigger_agents_run` — no parameters; cost ~$10, ~15 min; returns `workflow_name`
   - `mctl_trigger_mentor_only` — no parameters; cost ~$2, ~5 min; returns `workflow_name`
   - `mctl_trigger_single_service` — parameter `service` (enum of 7 repos); cost ~$2-5,
     ~5-10 min; returns `workflow_name`
   - `mctl_list_recent_agent_runs` — no parameters; returns JSON list of up to 10 recent
     runs with fields: `workflowName`, `operation`, `mode`, `service`, `status`, `user`,
     `timestamp`, `riskLevel`, `message`
   - `mctl_trigger_implementer` — parameters `service` (optional enum), `slug` (optional
     string), `force` (optional "true"/"false"); cost ~$3/proposal, variable duration;
     returns `workflow_name`

4. **Status polling note** — after any trigger tool, use `mctl_get_workflow_status(workflow_name)`
   to poll; alternatively use `mctl_list_recent_agent_runs` for a summary view.

5. **Example code block** — a short prose + MCP call example for the most common use case
   (triggering a single-service run for `mctl-docs`).

6. **Version note** — tools available as of mctl-api 4.15.0 (`016b3c8`) and 4.16.0 (`f41590e`).
   version-status: unverified.

No changes to `.vitepress/config` sidebar/nav are needed — this is an addition to an
existing page. If the tools-reference page gains its own per-category anchors in the future,
the new section should be assigned `#mctl-agents-pipeline`.

## Alternatives

1. **New standalone page `docs/mcp/agents-pipeline.md`** — would give the topic its own URL
   and sidebar entry. Dropped because the five tools are a natural extension of the tools
   reference, not a separate concept guide. A standalone page makes sense only if the section
   grows to include workflow examples, proposal lifecycle diagrams, etc. — that is a future
   proposal.

2. **Minimal one-line stubs per tool, no detail** — faster but does not satisfy the
   acceptance criteria (cost/duration, parameters, example call). Dropped.

## Impact

- **Sidebar / nav config:** no change required.
- **Mermaid diagrams:** not required for this proposal; a future "How the agents pipeline works"
  guide could add a flow diagram.
- **Documentation versioning:** applies to mctl-api 4.15.0–4.16.0 (commits `016b3c8`,
  `f41590e`). Confirm against production version before publishing.
