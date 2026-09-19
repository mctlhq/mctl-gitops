# Design: incident-3a73ead4

## Diagnosis
`mctl_get_resource_usage` for team `labs` shows `limits.cpu` at 11300m used
out of a 12000m quota (94%), with only ~700m of headroom. The `labs-agent-
worker-preview` deployment (`platform-gitops/services/labs/agent-worker-
preview/values.yaml`) has `resources.limits.cpu: 1000m` and does not set
`strategy`, so it renders through the shared `base-service` chart's default
(`strategy: {}` in `platform-gitops/helm-charts/base-service/values.yaml`),
which Kubernetes resolves to `RollingUpdate` with the default 25%
surge/unavailable. For `replicaCount: 1` that rounds to `maxSurge: 1,
maxUnavailable: 0` -- every rollout (this service's image tag is auto-bumped
on every push to main, per the comment in its values.yaml) must schedule a
second, brand-new 1000m-cpu-limit pod *before* the existing one terminates.

That second pod would push namespace `limits.cpu` usage to ~12300m, over the
12000m ResourceQuota ceiling. The pod is admitted by the scheduler but the
namespace ResourceQuota rejects it, so it sits unschedulable and the
Deployment can never reach the desired ready-replica count for the new
ReplicaSet. That is exactly `KubeDeploymentRolloutStuck`, and ArgoCD reports
the Application `Degraded` because the live state (old ReplicaSet still
serving, new ReplicaSet stuck at 0/1) never converges to the desired state.
The currently-running pod is unaffected and keeps processing jobs normally
(see requirements.md log snippet), which is consistent with this being a
scheduling deadlock rather than an application crash -- and explains why no
skill matched: neither alert's signal maps to an application-level symptom.

No skill matched because this is a platform capacity-vs-rollout-strategy
interaction, not a change in application behavior, so there was nothing in
the service's own logs for a generic skill to key off.

## Proposed Fix
`platform-gitops/services/labs/agent-worker-preview/values.yaml`: add an
explicit `strategy` block so the rollout replaces the single pod instead of
surging a second one alongside it:

```yaml
strategy:
  type: Recreate
```

This is a chart-supported field (see the `{{- with .Values.strategy }}`
block in `platform-gitops/helm-charts/base-service/templates/deployment.yaml`,
which passes `.Values.strategy` through verbatim as the Deployment's
`spec.strategy`). With `Recreate`, the existing pod terminates first,
freeing its 1000m cpu-limit reservation, before the replacement pod is
created -- peak usage during a rollout no longer exceeds the current
steady-state usage, so the ResourceQuota is never a blocker. `replicaCount`
is 1 and this is a background job-poller with no ingress (see the chart
comment "Chart: base-service (ingress disabled)"), so the brief gap between
old-pod-termination and new-pod-ready during a rollout is acceptable --
unlike a request-serving service, nothing is dropped, it just resumes
polling slightly later.

This does not touch `resources.limits.cpu: 1000m`, which the file's own
2026-08-03 comment explicitly warns not to trim from a steady-state sample
alone (throttling was observed even at 500m). It also does not touch the
namespace CPU quota itself, which is a separate, larger decision outside
this single alert's minimal scope.

## Confidence: LOW
Diagnosis is based on quota arithmetic and chart defaults observed via
`mctl_get_resource_usage` and the gitops repo, not a direct `kubectl
describe` of the stuck ReplicaSet/pod (this agent has no shell/cluster
access). The implementer should confirm, if possible, that the stuck
ReplicaSet's pod is in fact `Pending` with a `FailedCreate`/exceeded-quota
event before merging, and re-check current `limits.cpu` usage in case it has
changed.

## Scope
Minimal. Only adds the `strategy` field to this one service's values.yaml.
