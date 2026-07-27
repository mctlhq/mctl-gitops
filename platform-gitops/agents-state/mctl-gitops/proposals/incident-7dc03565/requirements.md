# Requirements: incident-7dc03565

## Incident
- ID: 8654ab38-9971-4a4f-9759-0d0ba112f2f0
- Tenant: monitoring
- Service: vmagent
- Alert: Vmagent has scrape_pool with 0 configured/discovered targets
- Created: 2026-07-25T16:16:02.025813Z
- Summary: Vmagent has scrape_pool with 0 configured/discovered targets

## Evidence
### Labels
- source: alertmanager
- type: generic
- severity: warning
- tenant: monitoring
- service: (empty - service not deployed)

### Log Snippet
Service not currently deployed in monitoring tenant. No logs available from vmagent itself.

Alert fired from AlertManager, indicating a scrape_pool configuration with 0 targets.

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for the monitoring/vmagent scrape pool.
