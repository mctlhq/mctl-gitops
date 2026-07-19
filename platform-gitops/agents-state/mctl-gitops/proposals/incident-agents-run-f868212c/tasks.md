# Tasks: incident-agents-run-f868212c

1. [ ] Do not action independently — this incident is a duplicate of the
       already-tracked issue in `mctl-gitops/proposals/incident-argo-mct`
       (status: in-progress). Confirm that proposal's status before doing
       anything else.
2. [ ] When resuming work on `incident-argo-mct`, open the Argo UI link for
       this run (https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-run-f868212c)
       and check whether the step trace shows time waiting on the
       `mctl-gitops-main-writes` Mutex before failing.
3. [ ] Once `incident-argo-mct` is resolved and deployed, confirm no further
       elevated-runtime `workflow_failed` incidents recur for the
       incident-responder pipeline for at least 24h.
