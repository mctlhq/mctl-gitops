# Worker: __SERVICE_NAME__
# Team: __TEAM_NAME__
# Environment: preview
# Chart: worker-service

image:
  repository: ghcr.io/dmitriimashkov/__SERVICE_NAME__
  tag: "__IMAGE_TAG__"

imagePullSecrets:
  - name: ghcr-credentials

workloadType: deployment

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi

env:
  APP_ENV: preview
