# Requirements: incident-c4881301

## Incident
- ID: 4b69c8b8-954e-4045-9f1c-8fb6c4881301
- Tenant: labs
- Service: mctl-telegram
- Alert: HighToolErrorRate (type=generic)
- Created: 2026-10-09T09:36:39.926237Z

### Summary
```
mctl-telegram: more than 10% of tool calls are failing
```

## Evidence
### Labels
```
source: alertmanager
severity: warning
analysis: Escalated: no skill matched this ticket (type=generic, alert=HighToolErrorRate). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed.
```

### Log Snippet
```
{"level":"WARN","msg":"human input poll actor failed","user_id":1,"outcome":"api_503"}   (pod labs-mctl-telegram-preview-base-service-fb8dd78c6-pbqr5, repeats every 30s from 10:01:53 to 10:14:23)
{"level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":1,"status":"ok"}   (same preview pod, successful)
{"level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok"}   (main pod labs-mctl-telegram-base-service-576d7c9fd8-ph8sl, all ok)
{"level":"INFO","msg":"canary run complete","ok":true,"version":"0.79.2"}   (canary at 10:10:03, all probes ok)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
