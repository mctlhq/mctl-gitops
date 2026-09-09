# Requirements: incident-88775245

## Incident
- ID: argo-mctl-agents-investigate-7afd8173-1788775245
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-09-07T10:00:45.661534Z

### Summary
```
investigate https://github.com/mctlhq/seerrsense/issues/6 Failed after 73.468402s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-investigate-7afd8173
```

## Evidence
### Labels
```
(none provided by mctl_get_incident for this incident)
```

### Log Snippet
```
[run-investigator, primary attempt]
-> Linking runtime state from /workdir/mctl-gitops/platform-gitops/agents-state
Success: State linked
-> python -m orchestrator.run_issue_investigator --issue-url https://github.com/mctlhq/seerrsense/issues/6
Repo 'seerrsense' is not a known service. Add it to config/settings.py SERVICES (NON_ROTATING_SERVICES if it has no agents/<svc>/ scaffold) before investigating its issues. Known: mctl-web, mctl-openclaw, mctl-docs, mctl-api, mctl-portal, mctl-agent, mctl-gitops, mctl-agents, mctl-telegram, mctl-design, mctl-pairdesk, mctl-academy
[model-policy] task=service_agent profile=balanced model=claude-sonnet-5 source=policy
info: auth mode: oauth - Claude Pro/Max OAuth token (CLAUDE_CODE_OAUTH_TOKEN)
$ gh issue view --json number,title,body,state,url -- https://github.com/mctlhq/seerrsense/issues/6
investigator exited 1
nothing to hand off

[run-investigator, fallback attempt on account 2]
Retrying on fallback OAuth token (account 2).
-> python -m orchestrator.run_issue_investigator --issue-url https://github.com/mctlhq/seerrsense/issues/6
Repo 'seerrsense' is not a known service. Add it to config/settings.py SERVICES (NON_ROTATING_SERVICES if it has no agents/<svc>/ scaffold) before investigating its issues.
investigator exited 1
nothing to hand off

[assert-attempt]
primary attempt: Failed   fallback attempt: Failed
No durable result produced. (Note: this step's generic quota-exhaustion
wording is misleading here -- both attempts failed identically and
deterministically before invoking the model, on the same "not a known
service" check, not on rate limiting.)

[commit-and-push]
No proposal files handed off -- nothing to commit.
```

## Acceptance Criteria
- WHEN an issue-investigator run targets https://github.com/mctlhq/seerrsense/issues/6 or any other seerrsense issue THEN the investigator recognizes the repo as a known service and proceeds past the SERVICES check instead of exiting 1 on both the primary and fallback attempts.
