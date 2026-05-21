# Design: issue-86-ship-prometheusrule-manifests-for-produc

## Current state

### Metric instrumentation

All Prometheus metrics are defined and registered in
`internal/metrics/metrics.go`. The struct `Registry` holds every collector;
`New()` registers them on a fresh `prometheus.Registry` (not the global
`DefaultRegisterer`). The metrics relevant to this issue are:

| Field | Metric name | Kind | Labels |
|---|---|---|---|
| `TelegramClientPoolSize` | `mctl_telegram_client_pool_size` | Gauge | — |
| `TelegramPoolCapacity` | `mctl_telegram_pool_capacity` | Gauge | — |
| `TelegramFloodWaitEventsTotal` | `mctl_telegram_flood_wait_events_total` | CounterVec | `tool` |
| `TelegramClientErrorsTotal` | `mctl_telegram_client_errors_total` | Counter | — |
| `OAuthPendingAuthSize` | `mctl_oauth_pending_auth_size` | Gauge | — |
| `AuthFailuresTotal` | `mctl_auth_failures_total` | CounterVec | `reason`, `provider` |
| `RateLimitEventsTotal` | `mctl_rate_limit_events_total` | CounterVec | `identity_kind` |

The `/metrics` endpoint is mounted in `cmd/server/main.go` (line 148) and
guarded by an optional CIDR allowlist via `metricsHandler`. Prometheus is
expected to scrape the endpoint via a `PodMonitor` or `ServiceMonitor` (not
present in this repo; presumably in `mctl-gitops`).

### Alert documentation (existing)

`docs/hpa.md` contains an "Alerts" section (lines 105-121) that shows a single
inline YAML block for `MctlTelegramPoolNearCapacity` as a code example. The
document notes that `mctl_telegram_flood_wait_events_total` and
`mctl_oauth_pending_auth_size` can be used for alerts but gives no expressions.
No `PrometheusRule` CRD manifest exists anywhere in the repository tree.

### Deployment layout

