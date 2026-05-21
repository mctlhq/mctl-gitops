# Design: issue-92-operational-runbook-for-beta-top-n-incid

## Current state

### Documentation

The only operational document currently in `docs/` is `docs/hpa.md`, which
covers per-session memory estimates, `TELEGRAM_MAX_SESSIONS` sizing tables, the
Kubernetes HPA stanza, and a brief `MctlTelegramPoolNearCapacity` alert stub.
There is no runbook, no `deploy/` directory, and no alert rules YAML in the
current clone.

### Metrics surface (internal/metrics/metrics.go)

All metric families that the playbooks will reference are already registered in
`internal/metrics/metrics.go` via `metrics.New()`. The relevant counters and
gauges are:

| Prometheus name | Type | Labels | Source |
|---|---|---|---|
| `mctl_telegram_client_pool_size` | Gauge | — | `clientpool.go` acquire/run |
| `mctl_telegram_pool_capacity` | Gauge | — | `main.go` startup (-1 = uncapped) |
| `mctl_telegram_flood_wait_events_total` | CounterVec | `tool` | `clientpool.go` run() |
| `mctl_telegram_client_errors_total` | Counter | — | `clientpool.go` run() |
| `mctl_oauth_pending_auth_size` | Gauge | — | `oauth/server.go` sweeper |
| `mctl_auth_failures_total` | CounterVec | `reason`, `provider` | `auth/middleware.go` |
| `mctl_sessions_active` | Gauge | — | `main.go` background sampler |
| `mctl_sessions_revoked_total` | CounterVec | `reason` | `db/store.go` |
| `mctl_tool_invocations_total` | CounterVec | `tool`, `status` | `mcp/server.go` |
| `mctl_tool_invocation_duration_seconds` | HistogramVec | `tool` | `mcp/server.go` |
| `mctl_http_requests_total` | CounterVec | `method`, `route`, `status_code` | `metrics/middleware.go` |

### Pool behaviour (internal/telegram/clientpool.go)

`ClientPool.acquire()` enforces the `MaxSessions` cap: when
`len(p.entries) >= p.MaxSessions` a new `Borrow()` returns `ErrPoolFull`.
The cap is set from `TELEGRAM_MAX_SESSIONS` (config.go line 90). When the env
var is 0 or unset, `pool.MaxSessions` is 0 and the cap is disabled;
`mctl_telegram_pool_capacity` is set to -1 in `main.go` so the ratio
`pool_size / pool_capacity` yields -∞, preventing false HPA triggers.

Idle eviction runs via a per-entry `gc()` goroutine that ticks every minute and
cancels the entry after `IdleTimeout` (default 10 min, env `IDLE_CLIENT_TIMEOUT`).

### Flood wait (internal/telegram/floodwait.go)

`FloodWaitSeconds()` parses both `FLOOD_WAIT_X` and `FLOOD_PREMIUM_WAIT_X`
(MTProto error code 420). The counter `mctl_telegram_flood_wait_events_total`
is labeled by MCP tool name so the query
`topk(5, rate(mctl_telegram_flood_wait_events_total[5m])) by (tool)` isolates
which tool is driving quota consumption.

### Auth failures (internal/auth/middleware.go)

`classifyAuthError()` maps error strings to fixed `reason` label values:
`jwt_expired`, `jwt_invalid_signature`, `jwt_invalid_issuer`,
`jwt_missing_audience`, `jwt_wrong_audience`, `bearer_scheme_error`, `other`.
The `provider` label distinguishes `local-jwt`, `shared-hmac`, `local-dev`.
A spike in `jwt_invalid_signature` or `jwt_expired` strongly suggests a JWT
secret rotation went wrong.

JWT secrets: in `local-jwt` mode `OAUTH_JWT_SIGNING_KEY` is preferred;
`OAUTH_JWT_SECRET` is a deprecated fallback. In `shared-hmac` mode the
service verifies tokens signed by `api.mctl.ai` and must use `OAUTH_JWT_SECRET`
(`config.go:jwtSigningKey`).

