# Tasks: incident-agents-incidents-1784484900

1. [ ] Do not action independently — this incident is a duplicate of the
       already-tracked issue in `mctl-gitops/proposals/incident-argo-mct`
       (status: in-progress). Confirm that proposal's status before doing
       anything else.
2. [ ] When resuming work on `incident-argo-mct`, additionally check for a
       stuck/orphaned holder of the `argo-workflows/Mutex/mctl-gitops-main-writes`
       lock (Argo UI Mutex/Semaphore panel or `argo workflows list -n
       argo-workflows`) as a contributing cause alongside the GitHub
       auth/timeout/OOM hypotheses already listed there.
3. [ ] Once `incident-argo-mct` is resolved and deployed, confirm no further
       `mctl-agents-incidents-*` workflow_failed incidents are created by the
       incident-responder cron for at least 24h.
