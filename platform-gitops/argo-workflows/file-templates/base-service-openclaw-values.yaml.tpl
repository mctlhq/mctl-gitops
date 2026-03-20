# Service: __SERVICE_NAME__
# Team: __TEAM_NAME__
# Template: openclaw
# Updated: 2026-03-20 (gemini-bot)

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
    memory: 768Mi
  limits:
    cpu: "1"
    memory: 1.2Gi

# Recreate strategy required for clean init
strategy:
  type: Recreate

env:
  APP_ENV: production
  NODE_OPTIONS: "--max-old-space-size=1024"
  OPENCLAW_CONFIG_PATH: /config/openclaw.json
  # PostgreSQL Connection (injected via ExternalSecret)
  DATABASE_URL: "postgresql://backstage:$(DB_PASSWORD)@shared-pg-rw.platform-db.svc.cluster.local:5432/__SERVICE_NAME__"
  # Environment variable placeholders for config injection
  OPENCLAW_TELEGRAM_TOKEN:
    valueFrom:
      secretKeyRef:
        name: openclaw-telegram-secret
        key: OPENCLAW_TELEGRAM_TOKEN
  OPENCLAW_MCTL_TOKEN:
    valueFrom:
      secretKeyRef:
        name: openclaw-mctl-token
        key: MCTL_API_TOKEN
        optional: true

initContainers:
  # 1. Pre-install mcp-remote
  - name: install-mcp-remote
    image: node:22-alpine
    command: ["sh", "-c"]
    args:
      - npm install --prefix /npm-cache mcp-remote
    volumeMounts:
      - name: npm-cache
        mountPath: /npm-cache
  # 2. Build whisper-cli (optimized)
  - name: install-whisper-cli
    image: debian:12-slim
    resources:
      requests:
        cpu: 200m
        memory: 512Mi
      limits:
        cpu: "2"
        memory: 1.2Gi
    command: ["sh", "-c"]
    args:
      - |
        set -e
        WHISPER_DIR=/whisper-storage
        BIN=$WHISPER_DIR/whisper-cli
        MODEL=$WHISPER_DIR/ggml-base.bin
        WRAPPER=$WHISPER_DIR/run-whisper.sh
        mkdir -p $WHISPER_DIR
        if [ ! -f $WHISPER_DIR/ffmpeg ]; then
          apt-get update -qq && apt-get install -y --no-install-recommends wget xz-utils ca-certificates
          wget -q "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" -O /tmp/ffmpeg.tar.xz
          tar -xJf /tmp/ffmpeg.tar.xz -C $WHISPER_DIR --strip-components=1 --wildcards "*/ffmpeg"
          rm /tmp/ffmpeg.tar.xz
        fi
        if [ ! -f $MODEL ]; then
          wget -q "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin" -O $MODEL
        fi
        if [ ! -f $BIN ]; then
          apt-get update -qq && apt-get install -y --no-install-recommends build-essential cmake git ca-certificates
          git clone --depth 1 --branch v1.8.3 https://github.com/ggml-org/whisper.cpp.git /tmp/whispersrc
          cmake -B /tmp/whispersrc/build -S /tmp/whispersrc -DCMAKE_BUILD_TYPE=Release -DWHISPER_BUILD_EXAMPLES=ON -DWHISPER_BUILD_TESTS=OFF
          make -C /tmp/whispersrc/build whisper-cli -j2
          cp /tmp/whispersrc/build/bin/whisper-cli $BIN
          rm -rf /tmp/whispersrc
        fi
        cat > $WRAPPER << 'WEOF'
        #!/bin/sh
        TMP_WAV=$(mktemp /tmp/whisper_XXXXXX.wav)
        /whisper-storage/ffmpeg -i "$1" -ar 16000 -ac 1 -f wav "$TMP_WAV" -y 2>/dev/null
        /whisper-storage/whisper-cli -m /whisper-storage/ggml-base.bin -f "$TMP_WAV" --language auto --no-timestamps 2>/dev/null
        EC=$?
        rm -f "$TMP_WAV"
        exit $EC
        WEOF
        chmod +x $WRAPPER
    volumeMounts:
      - name: pvc-whisper
        mountPath: /whisper-storage
  # 3. Auto-approve the tenant owner in PostgreSQL
  - name: auto-approve
    image: postgres:17-alpine
    command: ["sh", "-c"]
    args:
      - |
        echo "Waiting for database initialization..."
        sleep 30
        psql $DATABASE_URL <<EOF
        INSERT INTO identities (provider, provider_id, status, metadata)
        VALUES ('telegram', '__TELEGRAM_OWNER_ID__', 'approved', '{}')
        ON CONFLICT (provider, provider_id) DO UPDATE SET status = 'approved';
        EOF
    env:
      - name: DATABASE_URL
        value: "postgresql://backstage:$(DB_PASSWORD)@shared-pg-rw.platform-db.svc.cluster.local:5432/__SERVICE_NAME__"
      - name: DB_PASSWORD
        valueFrom:
          secretKeyRef:
            name: openclaw-db-creds
            key: password

