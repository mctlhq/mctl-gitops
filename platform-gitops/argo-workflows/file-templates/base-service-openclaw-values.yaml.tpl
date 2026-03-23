# Service: __SERVICE_NAME__
# Team: __TEAM_NAME__
# Template: openclaw
# Updated: 2026-03-22 - self-service onboarding baseline

# Chart: base-service

image:
  repository: ghcr.io/mctlhq/__SERVICE_NAME__
  tag: "2026.3.23-beta.9"

imagePullSecrets:
  - name: ghcr-credentials

service:
  port: 18789

resources:
  requests:
    cpu: 50m
    memory: 512Mi
  limits:
    cpu: "1500m"
    memory: 2560Mi

# RollingUpdate is safe now that resource limits fit within tenant quota
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 1
    maxUnavailable: 0

env:
  APP_ENV: production
  NODE_OPTIONS: "--max-old-space-size=2048"
  OPENCLAW_CONFIG_PATH: /config-rw/openclaw.json
  OPENCLAW_OPENAI_CODEX_PORTAL_CALLBACK_URL: "https://app.mctl.ai/api/oidc-provider/openai-codex/callback"
  OPENCLAW_OPENAI_CODEX_CLIENT_ID: ""
  # PostgreSQL Connection (using dedicated service credentials)
  DATABASE_URL: "postgresql://$(DB_USER):$(DB_PASSWORD)@shared-pg-rw.platform-db.svc.cluster.local:5432/__SERVICE_NAME__"

probes:
  startup:
    path: /healthz
    port: http
    initialDelaySeconds: 5
    periodSeconds: 5
    failureThreshold: 24
  readiness:
    path: /readyz
    port: http
    initialDelaySeconds: 10
    periodSeconds: 10
  liveness:
    path: /healthz
    port: http
    initialDelaySeconds: 30
    periodSeconds: 20

