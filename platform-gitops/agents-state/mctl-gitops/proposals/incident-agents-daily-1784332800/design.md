# Design: incident-agents-daily-1784332800

## Confidence: LOW

No Loki logs and no Argo workflow audit record were available for this
specific run.

## Diagnosis

Duplicate manifestation of the recurring `mctl-agents` `workflow_failed`
issue class already tracked in `mctl-gitops/proposals/incident-argo-mct`
(status: in-progress). This is the "full" daily pipeline run, which fans out
across multiple sub-workflows (incidents, implement, issue-poll, reconcile,
shepherd) and had the longest runtime in this batch (~8.5 minutes). A
sub-workflow (most plausibly `implement`, which needs the shared
`mctl-gitops-main-writes` write lock) blocking or timing out would explain a
failure of the aggregate "full" run at this duration. See
`incident-agents-incidents-1784484900/design.md` for the live Mutex
lock-contention observation from this triage session.

## Proposed Fix

No independent fix is proposed here. This incident is a duplicate of the
already-tracked issue in `incident-argo-mct`. When investigating, check which
sub-step of the "full" DAG failed via the Argo UI link in the incident
summary, and confirm whether it was blocked on `mctl-gitops-main-writes`.

## Scope

None (informational/duplicate). No file changes proposed independently of
`incident-argo-mct`.
