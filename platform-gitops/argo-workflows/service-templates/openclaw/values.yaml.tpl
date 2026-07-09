# Service: __SERVICE_NAME__
# Team: __TEAM_NAME__
# Template: openclaw
# Updated: 2026-03-22 - self-service onboarding + Codex OAuth + MinIO state

# Chart: base-service

image:
  repository: ghcr.io/mctlhq/mctl-openclaw
  tag: "__IMAGE_TAG__"

podSecurityContext:
  fsGroup: 1000

imagePullSecrets:
  - name: ghcr-credentials

service:
  port: 18789

resources:
  requests:
    cpu: 250m
    memory: 768Mi
  limits:
    cpu: 1500m
    # 2x the request, matching base-service's default ratio — new tenants
    # should not inherit the 3.33x ratio the existing openclaw instances
    # carried before their 2026-07 memory-limit trim.
    memory: 1536Mi

# Recreate avoids quota deadlocks for single-pod tenant deployments.
strategy:
  type: Recreate
# Give the s3-sync sidecar's preStop hook room to complete a synchronous
# `mc mirror` before SIGKILL. The default 30s is not enough when state is
# large; 60s leaves a comfortable margin for every current tenant.
terminationGracePeriodSeconds: 60

env:
  APP_ENV: production
  OPENCLAW_VERSION: "2026.3.25-beta.26"
  OPENCLAW_BUNDLED_SKILLS_DIR: /home/node/.openclaw/bundled-skills
  OPENCLAW_GITHUB_ALLOWED_REPOS: "mctlhq/mctl-gitops"
  PATH: "/whisper-storage:/usr/local/bin:/usr/bin:/bin:/usr/local/games:/usr/games"
  LD_LIBRARY_PATH: /whisper-storage
  WHISPER_CPP_MODEL: /whisper-storage/ggml-base.bin
  NODE_OPTIONS: "--max-old-space-size=1792"
  OPENCLAW_CONFIG_PATH: /config-rw/openclaw.json
  OPENCLAW_OPENAI_CODEX_PORTAL_CALLBACK_URL: "https://app.mctl.ai/api/oidc-provider/openai-codex/callback"
  # Empty until a real OAuth client is registered with OpenAI for the
  # app.mctl.ai redirect_uri. Do not reuse the localhost CLI client id here —
  # auth.openai.com rejects it with authorize_hydra_invalid_request because
  # that client is only registered for http://localhost:1455/auth/callback.
  # Empty falls back to manual_input mode (browser redirects to localhost,
  # tenant pastes the resulting URL back), which is the flow that works today.
  OPENCLAW_OPENAI_CODEX_CLIENT_ID: ""

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

envFrom:
  - secretRef:
      name: __TEAM_NAME__-__SERVICE_NAME__-db-creds