A `deploy/alerts/` directory now exists, created by the synthetic-canary work
(issue #89): `deploy/alerts/canary.rules.yaml`. **This file is the authoritative
precedent for this repo and the cluster** — follow it exactly. It is a
`PrometheusRule` (`monitoring.coreos.com/v1`) with:

```yaml
metadata:
  name: <rule-name>
  namespace: monitoring
  labels:
    prometheus: kube-prometheus
    role: alert-rules
```

The platform runs the **VictoriaMetrics operator**, which auto-converts any
`PrometheusRule` carrying those labels into a `VMRule` (verified: the canary
PrometheusRule was converted to an operational `mctl-telegram-canary` VMRule in
the `monitoring` namespace). So `kind: PrometheusRule` is correct AS LONG AS the
namespace is `monitoring` and the labels are `prometheus: kube-prometheus` +
`role: alert-rules`. **Do NOT use `namespace: mctl` or
`release: kube-prometheus-stack`** — those will silently never load.

### Existing deployed alerts (issue #59) — DO NOT DUPLICATE

A `VMRule` named `mctl-telegram-alerts` is already deployed in the `monitoring`
namespace (source: `mctl-gitops/platform-gitops/infra-components/observability/
vm-rules/mctl-telegram-alerts.yaml`, from issue #59). It already covers:

| Existing alert | Expression |
|---|---|
| `JWTExpiredSpike` | `rate(mctl_auth_failures_total{reason="jwt_expired"}[5m]) > 0.1` |
| `JWTInvalidSpike` | `rate(mctl_auth_failures_total{reason=~"jwt_invalid.*..."}[5m]) > 0.05` |
| `HighToolErrorRate`, `HighToolLatency`, `ZeroTraffic` | tool-invocation SLIs |
| `RateLimitSpike` | `rate(mctl_rate_limit_events_total[5m]) > 1` |
| `TelegramClientErrors` | `increase(mctl_telegram_client_errors_total[10m]) > 0` |
| `ServiceUnavailable` | blackbox `probe_success == 0` |

Three of the alerts this issue originally listed are **already covered** by the
above and MUST NOT be re-added (double-paging):
- `MctlTelegramRateLimitWave` ≈ existing `RateLimitSpike` (identical metric/threshold) → DROP
- `MctlTelegramClientErrorsSpike` ≈ existing `TelegramClientErrors` → DROP
- `MctlTelegramAuthFailuresSpike` ≈ existing `JWTExpiredSpike` + `JWTInvalidSpike` → DROP

The genuinely new alerts this issue should ship are only the three not yet
covered: `MctlTelegramPoolNearCapacity`, `MctlTelegramFloodWaitSpike`,
`MctlTelegramOAuthPendingStuck`.

## Proposed solution

### 1. New file: `deploy/alerts/mctl-telegram.rules.yaml`

Create a `PrometheusRule` custom resource (`monitoring.coreos.com/v1`) at
`deploy/alerts/mctl-telegram.rules.yaml`, mirroring the structure of the
existing `deploy/alerts/canary.rules.yaml` (same apiVersion, `namespace:
monitoring`, labels `prometheus: kube-prometheus` / `role: alert-rules`).

The manifest contains one `RuleGroup` named `mctl-telegram.rules` with the
THREE genuinely-new alert rules (the other surfaces are already covered by the
deployed `mctl-telegram-alerts` VMRule — see "Existing deployed alerts" above):

**MctlTelegramPoolNearCapacity (warning)**
```
expr: |
  (mctl_telegram_client_pool_size / mctl_telegram_pool_capacity) > 0.85
  and mctl_telegram_pool_capacity > 0
for: 5m
labels:
  severity: warning
```
The `and mctl_telegram_pool_capacity > 0` guard prevents a spurious alert when
the pool is uncapped (`TELEGRAM_MAX_SESSIONS` unset → gauge set to -1 by
`cmd/server/main.go` lines 90-95). Without the guard the expression evaluates to
a large negative number and the threshold is never crossed, but the semantic
intent should be explicit.

**MctlTelegramPoolNearCapacity (critical)**
```
expr: |
  (mctl_telegram_client_pool_size / mctl_telegram_pool_capacity) > 0.95
  and mctl_telegram_pool_capacity > 0
for: 2m
```

Both pool alerts share the same `alert:` name `MctlTelegramPoolNearCapacity`;
they are distinguished by the `severity` label. Prometheus Alertmanager can
route on `severity`.

**MctlTelegramFloodWaitSpike (warning and critical)**
```
expr: sum(rate(mctl_telegram_flood_wait_events_total[5m])) > 0.5
for: 2m   # warning

expr: sum(rate(mctl_telegram_flood_wait_events_total[5m])) > 2
for: 2m   # critical
```
A 2-minute stabilisation window prevents flapping on single request bursts. The
`sum()` aggregates across all `tool` label values.

**MctlTelegramOAuthPendingStuck**
```
expr: mctl_oauth_pending_auth_size > 100
for: 15m
labels:
  severity: warning
```
The 15-minute `for` window matches the issue specification exactly. The gauge is
refreshed every minute by the OAuth server sweeper (`oauth.Server.StartSweeper`
called in `cmd/server/main.go` line 449), so a 15-minute window sees at minimum
15 successive samples above threshold before firing.

(`MctlTelegramAuthFailuresSpike`, `MctlTelegramClientErrorsSpike`, and
`MctlTelegramRateLimitWave` are intentionally OMITTED — they duplicate the
already-deployed `mctl-telegram-alerts` VMRule. See "Existing deployed alerts".)

Every alert carries:
- `annotations.summary` — one-sentence human description.
- `annotations.description` — one sentence with `{{ $value }}` templating where
  appropriate.
- `annotations.runbook_url` — points to the runbook section that issue #92 will
  author at `docs/runbook.md#<anchor>` (use the anchor scheme in #92's design:
  `mctltelegramnearcapacity`, `mctltelegramfloodwaitspike`,
  `mctltelegramoauthpendingstuck`). The runbook file does not exist until #92
  lands; the URL is forward-referencing and harmless until then.
- `labels.severity` — `warning` or `critical`.
- `labels.service: mctl-telegram` — matches the convention in `canary.rules.yaml`.

The manifest metadata MUST be (matching `deploy/alerts/canary.rules.yaml`):
```yaml
namespace: monitoring
labels:
  prometheus: kube-prometheus
  role: alert-rules
```
The VictoriaMetrics operator converts this PrometheusRule into a VMRule
automatically (the canary rule proves this works). Do not use `namespace: mctl`
or `release: kube-prometheus-stack`.

### 2. Update `docs/hpa.md`

Replace the "Alerts" section (lines 105-121) inline YAML block with a paragraph
explaining that the authoritative alert definitions live in
`deploy/alerts/mctl-telegram.rules.yaml` and describing how operators should
apply the manifest (apply directly or mirror through `mctl-gitops`). The
existing prose notes about `mctl_telegram_flood_wait_events_total` and
`mctl_oauth_pending_auth_size` (lines 125-133) should be updated to reference
the manifest rather than suggesting future alert creation.

### 3. Follow-up gitops mirror (documented, not automated)

The PrometheusRule in this repo does NOT auto-deploy — it must be applied to the
cluster. The GitOps-managed home for mctl-telegram alerts is
`mctl-gitops/platform-gitops/infra-components/observability/vm-rules/` (where
`mctl-telegram-alerts.yaml` from issue #59 already lives). `docs/hpa.md` should
note that an operator mirrors the new rules there (as a sibling
`mctl-telegram-extra.rules.yaml`, or by extending `mctl-telegram-alerts.yaml`).
The implementer cannot write to `mctl-gitops` (writes outside its cwd clone are
forbidden), so this mirror is a manual operator step after the mctl-telegram PR
merges.

## Alternatives

### A. Inline the rules directly in `docs/hpa.md` (rejected)

The current state is essentially this: inline YAML in a doc. It has the obvious
problem that the doc and the deployed rules can diverge. The issue explicitly
asks to move the rules out of the doc. Rejected.

### B. Generate the `PrometheusRule` from a Go struct at build time (rejected)

One could write a Go tool (`cmd/gen-rules/main.go`) that reads metric
registration and emits YAML. This would guarantee the metric names in the
manifest stay in sync with `internal/metrics/metrics.go`. However, it adds
build-time complexity for three alert rules whose metric names are stable
identifiers unlikely to change silently. The risk of drift is low and caught at
review time. Over-engineering for a three-rule file. Rejected.

### C. Place the manifest only in `mctl-gitops`, not in this repo (rejected)

Keeping deployment artifacts in the application repo (`deploy/`) ensures that a
PR changing metric names also touches the alert expressions in the same diff, and
that PRs to this repo are the authoritative gate for alert configuration. The
issue explicitly names `deploy/alerts/mctl-telegram.rules.yaml` as the target
path, and `deploy/alerts/canary.rules.yaml` already establishes this pattern.
Note this is a source-of-truth choice only — the file must still be mirrored
into `mctl-gitops` to actually deploy (see section 3). Rejected as the *sole*
location, kept as the authoring location.

## Platform impact

### Migrations
None. Adding a new file under `deploy/alerts/` and editing `docs/hpa.md` require
no database migrations, no Go code changes, and no changes to the container image.

### Backward compatibility
The manifest is purely additive. No existing behaviour changes. The `/metrics`
endpoint, metric names, and cardinality are unaffected.

### Resource impact
A `PrometheusRule` CR is a lightweight Kubernetes object converted to a VMRule by
the VictoriaMetrics operator and evaluated by vmalert. Three rules against
time-series that are already being scraped add negligible evaluation overhead.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Pool-capacity guard omitted; alert fires spuriously when cap is uncapped | Explicit `and mctl_telegram_pool_capacity > 0` in both pool alert expressions |
| `for:` window absent on rate alerts; flapping on brief spikes | `for: 2m` stabilisation window added to all rate-based alerts |
| Wrong namespace/labels → VM operator never converts the PrometheusRule | Use `namespace: monitoring` + labels `prometheus: kube-prometheus` / `role: alert-rules`, matching `deploy/alerts/canary.rules.yaml` exactly (proven to convert) |
| Duplicate alerts with the deployed `mctl-telegram-alerts` VMRule → double-paging | Ship only the three new alerts (Pool, FloodWait, OAuthPending); drop RateLimitWave/ClientErrorsSpike/AuthFailuresSpike |
| File in repo does not auto-deploy | `docs/hpa.md` documents the manual gitops mirror into `infra-components/observability/vm-rules/` |
