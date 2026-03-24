# Spring worker: __SERVICE_NAME__
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
    path: /actuator/health
    port: http
    initialDelaySeconds: 5
    periodSeconds: 5
    failureThreshold: 36
  readiness:
    path: /actuator/health
    port: http
    initialDelaySeconds: 15
    periodSeconds: 5
  liveness:
    path: /actuator/health
    port: http
    initialDelaySeconds: 90
    periodSeconds: 15

env: {}
