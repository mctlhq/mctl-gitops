# Design: incident-agents-incidents-1784515500

## Confidence: LOW
No Loki logs and no Argo workflow audit record were available for this
specific run (see Evidence above). Diagnosis is by signature match against
already-triaged incidents in this same repo, not direct observation of this
run's failure.

## Diagnosis
Duplicate manifestation of the recurring `mctl-agents` `workflow_failed`
incident class already tracked in
`mctl-gitops/proposals/incident-mctl-agents-oauth-quota-exhaustion`
(status: implemented — added a `MctlAgentsPipelineStale` VictoriaMetrics
alert routed to the `telegram` receiver, but explicitly did NOT fix the
underlying credential problem, which requires an out-of-band Vault reseed of
`secret/platform/mctl-agents: claude-code-oauth-token` /
`claude-code-oauth-token-2` and is not achievable via a GitOps PR) and in
`mctl-gitops/proposals/incident-argo-mct` (status: in-progress).

This run's 178.297600s duration falls in the ~100-210s fast-fail band
associated with that OAuth-exhaustion signature, not the ~300-1250s band
seen when the cause is instead lock contention on the
`argo-workflows/Mutex/mctl-gitops-main-writes` mutex (see
`incident-agents-run-f868212c`). A separate slug-collision bug that could
independently have wedged this same CronWorkflow
(`mctl-agents/proposals/incident-argo-id-slug-collision`) was already fixed
and merged (mctl-agents PR #61, merged 2026-07-19T20:01:11Z) — this
incident was created afterwards, so that specific bug is unlikely to be the
cause here.

Live corroborating signal at triage time (2026-07-20T04:49Z):
`mctl_list_recent_agent_runs` shows the sibling `mctl-agents-implement`
pipeline succeeding repeatedly in the most recent window (04:15-04:40), so
whatever is failing is specific to the `mctl-agents-incidents` CronWorkflow
tick (or intermittent/credential-window-dependent), not a total platform
outage.

## Proposed Fix
No independent fix is proposed here. This incident is a duplicate of the
already-tracked, already-alerted issue class in
`incident-mctl-agents-oauth-quota-exhaustion` and `incident-argo-mct`. Do
not action a new GitOps change for this specific incident — doing so would
fragment the fix across many near-identical proposals instead of the one
place already tracking it.

## Scope
None (informational/duplicate). No file changes proposed independently of
`incident-mctl-agents-oauth-quota-exhaustion` / `incident-argo-mct`.
