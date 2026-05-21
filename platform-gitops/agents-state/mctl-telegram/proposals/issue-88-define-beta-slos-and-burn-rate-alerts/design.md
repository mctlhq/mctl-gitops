# Design: issue-88-define-beta-slos-and-burn-rate-alerts

## Current state

### Prometheus metrics registry

`internal/metrics/metrics.go` defines all collectors on a fresh (non-global)
`prometheus.Registry` returned by `New()`. The collectors relevant to this
proposal are:

- **`mctl_tool_invocations_total{tool, status}`** — Counter, incremented in
  `internal/mcp/tools.go:audit()`. `status` is "ok" or "error". Every MCP tool
  call exits through `audit()`; session-expiry errors and terminal FLOOD_WAIT
  failures both land in `status="error"`, making them indistinguishable from
  service failures.

- **`mctl_tool_invocation_duration_seconds{tool}`** — Histogram with buckets
  `[.05, .1, .25, .5, 1, 2.5, 5, 10]`. Recorded by `audit()` from `startedAt`
  (set at handler entry) to end of handler. Labels only by tool name; no
  read/write dimension exists.

- **`mctl_http_requests_total{method, route, status_code}`** — Counter recorded
  by `metrics.HTTPMiddleware()` using the chi route pattern as the route label
  (prevents high-cardinality labels from path parameters). The OAuth endpoints
  `/oauth/token` and `/oauth/telegram/callback` are routed as POST and GET
  respectively (`internal/oauth/server.go:678-679`) and appear in this counter
  with their exact path strings.

- **`mctl_sessions_revoked_total{reason}`** — Counter with reason values:
  "disconnect", "idle_expiry", "absolute_expiry", "delete", "unauthorized".
  Incremented in `db.Store.RevokeActiveSession()`, `SweepIdleSessions()`, and
  `SweepAbsoluteSessions()`. The sweeper goroutine increments this counter for
  sessions it expires in the background; these increments have no corresponding
  "borrow attempt" to pair against, making this counter alone insufficient as an
  SLI denominator.

- **`mctl_telegram_flood_wait_events_total{tool}`** — Counter incremented in
  `internal/mcp/tools.go:borrowWithRetry()` on each observed `FLOOD_WAIT_X`
  error, including those on attempts that are subsequently retried successfully.
  Critically, a retry that ultimately succeeds returns `nil` from `Borrow()` and
  `audit()` records `status="ok"` — matching the issue requirement that
  "FLOOD_WAIT retries that ultimately succeed are not errors."

### Session borrow path

`telegram.ClientPool.Borrow()` (`internal/telegram/clientpool.go:118`) is the
sole gating point for every hosted-mode tool invocation that reaches Telegram.
The function signature is:

```go
func (p *ClientPool) Borrow(ctx context.Context, userID int64,
    fn func(ctx context.Context, c *telegram.Client) error) error
```

Before acquiring a pool entry, `Borrow` calls `p.Store.CheckSessionValid()`. If
the session has exceeded the idle TTL (30 days, `idleSessionTTL` constant in
`internal/db/store.go`) or the absolute TTL (90 days, `absoluteSessionTTL`), the
store revokes the row and returns `db.ErrSessionExpired` wrapped with a
`SessionExpiryReason` string ("idle-expiry" or "absolute-expiry"). This error
propagates through `borrowWithRetry()` unchanged and reaches `audit()` as
`status="error"` — indistinguishable in `mctl_tool_invocations_total` from a
genuine MTProto or service failure.

There is no `mctl_sessions_borrow_total` counter in the current registry. The
session-borrow SLI (99%, TTL expirations excluded) cannot be computed from
existing metrics.

### Tool classification

The MCP tools registered in `internal/mcp/tools.go` fall into two groups for the
latency SLO:

- **Read tools** (`readOnly` annotation): `list_dialogs`, `get_unread_messages`,
  `get_messages`, `get_my_audit_log`, `list_telegram_identities`,
  `prepare_send_message`, `prepare_pin_message`. These never write to Telegram;
  the two prepare tools are read-only pre-flight steps.
- **Destructive/send tools** (`destructive` annotation): `send_message`,
  `pin_message`, `disconnect_telegram_account`, `delete_telegram_account`.

No `kind` label on the histogram separates these groups; PromQL must enumerate
tool names.

### OAuth endpoints and HTTP metrics

