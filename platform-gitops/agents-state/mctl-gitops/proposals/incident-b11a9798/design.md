# Design: incident-b11a9798

## Confidence: LOW
No Loki logs and no Argo workflow audit record were available for this
specific run (see Evidence in requirements.md). Diagnosis is by signature
match (failure duration, occurrence pattern) against already-triaged
incidents of the same recurring class tracked elsewhere in this repo, not
direct observation of this run's failure.

## Diagnosis
This incident tracks repeated `workflow_failed` events for the
`mctl-agents-incidents` CronWorkflow tick running in `incident-responder`
mode — i.e. the same pipeline that is triaging incidents right now,
including this one. It has fired 7 times over roughly 3.5 hours
(2026-07-24T23:17Z to 2026-07-25T02:18Z), each completing in ~135s (this
occurrence: 135.070697s). That duration falls in the ~100-210s fast-fail
band already associated with the `claude-code-oauth-token` quota/auth
exhaustion signature documented in
`mctl-gitops/proposals/incident-mctl-agents-oauth-quota-exhaustion`
(status: implemented — added a `MctlAgentsPipelineStale` VictoriaMetrics
alert, but explicitly did not fix the underlying credential problem, which
requires an out-of-band Vault reseed of `secret/platform/mctl-agents:
claude-code-oauth-token` / `claude-code-oauth-token-2` and is not
achievable via a GitOps PR). It is not in the ~300-1250s band associated
with `argo-workflows/Mutex/mctl-gitops-main-writes` lock contention (see
`mctl-gitops/proposals/incident-argo-mct`, status: in-progress).

That same referenced proposal calls out the self-referential failure mode
directly: a credential problem on this exact CronWorkflow "should have
paged a human once has instead silently produced [many] duplicate,
evidence-free workflow_failed incidents that pile up in analyzing with
nothing able to triage them (the incident-responder is the very pipeline
that is down)." This run (the one writing this proposal) evidently
succeeded, which is consistent with intermittent recovery (token quota
window resetting, or the primary/fallback OAuth split succeeding on some
ticks and not others) rather than a permanent outage — see
`incident-1820e6ee` (this same triage pass) for the sibling "full" pipeline
incident with an identical fast-fail signature.

## Proposed Fix
No independent fix is proposed here. This incident is a duplicate
manifestation of the already-tracked, already-alerted issue class in
`incident-mctl-agents-oauth-quota-exhaustion` (alerting shipped) and
`incident-argo-mct` (timeout/OOM/auth investigation in progress for the
sibling `implement` pipeline). Opening a new independent GitOps change here
would fragment the fix across many near-identical proposals instead of the
one place already tracking it. The operator should verify Vault
`secret/platform/mctl-agents: claude-code-oauth-token` /
`claude-code-oauth-token-2` state, per the existing proposal's tasks — this
is the actual fix for the recurring failures of this specific CronWorkflow.

## Scope
None (informational/duplicate). No file changes proposed independently of
`incident-mctl-agents-oauth-quota-exhaustion` / `incident-argo-mct`.
