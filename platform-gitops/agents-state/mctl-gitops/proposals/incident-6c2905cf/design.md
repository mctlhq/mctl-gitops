# Design: incident-6c2905cf

## Diagnosis
Same root cause as sibling proposal `mctl-gitops/proposals/incident-3a73ead4`
(incident 18b0c978-abb1-4664-a479-dcae3a73ead4), which fired 15 minutes after
this one for the same workload. Summarized here:

`mctl_get_resource_usage` for team `labs` shows `limits.cpu` at 11300m used
out of a 12000m quota (94%), with only ~700m of headroom. The `labs-agent-
worker-preview` deployment (`platform-gitops/services/labs/agent-worker-
preview/values.yaml`) has `resources.limits.cpu: 1000m` and does not set
`strategy`, so it renders through the shared `base-service` chart's default
(`strategy: {}`), which Kubernetes resolves to `RollingUpdate` with the
default 25% surge/unavailable. For `replicaCount: 1` that rounds to
`maxSurge: 1, maxUnavailable: 0` -- every rollout (this service's image tag
is auto-bumped on every push to main) must schedule a second, brand-new
1000m-cpu-limit pod before the existing one terminates.

That second pod would push namespace `limits.cpu` usage to ~12300m, over the
12000m ResourceQuota ceiling. The pod is rejected by the namespace
ResourceQuota and sits unschedulable, so the Deployment never reaches the
desired ready-replica count for the new ReplicaSet -- exactly
`KubeDeploymentRolloutStuck`. The currently-running pod is unaffected and
keeps processing jobs normally (see requirements.md log snippet), consistent
with a scheduling deadlock rather than an application crash, which explains
why no skill matched (this is a platform capacity/rollout-strategy
interaction, not an application-level symptom in the service's own logs).

## Proposed Fix
Identical to the sibling proposal -- this is one root cause manifesting as
two alerts. `platform-gitops/services/labs/agent-worker-preview/values.yaml`:
add an explicit `strategy` block so the rollout replaces the single pod
instead of surging a second one alongside it:

```yaml
strategy:
  type: Recreate
```

This is a chart-supported field (see the `{{- with .Values.strategy }}`
block in `platform-gitops/helm-charts/base-service/templates/deployment.yaml`).
With `Recreate`, the existing pod terminates first, freeing its 1000m
cpu-limit reservation, before the replacement pod is created -- peak usage
during a rollout no longer exceeds current steady-state usage, so the
ResourceQuota is never a blocker. `replicaCount` is 1 and this is a
background job-poller with no ingress, so the brief gap during a rollout is
acceptable.

This does not touch `resources.limits.cpu: 1000m` (explicitly flagged in the
file's own comments as not to be trimmed from a steady-state sample alone)
or the namespace CPU quota itself.

If the sibling proposal `mctl-gitops/proposals/incident-3a73ead4` is applied
first, this proposal's change is already satisfied -- the implementer should
check for an existing `strategy: {type: Recreate}` in this file before
re-adding it.

## Confidence: LOW
Diagnosis is based on quota arithmetic and chart defaults observed via
`mctl_get_resource_usage` and the gitops repo, not a direct `kubectl
describe` of the stuck ReplicaSet/pod (this agent has no shell/cluster
access). The implementer should confirm, if possible, that the stuck
ReplicaSet's pod is in fact `Pending` with a `FailedCreate`/exceeded-quota
event before merging, and re-check current `limits.cpu` usage in case it has
changed.

## Scope
Minimal. Only adds the `strategy` field to this one service's values.yaml
(shared with the sibling proposal -- a single edit resolves both incidents).