Routes `/oauth/token` (POST) and `/oauth/telegram/callback` (GET) are registered
in `internal/oauth/server.go:678-679`. The chi middleware captures their status
codes in `mctl_http_requests_total{route="/oauth/token", ...}` and
`mctl_http_requests_total{route="/oauth/telegram/callback", ...}`. These are the
correct SLI data sources for OAuth availability.

### Existing infrastructure for alerts and dashboards

`deploy/alerts/` already exists, with `canary.rules.yaml` (issue #89) as the
working precedent: a `monitoring.coreos.com/v1` `PrometheusRule` in
`namespace: monitoring` with labels `prometheus: kube-prometheus` /
`role: alert-rules`, which the VictoriaMetrics operator auto-converts to a
VMRule. Issue #86 adds `deploy/alerts/mctl-telegram.rules.yaml` (pool / flood /
oauth alerts). Issue #87 (Grafana dashboard) is already merged. So this
proposal only needs to (a) define new SLO content and (b) APPEND to the file
#86 creates — it does NOT create CRD infrastructure (that already exists) and
does NOT need to wait on a dashboard that is already present.

**Sequencing:** this proposal must be implemented AFTER #86 merges, because it
appends burn-rate alert groups to the same `deploy/alerts/mctl-telegram.rules.yaml`
file. Branch from a main that already contains #86's file.

---

## Proposed solution

### 1. New metric: `mctl_sessions_borrow_total{result}`

Add `SessionsBorrowTotal *prometheus.CounterVec` to `internal/metrics/metrics.go`
`Registry` struct and register it in `New()`:

```go
r.SessionsBorrowTotal = prometheus.NewCounterVec(prometheus.CounterOpts{
    Name: "mctl_sessions_borrow_total",
    Help: "Total Pool.Borrow() calls, labeled by outcome. " +
        "expired_idle and expired_absolute are expected user-side TTL expirations; " +
        "exclude them from the availability SLI denominator.",
}, []string{"result"})
```

Valid `result` label values: ok, expired_idle, expired_absolute, error.

Instrument `telegram.ClientPool.Borrow()` at four exit points:

```
CheckSessionValid returns ErrSessionExpired, reason=ReasonIdle
  -> SessionsBorrowTotal.WithLabelValues("expired_idle").Inc()

CheckSessionValid returns ErrSessionExpired, reason=ReasonAbsolute
  -> SessionsBorrowTotal.WithLabelValues("expired_absolute").Inc()

fn(ctx, e.client) returns nil (success path, after sessionErrorFor check)
  -> SessionsBorrowTotal.WithLabelValues("ok").Inc()

all other non-nil errors (ErrPoolFull, context error, MTProto error,
revoke-rejected path, etc.)
  -> SessionsBorrowTotal.WithLabelValues("error").Inc()
```

The nil-guard pattern already used for `p.metrics` in `acquire()` and `run()`
applies equally here. No new injection point is required.

The session-borrow SLI PromQL expression:

```promql
sum(rate(mctl_sessions_borrow_total{result="ok"}[28d]))
/
sum(rate(mctl_sessions_borrow_total{result=~"ok|error"}[28d]))
```

### 2. docs/slo.md

A new Markdown file documenting:

**SLI definitions with PromQL:**

| SLI | Expression |
|-----|-----------|
| Tool availability | `sum(rate(mctl_tool_invocations_total{status="ok"}[28d])) / sum(rate(mctl_tool_invocations_total[28d]))` |
| Tool latency p95 read | `histogram_quantile(0.95, sum by(le)(rate(mctl_tool_invocation_duration_seconds_bucket{tool=~"list_dialogs|get_unread_messages|get_messages|get_my_audit_log|prepare_send_message|prepare_pin_message|list_telegram_identities"}[5m])))` |
| Tool latency p95 send | `histogram_quantile(0.95, sum by(le)(rate(mctl_tool_invocation_duration_seconds_bucket{tool=~"send_message|pin_message|disconnect_telegram_account|delete_telegram_account"}[5m])))` |
| OAuth availability | `1 - sum(rate(mctl_http_requests_total{route=~"/oauth/token\|/oauth/telegram/callback",status_code=~"5.."}[28d])) / sum(rate(mctl_http_requests_total{route=~"/oauth/token\|/oauth/telegram/callback"}[28d]))` |
| Session borrow | `sum(rate(mctl_sessions_borrow_total{result="ok"}[28d])) / sum(rate(mctl_sessions_borrow_total{result=~"ok\|error"}[28d]))` |

**SLO targets:**

