# Requirements: incident-mctl-agents-oauth-quota-exhaustion

## Incident
- ID: argo-mctl-agents-incidents-1784168100-1784168441
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (source=argo-workflows; CronWorkflow `mctl-agents-incidents`
  invoking ClusterWorkflowTemplate `mctl-agents-run`, mode=full)
- Created: 2026-07-16T02:20:41.322462Z
- Summary: mctl-agents-run incident-responder Failed after 134.137772s —
  https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784168100

## Note on slug naming
The instructed slug rule (`incident-` + first 8 characters of the incident ID)
collides for every incident from this source: all IDs share the literal prefix
`argo-mctl-agents-`, so the first 8 characters (`argo-mct`) are identical across
every occurrence. A directory `proposals/incident-argo-mct/` already existed
from a prior run, written for an unrelated incident
(`argo-mctl-agents-implement-1784072700-1784073633`, created 2026-07-15T00:00:34Z).
Reusing that slug here would have silently overwritten that proposal's
requirements/design/tasks. This proposal was written under a descriptive slug
instead to avoid collision; see the final report for a recommendation to fix
the slug rule itself.

## Duplicate incidents covered by this proposal
The same failure signature (mctl-agents-run incident-responder failing after
~100-210s, every single 15/45 cron tick, tenant=admins, service=mctl-agents,
no evidence/labels attached) repeats with no material variation. This proposal
batches the 5 most recent occurrences (all older than 30 minutes at time of
triage) so the shared root cause is fixed once instead of once per duplicate:
- argo-mctl-agents-incidents-1784168100-1784168441 (2026-07-16T02:20:41Z)
- argo-mctl-agents-incidents-1784166300-1784166488 (2026-07-16T01:48:08Z)
- argo-mctl-agents-incidents-1784164500-1784164817 (2026-07-16T01:20:17Z)
- argo-mctl-agents-incidents-1784162700-1784162970 (2026-07-16T00:49:30Z)
- argo-mctl-agents-incidents-1784160900-1784161034 (2026-07-16T00:17:14Z)

At least 16 occurrences of this exact signature were visible in `analyzing`
status at triage time, spanning 2026-07-15T11:47Z through 2026-07-16T02:20Z —
i.e. every 30-minute cron tick for over 14.5 hours straight, with no successful
run in between.

## Evidence
### Labels
No structured labels are attached to these incidents. Unlike AlertManager-
sourced incidents (which carry Prometheus label sets), this source is
`argo-workflows` — direct polling of CronWorkflow/Workflow completion status —
and only exposes id/tenant/service/summary/timestamps.

### Log Snippet
```
mctl_get_service_logs(team=admins, service=mctl-agents, since=6h, lines=200)
  => {"app":"mctl-agents","count":0,"lines":null,"team":"admins"}

mctl_get_workflow_status(workflow_name=mctl-agents-incidents-1784168100)
  => error: "workflow record not found in audit log"

No Loki logs exist for these pods: the mctl-agents-run steps (clone-gitops /
run-orchestrator / commit-and-push / run-fallback) are short-lived Argo Workflow
job pods, not a continuously-scraped `base-service` deployment, so nothing is
shipped to Loki for them. The individual failed Workflow objects have also
already been garbage-collected from the audit log. Diagnosis below is therefore
based on static inspection of the CronWorkflow / ClusterWorkflowTemplate source
and the ExternalSecret manifest that provisions its credentials (both present
in this mctl-gitops checkout), plus a live cross-check against
mctl_list_recent_agent_runs (see design.md).
```

## Acceptance Criteria
- WHEN the change is applied THEN a persistently-failing `mctl-agents-run`
  pipeline raises exactly one clear, human-routed alert after a bounded window
  of no successful runs, instead of silently accumulating one duplicate
  `workflow_failed` incident per 30-minute tick indefinitely.
- WHEN an operator receives that alert THEN the alert body points them
  directly at the Vault path and keys to check
  (`secret/platform/mctl-agents`: `claude-code-oauth-token`,
  `claude-code-oauth-token-2`), which is the actual fix for the underlying
  auth failure (out of scope for this gitops-only proposal).
