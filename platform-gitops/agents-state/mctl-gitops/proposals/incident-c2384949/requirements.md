# Requirements: incident-c2384949

## Incident
- ID: eeb9a12b-b2b0-41d2-99b3-0100c2384949
- Tenant: mctl-api
- Service: mctl-api
- Alert: KubePodCrashLooping (type pod_crashloop)
- Created: 2026-11-16T09:48:45.291194Z

### Summary
```
Pod is crash looping.
```

## Evidence
### Labels
```
(none returned by mctl_get_incident)
```

### Log Snippet
```
Logs unavailable: mctl_get_service_logs returned "tenant not found: mctl-api".
Pods unavailable: mctl_get_service_pods returned "tenant not found: mctl-api".
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
