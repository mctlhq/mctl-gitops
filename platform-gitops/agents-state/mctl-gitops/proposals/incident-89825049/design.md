# Design: incident-89825049

## Diagnosis
This workflow_failed incident is not about a defect in the shepherd run
itself or in proposal issue-305. The run's own post-deploy-verify step
failed its environment health gate because it found argocd/labs-agent-worker-preview
"Still Degraded after 120s grace" — an app this shepherd run never touched.

The Degraded state has an independently-diagnosed root cause: the labs
tenant namespace's limits.cpu ResourceQuota is exhausted (11300m of 12000m
used, ~700m headroom) while agent-worker-preview (replicaCount=1, cpu limit
1000m) tries to do a routine rolling update. The RollingUpdate surge pod
cannot get the 1000m of cpu limit headroom it needs, so it's rejected by the
quota, the rollout stalls, and ArgoCD reports the app Degraded. Full
diagnosis and evidence is in sibling proposal
mctl-gitops/proposals/incident-cc221e40 (incident
b1eb40f5-a589-4745-a720-5b64cc221e40).

A second, independent shepherd run (issue-364,
argo-mctl-agents-shepherd-ac5088f0-1789825245) hit the identical
post-deploy-verify failure a few minutes later, which corroborates that this
is a standing environment condition, not something particular to this one
workflow or proposal.

## Proposed Fix
Same fix as sibling proposal incident-cc221e40: raise
tenant.quotas.limits.cpu from "12" to "14" in
platform-gitops/tenants/labs/values.yaml, so the labs tenant namespace has
enough limits.cpu headroom for a routine single-replica rolling update's
surge pod. See incident-cc221e40/design.md for the full diagnosis and the
exact comment text to add.

Once labs-agent-worker-preview's rollout can complete and its ArgoCD health
returns to Healthy, this shepherd's post-deploy-verify gate will stop
flagging it, and future shepherd runs (including any retry of issue-305)
will no longer be blocked by this unrelated app.

## Scope
Minimal, and identical to incident-cc221e40: only the tenant.quotas.limits.cpu
field in platform-gitops/tenants/labs/values.yaml. Do not modify the
shepherd/post-deploy-verify workflow logic and do not touch
services/labs/agent-worker-preview/values.yaml.
