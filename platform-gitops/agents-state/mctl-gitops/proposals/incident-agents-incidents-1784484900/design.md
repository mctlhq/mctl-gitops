# Design: incident-agents-incidents-1784484900

## Confidence: LOW

No Loki logs and no Argo workflow audit record were available for this
specific run. This diagnosis is based on pattern-matching against sibling
incidents and one live observation captured during this triage session.

## Diagnosis

This is one of at least ten recurring `workflow_failed` incidents for the
`mctl-agents` Argo Workflow pipeline (source: argo-workflows) observed over
the past several days, all sharing the same incident ID prefix
(`argo-mctl-agents-...`) and the same `type: workflow_failed`. A prior
incident-responder run already opened a tracking proposal for this exact
issue class: `mctl-gitops/proposals/incident-argo-mct` (status: in-progress),
which lists three candidate root causes: GitHub API/auth failure, Argo
`activeDeadlineSeconds` timeout, and OOMKilled sub-agent containers.

New evidence gathered during this triage session: `mctl_list_recent_agent_runs`
shows a currently-queued `mctl-agents-implement-1784488500` run whose status
message reads `Waiting for argo-workflows/Mutex/mctl-gitops-main-writes lock.
Lock status: 0/1` — i.e. the shared write-mutex for the mctl-gitops repo is
held by another workflow and not available. If this mutex is held longer than
expected (stuck holder, no lock TTL) it would cause any workflow needing it
(including `incidents` and `implement` runs) to queue and eventually fail once
the workflow's own deadline elapses. This is consistent with, and should be
folded into, the "Fix B — Argo workflow timeout" hypothesis already recorded
in `incident-argo-mct`, but adds a more specific candidate cause: lock
contention on `mctl-gitops-main-writes`, not merely an under-sized timeout.

This specific occurrence (147s runtime) is too short to be a full deadline
timeout by itself, so a mutex wait is not the direct cause of this particular
failure — it more likely crashed early (matches Fix A/auth or an unhandled
exception in the incident-responder skill itself). Without logs this cannot be
narrowed further.

## Proposed Fix

No independent fix is proposed here. This incident is a duplicate manifestation
of the already-tracked issue in `incident-argo-mct`. Recommended action:

1. Do not open a second, conflicting investigation — continue work on
   `incident-argo-mct`.
2. When investigating, additionally check for stuck/orphaned holders of the
   `argo-workflows/Mutex/mctl-gitops-main-writes` Mutex (e.g. via
   `argo workflows list -n argo-workflows` or the Argo UI Mutex/Semaphore
   panel) as a contributing cause alongside the three hypotheses already
   listed in `incident-argo-mct/design.md`.

## Scope

None (informational/duplicate). No file changes proposed independently of
`incident-argo-mct`.
