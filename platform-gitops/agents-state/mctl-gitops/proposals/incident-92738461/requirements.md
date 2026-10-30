# Requirements: incident-92738461

## Incident
- ID: argo-mctl-agents-investigate-b478e8fa-1792738461
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-10-23T06:54:21.831652Z

### Summary
```
investigate https://github.com/mctlhq/mctl-agents/issues/746 Failed after 93.580296s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-investigate-b478e8fa
```

## Evidence
### Labels
```
fingerprint: workflow_failed:investigate:https://github.com/mctlhq/mctl-agents/issues/746
workflow_name: mctl-agents-investigate-b478e8fa
```

### Log Snippet
```
orchestrator.run_token.RunTokenError: run token exchange refused: HTTP 403 agent_run_exchange_refused
investigator exited 1
primary attempt: Failed   fallback attempt: Failed
Primary investigate failed and no fallback token (claude-code-oauth-token-2) is set - cannot fall back.
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
