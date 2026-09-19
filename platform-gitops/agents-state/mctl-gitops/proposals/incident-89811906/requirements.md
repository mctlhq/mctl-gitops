# Requirements: incident-89811906

## Incident
- ID: argo-mctl-agents-implement-3eda73f8-1789811906
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-09-19T09:58:26Z

### Summary
```
implement implement issue-591-fix-metrics-lazily-created-agent-counter Failed after 1768.277211s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-implement-3eda73f8
```

## Evidence
### Labels
```
type: workflow_failed
source: argo-workflows
service: mctl-agents
tenant: admins
severity: warning
occurrence_count: 1
```

### Log Snippet
```
primary attempt: Failed   fallback attempt: Failed
[FAILED] Neither the primary attempt nor the account-2 fallback succeeded; inspect the durable needs-triage reason.
   Most often the Claude five_hour/seven_day usage limit / HTTP 429 on both accounts, or token-2 unset.
```

Note: the commit-and-push step that ran after this failure succeeded — it
pushed a `.status.yaml` update moving the underlying proposal (issue-591) to
`needs-triage`, per the implementer's documented failure handling. No code was
implemented; the pushed commit only records the failure state.

## Acceptance Criteria
- WHEN the mctl-agents implement workflow runs the primary and account-2
  fallback Claude attempts for a proposal THEN at least one of them succeeds
  (i.e. is not blocked by a missing/misconfigured fallback credential), so the
  workflow_failed alert stops firing for this fingerprint.
