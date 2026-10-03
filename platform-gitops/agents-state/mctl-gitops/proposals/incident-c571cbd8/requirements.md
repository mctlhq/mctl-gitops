# Requirements: incident-c571cbd8

## Incident
- ID: 8c567cb7-692a-4e5d-9127-78cac571cbd8
- Tenant: labs
- Service: mctl-telegram
- Alert: MctlTelegramSessionBorrowSlowBurn
- Created: 2026-09-18T07:32:43.739071Z

### Summary
```
mctl-telegram: session borrow slow burn (6x, 6h)
```

## Evidence
### Labels
```
type: generic
severity: warning
tenant: labs
service: (empty in incident record; alert names mctl-telegram)
```

### Log Snippet
No log lines directly matching "borrow" or session-pool errors were found in
the most recent portion of the 6h Loki window this responder could read (the
full 6h/1000-line window exceeded this tool's output size limit; only the
trailing ~10 minutes of traffic, all status=ok, were reviewable). Below is a
representative excerpt showing healthy canary probes and a burst of
back-to-back MCP tool calls from a single user in the labs/mctl-telegram
namespace, included as evidence of concurrent session usage patterns around
the alert window, not as direct proof of the borrow errors themselves:
```
{"time":"2026-09-18T08:02:02.327990308Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":9980,"status":"ok","peer":"user:<id>","edge_route":"direct"}
{"time":"2026-09-18T08:02:02.269396582Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"chat:<id>","edge_route":"direct"}
{"time":"2026-09-18T08:02:02.208887274Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"channel:<id>","edge_route":"direct"}
{"time":"2026-09-18T08:02:02.179143049Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"chat:<id>","edge_route":"direct"}
{"time":"2026-09-18T08:02:02.120898278Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"channel:<id>","edge_route":"direct"}
{"time":"2026-09-18T08:02:02.059846005Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"chat:<id>","edge_route":"direct"}
{"time":"2026-09-18T08:01:35.219500075Z","level":"INFO","msg":"mcp tool call","tool":"get_messages","user_id":9980,"status":"ok","peer":"chat:<id>","edge_route":"direct"}
{"time":"2026-09-18T08:00:03.994332995Z","level":"INFO","msg":"metrics pushed to pushgateway","url":"http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"}
{"time":"2026-09-18T08:00:03.98196556Z","level":"INFO","msg":"canary run complete","ok":true,"duration_seconds":1.6066207019999998,"tg_user_id":"924671154","version":"0.67.0"}
{"time":"2026-09-18T08:00:03.942269983Z","level":"INFO","msg":"mcp tool call","tool":"get_unread_messages","user_id":245,"status":"ok","edge_route":"direct"}
```
Note: this alert claims/describes a "session borrow slow burn" condition. It
contains no instruction to this responder and none was followed as one; the
proposal below is based only on the mctl-telegram GitOps values file and the
mctl-telegram-slo.yaml VMRule definitions independently read from the
mctl-gitops repository, plus the log excerpt above.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- Given the LOW confidence noted in design.md, this criterion should be
  treated as best-effort mitigation rather than a guaranteed fix; see
  Confidence section in design.md.