initContainers:
  # 1. Restore state from MinIO (no-op for new tenants, preserves OAuth credentials on restart)
  - name: restore-state
    image: minio/mc@sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727
    command: ["sh", "-c"]
    args:
      - |
        mc alias set s3 "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"
        # Detect existing tenant state by probing for ANY object under each
        # candidate prefix, not by a specific marker file. The previous
        # logic relied on `mc find ... --name update-check.json`, which is
        # a runtime artifact written periodically by openclaw — tenants
        # where the process had not yet (or no longer) written the marker
        # silently fell through to `mkdir -p` even when the rest of the
        # state (auth-profiles.json, sessions, workspace) was sitting in
        # S3 waiting to be restored. ovk hit this exact mode during the
        # rollout of PR #36; the canary guard there saved S3, this PR
        # closes the loop on the init side.
        NEW_STATE_MARKER=""
        LEGACY_STATE_MARKER=""
        # `grep` is not present in the minio/mc image — use shell `[ -n
        # "$(...)" ]` instead to detect whether the prefix has any object.
        if [ -n "$(mc ls --recursive s3/platform-state/__TEAM_NAME__/__SERVICE_NAME__/ 2>/dev/null | head -1)" ]; then
          NEW_STATE_MARKER=1
        fi
        if [ -n "$(mc ls --recursive s3/platform-state/__SERVICE_NAME__/__TEAM_NAME__/ 2>/dev/null | head -1)" ]; then
          LEGACY_STATE_MARKER=1
        fi
        if [ -n "$NEW_STATE_MARKER" ]; then
          mc mirror s3/platform-state/__TEAM_NAME__/__SERVICE_NAME__/ /home/node/.openclaw
        elif [ -n "$LEGACY_STATE_MARKER" ]; then
          mc mirror s3/platform-state/__SERVICE_NAME__/__TEAM_NAME__/ /home/node/.openclaw
        else
          mkdir -p /home/node/.openclaw
        fi
        # Defensive prune: openclaw's bundled-runtime-deps mirror creates a
        # `.openclaw-runtime-mirror.lock/` dir while it copies node_modules
        # into the emptyDir. Pre-fix versions of the s3-sync sidecar carried
        # only `--exclude '*.lock'` (file-level), which skipped the dir name
        # but still uploaded `owner.json` inside it. On the next pod restart
        # `mc mirror s3 -> emptyDir` rehydrated that owner.json, the runtime
        # mirror logic saw the lock as held, waited 5 min for the supposed
        # owner, failed startup probe, and crash-looped. Scrub any stale
        # *.lock/ dirs after restore so a single rotation self-heals even if
        # S3 still carries old lock-owner metadata from before the exclude
        # pattern was tightened.
        find /home/node/.openclaw -type d -name '*.lock' -exec rm -rf {} + 2>/dev/null || true
        # During layout migration, only backfill non-secret model metadata.
        # New tenants must start without preseeded Codex OAuth credentials.
        if [ -n "$LEGACY_STATE_MARKER" ]; then
          mkdir -p /home/node/.openclaw/agents/main/agent
          if [ ! -f /home/node/.openclaw/agents/main/agent/models.json ]; then
            mc cp s3/platform-state/__SERVICE_NAME__/__TEAM_NAME__/agents/main/agent/models.json /home/node/.openclaw/agents/main/agent/models.json 2>/dev/null || true
          fi
        fi
    env:
      - name: MINIO_ENDPOINT
        value: "http://minio.minio.svc.cluster.local:9000"
      - name: MINIO_ACCESS_KEY
        valueFrom: { secretKeyRef: { name: minio-cache-creds, key: access-key } }
      - name: MINIO_SECRET_KEY
        valueFrom: { secretKeyRef: { name: minio-cache-creds, key: secret-key } }
    volumeMounts:
      - name: state-data
        mountPath: /home/node/.openclaw
  # 2. Build whisper-cli (cached in MinIO platform-cache bucket)
  - name: install-whisper-cli
    image: minio/mc@sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727
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
        MODEL=$WHISPER_DIR/ggml-base.bin
        WRAPPER=$WHISPER_DIR/run-whisper.sh
        CACHE_PFX=whisper
        MARKER=$WHISPER_DIR/.whisper-cache-miss
        mkdir -p $WHISPER_DIR
        rm -f $MARKER

        echo "Initializing whisper assets from MinIO cache..."
        mc alias set cache "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --quiet

        # ffmpeg
        if [ ! -f $WHISPER_DIR/ffmpeg ]; then
          if mc stat cache/$MINIO_BUCKET/$CACHE_PFX/ffmpeg > /dev/null 2>&1; then
            echo "Restoring ffmpeg from cache..."
            mc cp cache/$MINIO_BUCKET/$CACHE_PFX/ffmpeg $WHISPER_DIR/ffmpeg && chmod +x $WHISPER_DIR/ffmpeg
          else
            echo "Cache miss: ffmpeg"
            echo ffmpeg >> $MARKER
          fi
        fi

        # whisper model
        if [ ! -f $MODEL ]; then
          if mc stat cache/$MINIO_BUCKET/$CACHE_PFX/ggml-base.bin > /dev/null 2>&1; then
            echo "Restoring whisper model from cache..."
            mc cp cache/$MINIO_BUCKET/$CACHE_PFX/ggml-base.bin $MODEL
          else
            echo "Cache miss: ggml-base.bin"
            echo model >> $MARKER
          fi
        fi

        # whisper-cli binary
        if [ ! -f $BIN ]; then
          if mc stat cache/$MINIO_BUCKET/$CACHE_PFX/whisper-cli > /dev/null 2>&1; then
            echo "Restoring whisper-cli from cache..."
            mc cp cache/$MINIO_BUCKET/$CACHE_PFX/whisper-cli $BIN && chmod +x $BIN
          else
            echo "Cache miss: whisper-cli"
            echo bin >> $MARKER
          fi
        fi

        # whisper shared libraries
        for asset in libwhisper.so.1 libggml.so.0 libggml-base.so.0 libggml-cpu.so.0; do
          TARGET=$WHISPER_DIR/$asset
          if [ ! -f $TARGET ]; then
            if mc stat cache/$MINIO_BUCKET/$CACHE_PFX/$asset > /dev/null 2>&1; then
              echo "Restoring $asset from cache..."
              mc cp cache/$MINIO_BUCKET/$CACHE_PFX/$asset $TARGET
            else
              echo "Cache miss: $asset"
              echo $asset >> $MARKER
            fi
          fi
        done

        cat > $WRAPPER << 'WEOF'
        #!/bin/sh
        export LD_LIBRARY_PATH=/whisper-storage${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
        TMP_WAV=$(mktemp /tmp/whisper_XXXXXX.wav)
        /whisper-storage/ffmpeg -i "$1" -ar 16000 -ac 1 -f wav "$TMP_WAV" -y 2>/dev/null
        /whisper-storage/whisper-cli -m /whisper-storage/ggml-base.bin -f "$TMP_WAV" --language auto --no-timestamps 2>/dev/null
        EC=$?
        rm -f "$TMP_WAV"
        exit $EC
        WEOF
        if [ ! -f "$MARKER" ]; then
          chmod +x $WRAPPER
          echo "Whisper assets ready from cache."
        else
          echo "Whisper cache incomplete; fallback build/download will run."
        fi
    env:
      - name: MINIO_ENDPOINT
        value: "http://minio.minio.svc.cluster.local:9000"
      - name: MINIO_ACCESS_KEY
        valueFrom:
          secretKeyRef:
            name: minio-cache-creds
            key: access-key
      - name: MINIO_SECRET_KEY
        valueFrom:
          secretKeyRef:
            name: minio-cache-creds
            key: secret-key
      - name: MINIO_BUCKET
        value: "platform-cache"
    volumeMounts:
      - name: pvc-whisper
        mountPath: /whisper-storage
  - name: install-whisper-cli-fallback
    image: ghcr.io/mctlhq/openclaw-whisper-builder:2026.3.24-beta.19
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
        MODEL=$WHISPER_DIR/ggml-base.bin
        WRAPPER=$WHISPER_DIR/run-whisper.sh
        CACHE_PFX=whisper
        MARKER=$WHISPER_DIR/.whisper-cache-miss

        if [ ! -f "$MARKER" ]; then
          echo "Whisper cache is complete; skipping fallback."
          exit 0
        fi

        echo "Whisper cache miss detected; restoring prebaked assets from builder image..."
        mc alias set cache "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY" --quiet

        if [ ! -f $WHISPER_DIR/ffmpeg ]; then
          cp /opt/whisper-assets/ffmpeg $WHISPER_DIR/ffmpeg
          chmod +x $WHISPER_DIR/ffmpeg
          mc cp $WHISPER_DIR/ffmpeg cache/$MINIO_BUCKET/$CACHE_PFX/ffmpeg || true
        fi

        if [ ! -f $MODEL ]; then
          cp /opt/whisper-assets/ggml-base.bin $MODEL
          mc cp $MODEL cache/$MINIO_BUCKET/$CACHE_PFX/ggml-base.bin || true
        fi

        if [ ! -f $BIN ]; then
          cp /opt/whisper-assets/whisper-cli $BIN
          chmod +x $BIN
          mc cp $BIN cache/$MINIO_BUCKET/$CACHE_PFX/whisper-cli || true
        fi

        for asset in libwhisper.so.1 libggml.so.0 libggml-base.so.0 libggml-cpu.so.0; do
          TARGET=$WHISPER_DIR/$asset
          if [ ! -f $TARGET ]; then
            cp /opt/whisper-assets/$asset $TARGET
            mc cp $TARGET cache/$MINIO_BUCKET/$CACHE_PFX/$asset || true
          fi
        done

        cat > $WRAPPER << 'WEOF'
        #!/bin/sh
        export LD_LIBRARY_PATH=/whisper-storage${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
        TMP_WAV=$(mktemp /tmp/whisper_XXXXXX.wav)
        /whisper-storage/ffmpeg -i "$1" -ar 16000 -ac 1 -f wav "$TMP_WAV" -y 2>/dev/null
        /whisper-storage/whisper-cli -m /whisper-storage/ggml-base.bin -f "$TMP_WAV" --language auto --no-timestamps 2>/dev/null
        EC=$?
        rm -f "$TMP_WAV"
        exit $EC
        WEOF
        chmod +x $WRAPPER
        rm -f $MARKER
        echo "Whisper fallback restored prebaked assets and refreshed cache."
    env:
      - name: MINIO_ENDPOINT
        value: "http://minio.minio.svc.cluster.local:9000"
      - name: MINIO_ACCESS_KEY
        valueFrom:
          secretKeyRef:
            name: minio-cache-creds
            key: access-key
      - name: MINIO_SECRET_KEY
        valueFrom:
          secretKeyRef:
            name: minio-cache-creds
            key: secret-key
      - name: MINIO_BUCKET
        value: "platform-cache"
    volumeMounts:
      - name: pvc-whisper
        mountPath: /whisper-storage
  # 3. Setup config and inject tokens
  - name: setup
    # Run as root so the chown -R at the end can correct ownership of
    # /home/node/.openclaw — the openclaw image bakes USER=node (UID 1000)
    # which doesn't have permission to chown root-owned restore-state output.
    securityContext:
      runAsUser: 0
      runAsGroup: 0
    image: "ghcr.io/mctlhq/mctl-openclaw:__IMAGE_TAG__"
    command: ["sh", "-c"]
    args:
      - |
        set -eu
        echo "Preparing writable OpenClaw config..."
        cp /config-tpl/openclaw.json /config-rw/openclaw.json
        if [ -n "$TELEGRAM_TOKEN" ]; then
          echo "Injecting Telegram token into runtime config..."
          sed -i "s|__TELEGRAM_TOKEN__|$TELEGRAM_TOKEN|g" /config-rw/openclaw.json
        else
          echo "Telegram token is empty; leaving placeholder unchanged."
        fi
        WORKSPACE=/home/node/.openclaw/workspace
        mkdir -p "$WORKSPACE/memory" "$WORKSPACE/skills" /home/node/.openclaw/bundled-skills

        # One-time migration: the previous base64 setup init wrote skill
        # dirs (mctl-platform + historical remediation set) without any
        # ownership marker. Backfill .layer2 on those names so the new
        # refresh logic below picks them up as Layer-2 and rewrites with
        # current /app overlay content. Skip if the fan-out sidecar has
        # already claimed the dir as .layer3 (name collision — Layer-3
        # wins).
        for legacy in mctl-platform mctl-agent-external mctl-gitops-remediation mctl-github-remediation; do
          d="$WORKSPACE/skills/$legacy"
          [ -d "$d" ] || continue
          [ -f "$d/.layer2" ] && continue
          [ -f "$d/.layer3" ] && continue
          : > "$d/.layer2"
        done

        # Always refresh Layer-2 identity files from the image overlay.
        # /app/mctl-identity is the source of truth — on image bump the
        # workspace picks up the new content on next boot, so operators
        # don't have to grep AGENTS.md for a specific section string to
        # detect staleness. Fail fast if the overlay is missing; a
        # rollback to a tag without /app/mctl-identity should surface
        # as a startup error, not a silently uninitialized workspace.
        if [ ! -d /app/mctl-identity ]; then
          echo "FATAL: /app/mctl-identity missing — openclaw image is missing the MCTL Layer-2 overlay. Check the image tag." >&2
          exit 1
        fi
        echo "Refreshing Layer-2 identity files from image overlay..."
        cp /app/mctl-identity/*.md "$WORKSPACE/"

        # Refresh Layer-2 skills per-dir, but never overwrite a dir the
        # fan-out sidecar owns (Layer-3). Rule: if a dir exists and is
        # missing the .layer2 marker, it was created by the sidecar from
        # a tenant ConfigMap key (or restored from S3) — leave it alone.
        if [ -d /app/mctl-skills ]; then
          for src in /app/mctl-skills/*/; do
            [ -d "$src" ] || continue
            name="${src%/}"
            name="${name##*/}"
            if [ -d "$WORKSPACE/skills/$name" ] && [ ! -f "$WORKSPACE/skills/$name/.layer2" ]; then
              echo "Skipping Layer-2 refresh of Layer-3 dir: $name"
              continue
            fi
            # Wipe the destination first so files deleted upstream in a new
            # image overlay don't linger as stale artefacts. Only the dirs
            # we already own (.layer2) or that are fresh (nonexistent) are
            # wiped — Layer-3 dirs are skipped above.
            rm -rf "$WORKSPACE/skills/$name"
            mkdir -p "$WORKSPACE/skills/$name"
            cp -r "$src." "$WORKSPACE/skills/$name/"
            : > "$WORKSPACE/skills/$name/.layer2"
          done
          # Prune Layer-2 dirs that were removed from the image overlay
          # — e.g. deprecated skills from previous base64 seeding that no
          # longer ship in /app/mctl-skills. Only touch dirs marked
          # .layer2 (we own them); dirs with .layer3 or without any
          # marker stay untouched.
          for d in "$WORKSPACE/skills"/*/; do
            [ -d "$d" ] || continue
            name="${d%/}"
            name="${name##*/}"
            [ -f "$d/.layer2" ] || continue
            [ -d "/app/mctl-skills/$name" ] && continue
            rm -rf "$d"
            echo "Removed deprecated Layer-2 skill: $name"
          done
        fi

        rm -f "$WORKSPACE/BOOTSTRAP.md"
        echo "Fixing ownership for config and restored state..."
        chown 1000:1000 /config-rw/openclaw.json
        chown -R 1000:1000 /home/node/.openclaw
        echo "Setup complete."
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
      - name: state-data
        mountPath: /home/node/.openclaw
extraVolumeMounts:
  - name: openclaw-config-rw
    mountPath: /config-rw
  - name: pvc-whisper
    mountPath: /whisper-storage
  - name: openclaw-scripts
    mountPath: /scripts
    readOnly: true
  - name: state-data
    mountPath: /home/node/.openclaw

extraContainers:
  - name: s3-sync
    image: minio/mc@sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727
    resources:
      requests:
        cpu: 25m
        memory: 64Mi
      limits:
        # Explicit 1000m overrides the tenant LimitRange default (500m).
        # `mc mirror` runs ~2s bursts every 10s and spikes past 500m; 1000m
        # sits within every tenant's LimitRange max (1500m/2) with headroom.
        cpu: 1000m
        memory: 256Mi
    command: ["sh", "-c"]
    args:
      - |
        mc alias set s3 "$MINIO_ENDPOINT" "$MINIO_ACCESS_KEY" "$MINIO_SECRET_KEY"
        # Canary path. Presence + non-empty content is our proxy for
        # "the pod has finished bootstrap and the agent has live state".
        # Empty or missing => either first-boot (nothing to wipe yet) or
        # post-wipe (e.g. ImagePullBackOff cascade left an empty emptyDir
        # — see incident write-up in references/k8s.md). In both cases we
        # mirror WITHOUT --remove so deletions can never propagate to S3.
        AGENT_DIR=/home/node/.openclaw/agents/main/agent
        while true; do
          if [ -d "$AGENT_DIR" ] && [ -n "$(ls -A "$AGENT_DIR" 2>/dev/null)" ]; then
            mc mirror --remove --overwrite \
              --exclude '*.lock' \
              --exclude '*.lock/*' \
              --exclude '*.tmp' \
              /home/node/.openclaw s3/platform-state/__TEAM_NAME__/__SERVICE_NAME__/ || true
          else
            mc mirror --overwrite \
              --exclude '*.lock' \
              --exclude '*.lock/*' \
              --exclude '*.tmp' \
              /home/node/.openclaw s3/platform-state/__TEAM_NAME__/__SERVICE_NAME__/ || true
          fi
          sleep 10
        done
    lifecycle:
      # Flush tenant state (auth-profiles.json, sessions, memory) to S3
      # synchronously before SIGTERM. Without this, the ongoing 10s mirror
      # loop often misses the last few writes, the Recreate rollout brings
      # up a fresh emptyDir, and restore-state pulls a stale snapshot from
      # S3 — auth connections and session history disappear. `mc alias set`
      # runs at container start and persists to ~/.mc/config.json, so the
      # `s3/...` path here is already resolved when preStop fires. Same
      # canary guard as the main loop applies here.
      preStop:
        exec:
          command:
            - sh
            - -c
            - |
              AGENT_DIR=/home/node/.openclaw/agents/main/agent
              if [ -d "$AGENT_DIR" ] && [ -n "$(ls -A "$AGENT_DIR" 2>/dev/null)" ]; then
                mc mirror --remove --overwrite \
                  --exclude '*.lock' \
                  --exclude '*.lock/*' \
                  --exclude '*.tmp' \
                  /home/node/.openclaw s3/platform-state/__TEAM_NAME__/__SERVICE_NAME__/ || true
              else
                mc mirror --overwrite \
                  --exclude '*.lock' \
                  --exclude '*.lock/*' \
                  --exclude '*.tmp' \
                  /home/node/.openclaw s3/platform-state/__TEAM_NAME__/__SERVICE_NAME__/ || true
              fi
    env:
      - name: MINIO_ENDPOINT
        value: "http://minio.minio.svc.cluster.local:9000"
      - name: MINIO_ACCESS_KEY
        valueFrom: { secretKeyRef: { name: minio-cache-creds, key: access-key } }
      - name: MINIO_SECRET_KEY
        valueFrom: { secretKeyRef: { name: minio-cache-creds, key: secret-key } }
    volumeMounts:
      - name: state-data
        mountPath: /home/node/.openclaw

  # Layer-3 skills fan-out: watch the tenant-scoped __TEAM_NAME__-__SERVICE_NAME__-skills
  # ConfigMap (rendered by platform-gitops/helm-charts/openclaw-skills from
  # generated/skills-values.yaml, which itself is rewritten on every
  # mctl_save_openclaw_skill / mctl_delete_openclaw_skill workflow) and
  # mirror each <name>.md key into /home/node/.openclaw/workspace/skills/
  # <name>/SKILL.md. Layer-2 skills shipped in /app/mctl-skills are left
  # alone — only Layer-3 entries that disappear from the CM are pruned.
  - name: skills-fanout
    image: busybox:1.36
    command: ["sh", "-c"]
    args:
      - |
        SRC=/mctl-layer3-skills
        DST=/home/node/.openclaw/workspace/skills
        MARK=.layer3
        mkdir -p "$DST"
        echo "layer3-skills fan-out started; source=$SRC dest=$DST"
        while true; do
          # `optional: true` on the CM volume means $SRC may be an empty
          # dir while the ConfigMap is still being rendered or has been
          # transiently deleted — treat that the same as "no mount" and
          # skip pruning, otherwise the prune loop would drop every
          # Layer-3 skill whenever ArgoCD blinks. Detect a real mount by
          # the presence of skill keys (*.md) or the chart-rendered empty
          # marker (.placeholder) — ignore k8s projected-volume metadata
          # such as `..data` / `..YYYY_MM_DD_...` which `ls -A` would
          # otherwise count as content.
          has_cm=0
          [ -f "$SRC/.placeholder" ] && has_cm=1
          if [ "$has_cm" = 0 ] && [ -d "$SRC" ]; then
            for _probe in "$SRC"/*.md; do
              [ -e "$_probe" ] || break
              has_cm=1
              break
            done
          fi
          if [ "$has_cm" = 1 ]; then
            for f in "$SRC"/*.md; do
              [ -e "$f" ] || continue
              base="${f##*/}"
              base="${base%.md}"
              [ "$base" = ".placeholder" ] && continue
              # A dir marked as Layer-2 (setup init seeded it from an image
              # overlay or from the legacy base64 blobs) is read-only from
              # the fan-out sidecar's perspective — never overwrite or
              # prune it, a Layer-3 skill with a name collision is a bug.
              if [ -f "$DST/$base/.layer2" ]; then
                continue
              fi
              mkdir -p "$DST/$base"
              if ! cmp -s "$f" "$DST/$base/SKILL.md" 2>/dev/null; then
                cp "$f" "$DST/$base/SKILL.md"
                echo "synced: $base"
              fi
              # Leave a marker so the prune loop knows this dir was written
              # by the fan-out sidecar. Layer-2 skills seeded by setup init
              # from /app/mctl-skills do not carry the marker and must
              # therefore never be pruned here.
              : > "$DST/$base/$MARK"
            done
            for d in "$DST"/*/; do
              [ -d "$d" ] || continue
              name="${d%/}"
              name="${name##*/}"
              [ -f "$SRC/$name.md" ] && continue
              [ -f "$d/$MARK" ] || continue
              rm -rf "$d"
              echo "removed: $name"
            done
          fi
          sleep 10
        done
    resources:
      requests:
        cpu: 10m
        memory: 16Mi
      limits:
        cpu: 100m
        memory: 64Mi
    volumeMounts:
      - name: layer3-skills-cm
        mountPath: /mctl-layer3-skills
        readOnly: true
      - name: state-data
        mountPath: /home/node/.openclaw
  - name: mctl-token-refresh
    # Proactive mctl OAuth token refresh. Checks every 5 min and refreshes when
    # the access token has < 45 min remaining, matching the mctl-mcp-proxy.js
    # threshold. Prevents silent expiry on idle pods without any UI interaction.
    image: node:22-alpine@sha256:968df39aedcea65eeb078fb336ed7191baf48f972b4479711397108be0966920
    resources:
      requests:
        cpu: 5m
        memory: 32Mi
      limits:
        cpu: 50m
        memory: 64Mi
    command: ["sh", "-c"]
    args:
      - |
        cat > /tmp/mctl-refresh.cjs << 'NODESCRIPT'
        'use strict';
        const fs = require('fs');
        const https = require('https');
        const CREDS = '/home/node/.openclaw/mcp-auth/mctl/credentials.json';
        const INTERVAL_MS = 5 * 60 * 1000;
        const THRESHOLD_MS = 45 * 60 * 1000;
        function post(hostname, path, body) {
          return new Promise(resolve => {
            const buf = Buffer.from(body);
            const req = https.request(
              { hostname, path, method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json', 'Content-Length': buf.length } },
              res => { let d = ''; res.on('data', c => d += c); res.on('end', () => { try { resolve({ ok: res.statusCode < 300, body: JSON.parse(d) }); } catch { resolve({ ok: false, body: {} }); } }); }
            );
            req.on('error', () => resolve({ ok: false, body: {} }));
            req.write(buf);
            req.end();
          });
        }
        async function check() {
          let creds;
          try { creds = JSON.parse(fs.readFileSync(CREDS, 'utf8')); } catch { return; }
          if (!creds.refreshToken || !creds.clientId || !creds.apiBase || (creds.refreshFailureCount || 0) > 0) return;
          const exp = Date.parse(creds.expiresAt);
          if (!Number.isFinite(exp) || exp - Date.now() > THRESHOLD_MS) return;
          const minLeft = Math.round((exp - Date.now()) / 60000);
          process.stdout.write('[mctl-refresh] ' + new Date().toISOString() + ' expires in ' + minLeft + 'min, refreshing\n');
          const params = new URLSearchParams({ grant_type: 'refresh_token', refresh_token: creds.refreshToken, client_id: creds.clientId });
          const host = creds.apiBase.replace(/^https?:\/\//, '');
          const { ok, body } = await post(host, '/oauth/token', params.toString());
          if (!ok || body.error) {
            const err = body.error || 'unknown', desc = body.error_description || '';
            process.stdout.write('[mctl-refresh] failed: ' + err + ' ' + desc + '\n');
            const invalid = ['invalid_grant', 'invalid_token'].includes(err) || desc.includes('refresh token');
            if (invalid) {
              let fresh; try { fresh = JSON.parse(fs.readFileSync(CREDS, 'utf8')); } catch { fresh = null; }
              if (fresh && fresh.refreshToken !== creds.refreshToken) return;
              const failed = { ...creds, refreshFailureCount: (creds.refreshFailureCount || 0) + 1, refreshFailureFirstAt: creds.refreshFailureFirstAt || new Date().toISOString(), updatedAt: new Date().toISOString() };
              fs.writeFileSync(CREDS + '.tmp', JSON.stringify(failed, null, 2), { mode: 0o600 }); fs.renameSync(CREDS + '.tmp', CREDS);
            }
            return;
          }
          if (!body.access_token) { process.stdout.write('[mctl-refresh] invalid response: missing access_token\n'); return; }
          const now = Date.now();
          const expiresIn = typeof body.expires_in === 'number' ? body.expires_in : 3600;
          const updated = { ...creds, accessToken: body.access_token, refreshToken: body.refresh_token || creds.refreshToken, expiresAt: new Date(now + expiresIn * 1000).toISOString(), updatedAt: new Date(now).toISOString(), refreshFailureCount: 0, refreshFailureFirstAt: null };
          fs.writeFileSync(CREDS + '.tmp', JSON.stringify(updated, null, 2), { mode: 0o600 }); fs.renameSync(CREDS + '.tmp', CREDS);
          process.stdout.write('[mctl-refresh] ok expiresAt=' + updated.expiresAt + '\n');
        }
        check().catch(e => process.stdout.write('[mctl-refresh] error: ' + e.message + '\n'));
        setInterval(() => check().catch(e => process.stdout.write('[mctl-refresh] error: ' + e.message + '\n')), INTERVAL_MS);
        NODESCRIPT
        exec node /tmp/mctl-refresh.cjs
    volumeMounts:
      - name: state-data
        mountPath: /home/node/.openclaw

persistence:
  state:
    enabled: false

extraVolumes:
  - name: openclaw-config-tpl
    configMap:
      name: __SERVICE_NAME__-config
  - name: openclaw-config-rw
    emptyDir: {}
  - name: pvc-whisper
    emptyDir: {}
  - name: state-data
    emptyDir: {}
  - name: layer3-skills-cm
    configMap:
      name: __TEAM_NAME__-__SERVICE_NAME__-skills
      optional: true
  - name: openclaw-scripts
    configMap:
      name: openclaw-scripts
      defaultMode: 0755

dbSecret:
  vaultPath: teams/__TEAM_NAME__/__SERVICE_NAME__/database
  secretName: __TEAM_NAME__-__SERVICE_NAME__-db-creds

dbInitJob:
  enabled: false

extraExternalSecrets:
  ghcr-credentials:
    refreshInterval: 24h
    targetSecret: ghcr-credentials
    targetTemplateType: kubernetes.io/dockerconfigjson
    targetTemplateMetadataAnnotations:
      argocd.argoproj.io/compare-options: IgnoreExtraneous
    data:
      - secretKey: .dockerconfigjson
        remoteKey: platform/backstage/ghcr-credentials
        property: dockerconfigjson
  openclaw-telegram-secret:
    refreshInterval: 1h
    targetSecret: openclaw-telegram-secret
    data:
      - secretKey: OPENCLAW_TELEGRAM_TOKEN
        remoteKey: secret/data/teams/__TEAM_NAME__/__SERVICE_NAME__/telegram
        property: telegram-bot-token
  minio-cache-creds:
    refreshInterval: 1h
    targetSecret: minio-cache-creds
    data:
      - secretKey: access-key
        remoteKey: secret/data/platform/minio
        property: root-user
      - secretKey: secret-key
        remoteKey: secret/data/platform/minio
        property: root-password

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
      let sessionId = '';
      let queue = Promise.resolve();
      process.stdin.setEncoding('utf8');
      let buf = '';
      process.stdin.on('data', chunk => {
        buf += chunk;
        let nl;
        while ((nl = buf.indexOf('\n')) !== -1) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (line) {
            queue = queue.then(() => handleLine(line)).catch(() => {});
          }
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
        const headers = {
          'Content-Type': 'application/json',
          'Accept': 'application/json, text/event-stream',
          'Authorization': `Bearer ${token}`,
        };
        if (sessionId) {
          headers['Mcp-Session-Id'] = sessionId;
        }
        const res = await fetch(`${apiBase}/mcp`, {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
        });
        const nextSessionId = res.headers.get('mcp-session-id');
        if (nextSessionId) {
          sessionId = nextSessionId;
        }
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
      // Proactive token refresh: keep credentials alive without waiting for
      // an incoming message. Checks every 30 min; refreshes when the access
      // token has less than 45 min left. Prevents the refresh token from
      // expiring during long idle periods (bug: on-demand-only refresh died
      // if no message arrived before the refresh token TTL elapsed).
      setInterval(async () => {
        try {
          const auth = await readAuth().catch(() => null);
          if (!auth || !auth.expiresAt) return;
          const ms = Date.parse(auth.expiresAt);
          if (Number.isFinite(ms) && ms <= Date.now() + 45 * 60_000) {
            await refreshAuth(auth);
          }
        } catch (_) {}
      }, 30 * 60 * 1000);
    github-pr-mcp.js: |-
      #!/usr/bin/env node
      const { Buffer } = require('buffer');
      const { McpServer } = require('/app/node_modules/@modelcontextprotocol/sdk/dist/cjs/server/mcp.js');
      const { StdioServerTransport } = require('/app/node_modules/@modelcontextprotocol/sdk/dist/cjs/server/stdio.js');
      const { z } = require('/app/node_modules/zod/index.cjs');
      const apiBase = 'https://api.github.com';
      function text(value) {
        return { content: [{ type: 'text', text: JSON.stringify(value, null, 2) }] };
      }
      function splitRepo(full) {
        const parts = String(full || '').trim().split('/');
        if (parts.length !== 2 || !parts[0] || !parts[1]) throw new Error('repo must be owner/name');
        return { owner: parts[0], repo: parts[1] };
      }
      function allowedRepos() {
        return String(process.env.OPENCLAW_GITHUB_ALLOWED_REPOS || process.env.GITHUB_PR_ALLOWED_REPOS || '')
          .split(',')
          .map((entry) => entry.trim())
          .filter(Boolean);
      }
      function assertAllowed(repo) {
        const allowed = allowedRepos();
        if (allowed.length > 0 && !allowed.includes(repo)) {
          throw new Error(`repo ${repo} is not in OPENCLAW_GITHUB_ALLOWED_REPOS`);
        }
      }
      function authToken() {
        return process.env.GITHUB_TOKEN || process.env.GH_TOKEN || '';
      }
      async function gh(method, pathname, body) {
        const token = authToken();
        if (!token) throw new Error('GITHUB_TOKEN is not configured for OpenClaw');
        const res = await fetch(`${apiBase}${pathname}`, {
          method,
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: 'application/vnd.github+json',
            'Content-Type': 'application/json',
            'User-Agent': 'openclaw-github-pr-mcp',
          },
          body: body === undefined ? undefined : JSON.stringify(body),
        });
        const raw = await res.text();
        let parsed = {};
        try { parsed = raw ? JSON.parse(raw) : {}; } catch (_) {}
        if (!res.ok) {
          const msg = parsed && parsed.message ? parsed.message : `GitHub API ${res.status}`;
          throw new Error(msg);
        }
        return parsed;
      }
      async function getRefSha(repoFull, ref) {
        const { owner, repo } = splitRepo(repoFull);
        const data = await gh('GET', `/repos/${owner}/${repo}/git/ref/heads/${encodeURIComponent(ref)}`);
        return data.object && data.object.sha ? data.object.sha : '';
      }
      async function ensureBranch(repoFull, branch, base) {
        const { owner, repo } = splitRepo(repoFull);
        try {
          await gh('GET', `/repos/${owner}/${repo}/git/ref/heads/${encodeURIComponent(branch)}`);
          return;
        } catch (err) {
          const msg = String(err && err.message ? err.message : err);
          if (!msg.includes('Reference does not exist') && !msg.includes('Not Found')) throw err;
        }
        const baseSha = await getRefSha(repoFull, base);
        await gh('POST', `/repos/${owner}/${repo}/git/refs`, {
          ref: `refs/heads/${branch}`,
          sha: baseSha,
        });
      }
      async function getFile(repoFull, filePath, ref) {
        const { owner, repo } = splitRepo(repoFull);
        const encodedPath = filePath.split('/').map(encodeURIComponent).join('/');
        try {
          return await gh('GET', `/repos/${owner}/${repo}/contents/${encodedPath}?ref=${encodeURIComponent(ref)}`);
        } catch (err) {
          if (String(err && err.message ? err.message : err).includes('Not Found')) return null;
          throw err;
        }
      }
      async function findOpenPullRequest(repoFull, branch, base) {
        const { owner, repo } = splitRepo(repoFull);
        const data = await gh('GET', `/repos/${owner}/${repo}/pulls?state=open&head=${encodeURIComponent(`${owner}:${branch}`)}&base=${encodeURIComponent(base)}`);
        return Array.isArray(data) && data.length > 0 ? data[0] : null;
      }
      const server = new McpServer({ name: 'github-pr-mcp', version: '1.0.0' });
      server.tool(
        'github_find_open_pull_request',
        'Find an existing open pull request for a deterministic remediation branch.',
        { repo: z.string(), branch: z.string(), base: z.string().optional() },
        async ({ repo, branch, base = 'main' }) => {
          assertAllowed(repo);
          const pr = await findOpenPullRequest(repo, branch, base);
          return text({
            ok: true,
            repo,
            branch,
            base,
            pullRequest: pr ? {
              number: pr.number,
              url: pr.html_url,
              title: pr.title,
              state: pr.state,
              headSha: pr.head && pr.head.sha ? pr.head.sha : '',
            } : null,
          });
        },
      );
      server.tool(
        'github_get_file',
        'Read a file from an allowlisted GitHub repo and ref.',
        { repo: z.string(), path: z.string(), ref: z.string().optional() },
        async ({ repo, path, ref = 'main' }) => {
          assertAllowed(repo);
          const file = await getFile(repo, path, ref);
          if (!file) return text({ ok: false, repo, path, ref, error: 'not_found' });
          const decoded = file.content ? Buffer.from(String(file.content).replace(/\\n/g, ''), 'base64').toString('utf8') : '';
          return text({ ok: true, repo, path, ref, sha: file.sha || '', content: decoded });
        },
      );
      server.tool(
        'github_upsert_file',
        'Create or update one file on a deterministic remediation branch.',
        {
          repo: z.string(),
          branch: z.string(),
          path: z.string(),
          content: z.string(),
          commitMessage: z.string(),
          base: z.string().optional(),
        },
        async ({ repo, branch, path, content, commitMessage, base = 'main' }) => {
          assertAllowed(repo);
          await ensureBranch(repo, branch, base);
          const { owner, repo: repoName } = splitRepo(repo);
          const encodedPath = path.split('/').map(encodeURIComponent).join('/');
          const existing = await getFile(repo, path, branch);
          const payload = {
            message: commitMessage,
            content: Buffer.from(content, 'utf8').toString('base64'),
            branch,
            sha: existing && existing.sha ? existing.sha : undefined,
          };
          const data = await gh('PUT', `/repos/${owner}/${repoName}/contents/${encodedPath}`, payload);
          return text({
            ok: true,
            repo,
            branch,
            path,
            commitSha: data.commit && data.commit.sha ? data.commit.sha : '',
          });
        },
      );
      server.tool(
        'github_open_pull_request',
        'Open or reuse a pull request for an existing remediation branch.',
        {
          repo: z.string(),
          branch: z.string(),
          title: z.string(),
          body: z.string(),
          base: z.string().optional(),
          draft: z.boolean().optional(),
        },
        async ({ repo, branch, title, body, base = 'main', draft = false }) => {
          assertAllowed(repo);
          const existing = await findOpenPullRequest(repo, branch, base);
          if (existing) {
            return text({
              ok: true,
              reused: true,
              repo,
              branch,
              pr_number: existing.number,
              pr_url: existing.html_url,
              commit_sha: existing.head && existing.head.sha ? existing.head.sha : '',
            });
          }
          const { owner, repo: repoName } = splitRepo(repo);
          const created = await gh('POST', `/repos/${owner}/${repoName}/pulls`, {
            title,
            body,
            head: branch,
            base,
            draft,
          });
          return text({
            ok: true,
            reused: false,
            repo,
            branch,
            pr_number: created.number,
            pr_url: created.html_url,
            commit_sha: created.head && created.head.sha ? created.head.sha : '',
          });
        },
      );
      server.connect(new StdioServerTransport()).catch((err) => {
        console.error(err);
        process.exit(1);
      });
  __SERVICE_NAME__-config:
    openclaw.json: |-
      {
        "gateway": {
          "bind": "lan",
          "port": 18789,
          "auth": {
            "mode": "trusted-proxy",
            "trustedProxy": {
              "userHeader": "X-Forwarded-User",
              "roleHeader": "X-Mctl-Team-Role"
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
        "agents": {
          "defaults": {
            "skipBootstrap": true,
            "model": {
              "primary": "__DEFAULT_MODEL__"
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
            "allowFrom": __TELEGRAM_OWNER_IDS_JSON__
          }
        },
        "hooks": {
          "enabled": true,
          "path": "/hooks",
          "token": "mctl-agent-hook-20260325",
          "defaultSessionKey": "hook:mctl-agent:default",
          "allowedSessionKeyPrefixes": ["hook:"],
          "allowedAgentIds": ["main"],
          "mappings": [
            {
              "id": "mctl-agent-event",
              "match": {
                "path": "mctl-agent"
              },
              "action": "agent",
              "name": "MCTL Agent Incident",
              "sessionKey": "hook:mctl-agent:{{payload.ticket.id}}",
              "messageTemplate": "You are the automated external remediation agent for mctl-agent.\n\nIncident:\n- Event: {{payload.event_type}}\n- Ticket: {{payload.ticket.id}}\n- Team: {{payload.ticket.team}}\n- Service: {{payload.ticket.service}}\n- Severity: {{payload.ticket.severity}}\n- Summary: {{payload.ticket.summary}}\n- Analysis: {{payload.ticket.analysis}}\n\nCallback contract:\n- claim_url: {{payload.delivery.claim_url}}\n- result_url: {{payload.delivery.result_url}}\n- callback_auth_header: {{payload.delivery.callback_auth_header}}\n- callback_auth_value: {{payload.delivery.callback_auth_value}}\n- agent_id: openclaw-labs\n- event_id: {{payload.event_id}}\n\nOperating mode:\n- Conservative PR-only remediation.\n- OpenClaw owns PR creation and follow-up commits for this incident flow.\n- mctl-agent remains the system of record for ticket state.\n- Do not perform direct destructive platform actions.\n- Do not resolve incidents directly.\n- Do not rely on any mctl-agent MCP server.\n- Ignore any generic startup ritual for this session.\n\nRules:\n1. Only auto-claim events ticket.fix_failed or ticket.escalated. Never auto-claim ticket.created.\n2. Before reading workspace files or doing any other exploration, call tool mctl_agent_external with action=claim.\n3. If claim returns 409 or ok=false, stop and summarize briefly.\n4. Only after a successful claim may you gather evidence.\n5. After claim, prefer available mctl_* tools first. Start with service status/config/logs, incidents, workflows, tenant details, and resource usage.\n6. Only use GitHub tools for explicit repo-backed remediation after evidence supports a concrete low-risk change. Respect the runtime repo allowlist.\n7. Reuse one deterministic remediation branch per ticket when updating an existing PR instead of creating parallel branches.\n8. Only send status=pr_created when a real PR has been created or updated and you have concrete artifacts for repo, branch, pr_url, pr_number, and commit_sha.\n9. If evidence is incomplete, the incident is synthetic, no safe repo-backed fix exists, GitHub access is unavailable, the repo is not allowlisted, the action would be destructive, or the safest path is operator review, send status=needs_human with a concise operator-ready summary and the next checks to perform.\n10. If the workflow itself fails after claim, send status=failed.\n11. Always send exactly one result callback after a successful claim.\n12. Use idempotencyKey=openclaw:{{payload.ticket.id}}:{{payload.event_id}}.",
              "deliver": false,
              "model": "__DEFAULT_MODEL__",
              "thinking": "medium",
              "timeoutSeconds": 180
            }
          ]
        },
        "tools": {
          "media": {
            "audio": {
              "enabled": true,
              "models": [
                {
                  "type": "cli",
                  "command": "/whisper-storage/run-whisper.sh",
                  "args": ["{{MediaPath}}"],
                  "timeoutSeconds": 45
                }
              ]
            }
          }
        },

        "mcp": {
          "servers": {
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
