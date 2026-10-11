# Requirements: incident-91548209

## Incident
- ID: argo-mctl-agents-incidents-1791548100-1791548209
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-10-09T12:16:49.728678Z

### Summary
```
mctl-agents-run incident-responder Failed after 105.850814s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1791548100
```

## Evidence
### Labels
```
fingerprint: workflow_failed:run:incident-responder:
source: argo-workflows
severity: warning
```

### Log Snippet
```
↻ Primary attempt did not succeed — retrying on fallback OAuth token (account 2).
error: incident-responder: mctl MCP server status=failed error='Error POSTing to endpoint: no available server' — check api.mctl.ai/mcp health and MCTL_TOKEN validity
  File "/app/orchestrator/run_incident_responder.py", line 189, in run_incident_responder
    await ensure_mctl_connected(client, fatal=True)
  File "/app/orchestrator/mcp_guard.py", line 114, in ensure_mctl_connected
orchestrator.mcp_guard.McpNotConnectedError: mctl MCP server status=failed
orchestrator exited 4
assert-attempt: primary attempt: Failed   fallback attempt: Failed
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
