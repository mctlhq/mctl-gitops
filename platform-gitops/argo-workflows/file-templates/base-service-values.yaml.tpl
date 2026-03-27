# Service: __SERVICE_NAME__
# Team: __TEAM_NAME__

# Chart: base-service

image:
  repository: ghcr.io/mctlhq/__SERVICE_NAME__
  tag: "__IMAGE_TAG__"

imagePullSecrets:
  - name: ghcr-credentials

service:
  port: __PORT__

backstage:
  kubernetesId: __SERVICE_NAME__

resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: 500m
    memory: 512Mi

env:
  APP_ENV: production

ingress:
  enabled: true
  hosts:
    - __HOST__
