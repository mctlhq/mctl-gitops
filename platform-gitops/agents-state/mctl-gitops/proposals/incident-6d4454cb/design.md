# Design: incident-6d4454cb

## Confidence: LOW

## Diagnosis

CPUThrottlingHigh fired for the `valkey` workload in `platform-events`. The
StatefulSet (platform-gitops/infra-components/data/valkey/statefulset.yaml)
runs two containers: `valkey` (requests 25m / limits 500m) and `exporter`
(requests 10m / limits 300m). The exporter's limit was already raised once
before, from 100m to 300m, specifically because of this same alert — the
container carries a comment recording that at a 100m limit it was throttled
in 39% of CFS periods. That fix is still in place, so the exporter is the
less likely repeat offender.

CPUThrottlingHigh is driven by `container_cpu_cfs_throttled_periods_total`
against the CFS quota implied by the *limit*, independent of the request.
The `valkey` container's limit (500m) is comparatively tight for a
single-threaded event-streaming broker: AOF rewrites, RDB snapshotting, or a
burst of inbound events on `platform-events` can spike single-core CPU usage
well past a 500m quota within one 100ms CFS period, producing exactly this
alert.

No Loki logs were available for this workload (see requirements.md), and no
per-container CPU-throttling metrics were reachable with the tools available
to this responder, so it is not possible to confirm from evidence alone
whether `valkey` or `exporter` is the container currently being throttled.
This diagnosis picks `valkey` as the more probable cause given the exporter's
already-raised limit and its comparatively light, periodic workload (a single
HTTP scrape per interval) versus valkey's continuous, bursty one. The
implementer should check
`container_cpu_cfs_throttled_periods_total{namespace="platform-events"}` by
container before applying, and adjust the exporter's limit instead if it is
the one still throttling.

## Proposed Fix

File: `platform-gitops/infra-components/data/valkey/statefulset.yaml`

In the `valkey` container's `resources.limits`, raise `cpu` from `500m` to
`750m` (a 50% headroom increase, matching the proportional bump already
applied to the exporter container in the same file). Leave `requests.cpu`
(25m) and all memory values unchanged.

```yaml
        - name: valkey
          ...
          resources:
            requests:
              cpu: 25m
              memory: 64Mi
            limits:
              cpu: 750m   # was 500m — CPUThrottlingHigh (incident 9b19d037-...-4454cb)
              memory: 300Mi
```

## Scope
Minimal. Only the `valkey` container's `resources.limits.cpu` field in this
one StatefulSet changes. No changes to the exporter container, replica count,
memory limits, or AlertManager rule.
