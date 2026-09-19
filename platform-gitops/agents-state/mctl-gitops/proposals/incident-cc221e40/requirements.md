# Requirements: incident-cc221e40

## Incident
- ID: b1eb40f5-a589-4745-a720-5b64cc221e40
- Tenant: labs
- Service: agent-worker-preview
- Alert: argocd_app_degraded (ArgoCD application labs-agent-worker-preview)
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
argocd_sync_status: Synced
argocd_health: Degraded (still Degraded as of 2026-09-19T14:15:50Z, re-checked at
  diagnosis time)
```

### Log Snippet
```
2026-09-19T13:21:57.687Z WARN agent-worker: poll failed err="do request: Post \"http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1/jobs/claim?limit=1\": EOF" retry_in=2s
2026-09-19T13:21:59.691Z WARN agent-worker: poll failed err="... connection refused" retry_in=4s
2026-09-19T13:22:03.695Z WARN agent-worker: poll failed err="... connection refused" retry_in=8s
2026-09-19T13:22:11.702Z WARN agent-worker: poll failed err="... connection refused" retry_in=16s
2026-09-19T13:24:08.271Z INFO agent-worker: job invocation finished job_id=6120 outcome=completed
2026-09-19T13:58:10.494Z INFO agent-worker: job invocation finished job_id=6123 outcome=completed
(no further log lines from labs-agent-worker-preview between 13:58:10Z and
14:15:50Z, a 17+ minute silence from a pod that otherwise logs every few
minutes; consistent with the running pod being the old, still-serving
ReplicaSet while a newer ReplicaSet's pod never became Ready)

mctl_get_resource_usage(team=labs), queried at diagnosis time:
  limits.cpu:    used=11300m allocated=12000m  (94% used, ~700m headroom)
  limits.memory: used=8736Mi allocated=10.5Gi
  requests.cpu:  used=1935m  allocated=3000m
  pods:          used=16     allocated=25

Corroborating evidence from two unrelated mctl-agents shepherd workflow runs
(post-deploy-verify step, same time window):
  "Newly Degraded apps detected: argocd/labs-agent-worker-preview — waiting
  120s to confirm (rolling-update grace)…"
  "Still Degraded after 120s grace: argocd/labs-agent-worker-preview"
  (workflow.creationTimestamp thresholds 2026-09-19T13:29:02Z and
  2026-09-19T13:29:22Z — both unrelated to any change in this service,
  confirming the rollout was already stuck by ~13:29, not caused by either
  of those PRs). See related incidents
  argo-mctl-agents-shepherd-ac5088f0-1789825245 and
  argo-mctl-agents-shepherd-78067ca0-1789825049.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
