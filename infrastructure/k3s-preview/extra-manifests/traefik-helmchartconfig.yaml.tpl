apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    # Traefik Hub CRDs were manually deleted on 2026-05-10.
    # The hub.enabled key is not accepted by the chart schema in Traefik >=v3.x
    # (additional properties not allowed), so it has been removed entirely.

    # SOC F11: pin the kube-hetzner Traefik PDB. Live is 3 replicas with
    # maxUnavailable 33% (desiredHealthy 2). Do not set minAvailable here:
    # the chart emits both fields independently, and Kubernetes rejects a
    # PDB that sets both. minAvailable: 1 would also weaken the live budget.
    # Replica count is already 3; do not drop it.
    podDisruptionBudget:
      enabled: true
      maxUnavailable: 33%
