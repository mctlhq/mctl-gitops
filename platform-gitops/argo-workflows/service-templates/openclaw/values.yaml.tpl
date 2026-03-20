# Service: __SERVICE_NAME__
# Team: __TEAM_NAME__
# Template: openclaw
# Updated: 2026-03-20 (gemini-bot) - Fixed DB and Auto-Approve

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
  OPENCLAW_CONFIG_PATH: /config-rw/openclaw.json
  # PostgreSQL Connection (using dedicated service credentials)
  DATABASE_URL: "postgresql://$(DB_USER):$(DB_PASSWORD)@shared-pg-rw.platform-db.svc.cluster.local:5432/__SERVICE_NAME__"

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
  # 3. Setup Config and inject tokens
  - name: setup
    image: busybox:1.36
    command: ["sh", "-c"]
    args:
      - |
        cp /config-tpl/openclaw.json /config-rw/openclaw.json
        if [ -n "$TELEGRAM_TOKEN" ]; then sed -i "s|__TELEGRAM_TOKEN__|$TELEGRAM_TOKEN|g" /config-rw/openclaw.json; fi
        if [ -n "$MCTL_TOKEN" ]; then sed -i "s|__MCTL_TOKEN__|$MCTL_TOKEN|g" /config-rw/openclaw.json; fi
        if [ -n "$OPENAI_API_KEY" ]; then sed -i "s|__OPENAI_API_KEY__|$OPENAI_API_KEY|g" /config-rw/openclaw.json; fi
        chown 1000:1000 /config-rw/openclaw.json
    env:
      - name: TELEGRAM_TOKEN
        valueFrom:
          secretKeyRef:
            name: openclaw-telegram-secret
            key: OPENCLAW_TELEGRAM_TOKEN
      - name: MCTL_TOKEN
        valueFrom:
          secretKeyRef:
            name: openclaw-mctl-token
            key: MCTL_API_TOKEN
            optional: true
      - name: OPENAI_API_KEY
        valueFrom:
          secretKeyRef:
            name: openclaw-openai-secret
            key: OPENAI_API_KEY
            optional: true
    volumeMounts:
      - name: openclaw-config-tpl
        mountPath: /config-tpl
        readOnly: true
      - name: openclaw-config-rw
        mountPath: /config-rw
  # 4. Auto-approve the tenant owner in PostgreSQL
  - name: auto-approve
    image: postgres:17-alpine
    command: ["sh", "-c"]
    args:
      - |
        # Wait for migrations to be applied by the main app (approximate)
        # Note: In production, it's better to use a dedicated migration job.
        # For simplicity, we loop until table exists or timeout.
        for i in $(seq 1 30); do
          if psql "$DATABASE_URL" -c "\dt identities" | grep -q "identities"; then
            echo "Identities table found! Approving owner..."
            psql "$DATABASE_URL" <<EOF
            INSERT INTO identities (provider, provider_id, status, metadata)
            VALUES ('telegram', '__TELEGRAM_OWNER_ID__', 'approved', '{}')
            ON CONFLICT (provider, provider_id) DO UPDATE SET status = 'approved';
        EOF
            exit 0
          fi
          echo "Waiting for migrations ($i/30)..."
          sleep 10
        done
        echo "Timeout waiting for identities table. Skipping auto-approval."
    env:
      - name: DATABASE_URL
        value: "postgresql://$(DB_USER):$(DB_PASSWORD)@shared-pg-rw.platform-db.svc.cluster.local:5432/__SERVICE_NAME__"
      - name: DB_USER
        valueFrom:
          secretKeyRef:
            name: openclaw-db-creds
            key: username
      - name: DB_PASSWORD
        valueFrom:
          secretKeyRef:
            name: openclaw-db-creds
            key: password
    volumeMounts:
      - name: openclaw-config-rw
        mountPath: /config-rw

extraVolumeMounts:
  - name: openclaw-config-rw
    mountPath: /config-rw
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
  - name: openclaw-config-tpl
    configMap:
      name: __SERVICE_NAME__-config
  - name: openclaw-config-rw
    emptyDir: {}
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
      - secretKey: username
        remoteKey: secret/data/teams/__TEAM_NAME__/__SERVICE_NAME__/database
        property: username
      - secretKey: password
        remoteKey: secret/data/teams/__TEAM_NAME__/__SERVICE_NAME__/database
        property: password
  openclaw-openai-secret:
    refreshInterval: 1h
    targetSecret: openclaw-openai-secret
    data:
      - secretKey: OPENAI_API_KEY
        remoteKey: secret/data/platform/openai
        property: api-key
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
  __SERVICE_NAME__-config:
    openclaw.json: |-
      {
        "gateway": {
          "bind": "lan",
          "port": 18789,
          "auth": {
            "mode": "trusted-proxy",
            "trustedProxy": {
              "userHeader": "X-Forwarded-For"
            }
          },
          "trustedProxies": [
            "10.42.0.0/16",
            "10.43.0.0/16",
            "172.16.0.0/12"
          ],
          "controlUi": {
            "enabled": true,
            "allowedOrigins": [
              "https://__TEAM_NAME__-__SERVICE_NAME__.mctl.ai",
              "https://__TEAM_NAME__-__SERVICE_NAME__.mctl.me"
            ]
          }
        },
        "providers": {
          "openai-codex": {
            "type": "openai-codex",
            "baseUrl": "https://codex.openai.com/v1",
            "models": {
              "gpt-5.4": "gpt-5.4"
            }
          },
          "anthropic": { "enabled": false },
          "openai": { "enabled": false },
          "google": { "enabled": false }
        },
        "defaultModel": "openai-codex/gpt-5.4",
        "auth": {
          "oauth": {
            "enabled": true,
            "providers": ["openai-codex"]
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
