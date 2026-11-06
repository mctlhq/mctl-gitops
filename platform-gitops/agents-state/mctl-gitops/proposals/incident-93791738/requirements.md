# Requirements: incident-93791738

## Incident
- ID: argo-mctl-agents-shepherd-168a17bd-1793791738
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (shepherd, issue-306-spike-journey-level-correlation-across-g)
- Created: 2026-11-04T11:28:58.945368Z

### Summary
```
shepherd shepherd issue-306-spike-journey-level-correlation-across-g Failed after 731.318601s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-168a17bd
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
workflow_name: mctl-agents-shepherd-168a17bd
fingerprint: workflow_failed:shepherd:.github:issue-306-spike-journey-level-correlation-across-g
```

### Log Snippet
```
assert-attempt step:
shepherd attempt: Failed   fallback attempt: Failed
Neither the primary attempt nor the account-2 fallback succeeded - no proposal was actually advanced this tick.
   Most often the Claude five_hour usage limit / HTTP 429 on both accounts, or token-2 unset.
commit-and-push step:
No agents-state updates handed off - nothing to commit.
post-deploy-verify step:
merged=no shepherd=unknown - verifying.
No persistent Degraded apps detected after shepherd run.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
