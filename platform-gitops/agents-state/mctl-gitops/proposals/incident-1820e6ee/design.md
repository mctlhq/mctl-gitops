# Design: incident-1820e6ee

## Confidence: LOW
No Loki logs and no Argo workflow audit record were available for this
specific run (see Evidence in requirements.md). Diagnosis is by signature
match (failure duration) against already-triaged incidents of the same
recurring class tracked elsewhere in this repo, not direct observation of
this run's failure.

## Diagnosis
This is the "full" daily `mctl-agents-run` pipeline (fans out across
incidents, implement, issue-poll, reconcile, and shepherd sub-steps),
Failed after 198.480406s. That duration falls in the ~100-210s fast-fail
band already associated with the `claude-code-oauth-token` quota/auth
exhaustion signature documented in
`mctl-gitops/proposals/incident-mctl-agents-oauth-quota-exhaustion`
(status: implemented — added a `MctlAgentsPipelineStale` VictoriaMetrics
alert, but explicitly did not fix the underlying credential problem,
which requires an out-of-band Vault reseed of `secret/platform/mctl-agents:
claude-code-oauth-token` / `claude-code-oauth-token-2` and is not
achievable via a GitOps PR). It is not in the ~300-1250s band associated
with `argo-workflows/Mutex/mctl-gitops-main-writes` lock contention (see
`mctl-gitops/proposals/incident-argo-mct`, status: in-progress).

A second sibling incident from this same triage pass,
`mctl-agents/proposals/incident-b11a9798` (source incident
`argo-mctl-agents-incidents-1784934900-1784935041`, the `incident-responder`
tick, occurrence_count 7 over ~3.5 hours), Failed after 135.070697s — also
in the fast-fail band, and consistent with the same shared-credential
signature (the "full" run's incidents sub-step and the standalone
`mctl-agents-incidents` CronWorkflow draw from the same OAuth token, per
`cwft-mctl-agents-run.yaml`'s own comments quoted in the referenced
proposal).

## Proposed Fix
No independent fix is proposed here. This incident is a duplicate
manifestation of the already-tracked, already-alerted issue class in
`incident-mctl-agents-oauth-quota-exhaustion` (alerting shipped) and
`incident-argo-mct` (timeout/OOM/auth investigation in progress for the
sibling `implement` pipeline). Opening a new independent GitOps change here
would fragment the fix across many near-identical proposals instead of the
one place already tracking it. The operator should verify Vault
`secret/platform/mctl-agents: claude-code-oauth-token` /
`claude-code-oauth-token-2` state, per the existing proposal's tasks.

## Scope
None (informational/duplicate). No file changes proposed independently of
`incident-mctl-agents-oauth-quota-exhaustion` / `incident-argo-mct`.
