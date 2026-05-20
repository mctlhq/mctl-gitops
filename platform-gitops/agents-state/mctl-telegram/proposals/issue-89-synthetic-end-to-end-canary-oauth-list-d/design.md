# Design: issue-89-synthetic-end-to-end-canary-oauth-list-d

## Current state

### Health signal

`cmd/server/main.go` line 313 registers `GET /healthz` and `GET /readyz` as
trivial responders that write `"ok\n"` and return HTTP 200. They confirm the
process is alive but exercise none of the following runtime paths:

- the Telegram OIDC client secret (used during OAuth flows in `internal/oauth/`)
- `internal/telegram/clientpool.go` (`ClientPool.Borrow`)
- `internal/db/` session lookup and decryption (`internal/crypto/aesgcm.go`)
- the MTProto session pool (authenticated calls via `gotd/td`)

### Metrics

`internal/metrics/metrics.go` defines a `Registry` struct backed by a fresh
`prometheus.Registry` (not the global `DefaultRegisterer`). All metric names
carry the `mctl_` prefix. The main server injects this registry into every
subsystem. The `/metrics` endpoint is served by
`promhttp.HandlerFor(m.Prometheus, ...)` gated by an optional CIDR allowlist
(`METRICS_ALLOW_CIDR`). There is currently no `mctl_telegram_canary_*` metric
family.

### Flood-wait handling

`internal/telegram/floodwait.go` exports `FloodWaitSeconds(err error) int`,
which extracts the wait duration from a `FLOOD_WAIT_X` or
`FLOOD_PREMIUM_WAIT_X` MTProto error (code 420). `internal/mcp/tools.go`'s
`borrowWithRetry` wraps this with up to `maxFloodWaitRetries=3` retries capped
at `maxFloodWaitSleep=60s` per attempt. This logic lives inside the MCP server;
the canary calls the MCP endpoint over HTTP and receives a tool error result, so
it cannot call `FloodWaitSeconds` directly.

### Build

`Dockerfile` (multi-stage):
- Stage `builder` (`golang:1.25-alpine`): builds `mctl-telegram` from
  `./cmd/server` and `mctl-telegram-login` from `./cmd/login`.
- Stage runtime (`alpine:3.20`): copies both binaries, creates non-root user
  1000, `EXPOSE 8080`, `ENTRYPOINT ["mctl-telegram"]`.

There is no `canary` binary or deploy manifests in the repository today.

### Auth

`internal/auth/` defines the `Provider` interface. In production (`AUTH_MODE=local-jwt`)
bearer tokens are JWTs signed with `OAUTH_JWT_SECRET`/`OAUTH_JWT_SIGNING_KEY`.
Scopes are embedded in the `scp` claim. The canary needs a pre-issued token
with `scp=telegram:dialogs:read telegram:messages:read` — no send scopes.

### MCP wire format

`internal/mcp/server.go` mounts
`mcpserver.NewStreamableHTTPServer(...)` at `cfg.MCPPath` (default `/mcp`).
`mark3labs/mcp-go` v0.46.0 (per `go.mod`) accepts JSON-RPC 2.0 requests:

```
POST /mcp HTTP/1.1
Authorization: Bearer <token>
Content-Type: application/json

{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"list_dialogs","arguments":{"limit":5}}}
```

The response is either a JSON-RPC result with a `content` array, or a
JSON-RPC error.

## Proposed solution

### New binary: `cmd/canary/main.go`

A self-contained Go program. It does not import any `internal/` package from
mctl-telegram — it is a black-box HTTP client. This keeps it honest as an
external probe: it catches regressions in the public surface, not in internals.

**Configuration (env vars)**:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `CANARY_BASE_URL` | yes | — | e.g. `https://tg.mctl.ai` |
| `CANARY_BEARER_TOKEN` | yes | — | Pre-issued read-only JWT |
| `CANARY_TG_USER_ID` | yes | — | Telegram user id of canary account (int64); used only for structured logging |
| `CANARY_TIMEOUT` | no | `30s` | Per-probe HTTP timeout (parsed with `time.ParseDuration`) |
| `CANARY_MCP_PATH` | no | `/mcp` | MCP endpoint path |
| `CANARY_PROBE_UNREAD` | no | `false` | When `true`, also run the `get_unread_messages` step |
| `PUSHGATEWAY_URL` | no | `""` | When set, push metrics here (e.g. `http://pushgateway:9091`); otherwise serve on `CANARY_METRICS_ADDR` |
| `CANARY_METRICS_ADDR` | no | `:9090` | Local metrics server address (used when `PUSHGATEWAY_URL` is empty) |

**Probe sequence**:

1. `step=oauth_metadata`: `GET <CANARY_BASE_URL>/.well-known/oauth-authorization-server`.
   Validate HTTP 200, `Content-Type: application/json`, and presence of keys
   `issuer`, `authorization_endpoint`, `token_endpoint` in the decoded JSON.
   Abort the run on failure.

