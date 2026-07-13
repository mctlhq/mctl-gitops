# Requirements: incident-43d9e608

## Incident
- ID: 43d9e608-1645-4857-a5e3-9310f0a7422d
- Tenant: monitoring
- Service: vmagent
- Alert: VmagentScrapePoolEmpty (Vmagent has scrape_pool with 0 configured/discovered targets)
- Created: 2026-07-13T15:45:58.588855Z
- Summary: Vmagent has scrape_pool with 0 configured/discovered targets

## Evidence
### Labels
- source: alertmanager
- severity: warning
- tenant: monitoring
- type: generic

### Log Snippet
```
(no log lines returned by mctl_get_service_logs for team=monitoring service=vmagent — vmagent pod logs unavailable via Loki at query time)
```

## Acceptance Criteria
- WHEN the orphaned scrape pool is removed or its selector is corrected THEN vmagent reports 0 scrape_pools with empty targets and the alert stops firing.
