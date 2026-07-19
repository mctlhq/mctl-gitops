# Tasks: incident-agents-daily-1784332800

1. [ ] Do not action independently — this incident is a duplicate of the
       already-tracked issue in `mctl-gitops/proposals/incident-argo-mct`
       (status: in-progress). Confirm that proposal's status before doing
       anything else.
2. [ ] When resuming work on `incident-argo-mct`, open the Argo UI link for
       this run (https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-daily-1784332800)
       and identify which sub-step of the "full" DAG failed, and whether it
       was blocked on the `mctl-gitops-main-writes` Mutex.
3. [ ] Once `incident-argo-mct` is resolved and deployed, confirm no further
       `mctl-agents-daily-*` workflow_failed incidents recur for at least one
       full daily cycle.
