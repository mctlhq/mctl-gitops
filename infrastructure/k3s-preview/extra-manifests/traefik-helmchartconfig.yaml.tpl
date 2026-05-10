apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: traefik
  namespace: kube-system
spec:
  valuesContent: |-
    # Disable Traefik Hub (paid add-on). Without this flag the Traefik chart
    # installs 13 *.hub.traefik.io CRDs even when Hub is not licensed or used.
    # Each unused CRD opens a separate watch in kube-apiserver, wasting ~100-200
    # MB of apiserver heap. CRDs were manually deleted on 2026-05-10 and this
    # config prevents them from being reinstalled on chart upgrades.
    hub:
      enabled: false