### OAuth pending flows (internal/oauth/server.go, internal/db/store_oauth.go)

`Server.StartSweeper()` runs a goroutine (default 1-minute interval) that:
1. Drops expired in-memory entries (pending, codes, client registrations).
2. When `UseDBForOAuth=true`, calls `Store.DeleteExpiredOAuthRows()` and
   `Store.DeleteExpiredClientRegs()` against Postgres.
3. Calls `samplePendingAuthGauge()` which reads `Store.CountOAuthPending()` (DB
   path) or `len(s.pending)` (in-memory path) and sets
   `mctl_oauth_pending_auth_size`.

A rising gauge with no traffic means: (a) the sweeper goroutine stopped, (b)
the Telegram OIDC IdP is down and callbacks never arrive to consume pending
state, or (c) the bot is being scanned (unauthenticated `/oauth/authorize`
requests). Restarting the pod clears the in-memory map; for the DB path a psql
count query provides ground truth.

### MTProto client errors

`clientpool.run()` increments `mctl_telegram_client_errors_total` whenever
`client.Run()` returns a non-`context.Canceled` error and logs at
`slog.Warn("telegram client exited", "user_id", ..., "err", ...)`. This counter
is a raw signal; the actual error category must be retrieved from pod logs.

## Proposed solution

### File 1: docs/runbook.md (new)

A single Markdown file structured as a table of contents followed by one
H2-level section per alert. Each section opens with a named HTML anchor:

```html
<a id="mctltelegramnearcapacity"></a>
## MctlTelegramPoolNearCapacity
```

The anchor names are lowercase-only, alphanumeric, and stable regardless of
section reordering. The `runbook_url` in each PrometheusRule annotation will
take the form:

```
https://github.com/mctlhq/mctl-telegram/blob/main/docs/runbook.md#<anchor>
```

Each section follows the six-subsection structure mandated by the issue:
Symptom, Likely causes, Diagnostic queries, Mitigation, Escalation, Postmortem
trigger.

Diagnostic queries use:
- **Prometheus:** PromQL expressions referencing only metric names from
  `internal/metrics/metrics.go`.
- **kubectl logs:** JSON-aware grep one-liners against the structured slog output
  (field names match what the application logs, e.g. `user_id`, `err`).
- **psql:** Direct table queries against `oauth_pending_auth` and related tables
  defined in `internal/db/store_oauth.go` for the DB-backed OAuth path.

The SLO burn-rate section (the seventh entry) does not have a single named
alert but links to both fast-burn and slow-burn Alertmanager alert names from
#88. The diagnostic subsection cross-references the specific alert sections
above, because SLO burn is a composite signal.

The canary alerts (`MctlTelegramCanaryFailing`, `MctlTelegramCanaryStale`,
`MctlTelegramCanaryAbsent`) are **already shipped** in #89 and ALREADY have a
dedicated runbook at `docs/runbooks/canary.md` (its alert annotations point
there). Do NOT recreate canary content in `docs/runbook.md` — instead, the
canary entry in the new runbook's table of contents links out to
`docs/runbooks/canary.md`. This avoids a divergent second copy.

