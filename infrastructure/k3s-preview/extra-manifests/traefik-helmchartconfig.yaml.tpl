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
