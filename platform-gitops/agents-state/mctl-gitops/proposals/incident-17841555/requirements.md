# Requirements: incident-17841555

## Incident
- ID: argo-mctl-agents-incidents-1784155500-1784155659
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (argo-workflows) — incident-responder (mctl-agents-incidents)
- Created: 2026-07-15T22:47:39.458701Z
- Summary: mctl-agents-run incident-responder Failed after 154.431270s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784155500

## Duplicate incidents (same root cause, same run pattern)
- ID: argo-mctl-agents-incidents-1784153700-1784153892, Created 2026-07-15T22:18:12.846463Z, Failed after 186.793567s
- ID: argo-mctl-agents-incidents-1784151900-1784152128, Created 2026-07-15T21:48:48.870754Z, Failed after 104.967038s
- ID: argo-mctl-agents-incidents-1784150100-1784150317, Created 2026-07-15T21:18:37.266190Z, Failed after 210.911712s
- ID: argo-mctl-agents-incidents-1784148300-1784148419, Created 2026-07-15T20:46:59.833338Z, Failed after 114.820357s
These four are resolved as duplicates referencing this proposal; see report.

Note: 15 further incidents with this same signature ("mctl-agents-run incident-responder
Failed") exist from earlier on 2026-07-15 (06:49-13:18 UTC and 20:29 UTC), still in
`analyzing` status. This run is capped at 5 incidents, so the remaining 15 are left for
a subsequent run to resolve against this same proposal rather than creating near-duplicate
proposal directories.

## Evidence
### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- tenant: admins
- service: mctl-agents
- operation: mctl-agents-incidents (the incident-responder's own scheduled cron workflow —
  this incident is a report of the incident-responder's own execution failing)

### Log Snippet
```
No log lines available from Loki: mctl_get_service_logs(team=admins, service=mctl-agents,
since=24h) returned 0 lines, a window spanning all 20 known failures of this workflow.
Argo Workflow audit lookup for mctl-agents-incidents-1784155500 failed: "workflow record
not found in audit log" (run has already aged out of the audit retention window).

Failure durations for the 5 incidents processed this run (variable, not a fixed-deadline
signature — contrast with the ~8250.6s identical-duration pattern documented in
incident-17841348/design.md):
  154.43s, 186.79s, 104.97s, 210.91s, 114.82s
(The full 20-incident set visible via mctl_list_incidents ranges 103.8s-210.9s, all
different — inconsistent with a single hard activeDeadlineSeconds kill.)

Timeline: failures of this operation clustered in two windows on 2026-07-15
(06:49-13:18 UTC and 20:29-22:47 UTC, 20 occurrences total). Per
mctl_list_recent_agent_runs, the same mctl-agents-incidents cron operation has since run
on 2026-07-16T05:45:00Z (status "succeeded") and 2026-07-16T06:15:00Z (status
"submitted"), with no failures recorded. Whatever caused the 2026-07-15 failures does
not appear to be reproducing at the time of this report.

Separately, mctl_list_recent_agent_runs shows a concurrent mctl-agents-implement run
(submitted 2026-07-16T06:15:00Z) with message "Waiting for argo-workflows/Mutex/
mctl-gitops-main-writes lock. Lock status: 0/1" — live, current confirmation that this
shared mutex, used when mctl-agents workflows write to the gitops repo (proposals and
.status.yaml files are written under platform-gitops/agents-state/), is a real and
currently active point of contention in this cluster. The incident-responder operation
also writes to this same tree, so contention on `mctl-gitops-main-writes` is a plausible
contributor to the variable-duration failures, though this is not confirmed by a
captured stack trace (see design.md Confidence note).
```

## Acceptance Criteria
- WHEN the mctl-agents-incidents (incident-responder) cron workflow runs THEN it
  completes without error, or fails fast with a specific, retrievable, logged reason
  rather than an opaque workflow_failed with no recoverable log line or audit record.
- WHEN it needs to write to the gitops repo under contention on
  `mctl-gitops-main-writes` THEN it retries with backoff instead of failing the entire
  run outright.
- WHEN a future run of this workflow fails THEN both `mctl_get_service_logs` and
  `mctl_get_workflow_status` return usable diagnostic detail for it.
