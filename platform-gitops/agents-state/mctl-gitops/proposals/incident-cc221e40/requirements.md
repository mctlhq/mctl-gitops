# Requirements: incident-cc221e40

## Incident
- ID: b1eb40f5-a589-4745-a720-5b64cc221e40
- Tenant: labs
- Service: agent-worker-preview
- Alert: argocd_app_degraded
- Created: 2026-09-19T13:33:31.443537Z

### Summary
```
ArgoCD app labs-agent-worker-preview health: Degraded
```

## Evidence
### Labels
```
source: polling
type: argocd_app_degraded
tenant: labs
service: agent-worker-preview
severity: warning
confidence: LOW
occurrence_count: 1
argocd.name: labs-agent-worker-preview
argocd.health (at investigation time, 2026-09-19T14:11Z): Degraded
argocd.syncStatus (at investigation time): Synced
```

### Log Snippet
Source: Loki logs for team=labs, service=agent-worker-preview, window 12:00-14:11 UTC on
2026-09-19. Only the pod labs-agent-worker-preview-base-service-657bd68fd5-5w7xp appears in
this window; no log lines from any newer/replacement pod were found, consistent with a
replacement pod that never became Ready (and so never started serving traffic or emitting
its own log lines).
```
{"time":"2026-09-19T13:16:59Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6113,"outcome":"completed"}
{"time":"2026-09-19T13:21:57Z","level":"WARN","msg":"agent-worker: poll failed","err":"do request: Post \"http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1/jobs/claim?limit=1\": EOF","retry_in":2000000000}
{"time":"2026-09-19T13:21:59Z","level":"WARN","msg":"agent-worker: poll failed","err":"do request: Post \"http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1/jobs/claim?limit=1\": dial tcp 10.43.43.156:8080: connect: connection refused","retry_in":4000000000}
{"time":"2026-09-19T13:22:03Z","level":"WARN","msg":"agent-worker: poll failed","err":"do request: Post \"http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1/jobs/claim?limit=1\": dial tcp 10.43.43.156:8080: connect: connection refused","retry_in":8000000000}
{"time":"2026-09-19T13:22:11Z","level":"WARN","msg":"agent-worker: poll failed","err":"do request: Post \"http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1/jobs/claim?limit=1\": dial tcp 10.43.43.156:8080: connect: connection refused","retry_in":16000000000}
{"time":"2026-09-19T13:24:54Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6114,"outcome":"completed"}
{"time":"2026-09-19T13:25:32Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6115,"outcome":"completed"}
{"time":"2026-09-19T13:26:29Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6116,"outcome":"completed"}
{"time":"2026-09-19T13:27:59Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6117,"outcome":"completed"}
{"time":"2026-09-19T13:37:37Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6118,"outcome":"completed"}
{"time":"2026-09-19T13:40:54Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6119,"outcome":"completed"}
{"time":"2026-09-19T13:58:10Z","level":"INFO","msg":"agent-worker: job invocation finished","job_id":6123,"outcome":"completed"}
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
