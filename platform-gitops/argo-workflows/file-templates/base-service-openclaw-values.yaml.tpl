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
    memory: 2Gi

# Recreate strategy required: openclaw-state PVC is RWO
strategy:
  type: Recreate

env:
  APP_ENV: production
  NODE_OPTIONS: "--max-old-space-size=1024"
  OPENCLAW_CONFIG_PATH: /config-rw/openclaw.json

initContainers:
  # 1. Pre-install mcp-remote so npx doesn't download it on every MCP call
  - name: install-mcp-remote
    image: node:22-alpine
    command: ["sh", "-c"]
    args:
      - npm install --prefix /npm-cache mcp-remote
    volumeMounts:
      - name: npm-cache
        mountPath: /npm-cache
  # 2. Build whisper-cli from source and download ggml-base model (skips if PVC already populated)
  - name: install-whisper-cli
    image: debian:12-slim
    resources:
      requests:
        cpu: 200m
        memory: 512Mi
      limits:
        cpu: "1"
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
        
        # 1. Download static ffmpeg
        if [ ! -f $WHISPER_DIR/ffmpeg ]; then
          echo "Downloading ffmpeg..."
          apt-get update -qq && apt-get install -y --no-install-recommends wget xz-utils ca-certificates
          wget -q "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" -O /tmp/ffmpeg.tar.xz
          tar -xJf /tmp/ffmpeg.tar.xz -C $WHISPER_DIR --strip-components=1 --wildcards "*/ffmpeg"
          rm /tmp/ffmpeg.tar.xz
        fi

        # 2. Download model
        if [ ! -f $MODEL ]; then
          echo "Downloading ggml-base.bin (~140MB)..."
          wget -q "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin" -O $MODEL
        fi

        # 3. Fast build (minimized, limited to 2 cores for stability)
        if [ ! -f $BIN ]; then
          apt-get update -qq && apt-get install -y --no-install-recommends build-essential cmake git ca-certificates
          git clone --depth 1 --branch v1.8.3 https://github.com/ggml-org/whisper.cpp.git /tmp/whispersrc
          cmake -B /tmp/whispersrc/build -S /tmp/whispersrc -DCMAKE_BUILD_TYPE=Release -DWHISPER_BUILD_EXAMPLES=ON -DWHISPER_BUILD_TESTS=OFF
          make -C /tmp/whispersrc/build whisper-cli -j2
          cp /tmp/whispersrc/build/bin/whisper-cli $BIN
          rm -rf /tmp/whispersrc
        fi

        # 4. Create wrapper
        cat > $WRAPPER << 'WEOF'
        #!/bin/sh
        TMP_WAV=$(mktemp /tmp/whisper_XXXXXX.wav)
        /whisper-storage/ffmpeg -i "$1" -ar 16000 -ac 1 -f wav "$TMP_WAV" -y 2>/dev/null
        /whisper-storage/whisper-cli \
          -m /whisper-storage/ggml-base.bin \
          -f "$TMP_WAV" \
          --language auto \
          --no-timestamps \
          2>/dev/null
        EC=$?
        rm -f "$TMP_WAV"
        exit $EC
        WEOF
        chmod +x $WRAPPER
    volumeMounts:
      - name: pvc-whisper
        mountPath: /whisper-storage

extraVolumeMounts:
  - name: openclaw-config-rw
    mountPath: /config-rw
  - name: pvc-state
    mountPath: /home/node/.openclaw
  - name: npm-cache
    mountPath: /npm-cache
  - name: pvc-whisper
    mountPath: /whisper-storage
  - name: openclaw-scripts
    mountPath: /scripts
    readOnly: true

# PVC for openclaw state (Telegram pairing, agent data)
persistence:
  state:
    size: 1Gi
    mountPath: /home/node/.openclaw
  whisper:
    size: 2Gi
    mountPath: /whisper-storage

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

configMaps:
  openclaw-config:
    openclaw.json: |
      {
        "gateway": {
          "bind": "0.0.0.0",
          "port": 18789,
          "trustProxy": true
        },
        "channels": {
          "telegram": {
            "enabled": true,
            "groupPolicy": "open",
            "dmPolicy": "pairing"
          }
        }
      }
