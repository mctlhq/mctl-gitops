# Tasks: issue-91-sticky-routing-by-user-id-for-multi-repl

- [ ] 1. Add `ReplicaID string` to `internal/config/config.go`
  DoD: `config.Load()` reads `REPLICA_ID` first, falls back to `POD_NAME`, then
  to `"unknown"`. Unit test `TestConfigReplicaID` passes (see Tests section).

- [ ] 2. Add `TelegramReplicaID *prometheus.GaugeVec` to `internal/metrics/metrics.go`
  (depends on nothing, can run in parallel with task 1)
  DoD: `metrics.New()` constructs and registers `mctl_telegram_replica_id` with
  label `replica_id`. No existing test breaks. `go vet ./internal/metrics/...`
  passes. Unit test `TestReplicaIDGauge` passes (see Tests section).

- [ ] 3. Wire replica identity into `cmd/server/main.go` (depends on 1, 2)
  DoD: After `metrics.New()` and config load, `cmd/server/main.go` calls
  `m.TelegramReplicaID.WithLabelValues(cfg.ReplicaID).Set(1)` and adds
  `"replica_id", cfg.ReplicaID` to the existing `slog.Info("starting", ...)`
  call. Running `go build ./cmd/server/` succeeds. A `go test -run TestStartup`
  integration test (if one exists) still passes; otherwise the change is
  verified by running the server locally and checking log output and
  `GET /metrics`.

- [ ] 4. Add `deploy/ingress/sticky-nginx.yaml` (depends on 1)
  DoD: The file is a valid Kubernetes YAML containing an `Ingress` resource
  annotated with `nginx.ingress.kubernetes.io/upstream-hash-by` and a
  `configuration-snippet` Lua block that (a) clears any incoming
  `X-Mctl-Route-Key` header, (b) extracts the `sub` claim from the JWT payload,
  and (c) sets `X-Mctl-Route-Key` to the extracted value. The file includes a
  comment explaining the security rationale (payload-only extraction without
  signature verification). A YAML lint check (`yamllint`) passes. The file
  includes a downward API env var snippet for `POD_NAME` as a comment example.

- [ ] 5. Add `deploy/ingress/sticky-envoy.yaml` (depends on 1)
  DoD: The file contains two Kubernetes resources: an Istio `DestinationRule`
  with `trafficPolicy.loadBalancer.consistentHash.httpHeaderName:
  "x-mctl-route-key"` and an `EnvoyFilter` applying a Lua HTTP filter that
  performs the same extraction logic as task 4. The file includes a comment
  noting the experimental Gateway API `BackendLBPolicy` alternative. A YAML
  lint check passes.

- [ ] 6. Extend `docs/hpa.md` with a sticky routing section (depends on 4, 5)
  DoD: `docs/hpa.md` gains a new top-level section "Sticky routing for
  multi-replica deployments" containing: (a) a one-paragraph problem statement
  referencing `internal/telegram/clientpool.go:60-91`, (b) the two-layer
  solution summary, (c) the security analysis for payload-only JWT extraction
  at the LB tier, (d) a downward API Deployment snippet for `POD_NAME`, (e)
  verification steps using `kubectl exec` + `/metrics`, (f) a note on one-time
  "New login" events during pod add/remove, and (g) references to
  `deploy/ingress/sticky-nginx.yaml` and `deploy/ingress/sticky-envoy.yaml`.
  `go vet` still passes (docs-only change); a markdown linter reports no errors.

- [ ] 7. Add soak test scenario to issue #90 (depends on 6)
  DoD: Issue #90 is updated (or a tracking comment is added) specifying a
  2-replica soak test scenario: deploy with `sticky-nginx.yaml` applied, run
  the existing load-test script for 30 minutes against the canary Telegram
  account, assert that exactly 0 "New login" Telegram notifications are
  received on the canary account during the test. This task produces no code
  change in this repository; it is complete when the scenario is documented
  on issue #90.

## Tests

- [ ] T1. `TestReplicaIDGauge` in `internal/metrics/metrics_test.go`
  Verify that `metrics.New()` registers `mctl_telegram_replica_id`, that
  calling `r.TelegramReplicaID.WithLabelValues("pod-0").Set(1)` produces a
  gauge with value 1 for label `replica_id="pod-0"`, and that a second call
  with a different label (`"pod-1"`) produces a distinct time-series. Uses the
  existing pattern of gathering from `r.Prometheus` with
  `prometheus.ToTransactionalGatherer` or `testutil.CollectAndCompare`.

- [ ] T2. `TestConfigReplicaID` in `internal/config/config_test.go` (or new
  file `internal/config/config_replicaid_test.go`)
  Three sub-cases using `t.Setenv`:
  1. `REPLICA_ID=pod-42` set — `cfg.ReplicaID == "pod-42"`.
  2. `REPLICA_ID` unset, `POD_NAME=mctl-telegram-7f9d` set — `cfg.ReplicaID
     == "mctl-telegram-7f9d"`.
  3. Both unset — `cfg.ReplicaID == "unknown"`.

- [ ] T3. Soak test: 2-replica + sticky routing (tracked in issue #90; see task 7)
  Deploy two replicas with `sticky-nginx.yaml` applied. Run the #90 load-test
  harness for 30 minutes. Assert: `mctl_telegram_client_pool_size` on each pod
  is non-zero and stable (no churning); zero "New login" Telegram notifications
  on the canary account; `mctl_telegram_replica_id` visible in `/metrics` on
  both pods with distinct `replica_id` labels.

## Rollback

1. Remove the `nginx.ingress.kubernetes.io/upstream-hash-by` and
   `configuration-snippet` annotations from the Ingress resource (or revert
   the kustomize patch in `mctl-gitops`). NGINX reverts to round-robin. Users
   may see a one-time "New login" notification as requests begin landing on new
   replicas, but no data is lost.
2. Scale the Deployment back to `replicas: 1` via the HPA `minReplicas`
   setting. This stops the multi-replica problem at the source while a
   permanent fix is arranged.
3. The application-level changes (`ReplicaID` config field, startup log line,
   `mctl_telegram_replica_id` gauge) are safe to leave in place — they add
   a harmless gauge and log field. If removal is desired, revert the three
   Go files changed in tasks 1-3 and re-deploy.
4. No database migration is involved; no DB rollback is required.
5. Update any Prometheus alert rules or dashboards that reference
   `mctl_telegram_replica_id` after rollback to avoid stale alert conditions.
