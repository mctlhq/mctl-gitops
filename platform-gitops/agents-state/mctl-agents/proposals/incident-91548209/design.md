# Design: incident-91548209

## Confidence: LOW

## Diagnosis
The incident-responder run at 2026-10-09T12:15 failed on both the primary and fallback OAuth attempts because the mctl MCP server was unreachable ("no available server" when POSTing to api.mctl.ai/mcp). The guard in mcp_guard.py raised McpNotConnectedError and the orchestrator exited 4. This is most likely a transient api.mctl.ai/mcp outage (for example a rollout or pod restart); at the time of this diagnosis the MCP API answers normally, which supports that. No incident-specific misconfiguration was observed. The generic skill did not match because this is a failure of the responder itself.

## Proposed Fix
Verify first; if the cause is confirmed transient, no change is needed. Optional hardening in mctl-agents: in orchestrator/mcp_guard.py, `wait_for_mctl_connected` could retry with backoff for longer (for example up to 2-3 minutes) before raising, so a brief API rollout does not fail both attempts. Do not change anything else.

## Scope
Minimal. Only the retry/backoff window in `wait_for_mctl_connected`. If the current window already covers a typical rollout, close with no change.
