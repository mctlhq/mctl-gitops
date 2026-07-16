# Design: incident-17841222

## Confidence: LOW

## Diagnosis

This `issue-poll` run took ~4.125 hours (14850.6s) before being marked Failed, which is
a large outlier against the normal cadence observed for this cron operation today
(runs completing in minutes, well inside their 30-minute scheduling window). A routine
polling operation taking over 4 hours points to a hang rather than genuine work —
candidates include: an unbounded retry/backoff loop against the GitHub API, a pagination
cursor that never advances, or a wait on a cluster-level lock/mutex that was held by
another workflow for an extended period.

The last point has a concrete, current corroborating data point: at the time this
report was written, a separate mctl-agents-implement run was observed in
`mctl_list_recent_agent_runs` sitting in "submitted" status with the message
"Waiting for argo-workflows/Mutex/mctl-gitops-main-writes lock. Lock status: 0/1" —
confirming that a shared mutex in this cluster can be held long enough to visibly
block other agent workflows right now. If issue-poll also acquires this (or a related)
mutex before writing anything to the gitops repo, a long-held lock would fully explain
a multi-hour stall with no forward progress and no distinguishing log output.

No Loki logs were available for mctl-agents over a 24h window, and the Argo Workflow
audit record for this specific run has already aged out of retention, so the exact
blocking point could not be directly confirmed. This diagnosis is inferred from timing
and a live, currently-observable analog (the mutex wait above), not a captured
stack trace or log line.

## Proposed Fix

1. Locate the Argo WorkflowTemplate / CronWorkflow manifest for `issue-poll` in this
   repo and check whether it has an explicit `activeDeadlineSeconds`.
   - If unset or unbounded: add one, e.g. 1800 (30 minutes) to match the cron cadence,
     so a hung run fails fast and the next scheduled run is not skipped or delayed.
   - If already set near 14850s: lower it to something closer to the normal-run
     baseline (minutes) and treat the current value as the bug.

2. If issue-poll acquires the same `mctl-gitops-main-writes` mutex used by
   mctl-agents-implement (verify in the workflow manifest's `synchronization` block):
   consider whether issue-poll needs that mutex at all (it should only be read-only
   polling of issues, not writing to gitops main). If it does not need the lock,
   remove the `synchronization` requirement from the issue-poll template so it cannot
   be blocked by unrelated implement/shepherd runs holding the same mutex.

3. If a Python-level hang is confirmed instead (via Argo UI logs, once accessible),
   escalate the root cause to a proposal targeting `mctl-agents` (the Python
   orchestrator) for a bounded retry/pagination fix, referencing this incident.

## Scope

Minimal. Start with the `activeDeadlineSeconds` bound (item 1) since it is safe,
config-only, and improves failure signal regardless of the true root cause. Only
proceed to the mutex/synchronization change (item 2) if the manifest confirms
issue-poll actually shares that lock.
