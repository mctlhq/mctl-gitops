# Requirements: incident-93710529

## Incident
- ID: argo-mctl-agents-shepherd-daa57eff-1793710529
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed
- Created: 2026-11-03T12:55:29.699827Z

### Summary
```
shepherd shepherd issue-986-feat-review-review-worker-producer-for-a Failed after 440.351232s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-shepherd-daa57eff
```

## Evidence
### Labels
```
fingerprint: workflow_failed:shepherd:mctl-agents:issue-986-feat-review-review-worker-producer-for-a
source: argo-workflows
severity: warning
```

### Log Snippet
```
shepherd: skipping mctl-academy (SHEPHERD_SKIP_SERVICES; owned by another PR lifecycle)
Found 1 proposal(s) to evaluate (budget cap $5.00):
  - mctl-agents/issue-986-feat-review-review-worker-producer-for-a [implemented] attempts=0
warn: gh graphql failed for mctlhq/mctl-agents#990: gh: No server is currently available to service your request. Sorry about that. Please try resubmitting your request and contact us if the problem persists. (HTTP 503)
=== Shepherd summary ===
mctl-agents/issue-986-feat-review-review-worker-producer-for-a: wait  ERROR: could not fetch PR snapshot
nothing to hand off
--- assert-attempt step ---
shepherd attempt: Failed   fallback attempt: Failed
Neither the primary attempt nor the account-2 fallback succeeded -- no proposal was actually advanced this tick.
Most often the Claude five_hour usage limit / HTTP 429 on both accounts, or token-2 unset.
```

## Acceptance Criteria
- WHEN the GitHub GraphQL API returns a transient 5xx for the PR snapshot THEN the shepherd retries with backoff before reporting the tick as failed.
- WHEN no proposal was advanced because of a snapshot fetch error THEN the assert-attempt message names that cause rather than only usage limits.
