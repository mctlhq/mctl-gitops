# Requirements: incident-72e0cc51

## Incident
- ID: argo-mctl-agents-incidents-1785302100-1785302255
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-07-29T05:17:35.129004Z
- Summary: mctl-agents-run incident-responder Failed after 150.232540s

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- occurrence_count: 1
- fingerprint: workflow_failed:run:incident-responder:

### Diagnosis Context
An Argo Workflow for the mctl-agents incident-responder job failed after 150 seconds (~2.5 minutes). No step logs are available in the archive (either aged out or job crashed before producing output). The workflow name suggests it was running the incident responder itself. This is a critical issue because the incident responder is part of the platform's incident diagnosis pipeline.

## Acceptance Criteria
- WHEN the root cause of the crash is identified and fixed THEN the next incident-responder run completes successfully.
- Verify that incident-responder workflow can reach the mctl API and query incidents without crashing.
