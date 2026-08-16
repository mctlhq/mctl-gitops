# Requirements: incident-5b968879

## Incident
- ID: fb6e1542-440b-4b1b-9ebf-d6ac35d6d8c6
- Tenant: labs
- Service: agent-worker-preview
- Alert: argocd_app_degraded
- Created: 2026-08-16T16:04:23Z
- Summary: ArgoCD app labs-agent-worker-preview health: Degraded

## Evidence
### Labels
- source: polling
- type: argocd_app_degraded
- severity: warning
- status: analyzing
- occurrence_count: 1

### Log Snippet
Recent logs show agent-worker successfully completing jobs:
- Job completions every 8-10 seconds (consistent throughput)
- Pods at maximum capacity: labs-agent-worker-preview-base-service-5b457c74b5-t5rln (multiple instances)
- Connection errors to labs-mctl-telegram-preview-base-service:8080 indicating downstream service capacity issue
- Previous replica cycling with auth errors suggests pod eviction due to resource pressure

## Acceptance Criteria
- WHEN the maxReplicas value for labs-agent-worker-preview HPA is increased from current limit (likely 5) to 10
- THEN the service can scale horizontally to handle pending workload
- AND ArgoCD health status returns to Healthy