extraVolumeMounts:
  - name: openclaw-config
    mountPath: /config
    readOnly: true
  - name: npm-cache
    mountPath: /npm-cache
  - name: pvc-whisper
    mountPath: /whisper-storage
  - name: openclaw-scripts
    mountPath: /scripts
    readOnly: true

persistence:
  state:
    enabled: false

extraVolumes:
  - name: openclaw-config
    configMap:
      name: openclaw-config
  - name: npm-cache
    emptyDir: {}
  - name: pvc-whisper
    emptyDir: {}
  - name: openclaw-scripts
    configMap:
      name: openclaw-scripts
      defaultMode: 0755

extraExternalSecrets:
  openclaw-db-creds:
    refreshInterval: 1h
    targetSecret: openclaw-db-creds
    data:
      - secretKey: password
        remoteKey: secret/data/platform/grafana
        property: admin-password
  openclaw-telegram-secret:
    refreshInterval: 1h
    targetSecret: openclaw-telegram-secret
    data:
      - secretKey: OPENCLAW_TELEGRAM_TOKEN
        remoteKey: secret/data/platform/alertmanager
        property: telegram-bot-token
  openclaw-mctl-token:
    refreshInterval: 1h
    targetSecret: openclaw-mctl-token
    data:
      - secretKey: MCTL_API_TOKEN
        remoteKey: secret/data/teams/__TEAM_NAME__/__SERVICE_NAME__
        property: mctl-api-token

configMaps:
  openclaw-scripts:
    mcp-agent-proxy.js: |-
      #!/usr/bin/env node
      const http = require('http');
      process.stdin.setEncoding('utf8');
      let buf = '';
      process.stdin.on('data', chunk => {
        buf += chunk;
        let nl;
        while ((nl = buf.indexOf('\n')) !== -1) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (line) handleLine(line);
        }
      });
      function handleLine(line) {
        let req;
        try { req = JSON.parse(line); } catch (_) { return; }
        callAgent(req).then(res => write(res), err => write({ jsonrpc: '2.0', id: req.id, error: { code: -32603, message: String(err) } }));
      }
      function write(obj) { process.stdout.write(JSON.stringify(obj) + '\n'); }
      function callAgent(body) {
        return new Promise((resolve, reject) => {
          const data = JSON.stringify(body);
          const req = http.request({ hostname: 'mctl-agent.admins.svc.cluster.local', port: 8080, path: '/mcp', method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } }, res => {
            let out = ''; res.on('data', c => { out += c; }); res.on('end', () => { try { resolve(JSON.parse(out)); } catch (_) { reject(new Error('invalid JSON')); } });
          });
          req.on('error', reject); req.write(data); req.end();
        });
      }
  openclaw-config:
    openclaw.json: |-
      {
        "gateway": {
          "port": 18789,
          "bind": "0.0.0.0",
          "controlUi": {
            "enabled": true,
            "allowedOrigins": ["https://__TEAM_NAME__-__SERVICE_NAME__.mctl.ai"]
          },
          "auth": { "mode": "trusted-proxy", "trustedProxy": { "userHeader": "X-Forwarded-For" } },
          "trustedProxies": ["10.42.0.0/16", "10.43.0.0/16", "172.16.0.0/12"]
        },
        "channels": {
          "telegram": {
            "enabled": true,
            "botToken": "${OPENCLAW_TELEGRAM_TOKEN}",
            "dmPolicy": "pairing",
            "groupPolicy": "allowlist",
            "allowlist": ["__TELEGRAM_OWNER_ID__"]
          }
        },
        "mcp": {
          "servers": {
            "mctl-agent": { "command": "node", "args": ["/scripts/mcp-agent-proxy.js"] }
          }
        }
      }
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
