# Design: incident-b22f782f

## Confidence: LOW

## Diagnosis
The `argocd_sync_failed` skill already flagged this as a low-confidence,
non-fixable Degraded status with no auto-recognizable signature, and by the
time this proposal was written the ArgoCD app had already returned to
Healthy/Synced on its own. The only concrete pattern visible in the fetched
logs is that `labs-pelican-proxy-staging` cycled through four different pod
hashes (four new ReplicaSets) within about 26 minutes, each one performing a
full login to the upstream Libertex account and reseeding its in-memory
catalog from R2 before serving traffic. No error, crash, or OOM lines are
present in the fetched window, so the root cause of the repeated
rollouts/restarts themselves could not be pinned down from logs alone —
only that the pod is doing real, non-trivial startup work (network login +
catalog seed) every time it restarts, which is a plausible source of a
transient Degraded/Progressing health reading if it ever runs slower than
usual (e.g. a slow upstream login) and outruns the default readiness probe's
grace period. The default `base-service` chart readiness probe grace is
`initialDelaySeconds: 5` + `periodSeconds: 10` * `failureThreshold: 3` ≈ 35s
before Kubernetes marks the pod NotReady, which ArgoCD then reflects as
Degraded/Progressing.

This is a LOW-confidence diagnosis: it explains a plausible mechanism for a
transient Degraded reading but does not identify why the pod restarted four
times in 26 minutes in the first place.

## Proposed Fix
Add an explicit `probes.startup` block to
`platform-gitops/services/labs/pelican-proxy-staging/values.yaml` with a
generous `failureThreshold`, giving the login + catalog-seed sequence more
grace before Kubernetes/ArgoCD treats a slow startup as unhealthy, without
loosening the steady-state liveness/readiness probes:

```yaml
probes:
  startup:
    path: /readyz
    port: http
    initialDelaySeconds: 5
    periodSeconds: 5
    timeoutSeconds: 2
    failureThreshold: 24   # ~2 minutes of startup grace for login + R2 seed
```

## Scope
Minimal. Only adds a `probes.startup` block to this one service's
values.yaml; does not change liveness/readiness probe values, resources, or
any other field. Verify manually whether the pod restarts continue after
this change — if they do, the underlying restart trigger still needs
investigation with resource-tree / event data this responder does not have
access to.
