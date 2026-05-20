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

There is no `deploy/` directory in the repository at this time. The issue
designates `deploy/alerts/mctl-telegram.rules.yaml` as the target path,
consistent with a convention where deployment manifests live alongside the
application source and are mirrored into `mctl-gitops` by the release pipeline.

## Proposed solution

### 1. New file: `deploy/alerts/mctl-telegram.rules.yaml`

Create a `PrometheusRule` custom resource (Prometheus Operator CRD,
`monitoring.coreos.com/v1`) at `deploy/alerts/mctl-telegram.rules.yaml`.

The manifest contains one `RuleGroup` named `mctl-telegram.rules` with eight
alert rules covering every metric surface called out in the issue:

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

**MctlTelegramAuthFailuresSpike, MctlTelegramClientErrorsSpike, MctlTelegramRateLimitWave**
Each uses `sum(rate(...[5m]))` with the threshold from the issue and `for: 2m`.

Every alert carries:
- `annotations.summary` — one-sentence human description.
- `annotations.description` — one sentence with `{{ $value }}` templating where
  appropriate.
- `annotations.runbook_url` — placeholder URL pointing to the GitHub wiki;
  a follow-up issue replaces these with real runbook content.
- `labels.severity` — `warning` or `critical`.

The manifest metadata uses:
```yaml
namespace: mctl
labels:
  app: mctl-telegram
  release: kube-prometheus-stack
```
`namespace: mctl` matches the HPA stanza in `docs/hpa.md`. The `release` label
is the standard selector used by kube-prometheus-stack's default
`Prometheus` CR `ruleSelector`. The implementer should verify this matches their
gitops Prometheus CR configuration (open question 1 in requirements).

### 2. Update `docs/hpa.md`

Replace the "Alerts" section (lines 105-121) inline YAML block with a paragraph
explaining that the authoritative alert definitions live in
`deploy/alerts/mctl-telegram.rules.yaml` and describing how operators should
apply the manifest (apply directly or mirror through `mctl-gitops`). The
existing prose notes about `mctl_telegram_flood_wait_events_total` and
`mctl_oauth_pending_auth_size` (lines 125-133) should be updated to reference
the manifest rather than suggesting future alert creation.

### 3. Follow-up gitops PR (documented, not automated)

`docs/hpa.md` will note that the manifest should be mirrored at
`platform-gitops/k8s/mctl-telegram/alerts/mctl-telegram.rules.yaml` in
`mctl-gitops` (adjacent to the existing
`platform-gitops/k8s/prometheus-adapter/` path referenced on line 101 of
`docs/hpa.md`). The implementer must open that PR manually after this one merges.

## Alternatives

### A. Inline the rules directly in `docs/hpa.md` (rejected)

The current state is essentially this: inline YAML in a doc. It has the obvious
problem that the doc and the deployed rules can diverge. The issue explicitly
asks to move the rules out of the doc. Rejected.

### B. Generate the `PrometheusRule` from a Go struct at build time (rejected)

One could write a Go tool (`cmd/gen-rules/main.go`) that reads metric
registration and emits YAML. This would guarantee the metric names in the
manifest stay in sync with `internal/metrics/metrics.go`. However, it adds
build-time complexity for six alert rules whose metric names are stable
identifiers unlikely to change silently. The risk of drift is low and caught at
review time. Over-engineering for a six-rule file. Rejected.

### C. Place the manifest in `mctl-gitops` directly, not in this repo (rejected)

Keeping deployment artifacts in the application repo (`deploy/`) ensures that a
PR changing metric names also touches the alert expressions in the same diff, and
that PRs to this repo are the authoritative gate for alert configuration. Placing
the manifest only in `mctl-gitops` breaks that coupling. The issue explicitly
names `deploy/alerts/mctl-telegram.rules.yaml` as the target path. Rejected.

## Platform impact

### Migrations
None. Adding a new file under `deploy/alerts/` and editing `docs/hpa.md` require
no database migrations, no Go code changes, and no changes to the container image.

### Backward compatibility
The manifest is purely additive. No existing behaviour changes. The `/metrics`
endpoint, metric names, and cardinality are unaffected.

### Resource impact
A `PrometheusRule` CR is a lightweight Kubernetes object evaluated by Prometheus
Operator. Eight rules against time-series that are already being scraped add
negligible evaluation overhead.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Pool-capacity guard omitted; alert fires spuriously when cap is uncapped | Explicit `and mctl_telegram_pool_capacity > 0` in both pool alert expressions |
| `for:` window absent on rate alerts; flapping on brief spikes | `for: 2m` stabilisation window added to all rate-based alerts |
| Namespace or `ruleSelector` labels mismatch; rule never loaded by Prometheus Operator | Document the assumption (open question 1); implementer must verify against the gitops Prometheus CR config before the gitops mirror PR |
| `docs/hpa.md` inline YAML removed but gitops mirror PR not opened | The gitops PR is a named task (task 4 in tasks.md); `docs/hpa.md` explicitly instructs operators on the mirror path |
