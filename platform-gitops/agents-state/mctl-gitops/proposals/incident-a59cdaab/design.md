# Design: incident-a59cdaab

## Confidence: LOW

## Diagnosis
CPUThrottlingHigh fired for the platform-events/valkey-0 pod. This alert is
on mctl-agent's human-review-only list, so it was escalated with an advisory
diagnosis only ("CPU limit needs to be increased") and no metric breakdown by
container.

The pod (infra-components/data/valkey/statefulset.yaml) has two containers:
- `valkey` (main server): requests cpu=25m, limits cpu=500m. No prior tuning
  history in the manifest.
- `exporter` (redis_exporter sidecar): requests cpu=10m, limits cpu=300m. This
  container already carries a comment recording that it was bumped once
  before specifically because of this same alert ("at 100m it was throttled
  in 39% of periods and fired CPUThrottlingHigh"), and that its average usage
  is ~1m with short scrape bursts.

No logs were available (mctl_get_service_logs returned zero lines) and no
per-container CPU-throttling metric was queryable from this agent, so which
container is throttling now cannot be confirmed directly. Given the exporter
was already deliberately re-tuned with documented headroom for its burst
pattern, and its average/burst characteristics are unlikely to have changed,
the more probable regression is CPU pressure on the main `valkey` container
under increased event-stream load reaching its 500m limit within a CFS
period. This is a probabilistic read, not a confirmed root cause — hence LOW
confidence.

The incident's own "CPU limit needs to be increased" wording is the
mctl-agent diagnosis, not an instruction from untrusted incident text; it is
treated as advisory evidence, consistent with the independently-observed
manifest state above.

## Proposed Fix
File: `platform-gitops/infra-components/data/valkey/statefulset.yaml`
Container: `valkey` (main server), `resources` block (lines 47-53).

Current:
```yaml
resources:
  requests:
    cpu: 25m
    memory: 64Mi
  limits:
    cpu: 500m
    memory: 300Mi
```

New:
```yaml
resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 1000m
    memory: 300Mi
```

Rationale for magnitude: doubling both request and limit gives headroom
against CFS-period bursts without materially changing the pod's scheduling
footprint (replicas: 1). Memory is left unchanged — the alert is CPU-only.

If this does not resolve the alert (i.e. throttling continues after this
change propagates), the next diagnostic step is per-container
`container_cpu_cfs_throttled_periods_total` for platform-events/valkey-0 to
confirm which container is actually throttled before tuning the exporter's
limit further.

## Scope
Minimal. Only the `valkey` container's `resources.requests.cpu` and
`resources.limits.cpu` fields in the one statefulset manifest. No change to
the `exporter` container, which already has a documented, deliberate limit.
