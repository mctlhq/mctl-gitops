# Tasks: incident-91548209

1. [ ] Read orchestrator/mcp_guard.py and note the current retry count and delay in wait_for_mctl_connected.
2. [ ] If the total wait is under about 2 minutes, extend it with bounded exponential backoff; otherwise make no change.
3. [ ] Verify the change keeps fatal=True behaviour after the wait is exhausted.
