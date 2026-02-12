# Worker: __SERVICE_NAME__
# Team: __TEAM_NAME__
# Environment: preprod
# Chart: worker-service

image:
  repository: ghcr.io/dmitriimashkov/__SERVICE_NAME__
  tag: "__IMAGE_TAG__"

workloadType: deployment

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi

env:
  APP_ENV: preprod
