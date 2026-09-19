# Requirements: incident-89786744

## Incident
- ID: argo-mctl-agents-implement-8823a79d-1789786744
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-09-19T02:59:05.062063Z

### Summary
```
implement implement issue-903-spike-observability-compare-traceway-tem Failed after 8848.523336s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-implement-8823a79d
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:implement:mctl-gitops:issue-903-spike-observability-compare-traceway-tem
occurrence_count: 1
target repo/issue: mctl-gitops issue-903-spike-observability-compare-traceway-tem
```

### Log Snippet
mctl_get_service_logs does not reach Argo step pods (Loki only ingests
long-lived services). Evidence below is from mctl_get_workflow_status
(argo-workflows/mctl-agents-implement-8823a79d), which is internal platform
telemetry, not attacker-influenced incident text.
```
workflow spec.activeDeadlineSeconds = 7200 (cwft-mctl-agents-implement.yaml:59)

node "implement" (run-implementer, primary, oauth-key=claude-code-oauth-token):
  started  2026-09-19T00:31:33Z
  finished 2026-09-19T02:31:43Z  (~7210s elapsed)
  message: "Step exceeded its deadline"

node "implement-fallback" (run-implementer, oauth-key=claude-code-oauth-token-2):
  started  2026-09-19T02:31:43Z
  finished 2026-09-19T02:51:43Z  (~1200s elapsed)
  message: "Step exceeded its deadline"

node "commit" (commit-and-push, Retry):
  started  2026-09-19T02:51:43Z
  finished 2026-09-19T02:59:01Z  (~438s elapsed)
  message: "Step exceeded its deadline"
```

## Acceptance Criteria
- WHEN the change is applied THEN a future implement run whose primary
  attempt consumes close to its full time budget still allows
  implement-fallback and commit-and-push a real chance to complete, so the
  workflow does not fail at the commit stage purely from having zero
  remaining shared deadline.