initContainers:
  # 1. Build whisper-cli (optimized)
  - name: install-whisper-cli
    image: debian:12-slim
    resources:
      requests:
        cpu: 50m
        memory: 128Mi
      limits:
        cpu: 500m
        memory: 512Mi
    command: ["sh", "-c"]
    args:
      - |
        set -e
        WHISPER_DIR=/whisper-storage
        BIN=$WHISPER_DIR/whisper-cli
        MODEL=$WHISPER_DIR/ggml-tiny.bin
        WRAPPER=$WHISPER_DIR/run-whisper.sh
        mkdir -p $WHISPER_DIR
        if [ ! -f $WHISPER_DIR/ffmpeg ]; then
          apt-get update -qq && apt-get install -y --no-install-recommends wget xz-utils ca-certificates
          wget -q "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" -O /tmp/ffmpeg.tar.xz
          tar -xJf /tmp/ffmpeg.tar.xz -C $WHISPER_DIR --strip-components=1 --wildcards "*/ffmpeg"
          rm /tmp/ffmpeg.tar.xz
        fi
        if [ ! -f $MODEL ]; then
          wget -q "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin" -O $MODEL
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
        /whisper-storage/whisper-cli -m /whisper-storage/ggml-tiny.bin -f "$TMP_WAV" --language auto --no-timestamps 2>/dev/null
        EC=$?
        rm -f "$TMP_WAV"
        exit $EC
        WEOF
        chmod +x $WRAPPER
    volumeMounts:
      - name: pvc-whisper
        mountPath: /whisper-storage
  # 2. Setup config and inject service-scoped tokens
  - name: setup
    image: busybox:1.36
    command: ["sh", "-c"]
    args:
      - |
        cp /config-tpl/openclaw.json /config-rw/openclaw.json
        if [ -n "$TELEGRAM_TOKEN" ]; then sed -i "s|__TELEGRAM_TOKEN__|$TELEGRAM_TOKEN|g" /config-rw/openclaw.json; fi
        chown 1000:1000 /config-rw/openclaw.json
    env:
      - name: TELEGRAM_TOKEN
        valueFrom:
          secretKeyRef:
            name: openclaw-telegram-secret
            key: OPENCLAW_TELEGRAM_TOKEN
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
      name: openclaw-config
  - name: openclaw-config-rw
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
  openclaw-telegram-secret:
    refreshInterval: 1h
    targetSecret: openclaw-telegram-secret
    data:
      - secretKey: OPENCLAW_TELEGRAM_TOKEN
        remoteKey: secret/data/teams/__TEAM_NAME__/__SERVICE_NAME__/telegram
        property: telegram-bot-token
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
          const req = http.request({ hostname: 'admins-mctl-agent-base-service.admins.svc.cluster.local', port: 8080, path: '/mcp', method: 'POST', headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } }, res => {
            let out = ''; res.on('data', c => { out += c; }); res.on('end', () => { try { resolve(JSON.parse(out)); } catch (_) { reject(new Error('invalid JSON')); } });
          });
          req.on('error', reject); req.write(data); req.end();
        });
      }
    mctl-mcp-proxy.js: |-
      #!/usr/bin/env node
      const fs = require('fs');
      const path = require('path');
      const apiBase = (process.env.MCTL_API_URL || 'https://api.mctl.ai').replace(/\/+$/, '');
      const authFile = process.env.MCTL_AUTH_FILE || '/home/node/.openclaw/mcp-auth/mctl/credentials.json';
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
      function write(obj) { process.stdout.write(JSON.stringify(obj) + '\n'); }
      async function handleLine(line) {
        let req;
        try { req = JSON.parse(line); } catch (_) { return; }
        try {
          const res = await callMctl(req);
          write(res);
        } catch (err) {
          write({ jsonrpc: '2.0', id: req.id, error: { code: -32603, message: String(err && err.message ? err.message : err) } });
        }
      }
      async function readAuth() {
        const raw = await fs.promises.readFile(authFile, 'utf8');
        return JSON.parse(raw);
      }
      async function writeAuth(auth) {
        await fs.promises.mkdir(path.dirname(authFile), { recursive: true, mode: 0o700 });
        const tmp = `${authFile}.tmp`;
        await fs.promises.writeFile(tmp, JSON.stringify(auth, null, 2) + '\n', { mode: 0o600 });
        await fs.promises.rename(tmp, authFile);
      }
      function isExpiring(auth) {
        if (!auth || !auth.expiresAt) return false;
        const ms = Date.parse(auth.expiresAt);
        return Number.isFinite(ms) && ms <= Date.now() + 60_000;
      }
      async function refreshAuth(auth) {
        if (!auth || !auth.refreshToken || !auth.clientId) {
          throw new Error('mctl not connected');
        }
        const body = new URLSearchParams({
          grant_type: 'refresh_token',
          refresh_token: auth.refreshToken,
          client_id: auth.clientId,
        });
        const res = await fetch(`${apiBase}/oauth/token`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json' },
          body,
        });
        const payload = await res.json().catch(() => ({}));
        if (!res.ok || !payload.access_token || !payload.refresh_token) {
          throw new Error(payload.error_description || payload.error || `mctl refresh failed (${res.status})`);
        }
        const expiresAt = typeof payload.expires_in === 'number' ? new Date(Date.now() + payload.expires_in * 1000).toISOString() : null;
        const next = {
          ...auth,
          accessToken: String(payload.access_token),
          refreshToken: String(payload.refresh_token),
          scope: typeof payload.scope === 'string' ? payload.scope : (auth.scope || 'mctl'),
          expiresAt,
          updatedAt: new Date().toISOString(),
        };
        await writeAuth(next);
        return next;
      }
      async function ensureAuth() {
        const auth = await readAuth().catch(() => null);
        if (!auth) {
          throw new Error('mctl is not connected in Control UI');
        }
        if (isExpiring(auth)) {
          return await refreshAuth(auth);
        }
        return auth;
      }
      async function post(body, token) {
        const res = await fetch(`${apiBase}/mcp`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': `Bearer ${token}`,
          },
          body: JSON.stringify(body),
        });
        const text = await res.text();
        let parsed;
        try { parsed = text ? JSON.parse(text) : {}; } catch (_) { throw new Error(`invalid JSON from mctl MCP (${res.status})`); }
        return { status: res.status, body: parsed };
      }
      async function callMctl(body) {
        let auth = await ensureAuth();
        let res = await post(body, auth.accessToken);
        if (res.status === 401 && auth.refreshToken) {
          auth = await refreshAuth(auth);
          res = await post(body, auth.accessToken);
        }
        if (res.status >= 400) {
          const message = res.body && res.body.error && res.body.error.message ? res.body.error.message : `mctl MCP request failed (${res.status})`;
          throw new Error(message);
        }
        return res.body;
      }
  openclaw-config:
    openclaw.json: |-
      {
        "gateway": {
          "port": 18789,
          "bind": "lan",
          "controlUi": {
            "enabled": true,
            "allowedOrigins": ["https://__TEAM_NAME__-__SERVICE_NAME__.mctl.ai"]
          },
          "auth": { "mode": "trusted-proxy", "trustedProxy": { "userHeader": "X-Forwarded-User", "roleHeader": "X-Mctl-Team-Role" } },
          "trustedProxies": ["10.42.0.0/16", "10.43.0.0/16", "172.16.0.0/12"]
        },
        "agents": {
          "defaults": {
            "model": {
              "primary": "openai-codex/gpt-5.4"
            }
          }
        },
        "auth": {
          "profiles": {
            "openai-codex:default": {
              "provider": "openai-codex",
              "mode": "oauth"
            }
          },
          "order": {
            "openai-codex": ["openai-codex:default"]
          }
        },
        "channels": {
          "telegram": {
            "enabled": true,
            "botToken": "__TELEGRAM_TOKEN__",
            "dmPolicy": "pairing",
            "groupPolicy": "open",
            "allowFrom": ["__TELEGRAM_OWNER_ID__"]
          }
        },
        "mcp": {
          "servers": {
            "mctl-agent": { "command": "node", "args": ["/scripts/mcp-agent-proxy.js"] },
            "mctl": {
              "command": "node",
              "args": ["/scripts/mctl-mcp-proxy.js"],
              "env": {
                "MCTL_API_URL": "https://api.mctl.ai",
                "MCTL_AUTH_FILE": "/home/node/.openclaw/mcp-auth/mctl/credentials.json"
              }
            }
          }
        }
      }
ingress:
  enabled: true
  forwardAuth:
    enabled: true
    address: "https://app.mctl.ai/api/oidc-provider/forward-auth?tenant=__TEAM_NAME__&service=__SERVICE_NAME__"
    trustForwardHeader: true
    authResponseHeaders:
      - X-Forwarded-User
      - X-Mctl-Team-Role
  hosts:
    - __HOST__
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  tls:
    - secretName: __SERVICE_NAME__-tls
      hosts:
        - __HOST__
