# Requirements: incident-17841222

## Incident
- ID: argo-mctl-agents-issue-poll-1784122200-1784137072
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (argo-workflows) — issue-poll
- Created: 2026-07-15T17:37:52.887521Z
- Summary: mctl-agents issue-poll Failed after 14850.638502s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-issue-poll-1784122200

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- tenant: admins
- service: mctl-agents
- operation: mctl-agents-issue-poll

### Log Snippet
```
No log lines available from Loki (mctl-agents / admins returned 0 lines for a 24h window).
Argo Workflow audit record for mctl-agents-issue-poll-1784122200 not queryable (workflow
older than the audit retention window at query time).

Duration observation: 14850.638502s = ~4.125 hours before this run was marked Failed.
For comparison, other issue-poll cron runs observed today (2026-07-16) via
mctl_list_recent_agent_runs completed and reported "succeeded" within the same
30-minute cron cadence window (e.g. mctl-agents-issue-poll-1784179800 and
mctl-agents-issue-poll-1784178900, both submitted and succeeded inside a ~15 minute
span). A routine issue-poll run taking 4+ hours is a strong outlier versus that normal
baseline, consistent with a hang (e.g. blocked on an external API call, pagination
loop that never advances, or a lock/mutex wait) rather than a deliberate long-running
operation.

Separately, at the time this report was generated, mctl_list_recent_agent_runs showed a
currently in-flight mctl-agents-implement run (submitted 2026-07-16T05:45:00Z) with
message: "Waiting for argo-workflows/Mutex/mctl-gitops-main-writes lock. Lock status:
0/1" — live, current evidence that mctl-agents workflows in this cluster can and do
block for extended periods on a contended mutex. This supports (but does not confirm)
a lock-wait hang as one plausible cause of the 4+ hour issue-poll run.
```

## Acceptance Criteria
- WHEN issue-poll runs THEN it completes within a bounded time (minutes, not hours)
  consistent with its normal cron cadence baseline.
- WHEN issue-poll cannot make progress (blocked on a lock, rate limit, or external API)
  THEN it fails fast with an actionable error rather than silently hanging for hours.
