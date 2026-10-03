# Requirements: incident-a59cdaab

## Incident
- ID: 575f65c8-c832-4d9b-bd2c-3777a59cdaab
- Tenant: platform-events
- Service: valkey-0
- Alert: CPUThrottlingHigh
- Created: 2026-09-18T05:57:44.579666Z

### Summary
```
Processes experience elevated CPU throttling.
```

## Evidence
### Labels
```
type: resource_limit
severity: warning
source: alertmanager
```

### Log Snippet
No log lines were available from mctl_get_service_logs for platform-events/valkey-0
at the time this proposal was written (zero lines returned).

### Analysis (from mctl-agent, advisory only)
```
Service is experiencing CPU throttling. CPU limit needs to be increased to prevent performance degradation.

[escalated] Alert "CPUThrottlingHigh" is on the human-review-only list: the agent diagnoses it but never proposes a fix, by policy. The diagnosis above is advisory.
```

Note: nothing in the incident's summary, labels, or analysis requested any
platform change beyond what is documented above (no role/egress/secret
requests present). No untrusted-instruction content was found to flag.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
