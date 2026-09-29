# Requirements: incident-2932eaa0

## Incident
- ID: 18bc5134-18f5-4959-b594-6f2f2932eaa0
- Tenant: labs
- Service: labs-mctl-telegram
- Alert: ArgoCDApplicationDegraded (type=argocd_app_degraded)
- Created: 2026-09-29T00:25:19.954005Z

### Summary
```
ArgoCD application labs-mctl-telegram has been Degraded for 30m
```

## Evidence
### Labels
```
source: alertmanager
type: argocd_app_degraded
tenant: labs
service: labs-mctl-telegram
severity: warning
status (at pickup): escalated
analysis (mctl-agent): Escalated: no skill matched this ticket (type=argocd_app_degraded, alert=ArgoCDApplicationDegraded). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
argocd status (mctl_get_service_status, checked 2026-09-29T01:10:00Z): health=Degraded, syncStatus=Synced, namespace=argocd, project=apps
```

### Log Snippet
Relevant lines from `mctl_get_service_logs(team=labs, service=mctl-telegram)`, most recent first, covering the window the app has been Degraded. The base-service pod and the canary CronJob are healthy and serving traffic throughout — no errors, restarts, or failed probes were found for the main workload.
```
2026-09-29T01:10:03Z canary  msg=canary run complete ok=true duration_seconds=1.44 tg_user_id=924671154 version=0.70.0
2026-09-29T01:10:03Z canary  msg=probe ok step=get_unread_messages
2026-09-29T01:10:03Z base-service msg=mcp tool call tool=get_unread_messages user_id=245 status=ok
2026-09-29T01:10:03Z canary  msg=probe ok step=list_dialogs
2026-09-29T01:10:03Z base-service msg=mcp tool call tool=list_dialogs user_id=245 status=ok
2026-09-29T01:10:03Z canary  msg=probe ok step=mcp_init
2026-09-29T01:10:02Z canary  msg=probe ok step=oauth_metadata
2026-09-29T01:00:03Z canary  msg=canary run complete ok=true duration_seconds=1.42 tg_user_id=924671154 version=0.70.0
2026-09-29T00:50:03Z canary  msg=canary run complete ok=true duration_seconds=1.47 tg_user_id=924671154 version=0.70.0
(all base-service/canary pod names stable across the window: no restarts observed)

Unrelated WARN found in the same query (different workload, DIFFERENT ArgoCD
Application "labs-mctl-telegram-preview", not the Degraded one under
investigation — included only because it shares log labels with the main app
and could otherwise be mistaken for the cause):
2026-09-29T00:51:19Z preview base-service level=WARN msg="db not reachable yet, retrying" err="ping pgx: failed to connect to `user=labs-mctl-telegram-preview database=labs-mctl-telegram-preview`: ... connection refused"
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service (ArgoCD reports the `labs-mctl-telegram` Application as Healthy).
