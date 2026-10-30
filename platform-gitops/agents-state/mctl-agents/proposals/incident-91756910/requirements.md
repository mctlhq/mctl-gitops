# Requirements: incident-91756910

## Incident
- ID: argo-mctl-agents-implement-dae24112-1791756910
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-10-11T22:15:10.578256Z

### Summary
```
implement implement issue-757-tool-availability-sli-counts-caller-erro Failed after 437.333132s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-implement-dae24112
```

## Evidence
### Labels
```
fingerprint: workflow_failed:implement:mctl-telegram:issue-757-tool-availability-sli-counts-caller-erro
severity: warning
source: argo-workflows
```

### Log Snippet
```
primary attempt: Failed   fallback attempt: Failed
Neither the primary attempt nor the account-2 fallback succeeded; inspect the durable needs-triage reason.
info: auth mode: oauth - Claude Pro/Max OAuth token (CLAUDE_CODE_OAUTH_TOKEN)
AssistantMessage: Your organization has disabled Claude subscription access for Claude Code - Use an Anthropic API key instead, or ask your admin to enable access
error='oauth_org_not_allowed' api_error_status=403
=== [mctl-telegram/issue-757-tool-availability-sli-counts-caller-erro] Finished: failed ===
fail: implementer produced no commits
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
