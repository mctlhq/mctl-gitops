# Design: incident-90035494

## Diagnosis
This is a downstream symptom of mctl incident f79e783d-3400-4fd1-9656-09125ae3a90e
(ArgoCD application labs-mctl-telegram Degraded), not an independent failure
of the shepherd or of mctl-agents. The shepherd's post-deploy-verify step is
a safety gate: after merging PRs it sleeps 300s for ArgoCD to reconcile, then
checks for any ArgoCD Application that newly became Degraded since the
workflow started (threshold 2026-09-21T23:40:39Z). It found
argocd/labs-mctl-telegram newly Degraded, waited a further 120s grace period
for a possible rolling-update blip, saw it was still Degraded, and correctly
failed the whole run as a precaution -- this is the gate doing its job, not a
bug in the gate.

The timing lines up with incident-5ae3a90e's root cause: labs-mctl-telegram's
one-shot `local-mode-flip-1` Job had two failed pod attempts at 23:51:20Z and
23:51:21Z (transient `Connection refused` against the shared Postgres
cluster) before succeeding at 23:51:37Z, all inside this workflow's
23:40:39Z-00:04Z verification window. No evidence here implicates the
shepherd's own PR merges, mctl-agents code, or any other Application.

## Proposed Fix
No independent fix is needed for mctl-agents or the shepherd workflow itself.
The proposed fix is the one already written for incident-5ae3a90e: remove the
completed one-shot Job `labs-mctl-telegram-local-mode-flip-1` (and its
explanatory comment block) from
`platform-gitops/services/labs/mctl-telegram/values.yaml`, since that Job's
transient failures are what most likely drove labs-mctl-telegram's ArgoCD
health to Degraded during this window. See
`mctl-gitops/proposals/incident-5ae3a90e/` for the full diagnosis and the
exact edit.

If `mctl-gitops/proposals/incident-5ae3a90e` has already been implemented
(merged) by the time this proposal is picked up, no further action is
required here -- this proposal exists so the workflow_failed incident has its
own recorded resolution, not to duplicate the gitops change.

## Scope
None beyond incident-5ae3a90e's change. This proposal intentionally makes no
additional edits, to avoid two PRs racing on the same file.

## Confidence: MEDIUM
The timestamp correlation between the shepherd's post-deploy-verify window
and the flip Job's failed attempts is direct and drawn from the workflow's
own logs, but this agent cannot confirm via kubectl that the flip Job (rather
than some other resource) is what ArgoCD's health aggregation flagged.
