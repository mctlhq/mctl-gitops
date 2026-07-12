# Requirements: incident-992434e2

## Incident
- ID: 992434e2-47ee-4ab7-850f-e00de44e0630
- Tenant: monitoring
- Service: vmagent (monitoring namespace)
- Alert: VmagentScrapePoolEmpty (generic / alertmanager)
- Created: 2026-07-12T07:45:58.185958Z
- Summary: Vmagent has scrape_pool with 0 configured/discovered targets

## Evidence
### Labels
- source: alertmanager
- type: generic
- tenant: monitoring
- severity: warning

### Log Snippet
```
(no vmagent logs available via mctl_get_service_logs for team=monitoring service=vmagent — 0 lines returned for both 1h and 6h windows)
```

## Acceptance Criteria
- WHEN the orphaned or misconfigured scrape pool is removed or its selector is corrected THEN the VmagentScrapePoolEmpty alert stops firing for the monitoring tenant.
