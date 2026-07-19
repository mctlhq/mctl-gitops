# Tasks: incident-agents-incidents-1784472300

1. [ ] Do not action independently — this incident is a duplicate of the
       already-tracked issue in `mctl-gitops/proposals/incident-argo-mct`
       (status: in-progress). Confirm that proposal's status before doing
       anything else.
2. [ ] Once `incident-argo-mct` is resolved and deployed, confirm no further
       `mctl-agents-incidents-*` workflow_failed incidents are created by the
       incident-responder cron for at least 24h.
