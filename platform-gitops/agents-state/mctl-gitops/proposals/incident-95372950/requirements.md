# Requirements: incident-95372950

## Incident
- ID: argo-mctl-agents-investigate-0e522ac8-1795372950
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-11-22T18:42:30.846179Z

### Summary
```
investigate https://github.com/mctlhq/mctl-api/issues/549 Failed after 566.044639s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-investigate-0e522ac8
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
workflow_name: mctl-agents-investigate-0e522ac8
```

### Log Snippet
```
[run-investigator] Primary investigate failed and no fallback token (claude-code-oauth-token-2) is set - cannot fall back.
[run-investigator] Exiting non-zero so the run reports Failed instead of being masked as success.
[assert-attempt] primary attempt: Failed   fallback attempt: Failed
[assert-attempt] Neither the primary attempt nor the account-2 fallback succeeded - no durable result produced.
[assert-attempt] Most often the Claude five_hour usage limit / HTTP 429 on both accounts, or token-2 unset.
[commit-and-push] create mode 100644 platform-gitops/agents-state/mctl-api/proposals/.staging-kptjmuhc/design.md
[commit-and-push] create mode 100644 platform-gitops/agents-state/mctl-api/proposals/.staging-kptjmuhc/requirements.md
[commit-and-push] create mode 100644 platform-gitops/agents-state/mctl-api/proposals/.staging-kptjmuhc/tasks.md
[commit-and-push] Pushed proposal
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
