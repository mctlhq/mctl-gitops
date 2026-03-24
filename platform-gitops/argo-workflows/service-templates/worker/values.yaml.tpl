# Worker: __SERVICE_NAME__
# Team: __TEAM_NAME__
# Chart: base-service (ingress disabled)

image:
  repository: ghcr.io/mctlhq/__SERVICE_NAME__
  tag: "__IMAGE_TAG__"

imagePullSecrets:
  - name: ghcr-credentials

ingress:
  enabled: false

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi

probes:
  startup:
    path: /healthz
    port: http
    initialDelaySeconds: 5
    periodSeconds: 5
    failureThreshold: 24
  readiness:
    path: /readyz
    port: http
    initialDelaySeconds: 15
    periodSeconds: 5
  liveness:
    path: /healthz
    port: http
    initialDelaySeconds: 60
    periodSeconds: 15

env: {}
