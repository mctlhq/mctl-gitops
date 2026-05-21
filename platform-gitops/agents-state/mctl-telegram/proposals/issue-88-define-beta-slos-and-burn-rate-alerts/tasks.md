# Tasks: issue-88-define-beta-slos-and-burn-rate-alerts

- [ ] 1. Add `mctl_sessions_borrow_total{result}` to the metrics registry
  — DoD: `internal/metrics/metrics.go` declares `SessionsBorrowTotal
  *prometheus.CounterVec` on the `Registry` struct; `New()` constructs it with
  `prometheus.CounterOpts{Name: "mctl_sessions_borrow_total", Help: "..."}` and
  label `result`; `reg.MustRegister(r.SessionsBorrowTotal)` is added to the
  registration block; the counter is exported for injection into `ClientPool`;
  `internal/metrics/metrics_test.go` verifies the counter appears in the gathered
  metrics output.

- [ ] 2. Instrument `telegram.ClientPool.Borrow()` with the new counter
  (depends on 1)
  — DoD: `internal/telegram/clientpool.go:Borrow()` increments
  `p.metrics.SessionsBorrowTotal` on all four exit paths — `result=ok` when
  `fn(ctx, e.client)` returns nil and `sessionErrorFor` returns nil,
  `result=expired_idle` when `CheckSessionValid` returns `db.ErrSessionExpired`
  with reason `db.ReasonIdle`, `result=expired_absolute` when the reason is
  `db.ReasonAbsolute`, and `result=error` for all other non-nil error returns
  (ErrPoolFull, context error, MTProto sentinel, revokeRejected failure, TG API
  credentials not configured); the nil-guard `if p.metrics != nil` wraps each
  increment; existing `clientpool_test.go` tests still pass; new subtests cover
  each of the four result labels.

- [ ] 3. Write `docs/slo.md`
  — DoD: file exists; documents all four SLIs with copy-pasteable PromQL
  expressions; states the four SLO percentage targets and their 30-day error
  budgets in minutes; defines the error-budget policy (freeze non-critical merges,
  gate deploys on 6h green burn, restore at >= 50% remaining budget); includes a
  table classifying each MCP tool as read or destructive for the latency SLO;
  explicitly documents the FLOOD_WAIT and TTL-expiry exclusions; references
  `deploy/alerts/mctl-telegram.rules.yaml` for the alert YAML.

- [ ] 4. APPEND burn-rate groups to `deploy/alerts/mctl-telegram.rules.yaml`
  (depends on 3 AND on #86 having merged — the file and its
  `namespace: monitoring` + `prometheus: kube-prometheus`/`role: alert-rules`
  metadata are created by #86; do NOT overwrite #86's pool/flood/oauth groups)
  — DoD: file is a valid PrometheusRule CRD YAML (apiVersion:
  monitoring.coreos.com/v1); retains #86's existing groups; adds group
  `mctl-telegram-tool-availability`
  with MctlToolAvailabilityFastBurn (14.4x/1h, severity=page) and
  MctlToolAvailabilitySlowBurn (6x/6h, severity=ticket); contains group
  `mctl-telegram-oauth-availability` with MctlOAuthAvailabilityFastBurn and
  MctlOAuthAvailabilitySlowBurn using the same burn multipliers; contains group
  `mctl-telegram-session-borrow` with stub alerts commented as `# status:
  pending instrumentation (tasks 1-2 in issue-88)`; every alert has `summary`
  and `description` annotations; `promtool check rules` exits 0 on the file.

- [ ] 5. Update `deploy/grafana/mctl-telegram-beta.json` with SLO panels
  (depends on #87 being merged, and on task 3)
  — DoD: the dashboard JSON contains a new row titled "SLO" with four panels:
  tool-availability stat (threshold green >= 99.5%), OAuth-availability stat
  (threshold green >= 99.9%), burn-rate time-series (1h and 6h series vs 14.4x
  and 6x reference lines), and remaining-budget stats for each SLO in minutes;
  all panel IDs are unique within the dashboard; the JSON is accepted by Grafana
  dashboard validation (no provisioning errors in the Grafana startup log).

- [ ] 6. Update `README.md` and `docs/hpa.md` with cross-references
  (depends on task 3)
  — DoD: `README.md` contains a sentence after the "## Deploy" section linking
  to `docs/slo.md`; `docs/hpa.md` "## Alerts" section contains a sentence
  pointing to `docs/slo.md` for SLO-level burn-rate alerts; both links use
  relative Markdown paths and resolve correctly from the repo root; neither file
  introduces new trailing whitespace or line-length violations.

## Tests

- [ ] T1. `internal/metrics/metrics_test.go`: call `metrics.New()` and use
  `prometheus/testutil.CollectAndCompare` (or `GatherAndCompare`) to assert that
  `mctl_sessions_borrow_total` appears in the gathered output; assert that the
  label `result` is present and accepts values ok, expired_idle, expired_absolute,
  error by calling `WithLabelValues` for each and verifying no registration panic.

- [ ] T2. `internal/telegram/clientpool_test.go`: add four sub-tests, one per
  result label. For each, construct a `ClientPool` with a mock `db.Store` that
  controls what `CheckSessionValid` returns, wire a `metrics.New()` registry,
  call `Borrow()`, and assert via `testutil.ToFloat64` that exactly the expected
  label's counter has value 1 and the other three have value 0. The
  `expired_idle` and `expired_absolute` paths require the mock store to return
  `fmt.Errorf("%w: %s", db.ErrSessionExpired, db.ReasonIdle)` and the absolute
  variant respectively.

- [ ] T3. CI lint step: add `promtool check rules deploy/alerts/mctl-telegram.rules.yaml`
  to `.github/workflows/` (or the existing lint workflow) so PromQL syntax errors
  are caught before the manifest reaches the cluster. The step should run on every
  PR that touches `deploy/alerts/`.

- [ ] T4. Manual post-deploy smoke test: after deploying the new binary, call any
  hosted-mode MCP tool (e.g., `list_dialogs`) and confirm via
  `curl .../metrics | grep mctl_sessions_borrow_total` that
  `mctl_sessions_borrow_total{result="ok"}` has incremented. Confirm the
  PrometheusRule alerts appear under Prometheus UI `Status > Rules` without
  evaluation errors.

## Rollback

The changes have three independent rollback paths:

**Metric + instrumentation (tasks 1-2):**
Remove `SessionsBorrowTotal` from `metrics.New()` and remove the four increment
calls from `ClientPool.Borrow()`. Neither change affects any existing behavior.
Redeploy. The session-borrow SLI expression in `docs/slo.md` becomes temporarily
uncomputable; add a note to `docs/slo.md` stating the metric is absent in the
running version. All other alerts remain functional.

**PrometheusRule (task 4):**
Delete or revert `deploy/alerts/mctl-telegram.rules.yaml` and apply the gitops
change to remove the PrometheusRule CR from the cluster. Prometheus stops
evaluating the alert rules within one scrape interval. No historical data is
affected; Prometheus does not retain alert state across rule deletions.

**Grafana dashboard (task 5):**
Revert `deploy/grafana/mctl-telegram-beta.json` to the version produced by #87.
The SLO panels disappear; all other panels are unaffected. The dashboard can be
reverted via the Grafana UI (version history) or by redeploying the prior JSON
through the gitops provisioning pipeline.

`docs/slo.md`, `README.md`, and `docs/hpa.md` are documentation changes only and
carry no operational rollback risk.
