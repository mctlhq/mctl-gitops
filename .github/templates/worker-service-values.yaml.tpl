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

env: {}
