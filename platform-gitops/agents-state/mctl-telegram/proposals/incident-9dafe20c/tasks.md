# Tasks: incident-9dafe20c

1. [ ] Locate where mctl-telegram increments `mctl_tool_invocations_total{status=...}` for MCP tool calls, and where CHANNEL_INVALID / PEER_ID_INVALID Telegram API errors are currently detected (the log lines already show these are recognized and logged with a structured `err` field).
2. [ ] Add a new status value (e.g. `client_error`) for calls that fail specifically because the caller supplied a peer/channel id not present in `list_dialogs` (CHANNEL_INVALID, PEER_ID_INVALID), so they are recorded but no longer counted as `status="error"`.
3. [ ] Confirm no other consumer of `mctl_tool_invocations_total{status="error"}` (dashboards, other alerts) depends on these client-input errors being classified as "error"; update `platform-gitops/infra-components/observability/grafana-dashboards/mctl-telegram-overview-dashboard-configmap.yaml` and `mctl-telegram-per-user-dashboard-configmap.yaml` only if they break, since this proposal's target repo is mctl-telegram, not mctl-gitops.
4. [ ] Add/update a unit test in mctl-telegram covering that a CHANNEL_INVALID/PEER_ID_INVALID response maps to the new client-input status, not "error".
5. [ ] Bump mctl-telegram's version/image tag per its normal release process if the platform's deploy pipeline requires it for this change to reach labs.
