# Requirements: mctl-agents-image-tag-stale-post-slug-fix

## Incident
- ID: argo-mctl-agents-incidents-1784501100-1784501253
- Tenant: admins
- Service: mctl-agents
- Alert: workflow_failed (Argo Workflows) — mctl-agents-run incident-responder
- Created: 2026-07-19T22:47:33.198749Z
- Summary: mctl-agents-run incident-responder Failed after 148.000069s — https://workflows.mctl.ai/workflows/argo-workflows/mctl-agents-incidents-1784501100

### Duplicate incidents (same root cause, resolved together in this run)
- argo-mctl-agents-incidents-1784499300-1784499420 (created 2026-07-19T22:17:00.705692Z)
- argo-mctl-agents-incidents-1784497500-1784497653 (created 2026-07-19T21:47:33.810368Z)
- argo-mctl-agents-incidents-1784495700-1784495875 (created 2026-07-19T21:17:55.750624Z)
- argo-mctl-agents-incidents-1784493900-1784494061 (created 2026-07-19T20:47:41.646351Z)

Note: additional analyzing incidents of the same shape exist beyond this
run's 5-incident cap, both older (back to 2026-07-15) and one too-recent to
qualify by the 30-minute age rule (argo-mctl-agents-incidents-1784502900,
created 2026-07-19T23:17:37Z). A follow-up incident-responder run should
re-triage the remainder once this fix is confirmed deployed; most of them
should turn out to be duplicates of this same root cause.

## Evidence

### Labels
- source: argo-workflows
- type: workflow_failed
- severity: warning
- status: analyzing (prior to this run)
- tenant: admins
- service: mctl-agents

### Log Snippet
```
mctl_get_service_logs(team=admins, service=mctl-agents, since=24h) -> 0 lines
  (Loki has no application logs for mctl-agents; the incident-responder and
  implementer both run as short-lived Argo Workflow pods, not scraped
  long-running services.)

mctl_get_workflow_status(workflow_name=mctl-agents-incidents-1784501100) ->
  "workflow record not found in audit log" (cron-submitted CronWorkflow runs
  are not tracked in the operator audit log used by that tool — same
  limitation noted in the incident-argo-id-slug-collision proposal below).
```

### Repository evidence (root cause already diagnosed, fix merged, deploy step missing)
```
$ cat agents-state/mctl-agents/proposals/incident-argo-id-slug-collision/.status.yaml
status: merged
updated_at: '2026-07-19T20:01:11Z'
pr: https://github.com/mctlhq/mctl-agents/pull/61
merge_commit: e316c46341b6fcc3b767a2035c09cee6fcd055d2

$ grep -n "image:" platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-run.yaml
171:        image: ghcr.io/mctlhq/mctl-agents:1.17.0
```
PR #61 (merged 2026-07-19T20:01:11Z) fixed the slug-collision bug that made
every argo-workflows-sourced incident resolve to the same occupied proposal
directory (`incident-argo-mct`), which was the root cause of the
incident-responder CronWorkflow failing on every tick since at least
2026-07-18T13:24. Task 6 of that proposal's tasks.md explicitly calls for
bumping the `mctl-agents` image tag in this same file once the fix is
released, "so the CronWorkflow picks it up." That task was never executed —
the running image is still `1.17.0`, the same tag that was in place before
the fix merged.

### Evidence the CronWorkflow is still running the unpatched image
All five incidents listed above (this incident and its four duplicates) were
created strictly *after* the 20:01:11Z merge:
- 20:47:41Z, 21:17:55Z, 21:47:33Z, 22:17:00Z, 22:47:33Z — five consecutive
  incident-responder ticks, all failed, all after the fix was merged.

This is inconsistent with "the code fix resolved the issue" and consistent
with "the fix is merged but not yet deployed": the CronWorkflowTemplate
still pins `ghcr.io/mctlhq/mctl-agents:1.17.0`, so every tick keeps running
the pre-fix binary and keeps hitting the same slug collision against the
pre-existing `agents-state/mctl-gitops/proposals/incident-argo-mct/`
directory (still `status: in-progress`, untouched, as instructed by the
prior proposal).

By contrast, `mctl-agents-implement` cron ticks in the same window
(23:15–23:40Z) all succeeded — consistent with the implement pipeline never
exercising the argo-workflows-incident slug path at all, so it is unaffected
by whether the image is patched.

## Acceptance Criteria
- WHEN the `mctl-agents` image tag in
  `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-run.yaml`
  is bumped to a released tag that contains commit `e316c46341b6fcc3b767a2035c09cee6fcd055d2`
  (PR #61) THEN the `mctl-agents-run incident-responder` CronWorkflow
  (schedule `15,45 * * * *`) completes with status Succeeded on its next
  scheduled tick.
- WHEN that tick runs THEN it does not write to
  `agents-state/mctl-gitops/proposals/incident-argo-mct/` (the pre-existing,
  unrelated, still-open proposal) for any of the incidents in this list.
