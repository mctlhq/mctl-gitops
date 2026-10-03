# Requirements: incident-f603f940

## Incident
- ID: ba14064b-4830-42a2-8222-6d44f603f940
- Tenant: platform
- Service: TooHighChurnRate24h
- Alert: TooHighChurnRate24h
- Created: 2026-09-20T13:16:32.188888Z

### Summary
```
Too high number of new series on "10.42.6.245:8428" created over last 24h
```

## Evidence
### Labels
```
(none returned by mctl_get_incident for this incident)
```

### Log Snippet
`mctl_get_service_logs` was queried for tenant "platform" / service
"TooHighChurnRate24h" and returned zero lines. This is expected: the
incident's "service" field here is the alertname, not a deployed
component. `mctl_list_services` confirms there is no service named
"TooHighChurnRate24h" (or any VictoriaMetrics component) registered
under any team, including "platform". The alert targets
10.42.6.245:8428, which is the vmsingle pod's own metrics/ingest port
inside the `monitoring` namespace, not a tenant workload. No log
snippet is available; the diagnosis below is based on the platform's
own GitOps configuration instead.

```
(no logs available - alert target is the vmsingle metrics backend
itself, not a service with log output reachable via mctl_get_service_logs)
```

## Acceptance Criteria
- WHEN the change is applied THEN a future TooHighChurnRate24h firing is
  delivered to a human operator (Telegram) instead of only opening a
  generic ticket that mctl-agent has no skill to act on.
