# Service: __SERVICE_NAME__
# Team: __TEAM_NAME__
# Environment: preprod
# Chart: base-service

image:
  repository: ghcr.io/dmitriimashkov/__SERVICE_NAME__
  tag: "__IMAGE_TAG__"

service:
  port: __PORT__

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi

env:
  APP_ENV: preprod

ingress:
  enabled: true
  host: __HOST__
