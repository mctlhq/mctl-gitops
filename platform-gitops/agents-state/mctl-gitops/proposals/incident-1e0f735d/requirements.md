# Requirements: incident-1e0f735d

## Incident
- ID: f3735698-1751-4148-93b1-656e1e0f735d
- Tenant: argocd
- Service: argocd-applicationset-controller
- Alert: CPUThrottlingHigh (type: resource_limit)
- Created: 2026-09-29T20:38:44.652273Z

### Summary
```
Processes experience elevated CPU throttling.
```

## Evidence
### Labels
```
source: alertmanager
type: resource_limit
severity: warning
occurrence_count: 1
confidence: MEDIUM
analysis (from mctl-agent, advisory only): Service is experiencing CPU throttling. CPU limit needs to be increased to prevent performance degradation. [escalated] Alert "CPUThrottlingHigh" is on the human-review-only list: the agent diagnoses it but never proposes a fix, by policy. The diagnosis above is advisory.
```

### Log Snippet
```
No logs were available. mctl_get_service_logs(team=argocd, service=argocd-applicationset-controller) returned 0 lines. This is an ArgoCD control-plane component, not a tenant-onboarded service, so it is not registered in the Loki-backed service log path used by mctl tooling. mctl_get_service_config also returned "service not found" for the same reason. Diagnosis below is based solely on the alert type/name and the advisory analysis text above.
```

## Acceptance Criteria
- WHEN the change is applied THEN the CPUThrottlingHigh alert stops firing for argocd/argocd-applicationset-controller.
