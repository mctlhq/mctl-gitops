apiVersion: helm.cattle.io/v1
kind: HelmChartConfig
metadata:
  name: cert-manager
  namespace: kube-system
spec:
  valuesContent: |-
    resources:
      requests:
        cpu: 50m
        memory: 96Mi
      limits:
        cpu: 250m
        memory: 192Mi
    cainjector:
      resources:
        requests:
          cpu: 50m
          memory: 128Mi
        limits:
          cpu: 250m
          memory: 256Mi
    webhook:
      resources:
        requests:
          cpu: 25m
          memory: 64Mi
        limits:
          cpu: 100m
          memory: 128Mi
