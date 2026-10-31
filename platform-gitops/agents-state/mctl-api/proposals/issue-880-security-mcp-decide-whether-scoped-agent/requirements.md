# Scoped agent run tokens: own WorkItem only, and intent text withheld unless explicitly granted (decision for mctl-api#880)

## Context
mctl-api#868 added `mctl_list_work_item_intents` (`internal/mcp/workitems.go`,
`toolListWorkItemIntents`). Scoped agent run tokens choose MCP tools with
`auth.IsReadTool` (`internal/auth/agent_scope.go`), which admits every
`list_` tool, so the `investigate` scope admits this tool. Raw intents are
text written by people, more sensitive than state metadata.

The investigation found that the exposure is narrower than the issue first
assumed, and that the control point is the REST handler, not the MCP tool:
- The MCP tool sends `GET /api/v1/work-items/{id}/intents` with the caller's
  own token, so the REST scope gate (`internal/api/agent_scope_gate.go`)
  checks it again.
- The `investigate` scope admits work-item reads only through a
  `BindWorkItem` route, `^/api/v1/work-items/([^/]+)(/.*)?$`, so a scoped run
  can reach only the intents of the WorkItem it was minted for. That same
  route also admits the REST read directly, so excluding only the MCP tool
  would leave the data reachable.
- The `support` scope already refuses the tool (not in `supportTools`).

**Owner decision (2026-10-31, recorded on mctl-api#880): fail closed.** A
scoped agent run token does not receive raw intent text by default, on any
path. Raw text requires an explicit, server-defined capability
`workitem:intents:read_raw` on the scope. No existing scope is granted it in
this change: no current agent flow needs intent text (the mcp-origin
fulfilment flows are mctl-agents#904 / mctl-api#871 and will request the
capability as their own decision). The own-WorkItem bound found by the
investigation is kept as well, as defence in depth.

## User stories
- AS the platform owner I WANT scoped agent runs to see that intents exist but not their text unless a scope is explicitly granted the capability SO THAT human-written instructions reach an automated run only by decision.
- AS a tenant member who wrote an intent I WANT no agent run to read its text unless its scope was granted `workitem:intents:read_raw`, and never for a WorkItem the run was not minted for SO THAT my instruction does not leak to unrelated or ungranted runs.
- AS a client reading intents I WANT text withheld by scope to be distinguishable from text removed by retention SO THAT I do not treat a withheld intent as permanently gone, or as an empty instruction.

## Acceptance criteria (EARS)
- WHEN a scoped run token whose scope does not grant `workitem:intents:read_raw` reads the intents of its own WorkItem (REST `GET /work-items/{id}/intents`, `GET /work-items/{id}/intents/{intent_id}`, or `mctl_list_work_item_intents`) THE SYSTEM SHALL return every intent with `text: ""` and `text_withheld: true`, keeping id, actor, surface, timestamps and `text_redacted` unchanged.
- WHEN a scoped run token whose scope grants `workitem:intents:read_raw` reads the intents of its own WorkItem THE SYSTEM SHALL return the text as stored, with `text_withheld: false`.
- WHEN a human caller, an admin, or an unscoped token reads intents THE SYSTEM SHALL behave exactly as today, with `text_withheld: false` on every intent.
- THE SYSTEM SHALL apply the withholding in the REST handlers (`ListWorkItemIntents`, `GetWorkItemIntent`), so the MCP tool and direct REST calls get the same result. The MCP tool passes the response through unchanged.
- THE SYSTEM SHALL keep `text_redacted` (retention) and `text_withheld` (scope) as separate fields. An intent can be both. Neither ever carries reconstructed or placeholder text.
- IF a run token with scope `investigate` bound to work item W requests `GET /api/v1/work-items/{X}/intents` or `.../intents/{intent_id}` for X != W (directly or through `mctl_list_work_item_intents`) THEN THE SYSTEM SHALL refuse with 403 `agent_scope_denied` and write an `agent_scope_denied` audit row.
- IF a scoped run token reaches `ListWorkItemIntents` or `GetWorkItemIntent` for a WorkItem other than its own (for example because the gate was misconfigured) THEN THE SYSTEM SHALL answer 404 `work_item_not_found`, the same as an invisible item.
- IF a run token with scope `support` calls `mctl_list_work_item_intents` THEN THE SYSTEM SHALL refuse it with `agent_scope_denied` before the handler runs.
- WHILE a scoped run reads intents THE SYSTEM SHALL keep the existing private-item rule: a `private` WorkItem is visible only to its owner principal, never to a run token.
- THE SYSTEM SHALL grant `workitem:intents:read_raw` to no scope in this change. A unit test SHALL fail the build if any scope in `AgentScopeNames()` grants it without being listed in an explicit, reviewed allowlist in the test (empty today).
- IF a future change adds an agent scope with a route that admits `/work-items/{id}/intents` without `BindWorkItem` THEN THE SYSTEM SHALL fail the build through a unit test.
- IF `mctl_list_work_item_intents` is added to `supportTools` THEN THE SYSTEM SHALL fail the build through a unit test.
- WHILE this decision stands THE SYSTEM SHALL keep `mctl_list_work_item_intents` at `enabled: false` in `docs/portal-allowlist.json` (shared-portal exposure is mctlhq/.github#237).

## Out of scope
- Granting `workitem:intents:read_raw` to any scope (`investigate` included). That is the decision of the flow that needs it (mctl-agents#904 / mctl-api#871).
- Enabling `mctl_list_work_item_intents` or `mctl_append_work_item_intent` on the shared portal.
- Changing `auth.IsReadTool`, `readVerbs` or the mctl-agents policy checkpoint naming rule.
- Unscoped run tokens. They have no tenant access, so `canSeeWorkItem` already returns 404 for them.
- Retention/redaction of intent text (mctl-api#353), and the server-derived client id on intents (mctl-api#883).
- Prompt-injection hardening in mctl-agents for intent text, once a scope is granted it.

## Open questions
- None blocking. The owner answered the investigator's human-input request (`hir-5ac263d9fe137575`) on mctl-api#880: fail closed, with the capability-based exception.
- Deployed state of mctl-api (scope enforcement mode, agent-scope env) was not observable from the investigation run. This change is code, tests and docs only.
