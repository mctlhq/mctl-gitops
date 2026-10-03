# Requirements: incident-21ed36ff

## Incident
- ID: 9af84c63-ed36-4b7b-9cd1-0fe821ed36ff
- Tenant: admins
- Service: admins-openclaw
- Alert: ArgoCDApplicationOutOfSyncLong (type: argocd_app_degraded)
- Created: 2026-09-11T19:37:21.476399Z

### Summary
```
ArgoCD application admins-openclaw OutOfSync for 1h
```

## Evidence
### Labels
```
source: alertmanager
type: argocd_app_degraded
severity: warning
confidence (reported by mctl-agent): LOW
occurrence_count: 1
mctl-agent analysis: Escalated: no skill matched this ticket (type=argocd_app_degraded,
  alert=ArgoCDApplicationOutOfSyncLong). Evidence was collected, but the agent has no
  diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Live ArgoCD status (mctl_get_service_status, queried at diagnosis time)
```
argocd.name: admins-openclaw
argocd.health: Healthy
argocd.syncStatus: OutOfSync
argocd.revision: "" (empty)
argocd.updatedAt: 2026-09-11T20:09:20Z
service.imageTag: 2026.7.11-beta.2
```

### Log Snippet
Logs pulled for admins/openclaw (last 50 lines, `since=6h`) contain only the s3-sync
sidecar's periodic `mc mirror` progress-table output (state backup to MinIO). No
error, warning, or ArgoCD-related log line appears in the application/base-service
or s3-sync containers in this window. The alert is about ArgoCD's own reconciliation
state, which is not surfaced in tenant pod logs, so this is expected and not itself
diagnostic:
```
`/home/node/.openclaw/workspace/skills/mctl-skill-manager/.layer3` -> `s3/platform-state/admins/openclaw/workspace/skills/mctl-skill-manager/.layer3`
`/home/node/.openclaw/workspace/skills/mctl-gitops-remediation/.layer3` -> `s3/platform-state/admins/openclaw/workspace/skills/mctl-gitops-remediation/.layer3`
`/home/node/.openclaw/workspace/skills/mctl-agent-external/.layer3` -> `s3/platform-state/admins/openclaw/workspace/skills/mctl-agent-external/.layer3`
`/home/node/.openclaw/workspace/skills/mctl-github-remediation/.layer3` -> `s3/platform-state/admins/openclaw/workspace/skills/mctl-github-remediation/.layer3`
`/home/node/.openclaw/update-check.json` -> `s3/platform-state/admins/openclaw/update-check.json`
(remaining lines: repeated mc-mirror transfer-summary tables, no errors)
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service
  (ArgoCD reports admins-openclaw as Synced, not just Healthy).
