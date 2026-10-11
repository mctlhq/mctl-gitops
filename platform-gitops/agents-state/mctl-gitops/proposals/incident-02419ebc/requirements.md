# Requirements: incident-02419ebc

## Incident
- ID: f97fd528-7130-4871-9ca3-56f002419ebc
- Tenant: labs
- Service: smoke-test-svc
- Alert: argocd_app_degraded
- Created: 2026-10-11T18:14:35.692233Z

### Summary
```
ArgoCD app labs-smoke-test-svc health: Missing
```

## Evidence
### Labels
```
source: polling
type: argocd_app_degraded
severity: warning
status: escalated
occurrence_count: 1
analysis: Escalated: no skill matched this ticket (type=argocd_app_degraded, alert=)
```

### Log Snippet
```
2026-10-11T18:51:11Z labs-smoke-test-svc-base-service-546dc7f545-2mgbz [::ffff:10.42.6.1]:60914: response:200
2026-10-11T18:51:06Z labs-smoke-test-svc-base-service-546dc7f545-2mgbz [::ffff:10.42.6.1]:51748: response:200
2026-10-11T18:48:16Z labs-smoke-test-svc-base-service-fb6d58db-9dkdq [::ffff:10.42.4.1]:38028: response:200
(all ~50 returned lines are HTTP 200 health-probe responses; no errors; newest line is 18:51:11, and the older ReplicaSet fb6d58db stops logging at 18:48:16, consistent with a rollout)
```

Service status check at 19:11 UTC: mctl_get_service_status reports "ArgoCD application not found: labs-smoke-test-svc".

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