2. `step=list_dialogs`: POST to `<CANARY_BASE_URL><CANARY_MCP_PATH>` with
   `Authorization: Bearer <CANARY_BEARER_TOKEN>` and a JSON-RPC 2.0
   `tools/call` body for `list_dialogs` with `limit=5`. Validate: HTTP 200,
   JSON-RPC result (not error), `result.content` array is non-nil, `IsError`
   false. If the response text contains `"FLOOD_WAIT"` or `"FLOOD_PREMIUM_WAIT"`,
   mark the step as `degraded` (failure recorded, no retry).

3. `step=get_unread_messages` (when `CANARY_PROBE_UNREAD=true`): POST to the
   same MCP endpoint with `tools/call` for `get_unread_messages`, `limit=1`.
   Validate the same conditions as step 2.

**Metrics** (registered on a fresh `prometheus.NewRegistry()`):

```
mctl_telegram_canary_success             gauge    1=all ok, 0=any failure
mctl_telegram_canary_duration_seconds    histogram  total wall time of the run
mctl_telegram_canary_step_failure_total  counter  {step="oauth_metadata"|"list_dialogs"|"get_unread_messages"}
```

Histogram buckets: `{1, 2.5, 5, 10, 15, 20, 30}` seconds — appropriate for a
30 s timeout with possible FLOOD_WAIT back-off.

**Metric emission**:

- When `PUSHGATEWAY_URL` is set: use `prometheus/client_golang`'s
  `push.New(url, "mctl_telegram_canary").Gatherer(reg).Push()`. The pod then
  exits with status 0 (metrics pushed) or 1 (any probe failed — exit code lets
  Kubernetes record the Job as failed, which is visible in `kubectl get cronjob`
  events). Pushgateway retains the last pushed values between scrapes.
- When `PUSHGATEWAY_URL` is empty: start an HTTP server on `CANARY_METRICS_ADDR`
  at `/metrics` and block. This mode is for local development and testing only;
  it is not used by the CronJob.

**Flood-wait detection in HTTP response**: The canary does not have access to
`internal/telegram.FloodWaitSeconds`. Instead, it inspects the MCP response
text content for the substrings `FLOOD_WAIT_` or `FLOOD_PREMIUM_WAIT_`. When
detected, it records `step=list_dialogs` failure with an additional log field
`flood_wait=true` and proceeds to metric emission without sleeping (the
back-off is Telegram-side; the canary's job is to signal degraded, not to
retry the request).

**Safety invariant**: The canary binary has no knowledge of `prepare_send_message`,
`send_message`, `pin_message`, or any other write tool. The `list_dialogs` and
`get_unread_messages` tool names are the only ones ever written into probe
request bodies. A code reviewer can verify this by reading the single file
`cmd/canary/main.go`.

### Dockerfile changes

Add a third `go build` invocation in the `builder` stage:

```dockerfile
RUN CGO_ENABLED=0 GOOS=linux \
    go build -ldflags="-s -w -X main.version=${APP_VERSION}" \
    -o /mctl-telegram-canary ./cmd/canary
```

Add a `COPY` line in the runtime stage:

```dockerfile
COPY --from=builder /mctl-telegram-canary /usr/local/bin/mctl-telegram-canary
```

The canary binary runs as the same non-root user 1000. No new base image or
layer is required.

The `build.yml` workflow (`docker` job) already builds the Dockerfile — the
canary binary will be included automatically.

### `deploy/canary/cronjob.yaml`

A `batch/v1 CronJob` in namespace `mctl-telegram`:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: mctl-telegram-canary
  namespace: mctl-telegram
spec:
  schedule: "*/2 * * * *"
  concurrencyPolicy: Forbid
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 5
  jobTemplate:
    spec:
      activeDeadlineSeconds: 90
      template:
        spec:
          restartPolicy: Never
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
          containers:
            - name: canary
              image: ghcr.io/mctlhq/mctl-telegram:latest
              command: ["/usr/local/bin/mctl-telegram-canary"]
              env:
                - name: CANARY_BASE_URL
                  value: "https://tg.mctl.ai"
                - name: CANARY_TG_USER_ID
                  valueFrom:
                    secretKeyRef:
                      name: mctl-telegram-canary
                      key: tg_user_id
                - name: CANARY_BEARER_TOKEN
                  valueFrom:
                    secretKeyRef:
                      name: mctl-telegram-canary
                      key: bearer_token
                - name: CANARY_PROBE_UNREAD
                  value: "true"
                - name: PUSHGATEWAY_URL
                  value: "http://prometheus-pushgateway.monitoring.svc.cluster.local:9091"
              resources:
                requests:
                  cpu: "10m"
                  memory: "32Mi"
                limits:
                  cpu: "100m"
                  memory: "64Mi"
