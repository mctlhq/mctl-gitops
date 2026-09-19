# Design: incident-cc221e40

## Diagnosis
labs-agent-worker-preview runs a single replica (replicaCount: 1) with a
per-container cpu limit of 1000m. mctl-telegram's preview-deploy.yml
auto-bumps this worker's image tag on every push to main (see the comment in
services/labs/agent-worker-preview/values.yaml), which triggers a normal
Kubernetes RollingUpdate. With replicaCount=1 the default RollingUpdate
strategy (maxSurge=25%, rounded up to 1 pod) needs to schedule one extra pod
carrying its own 1000m cpu limit before it can retire the old one.

At the time this alert fired, the labs tenant namespace's ResourceQuota for
limits.cpu was already at 11300m of a 12000m ceiling (94% used, ~700m
headroom) — see mctl_get_resource_usage(team=labs) in requirements.md. That
leaves less than the 1000m the surge pod needs, so the new ReplicaSet's pod
is rejected with an exceeded-quota error and never becomes Ready. The old
pod keeps running (explaining the "job invocation finished" log lines seen
through 13:58Z) but the Deployment's rollout stalls, which is exactly what
ArgoCD reports as Degraded and what triggered the separate
KubeDeploymentRolloutStuck alert for the same service (a different incident,
too young to qualify for this run).

Two unrelated mctl-agents shepherd runs (issue-364, issue-305) independently
observed this same app "Still Degraded after 120s grace" during their own
post-deploy-verify step around 13:29Z-13:41Z, confirming the rollout was
already stuck and unrelated to their own changes (see
argo-mctl-agents-shepherd-ac5088f0-1789825245 and
argo-mctl-agents-shepherd-78067ca0-1789825049).

This exact failure mode — a Deployment's RollingUpdate surge pod pushing the
labs tenant over its limits.cpu ResourceQuota, stalling rollouts — is already
documented as a recurring pattern in
platform-gitops/tenants/labs/values.yaml's own quota comment history (five
prior bumps, most recently limits.cpu 6 -> 8 -> 12 for the same class of
"workflow/preview pod stuck Pending" symptom). This is the same class of
problem recurring because headroom was consumed again by the tenant's normal
growth (currently 17 services, 16 pods).

I was not able to directly confirm the underlying Kubernetes "exceeded quota"
FailedCreate event (no kubectl/argocd CLI access from this agent), so this
diagnosis rests on the quota-usage snapshot plus the two independent
post-deploy-verify observations rather than a first-hand event log. The fix
below is the same low-risk, easily-reversible quota bump this tenant has
applied for this exact symptom before.

## Proposed Fix
File: platform-gitops/tenants/labs/values.yaml
Field: tenant.quotas.limits.cpu
Current value: "12"
New value: "14"

This gives headroom for 11300m of current steady-state usage plus the 1000m
a single-replica rolling update's surge pod needs, plus a buffer similar in
size to previous bumps in this file (they consistently leave ~2 cores of
headroom rather than sizing exactly to the observed minimum).

Add a dated comment above the changed line, following the existing style in
this file, e.g.:

```
# Bumped 2026-09-19: limits.cpu was at 11300m/12000m (94% used, ~700m
# headroom) when a routine rolling update of agent-worker-preview (1
# replica, 1000m cpu limit) needed a surge pod and could not get one,
# stalling the rollout and marking the ArgoCD app Degraded (incident
# b1eb40f5). Bump limits.cpu 12 -> 14 for ~2 cores of headroom, matching
# past bumps in this file for the same symptom.
```

## Scope
Minimal. Only the tenant.quotas.limits.cpu field (and its preceding comment)
in platform-gitops/tenants/labs/values.yaml. No service-level values.yaml
files need to change; the stuck rollout should resolve on its own once the
quota is raised and ArgoCD re-syncs / Kubernetes retries pod creation.
