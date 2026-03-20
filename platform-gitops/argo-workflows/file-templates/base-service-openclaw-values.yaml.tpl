# Service: __SERVICE_NAME__
# Team: __TEAM_NAME__
# Template: openclaw

# Chart: base-service

image:
  repository: ghcr.io/mctlhq/__SERVICE_NAME__
  tag: "__IMAGE_TAG__"

imagePullSecrets:
  - name: ghcr-credentials

service:
  port: 18789

resources:
  requests:
    cpu: 200m
    memory: 512Mi
  limits:
    cpu: "1"
    memory: 1Gi

env:
  APP_ENV: production
  NODE_OPTIONS: "--max-old-space-size=768"
  OPENCLAW_CONFIG_PATH: /config/openclaw.json

probes:
  startup:
    path: /healthz
    port: http
    initialDelaySeconds: 5
    periodSeconds: 10
    failureThreshold: 30
  liveness:
    path: /healthz
    port: http
    initialDelaySeconds: 10
    periodSeconds: 15
  readiness:
    path: /readyz
    port: http
    initialDelaySeconds: 5
    periodSeconds: 10

extraVolumeMounts:
  - name: openclaw-config
    mountPath: /config
    readOnly: true
extraVolumes:
  - name: openclaw-config
    configMap:
      name: __SERVICE_NAME__-config

ingress:
  enabled: true
  hosts:
    - __HOST__
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  tls:
    - secretName: __SERVICE_NAME__-tls
      hosts:
        - __HOST__
