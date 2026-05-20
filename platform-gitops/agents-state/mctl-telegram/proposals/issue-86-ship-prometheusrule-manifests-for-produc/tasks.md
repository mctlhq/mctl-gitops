# Tasks: issue-86-ship-prometheusrule-manifests-for-produc

- [ ] 1. Create `deploy/alerts/` directory and write `deploy/alerts/mctl-telegram.rules.yaml`
  as a `monitoring.coreos.com/v1` `PrometheusRule` manifest containing one
  `RuleGroup` (`mctl-telegram.rules`) with eight alert rules:
  `MctlTelegramPoolNearCapacity` (warning, `> 0.85 for 5m`),
  `MctlTelegramPoolNearCapacity` (critical, `> 0.95 for 2m`),
  `MctlTelegramFloodWaitSpike` (warning, `> 0.5 for 2m`),
  `MctlTelegramFloodWaitSpike` (critical, `> 2 for 2m`),
  `MctlTelegramOAuthPendingStuck` (warning, `> 100 for 15m`),
  `MctlTelegramAuthFailuresSpike` (warning, `> 1 for 2m`),
  `MctlTelegramClientErrorsSpike` (warning, `> 0.2 for 2m`),
  `MctlTelegramRateLimitWave` (warning, `> 1 for 2m`).
  Pool alerts must include the `and mctl_telegram_pool_capacity > 0` guard.
  All alerts carry `summary`, `description`, `runbook_url`, and `severity`.
  Manifest metadata: `namespace: mctl`, labels `app: mctl-telegram` and
  `release: kube-prometheus-stack`.
  DoD: file exists at `deploy/alerts/mctl-telegram.rules.yaml`; `kubectl apply
  --dry-run=client -f deploy/alerts/mctl-telegram.rules.yaml` succeeds against
  a cluster with Prometheus Operator CRDs installed; all eight rules are present
  and `promtool check rules deploy/alerts/mctl-telegram.rules.yaml` exits 0.

- [ ] 2. Update `docs/hpa.md` (depends on 1) — replace the "Alerts" section
  (currently lines 105-121) inline YAML block with a reference paragraph pointing
  to `deploy/alerts/mctl-telegram.rules.yaml` as the authoritative source.
  Update the trailing notes about `mctl_telegram_flood_wait_events_total` and
  `mctl_oauth_pending_auth_size` (lines 125-133) to say the corresponding alerts
  are defined in the manifest rather than suggesting they should be added. Add a
  short sub-section explaining that operators should mirror the manifest into
  `mctl-gitops` at
  `platform-gitops/k8s/mctl-telegram/alerts/mctl-telegram.rules.yaml`.
  DoD: `docs/hpa.md` no longer contains any raw alert YAML blocks; a link to
  `deploy/alerts/mctl-telegram.rules.yaml` is present; the gitops mirror path is
  documented.

- [ ] 3. Open PR on `mctlhq/mctl-telegram` with tasks 1-2 (depends on 2) —
  commit message `feat: add PrometheusRule manifest for production alerts (#86)`.
  PR description references issue #86 and notes the follow-up gitops PR required.
  DoD: PR is open, CI passes (`go vet ./...`, `go test ./...`, golangci-lint).

- [ ] 4. Open follow-up PR on `mctlhq/mctl-gitops` (depends on 3, after merge) —
  mirror `deploy/alerts/mctl-telegram.rules.yaml` to
  `platform-gitops/k8s/mctl-telegram/alerts/mctl-telegram.rules.yaml`.
  Verify the `ruleSelector` labels on the `Prometheus` CR in that repo match
  the labels set in the manifest (`app: mctl-telegram`, `release:
  kube-prometheus-stack`). Adjust labels if they differ.
  DoD: the `PrometheusRule` CR is present in `mctl-gitops`; `kubectl apply
  --dry-run=server` passes; PR description cross-references the `mctl-telegram`
  PR that introduced the manifest; a reviewer with cluster access confirms the
  rules appear in the Prometheus UI after merge.

## Tests

- [ ] T1. `promtool check rules deploy/alerts/mctl-telegram.rules.yaml` exits 0.
  This validates PromQL syntax and `for` duration fields without requiring a
  live Prometheus instance.

- [ ] T2. Run `kubectl apply --dry-run=client --validate=true -f
  deploy/alerts/mctl-telegram.rules.yaml` against a cluster (or `kind` instance)
  with Prometheus Operator CRDs. Confirms the manifest is well-formed YAML and
  the CR schema is satisfied.

- [ ] T3. Manual spot-check after gitops PR merges: open the Prometheus UI in the
  Beta cluster, navigate to Status > Rules, search for
  `mctl-telegram.rules`. Verify all eight rules are loaded and none show a
  parse error.

- [ ] T4. Verify the pool-capacity guard: with `TELEGRAM_MAX_SESSIONS` unset
  (capacity gauge = -1), confirm `MctlTelegramPoolNearCapacity` does not fire.
  Can be done via `promtool test rules` with a synthetic unit-test YAML file
  that provides sample values for the two pool gauges.

- [ ] T5. Existing Go tests (`go test ./...`) must continue to pass — no changes
  to Go source are expected, so this is a no-regression check.

## Rollback

**In `mctl-telegram`**: if the new manifest or the `docs/hpa.md` change causes
issues, revert the PR with `git revert <merge-commit>` and open a follow-up PR.
No Go code, no migration, no container image change — rollback has zero runtime
risk.

**In `mctl-gitops`**: delete or rename the file at
`platform-gitops/k8s/mctl-telegram/alerts/mctl-telegram.rules.yaml` and commit.
Prometheus Operator will remove the rule group from Prometheus on the next
reconcile (typically within 30 seconds). Alerts in Alertmanager that fired
before rollback will resolve on their own once the rules disappear. No data is
lost.
