# Design: incident-cc221e40

## Diagnosis
ArgoCD reports the `labs-agent-worker-preview` Application as `Degraded` while `Synced`
(confirmed live at investigation time, `updatedAt: 2026-09-19T14:10:05Z`). No skill matched
this signal because `argocd_app_degraded` has no auto-diagnostic rule. Cross-referencing
Loki logs for the underlying `agent-worker-preview` service shows the existing pod
(`labs-agent-worker-preview-base-service-657bd68fd5-5w7xp`) has continued completing job
invocations without interruption both before and after the incident was created (last seen
job at 13:58:10 UTC, well after the 13:33:31 UTC incident), and no log lines from any other
pod appear in the window. That pattern — ArgoCD Degraded, old pod still healthy and serving
— is the signature of a stuck Deployment rollout: a *new* ReplicaSet's pod never reached
`Ready`, so the old pod was never scaled down, and the Application health stays Degraded
until the rollout is retried or the deadline is manually cleared. A separate, not-yet-30-
minutes-old incident for the same Deployment (`KubeDeploymentRolloutStuck` on
`labs-agent-worker-preview-base-service`) corroborates this reading.

A plausible trigger: at 13:21:57-13:22:11 UTC the worker's background poll loop hit
`connection refused` / `EOF` calling `http://labs-mctl-telegram-preview-base-service:8080/...`
(the `AGENT_API_BASE_URL` dependency configured in this service's own values.yaml), which
lines up with `mctl-telegram-preview`'s own rollout to the same image tag
(`main-2c065a6`) around the same time. This specific values.yaml already documents one prior
incident where a misconfigured `AGENT_API_BASE_URL` "left the pod stuck failing readiness
indefinitely... never Ready either" (see the comment block above the `env:` key) — the same
failure shape, though this time the URL itself is correct and the outage was brief, so a
transient dependency hiccup during a rollout window is a credible cause for the *replacement*
pod's readiness probe (`/readyz`) failing during startup.

I do not have `argocd app get` / `kubectl describe` access to directly inspect the resource
tree and confirm which specific child resource (ReplicaSet/Pod) is unhealthy, so I cannot
rule out a real code regression shipped in image tag `main-2c065a6` instead of a transient
blip.

## Confidence: LOW

## Proposed Fix
File: `platform-gitops/services/labs/agent-worker-preview/values.yaml`
Add a `podAnnotations` block (not currently present) with a restart marker. The
`base-service` Helm chart (`platform-gitops/helm-charts/base-service/templates/deployment.yaml`,
lines 36-38) renders `.Values.podAnnotations` onto the Pod template, so adding/changing this
value changes the pod template hash and forces Kubernetes/ArgoCD to create a fresh
ReplicaSet — the standard "retry the rollout" lever available without touching image, probes,
or resource requests/limits.

Add, after the `automountServiceAccountToken: false` line:
```yaml
podAnnotations:
  rollout-restart-at: "2026-09-19T14:11:18Z"
```

If the Application is still Degraded after this rollout completes (allow a few minutes for
ArgoCD to sync and the new pod to pass its startup/readiness probes), the cause is not
transient and needs a human to run `argocd app get labs-agent-worker-preview` and inspect the
resource tree / new pod's own logs directly — this proposal does not attempt a deeper fix
without that visibility.

## Scope
Minimal. Only adds a `podAnnotations` restart marker to the one service's values.yaml; no
image, probe, resource, or env changes.