| SLO | Target | 30-day error budget |
|-----|--------|---------------------|
| MCP tool availability | 99.5% | 3 h 36 min |
| MCP tool latency p95 read | < 2 s | N/A (latency SLOs typically alert on sustained breach, no time-budget model) |
| MCP tool latency p99 read | < 5 s | N/A |
| MCP tool latency p95 send | < 4 s | N/A |
| OAuth token-endpoint availability | 99.9% | 43 min |
| Session borrow success rate | 99% | 7 h 12 min |

**Error-budget policy** (when any SLO's budget is exhausted):

1. Freeze non-critical feature merges (PRs not labeled `reliability` or
   `security`). Only bug fixes, hotfixes, and reliability work merge.
2. Gate new production deploys on a green burn rate: the 6h burn rate for the
   affected SLO must be below 1x (i.e., the budget is not actively burning) at
   the time of the deploy.
3. Restore policy: normal merge flow resumes once the rolling-28-day SLI returns
   to target and remaining budget is at least 50% (i.e., burn has recovered to
   below half the error rate for at least half the window).

**Exclusions section:**
- `db.ErrSessionExpired` (idle_expiry or absolute_expiry): counted in
  `mctl_sessions_borrow_total{result=expired_*}`, excluded from the borrow SLI
  denominator. These are expected user-side state, not service errors.
- FLOOD_WAIT retries that ultimately succeed: `borrowWithRetry()` in
  `internal/mcp/tools.go` retries up to 3 times with a 60-second cap per sleep.
  If the final attempt succeeds, `mctl_tool_invocations_total{status="ok"}` is
  incremented. Only terminal FLOOD_WAIT failures (exhausted retries) count as
  errors.

### 3. deploy/alerts/mctl-telegram.rules.yaml

APPEND two new burn-rate alert groups to the existing
`deploy/alerts/mctl-telegram.rules.yaml` (created by #86). Keep the file's
metadata unchanged (`namespace: monitoring`, labels `prometheus: kube-prometheus`
/ `role: alert-rules` — matching `canary.rules.yaml`). The VM operator converts
the whole PrometheusRule, including the new groups.

**Group: mctl-telegram-tool-availability**

Error rate expression (1h window):
```promql
sum(rate(mctl_tool_invocations_total{status="error"}[1h]))
/
sum(rate(mctl_tool_invocations_total[1h]))
```

| Alert | Threshold | Window | Severity | Fires when |
|-------|-----------|--------|----------|-----------|
| MctlToolAvailabilityFastBurn | > 0.072 | 1h | page | 14.4x burn; 7.2% error rate for 1h exhausts ~14.4x the per-hour error budget |
| MctlToolAvailabilitySlowBurn | > 0.030 | 6h | ticket | 6x burn over 6h exhausts 36% of the 30-day budget |

The `for: 0m` convention is standard for burn-rate alerts (the window itself
provides the stabilization; adding `for:` would delay by double).

**Group: mctl-telegram-oauth-availability**

Error rate expression (1h window):
```promql
sum(rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback",status_code=~"5.."}[1h]))
/
sum(rate(mctl_http_requests_total{route=~"/oauth/token|/oauth/telegram/callback"}[1h]))
```

| Alert | Threshold | Window | Severity | Fires when |
|-------|-----------|--------|----------|-----------|
| MctlOAuthAvailabilityFastBurn | > 0.01440 | 1h | page | 14.4x burn on 99.9% SLO (0.1% budget) |
| MctlOAuthAvailabilitySlowBurn | > 0.00600 | 6h | ticket | 6x burn over 6h |

**Group: mctl-telegram-session-borrow (pending instrumentation)**

Include alert stubs for the session-borrow SLI, marked with a comment
`# status: pending — requires mctl_sessions_borrow_total (tasks 1-2)`. The
alerts are syntactically valid but the expression references the new counter;
they should be deployed only after tasks 1 and 2 are merged and the metric has
been collected for at least one 6h slow-burn window.

### 4. deploy/grafana/mctl-telegram-beta.json — SLO row

Append a new row titled "SLO" to the dashboard produced by #87. The row contains
four panels:

- **Stat: Tool availability (28d)** — displays `sum(rate(mctl_tool_invocations_total{status="ok"}[28d])) / sum(rate(mctl_tool_invocations_total[28d]))` as a percentage, threshold colormap green >= 0.995 / yellow >= 0.990 / red below.
- **Stat: OAuth availability (28d)** — same pattern with the OAuth expression,
  threshold at 0.999.
- **Time-series: Burn rate** — two series: 1h burn and 6h burn for the tool
  availability SLO. Reference lines at 14.4 and 6. Y-axis: burn multiplier.
- **Stat: Remaining error budget** — computed as
  `(error_budget_seconds - consumed_seconds) / 60` displayed in minutes for each
  SLO. Uses a `$__range` variable set to 30d.

Because #87 is not yet merged, exact panel IDs and grid positions are
placeholders. The implementer merges the new row into the #87 dashboard JSON at
implementation time, verifying no ID conflicts.

### 5. README.md and docs/hpa.md cross-references

In `README.md`, after the existing "## Deploy" section, add one sentence:

> For Beta-tier service-level objectives, error-budget policy, and burn-rate alert
> definitions, see [docs/slo.md](docs/slo.md).

In `docs/hpa.md`, under "## Alerts" (after the existing `MctlTelegramPoolNearCapacity`
block and before the "## Notes" section), add a paragraph:

> For SLO-level burn-rate alerts (MCP tool availability, OAuth endpoint
> availability, session borrow success rate), see the PrometheusRule stanzas
> documented in [docs/slo.md](slo.md).

---

## Alternatives

### A. Derive the session-borrow SLI from existing metrics without a new counter

Subtract `mctl_sessions_revoked_total{reason=~"idle_expiry|absolute_expiry"}` from
`mctl_tool_invocations_total{status="error"}` to approximate non-expiry errors.
This is invalid because the sweeper goroutine in `internal/sweeper/sweeper.go`
increments `mctl_sessions_revoked_total` independently of tool invocations —
there is no corresponding "borrow attempt" counter for sweeper-revoked sessions.
Dividing by `mctl_tool_invocations_total` as the denominator would further
conflate dry-run invocations (which never call `Borrow()`) with hosted-mode ones.
**Rejected**: inaccurate SLI expression with no clean fix.

### B. Add a `reason` sub-label to `mctl_tool_invocations_total{status="error"}`

Extend the `status` label to carry a reason (e.g., `status="error:expired"`).
This breaks all existing queries and dashboards that filter on `status="error"`,
requiring simultaneous updates to every consumer. Label cardinality increases.
**Rejected**: a separate counter is cleaner and backward compatible.

### C. Use Sloth for SLO-rule generation

Sloth generates PrometheusRule YAML from a high-level SLO manifest, removing the
need to hand-write burn-rate math. The mctl-gitops repository has no confirmed
Sloth installation; adding a build-time dependency for a single service's SLO
increases platform complexity. **Rejected**: raw PromQL YAML is self-contained,
portable, and reviewable without tooling.

---

## Platform impact

### New counter cardinality

`mctl_sessions_borrow_total` has one label (`result`) with four possible values.
At one pod this is four time series. Total metric count impact is negligible.

### Borrow hot-path impact

`CounterVec.WithLabelValues(...).Inc()` is a goroutine-safe atomic operation with
no allocation after the first call (the label-set is cached in a sync.Map inside
the CounterVec). The nil-guard on `p.metrics` is identical to the existing guards
in `acquire()` (line ~217) and `run()` (line ~244). Performance impact is
immeasurable relative to MTProto round-trip latency.

### Histogram bucket resolution for latency SLOs

The histogram buckets `[.05, .1, .25, .5, 1, 2.5, 5, 10]` do not have explicit
boundaries at 2s or 4s. `histogram_quantile` interpolates linearly between the
1s and 2.5s buckets. The interpolation error is bounded: if true p95 is 2.0s,
the computed value will be within the 1-2.5s range. For alerting purposes this
is acceptable. If higher resolution is needed, a follow-up chore can add 2s and
4s buckets (a non-breaking change; new buckets are additive to existing data).

### Dependency on #86 and #87

- The burn-rate groups APPEND to `deploy/alerts/mctl-telegram.rules.yaml`, which
  #86 creates — so this must be implemented after #86 merges (file-level
  ordering, not a CRD dependency: the PrometheusRule CRD / VM-operator conversion
  is already proven by `canary.rules.yaml`).
- The Grafana SLO row appends to the dashboard from #87, which is already merged
  (`deploy/grafana/`). Verify the actual JSON path and avoid panel-ID conflicts
  at implementation time.
- `docs/slo.md` and the new `mctl_sessions_borrow_total` counter can be merged
  independently of both.

### Backward compatibility

All changes are additive. No existing metric names, label names, or dashboard
panel IDs are modified. Existing queries against `mctl_tool_invocations_total`
continue to work unchanged.
