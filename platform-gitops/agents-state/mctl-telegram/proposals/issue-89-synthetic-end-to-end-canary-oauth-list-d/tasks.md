# Tasks: issue-89-synthetic-end-to-end-canary-oauth-list-d

- [ ] 1. Create `cmd/canary/main.go` — DoD: binary compiles with `go build ./cmd/canary`,
  reads all required env vars, validates their presence, runs the three-step
  probe sequence (oauth_metadata, list_dialogs, optional get_unread_messages),
  registers the three `mctl_telegram_canary_*` metric families on a fresh
  `prometheus.NewRegistry()`, pushes to Pushgateway when `PUSHGATEWAY_URL` is
  set and serves `/metrics` on `CANARY_METRICS_ADDR` otherwise, exits status 1
  on any probe failure, logs structured JSON via `log/slog` using the same
  `audit.NewRedactingHandler` pattern as `cmd/server/main.go`, and does not
  import any `internal/` package from mctl-telegram.

- [ ] 2. Add canary build step to `Dockerfile` (depends on 1) — DoD: `docker build .`
  produces an image containing `/usr/local/bin/mctl-telegram-canary`; the
  existing `mctl-telegram` and `mctl-telegram-login` binaries are unchanged;
  the image still uses non-root user 1000 and `ENTRYPOINT ["mctl-telegram"]`.
  Specifically: add `go build -ldflags="-s -w" -o /mctl-telegram-canary ./cmd/canary`
  to the builder `RUN` block and `COPY --from=builder /mctl-telegram-canary /usr/local/bin/mctl-telegram-canary`
  to the runtime stage.

- [ ] 3. Create `deploy/canary/cronjob.yaml` (depends on 2) — DoD: YAML is valid
  (`kubectl apply --dry-run=client -f deploy/canary/cronjob.yaml` passes),
  schedule is `*/2 * * * *`, `concurrencyPolicy: Forbid`,
  `activeDeadlineSeconds: 90`, `restartPolicy: Never`, container image uses the
  same image tag as the main server, all three required env vars are sourced from
  the `mctl-telegram-canary` Kubernetes Secret, `PUSHGATEWAY_URL` is set to the
  cluster-internal Pushgateway address, resource requests and limits are set.

- [ ] 4. Create `deploy/alerts/canary.rules.yaml` — DoD: YAML is a valid
  `monitoring.coreos.com/v1 PrometheusRule`, contains the
  `MctlTelegramCanaryFailing` alert rule with expression
  `min_over_time(mctl_telegram_canary_success[10m]) == 0`, `for: 5m`,
  `severity: critical`, and an annotation referencing a runbook path.
  File applies cleanly against a cluster with the Prometheus Operator CRD
  installed (`kubectl apply --dry-run=client -f deploy/alerts/canary.rules.yaml`).

- [ ] 5. Add "Operations: Canary account" section to `README.md` (depends on 3, 4)
  — DoD: section explains (a) the canary must be a dedicated test Telegram
  account separate from the operator's personal account; (b) the account must
  complete the browser setup at `GET /telegram/connect` before a token can be
  issued; (c) how to issue a read-only token via the `set_telegram_access`
  admin tool and the `local-jwt` OAuth flow; (d) the required shape of the
  `mctl-telegram-canary` Kubernetes Secret (`tg_user_id`, `bearer_token`);
  (e) that the token must carry scopes `telegram:dialogs:read,telegram:messages:read`
  and must not have any send scope.

## Tests

- [ ] T1. Unit test for oauth_metadata probe (`cmd/canary/main_test.go` or
  `cmd/canary/probe_test.go`): use `httptest.NewServer` to serve a valid
  `/.well-known/oauth-authorization-server` JSON response and a malformed one;
  assert that the probe returns nil error for valid and non-nil for missing
  required keys. DoD: `go test ./cmd/canary/...` passes.

- [ ] T2. Unit test for `list_dialogs` probe: use `httptest.NewServer` to serve
  (a) a valid JSON-RPC success response, (b) a JSON-RPC error response, and
  (c) a success response whose content text contains `"FLOOD_WAIT_30"`. Assert
  that (a) returns nil, (b) and (c) return non-nil errors, and (c) sets the
  `flood_wait=true` log field. DoD: `go test ./cmd/canary/...` passes.

- [ ] T3. Integration test of metric emission: run the full probe sequence against
  two `httptest.Server` instances (one for the server, one simulating
  Pushgateway). Assert that after a successful run, `mctl_telegram_canary_success`
  value in the pushed payload is 1, and after a failed `list_dialogs` run, value
  is 0 and `mctl_telegram_canary_step_failure_total{step="list_dialogs"}` is 1.
  DoD: `go test ./cmd/canary/...` passes with `-count=1`.

- [ ] T4. Dockerfile smoke test: `docker build .` produces an image in which
  `docker run --rm <image> /usr/local/bin/mctl-telegram-canary --help` (or just
  invocation with missing env vars) exits with status 1 and prints a usage/error
  message (not a panic). DoD: verified in CI `docker` job.

- [ ] T5. PrometheusRule lint: add a step to `build.yml` (or a separate workflow)
  that runs `promtool check rules deploy/alerts/canary.rules.yaml` (using the
  `prom/prometheus` Docker image or the `prometheus/prometheus` binary in the CI
  runner). DoD: `promtool check rules` exits 0 with no warnings.

## Rollback

1. **Metrics**: The canary metrics (`mctl_telegram_canary_*`) are pushed by the
   CronJob pod to Pushgateway. Pushgateway retains the last pushed values. To
   stop polluting the Pushgateway, delete the CronJob
   (`kubectl delete cronjob mctl-telegram-canary -n mctl-telegram`) and manually
   delete the metric group from Pushgateway via its HTTP API
   (`DELETE /metrics/job/mctl_telegram_canary`). The alert will fire once the
   metric goes stale (after `[10m]` lookback window); silence the alert in
   Alertmanager until the metric group is deleted.

2. **Alert**: Delete or disable `deploy/alerts/canary.rules.yaml` from the
   cluster (`kubectl delete prometheusrule mctl-telegram-canary -n monitoring`).
   If merged into #86's file, remove only the `MctlTelegramCanaryFailing` rule
   block and re-apply.

3. **Dockerfile / binary**: The canary binary is additive. Reverting the
   Dockerfile change removes it from future image builds, but existing images
   already in the registry are unaffected. The CronJob must be deleted first
   (step 1) so it does not try to run the missing binary.

4. **No database migrations**: No schema was changed. Rollback requires no
   database operation.

5. **Git rollback**: Revert the PR with `git revert <merge-commit>` to remove
   `cmd/canary/`, the Dockerfile changes, `deploy/canary/cronjob.yaml`, and
   `deploy/alerts/canary.rules.yaml` in a single commit. After reverting, delete
   the CronJob and PrometheusRule from the cluster as above.
