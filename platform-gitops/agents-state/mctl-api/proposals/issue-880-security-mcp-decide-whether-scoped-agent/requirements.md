# Scoped agent run tokens may read only their own WorkItem's intents (decision for mctl-api#880)

## Context
mctl-api#868 added `mctl_list_work_item_intents` (`internal/mcp/workitems.go`,
`toolListWorkItemIntents`). Scoped agent run tokens choose MCP tools with
`auth.IsReadTool` (`internal/auth/agent_scope.go`), which admits every
`list_` tool, so the `investigate` scope admits this tool. The issue asks the
owner to choose between accepting that (option 1) and excluding the tool from
agent scopes (option 2). Raw intents are text written by people. They are
more sensitive than state metadata.

The code shows that the risk is narrower than the issue suggests. The MCP tool
sends `GET /api/v1/work-items/{id}/intents` with the caller's own token. The
REST scope gate (`internal/api/agent_scope_gate.go`) checks that request
against the `investigate` scope. That scope admits work-item reads only through
a `BindWorkItem` route, `^/api/v1/work-items/([^/]+)(/.*)?$`, so a scoped run
can read only the intents of the WorkItem it was minted for. That route already
admits the same REST read directly. Excluding only the MCP tool (option 2 as
written) would therefore not stop a scoped token from reading intents. The
`support` scope already refuses the tool, because it is not in `supportTools`.
The intents of its own WorkItem are the investigator's literal input ("what was
asked"), just as the issue body is today. This proposal takes **option 1
(accept), bounded to the run's own WorkItem**. It records the decision in
`docs/work-context-contract.md` and pins it with tests that fail if the bound
or the support exclusion is lost. The owner still has to confirm this choice
(see Open questions).

## User stories
- AS the platform owner I WANT the rule for agent-run reads of intents written down and enforced by tests SO THAT it cannot widen without anyone noticing.
- AS an issue-investigator run on a scoped token I WANT to read the intents of my own WorkItem SO THAT my proposal works from what the person actually asked for, without a static admin token.
- AS a tenant member who wrote an intent I WANT no agent run except one minted for that WorkItem to read it SO THAT my instruction does not reach unrelated runs.

## Acceptance criteria (EARS)
- WHEN a run token with scope `investigate` bound to work item W calls `mctl_list_work_item_intents` for W THE SYSTEM SHALL pass the MCP scope check and return W's intents (subject to `canSeeWorkItem`).
- IF a run token with scope `investigate` bound to work item W requests `GET /api/v1/work-items/{X}/intents` or `GET /api/v1/work-items/{X}/intents/{intent_id}` for X != W (directly or through `mctl_list_work_item_intents`) THEN THE SYSTEM SHALL refuse with 403 `agent_scope_denied` and write an `agent_scope_denied` audit row.
- IF a run token with scope `support` calls `mctl_list_work_item_intents` THEN THE SYSTEM SHALL refuse it with `agent_scope_denied` before the handler runs.
- IF a scoped run token reaches `ListWorkItemIntents` or `GetWorkItemIntent` for a WorkItem other than its own, for example because the gate was misconfigured, THEN THE SYSTEM SHALL answer 404 `work_item_not_found`, the same as an invisible item. This is a second check in the handler, so the handler does not rely on the gate alone.
- WHILE a scoped run reads intents THE SYSTEM SHALL keep the existing private-item rule. A `private` WorkItem is visible only to its owner principal, never to a run token.
- WHILE this decision stands THE SYSTEM SHALL keep `mctl_list_work_item_intents` at `enabled: false` in `docs/portal-allowlist.json`. Shared-portal exposure is a separate owner decision (mctlhq/.github#237).
- IF a future change adds an agent scope with a route that admits `/work-items/{id}/intents` without `BindWorkItem` THEN THE SYSTEM SHALL fail the build through a unit test.
- IF `mctl_list_work_item_intents` is added to `supportTools` THEN THE SYSTEM SHALL fail the build through a unit test.

## Out of scope
- Enabling `mctl_list_work_item_intents` or `mctl_append_work_item_intent` on the shared portal.
- Changing `auth.IsReadTool`, `readVerbs` or the mctl-agents policy checkpoint naming rule.
- Unscoped run tokens. They have no tenant access, so `canSeeWorkItem` already returns 404 for them.
- Redaction or retention of intent text (mctl-api#353).
- Prompt-injection hardening in mctl-agents for intent text. Intent text is untrusted input, like the issue body. How to handle it belongs to the agent prompt (mctl-agents).

## Open questions
- Owner decision required (the issue says so). This proposal implements option 1 (accept, bounded to the run's own WorkItem) because the REST route already admits the same read. If the owner chooses option 2 instead, the exclusion must cover both the MCP tool (`AgentScope.Tool`) and the REST routes `/work-items/{id}/intents(/...)` in the `investigate` scope. Excluding only the tool would leave the REST path open. A clarification question was filed for this.
- Whether issue-investigator runs started from mcp-origin WorkItems actually need intent text (mctl-agents#904 / mctl-api#871). This decides whether option 2 would break a planned flow.
- Deployed state of mctl-api (scope enforcement mode, agent-scope env) was not observable from this run. See design.md.
