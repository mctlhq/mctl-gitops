# Design: incident-17841348

## Confidence: LOW

## Diagnosis

Two consecutive `shepherd (all open PRs)` runs (16:17 and 19:17 UTC on 2026-07-15) both
failed after almost exactly 8250.6 seconds (delta of 4ms between the two). A duration
match this precise across independent runs, each processing a different set of open PRs,
is not consistent with organic work taking variable time — it is the signature of a fixed
`activeDeadlineSeconds` (or an equivalent step/pod-level timeout) killing the workflow at
a hard-coded ~8250s ceiling regardless of how much work remains.

Both failing runs also carry the exact same defect in their summary text: a literal,
unresolved Argo expression `{{workflow.outputs.parameters.degraded_apps}}` instead of an
actual value. The most likely explanation that ties both observations together: the
`post-deploy-verify` step is what sets the `degraded_apps` output parameter, but the
workflow is killed by the deadline before that step finishes, so the parameter is never
set. The exit-handler/notification template that builds the incident summary then
renders the raw, un-substituted expression because it has no fallback/default for a
missing output parameter.

No Loki logs were available (0 lines over 24h for admins/mctl-agents) and the Argo
Workflow audit record for this run has already aged out, so the exact step name and
kill reason (`DeadlineExceeded` vs pod failure) could not be directly confirmed. The
diagnosis below is inferred from the timing pattern and the broken template, which is
the strongest evidence available.

## Proposed Fix

1. Locate the Argo WorkflowTemplate / CronWorkflow manifest for the `shepherd` operation
   in this repo (search for `shepherd` under the Argo Workflows manifests, likely near
   where `mctl-agents-incidents` / `mctl-agents-issue-poll` templates live). Find the
   `spec.activeDeadlineSeconds` (or per-template `activeDeadlineSeconds`) field.
   - Current value: ~8250 (inferred from the two matching failures).
   - New value: raise to a generous ceiling for an "all open PRs" sweep, e.g. 21600
     (6 hours), or make it scale with PR count if the template supports parameterization.

2. Locate the Sensor/Trigger (or notification-building code) that formats the incident
   summary using `workflow.outputs.parameters.degraded_apps`. Add a default so a missing
   parameter never leaks a raw template expression into a human-facing message, e.g.
   using the Argo Sensor/Sprig default filter:
   - Current: `{{workflow.outputs.parameters.degraded_apps}}`
   - New: `{{=sprig.default("unknown (step did not complete)", workflow.outputs.parameters.degraded_apps)}}`
   (or the equivalent syntax used by the actual templating engine in this manifest —
   verify against neighboring examples in the same file before applying).

## Scope

Minimal. Only touch the `shepherd` workflow's deadline field and the summary template's
parameter substitution. Do not change the `post-deploy-verify` step logic itself unless
step 1 alone does not resolve the recurrence.
