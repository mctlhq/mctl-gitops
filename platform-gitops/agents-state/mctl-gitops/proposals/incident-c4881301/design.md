# Design: incident-c4881301

## Diagnosis
The HighToolErrorRate alert fired for labs/mctl-telegram, but no skill matched so nothing was analysed. The last ~50 log lines show no failing MCP tool calls: every "mcp tool call" line has status ok, and the canary probes (mcp_init, list_dialogs, get_unread_messages) all pass on version 0.79.2. The only recurring error is in the preview instance (labs-mctl-telegram-preview, user_id 1): "human input poll actor failed" with outcome api_503 every 30 seconds, meaning the preview deployment's call to the upstream mctl API returns 503. If this poll is counted in the tool-error metric, it would explain the alert. The alert may also have been transient and already cleared; the main production-like instance looks healthy.

## Confidence: LOW

## Proposed Fix
Verify before changing anything. Inspect platform-gitops/services/labs/mctl-telegram (preview values) for the API base URL / credentials the human-input poller uses, and check that the target endpoint exists in the preview environment. If the preview points at an unavailable or wrong endpoint, correct that value, or disable the human-input poller for the preview instance. If the preview config is correct and the 503 comes from mctl-api itself, make no change in this repo and note that a code-level fix (backoff or not counting poller failures in the tool error rate) belongs in mctl-telegram.

## Scope
Minimal. Only touch the single field that causes the preview poller 503s. Do not alter the main instance.