```

The `mctl-telegram-canary` Secret must be provisioned out-of-band (Vault or
`kubectl create secret`). It requires two keys: `tg_user_id` and `bearer_token`.

### `deploy/alerts/canary.rules.yaml`

A standalone `PrometheusRule` manifest. Once issue #86 lands, this can be
merged into the file that #86 introduces (`deploy/alerts/mctl-telegram.rules.yaml`).

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: mctl-telegram-canary
  namespace: monitoring
  labels:
    prometheus: kube-prometheus
    role: alert-rules
spec:
  groups:
    - name: mctl-telegram-canary
      interval: 60s
      rules:
        - alert: MctlTelegramCanaryFailing
          expr: min_over_time(mctl_telegram_canary_success[10m]) == 0
          for: 5m
          labels:
            severity: critical
            service: mctl-telegram
          annotations:
            summary: "mctl-telegram canary probe has been failing for 5 minutes"
            description: >
              The synthetic end-to-end canary for mctl-telegram has reported
              mctl_telegram_canary_success=0 for every scrape in the last 10
              minutes, and the condition has persisted for at least 5 minutes.
              Check mctl_telegram_canary_step_failure_total{step=} to identify
              which probe step is failing (oauth_metadata, list_dialogs, or
              get_unread_messages).
              Runbook: https://github.com/mctlhq/mctl-telegram/blob/main/docs/runbooks/canary.md
```

### README section

Add an "Operations: Canary account" section to `README.md` explaining:
- that the canary Telegram account must be a separate test account (not the
  operator's personal account) created specifically for automated probing;
- how to provision a bearer token with read-only scopes via the admin
  `set_telegram_access` MCP tool;
- that the account must complete the browser setup flow
  (`GET /telegram/connect`) before a token can be issued;
- that the Kubernetes Secret `mctl-telegram-canary` in namespace
  `mctl-telegram` must be populated with the resulting token and the account's
  Telegram user id.

## Alternatives

### 1. Canary as a flag on `cmd/server` (in-process probe loop)

The issue mentions "cmd/server flag" as an option. An in-process goroutine
would have direct access to `internal/telegram` and avoid HTTP overhead.
Rejected because: (a) it conflates the health of the canary account with the
health of the server process — a crash in the canary goroutine could affect the
main server; (b) it cannot distinguish between "server process alive" and "HTTP
layer alive", which is the precise gap the issue wants to close; (c) it makes
the canary harder to test in isolation.

### 2. Single-replica Deployment with a sleep loop instead of CronJob

A Deployment with `while true; do canary; sleep 120; done` would avoid the
Pushgateway dependency and allow pull-based scraping. Rejected because: (a) a
Deployment adds a persistent pod whose cost is disproportionate to a 30-second
probe that runs once every two minutes; (b) the CronJob model provides built-in
retries, history, and failure accounting via Kubernetes Job status; (c) the
issue explicitly requests a CronJob manifest.

### 3. Canary importing `internal/` packages directly (not black-box HTTP)

Importing `internal/telegram`, `internal/auth`, and `internal/db` would let the
canary exercise the MTProto client pool directly without HTTP overhead and would
share the flood-wait retry logic in `borrowWithRetry`. Rejected because: (a) it
turns the canary into a unit test of internals rather than an integration probe
of the deployed service surface; (b) it requires its own DB connection and
Telegram API credentials, making deployment configuration significantly more
complex; (c) it would not catch regressions in the HTTP auth middleware,
`/.well-known/` metadata, or the MCP request parsing layer — exactly the layers
that have caused past surprises.

## Platform impact

### Migrations

None. The canary binary requires no database schema changes and no changes to
`internal/` packages.

### Backward compatibility

The Dockerfile change adds one `go build` invocation and one `COPY` line. The
existing `mctl-telegram` and `mctl-telegram-login` binaries are unchanged. The
new binary is additive.

### Resource impact

- CronJob pod: 10m CPU / 32 Mi memory request; pod lifetime ~10–30 s every
  2 minutes. Negligible cluster impact.
- Pushgateway: each run pushes three small metric families (~500 bytes). No
  meaningful load on the Pushgateway.
- The canary hits `GET /.well-known/oauth-authorization-server` and makes two
  MCP calls against the live server every two minutes. The OAuth metadata handler
  is static (no DB). The `list_dialogs` call touches the session pool and MTProto;
  this is intentional — it is the probe's purpose. On a Telegram account that has
  no FLOOD_WAIT pressure, two MCP calls per two minutes is well within
  Telegram's rate limits.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Canary token compromised | Token has read-only scopes (`telegram:dialogs:read,telegram:messages:read`); no write capability even if stolen. Rotate via `set_telegram_access` + re-issue. |
| FLOOD_WAIT on canary account | Detected by substring match in MCP response; canary reports degraded and exits without tight retry. CronJob `concurrencyPolicy: Forbid` prevents pile-up. |
| Pushgateway unavailable | Canary exits with status 1; CronJob records a failed Job. Prometheus alert on canary success=0 fires normally once the Pushgateway recovers and the canary pushes again. |
| Canary pod takes longer than 2 minutes | `activeDeadlineSeconds: 90` terminates the pod before the next CronJob firing. |
| Issue #86 not yet merged | Alert file is a standalone manifest that can be applied independently or merged into #86's file after that PR lands. |
