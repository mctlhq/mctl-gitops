# Requirements: incident-95386506

## Incident
- ID: argo-mctl-agents-investigate-79927b83-1795386506
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (investigate)
- Created: 2026-11-22T22:28:26Z

### Summary
```
investigate https://github.com/mctlhq/mctl-glovo/issues/42 Failed after 101.932783s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-investigate-79927b83
```

## Evidence
### Labels
```
fingerprint: workflow_failed:investigate:https://github.com/mctlhq/mctl-glovo/issues/42
workflow_name: mctl-agents-investigate-79927b83
source: argo-workflows
severity: warning
```

### Log Snippet
```
Repo 'mctl-glovo' is not a known service. Add it to config/settings.py SERVICES (NON_ROTATING_SERVICES if it has no agents/<svc>/ scaffold) before investigating its issues. Known: mctl-web, mctl-docs, mctl-api, mctl-portal, mctl-agent, mctl-gitops, mctl-agents, mctl-telegram, mctl-design, mctl-pairdesk, mctl-academy, seerrsense, portfolio, .github, newton-mcp-gateway, mctl-claude-remote, mctl-alice, mctl-support
investigator exited 1
nothing to hand off
primary attempt: Failed   fallback attempt: Failed
No fallback token (claude-code-oauth-token-2) is set - cannot fall back.
```

## Acceptance Criteria
- WHEN the change is applied THEN an investigate run for a mctl-glovo issue no longer fails with "not a known service".
