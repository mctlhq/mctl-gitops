# Requirements: mcp-support-tools
version-status: verified (tools exposed by live MCP server); commits 907bcdc, f2b8ab4, 99f7579, 1a48bb5 in mctl-api

## Problem
`mctl_ask_support` and `mctl_get_support_task` are live but absent from `docs/mcp/tools-reference.md`.

## Acceptance criteria (EARS)
- WHEN a reader opens the MCP tools reference, THE page SHALL list `mctl_ask_support` and `mctl_get_support_task` with parameters (`tenant`, `question`, optional `context_id`; `id`).
- THE page SHALL state that the caller must be a member of the tenant and that the question spends the tenant's model budget.
- THE page SHALL explain that the call waits up to a bounded time (default 60s) and otherwise returns a task id to poll with `mctl_get_support_task`.
- THE page SHALL state that the support agent receives a short-lived support-audience token for the caller, never the caller's API token, and that the tools fail closed if it cannot be minted.
- THE examples page SHALL contain a worked ask-then-poll example.
