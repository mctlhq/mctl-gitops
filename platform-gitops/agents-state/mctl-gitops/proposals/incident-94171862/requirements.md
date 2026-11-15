# Requirements: incident-94171862

## Incident
- ID: argo-mctl-agents-investigate-050de6b3-1794171862
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (investigate)
- Created: 2026-11-08T21:04:22.70449Z

### Summary
```
investigate https://github.com/mctlhq/mctl-agents/issues/1051 Failed after 405.781626s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-investigate-050de6b3
```

## Evidence
### Labels
```
source: argo-workflows
type: workflow_failed
severity: warning
fingerprint: workflow_failed:investigate:https://github.com/mctlhq/mctl-agents/issues/1051
workflow_name: mctl-agents-investigate-050de6b3
```

### Log Snippet
```
[run-investigator-2257218791] Primary investigate failed and no fallback token (claude-code-oauth-token-2) is set - cannot fall back.
[run-investigator-3473782135] AssistantMessage: Your organization has disabled Claude subscription access for Claude Code · Use an Anthropic API key instead, or ask your admin to enable access
[run-investigator-3473782135] ResultMessage(is_error=True, api_error_status=403, error=oauth_org_not_allowed, num_turns=28)
[run-investigator-3473782135] Investigate summary: fail mctl-agents/issue-1051-devloop-part-m-m2b-1d-2-deadline-exit-of: agent did not write: requirements.md, design.md, tasks.md
[commit-and-push] No proposal files handed off - nothing to commit.
[assert-attempt] primary attempt: Failed   fallback attempt: Failed
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
- WHEN issue 1051 is re-investigated THEN the investigator produces proposal files.
