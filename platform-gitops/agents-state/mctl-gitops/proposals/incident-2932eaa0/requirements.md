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
severity: warning
occurrence_count: 1
escalation_analysis: Escalated: no skill matched this ticket (type=argocd_app_degraded, alert=ArgoCDApplicationDegraded). Evidence was collected, but the agent has no diagnostic rule for this signal, so nothing was analysed. Needs a human, or a new skill.
```

### Log Snippet
mctl_get_service_status for labs/mctl-telegram at investigation time (2026-09-29T01:15Z, i.e. ~50 minutes after the alert fired):
```
{"argocd":{"name":"labs-mctl-telegram","health":"Degraded","syncStatus":"Synced","updatedAt":"2026-09-29T01:13:03Z"}}
```
Two independent post-deploy-verify checks from unrelated mctl-agents shepherd runs, at different times, both found the app already Degraded and never recovering:
```
Listing applications that became Degraded after 2026-09-28T23:31:49Z...
Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm (rolling-update grace)...
Still Degraded after 120s grace: argocd/labs-mctl-telegram
```
```
Listing applications that became Degraded after 2026-09-28T23:53:27Z...
Newly Degraded apps detected: argocd/labs-mctl-telegram - waiting 120s to confirm (rolling-update grace)...
Still Degraded after 120s grace: argocd/labs-mctl-telegram
```
Meanwhile labs-mctl-telegram service logs across the same window (00:00-01:15Z) show only healthy traffic, no errors:
```
"msg":"mcp tool call","tool":"get_messages","status":"ok"
"msg":"canary run complete","ok":true,"duration_seconds":1.437504623,"version":"0.70.0"
"msg":"probe ok","step":"get_unread_messages"
"msg":"probe ok","step":"list_dialogs"
"msg":"probe ok","step":"mcp_init"
"msg":"probe ok","step":"oauth_metadata"
"msg":"listening","addr":":8080"
```
The synthetic canary CronJob (labs-mctl-telegram-canary, every 10 minutes) succeeded on every run sampled, going back well before the alert fired, with no gaps and no failures.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