Note on alert sourcing: the only alerts whose `runbook_url` this issue can edit
in `deploy/alerts/mctl-telegram.rules.yaml` are #86's three new alerts
(`MctlTelegramPoolNearCapacity`, `MctlTelegramFloodWaitSpike`,
`MctlTelegramOAuthPendingStuck`). The auth-failure, client-error, and
rate-limit alerts live in the `mctl-telegram-alerts` VMRule in `mctl-gitops`
(from #59) — the runbook can still document them, but adding `runbook_url`
there is a separate gitops edit, out of scope for the implementer's repo clone.

### File 2: deploy/alerts/mctl-telegram.rules.yaml (update, depends on #86 merged)

After #86 merges and the alert rules YAML exists, add/confirm a `runbook_url`
annotation on the three new alert blocks it contains
(`MctlTelegramPoolNearCapacity`, `MctlTelegramFloodWaitSpike`,
`MctlTelegramOAuthPendingStuck`). #86 already sets forward-referencing
`docs/runbook.md#<anchor>` URLs; this issue just guarantees they resolve to the
new sections. Do NOT touch `canary.rules.yaml` (its runbook_url already points
to `docs/runbooks/canary.md`). Example diff:

```yaml
annotations:
  summary: "..."
  description: "..."
  runbook_url: "https://github.com/mctlhq/mctl-telegram/blob/main/docs/runbook.md#mctltelegramnearcapacity"
```

This task is explicitly listed as "depends on #86" in tasks.md.

### Anchor scheme

| Alert name | Anchor id | Source |
|---|---|---|
| MctlTelegramPoolNearCapacity | `mctltelegramnearcapacity` | #86 (repo rules file) |
| MctlTelegramFloodWaitSpike | `mctltelegramfloodwaitspike` | #86 |
| MctlTelegramOAuthPendingStuck | `mctltelegramoauthpendingstuck` | #86 |
| JWTExpiredSpike / JWTInvalidSpike | `jwtfailures` | #59 (gitops VMRule) |
| TelegramClientErrors | `telegramclienterrors` | #59 (gitops VMRule) |
| RateLimitSpike | `ratelimitspike` | #59 (gitops VMRule) |
| Canary (Failing/Stale/Absent) | — links to `docs/runbooks/canary.md` | #89 (already shipped) |
| SLO burn-rate (fast + slow) | `sloburnrate` | #88 |

(The auth/client-error/rate-limit alerts use the deployed `mctl-telegram-alerts`
VMRule names from #59, not the duplicate names the issue text originally drafted.)

Anchors are all lowercase to match GitHub Markdown's auto-anchor behaviour and
to avoid ambiguity between `id=` and fragment navigation.

## Alternatives

### 1. Embed runbook prose in PrometheusRule annotations

Alert `annotations` support multi-line strings in YAML. All diagnostic steps
could live in the `description` annotation.

Rejected: YAML annotation text is unrendered in Alertmanager and PagerDuty;
Prometheus queries with curly braces must be escaped. There is no formatting, no
table of contents, and no ability to link to subsections. Maintainability is
poor as the text grows.

### 2. External wiki (Confluence, Notion, or GitHub Wiki)

A separate hosted platform provides richer formatting and real-time editing.

Rejected: external platforms require authentication or a separate permission
model; they are not co-versioned with the codebase; URLs break when pages are
renamed; and the issue explicitly specifies `docs/runbook.md` as the target
file.

### 3. One runbook file per alert

Seven separate Markdown files, one per alert, each at a stable path
(`docs/runbooks/pool-near-capacity.md` etc.).

Rejected: the issue specifies a single `docs/runbook.md`. Cross-referencing
(e.g. SLO burn linking to specific alert sections) is cleaner in a single file.
One file also means one PR, one review, and no risk of partial delivery.

## Platform impact

### Migrations

None. The proposal adds only documentation files. No schema changes, no new
dependencies, no config changes.

### Backward compatibility

No existing behaviour changes. `docs/hpa.md` is not modified.

### Resource impact

A Markdown file of approximately 600-900 lines adds negligible repository size.
No runtime memory or CPU is affected.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Anchor names drift from `runbook_url` values in #86 | Anchor scheme table in this design is the single source of truth; #86 already uses these anchors |
| Canary content duplicated | #89 is already shipped with `docs/runbooks/canary.md`; this runbook LINKS to it rather than copying — no second source of truth |
| SLO burn policy not yet defined by #88 | Section describes the intent (feature freeze, rollback) at a conceptual level; a follow-up sharpens the wording post-#88 |
| Pod restart clears in-memory OAuth pending state | Runbook documents this trade-off explicitly in the `MctlTelegramOAuthPendingStuck` mitigation section |
