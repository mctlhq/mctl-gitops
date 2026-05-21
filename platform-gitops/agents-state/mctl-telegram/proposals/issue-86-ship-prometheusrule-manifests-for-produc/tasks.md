# Tasks: issue-86-ship-prometheusrule-manifests-for-produc

- [ ] 1. Create `deploy/alerts/mctl-telegram.rules.yaml` as a
  `monitoring.coreos.com/v1` `PrometheusRule` manifest containing one
  `RuleGroup` (`mctl-telegram.rules`) with the THREE genuinely-new alert rules
  (the others are already covered by the deployed `mctl-telegram-alerts` VMRule):
  `MctlTelegramPoolNearCapacity` (warning, `> 0.85 for 5m`),
  `MctlTelegramPoolNearCapacity` (critical, `> 0.95 for 2m`),
  `MctlTelegramFloodWaitSpike` (warning, `> 0.5 for 2m`),
  `MctlTelegramFloodWaitSpike` (critical, `> 2 for 2m`),
  `MctlTelegramOAuthPendingStuck` (warning, `> 100 for 15m`).
  Do NOT add AuthFailuresSpike / ClientErrorsSpike / RateLimitWave — they
  duplicate the existing VMRule (see design.md).
  Pool alerts must include the `and mctl_telegram_pool_capacity > 0` guard.
  All alerts carry `summary`, `description`, `runbook_url`, and `severity`.
  Manifest metadata MUST match `deploy/alerts/canary.rules.yaml`:
  `namespace: monitoring`, labels `prometheus: kube-prometheus` and
  `role: alert-rules` (plus `service: mctl-telegram` on each alert).
  DoD: file exists; `promtool check rules deploy/alerts/mctl-telegram.rules.yaml`
  exits 0; metadata labels/namespace match canary.rules.yaml exactly.

- [ ] 2. Update `docs/hpa.md` (depends on 1) — replace the "Alerts" section
  (currently lines 105-121) inline YAML block with a reference paragraph pointing
  to `deploy/alerts/mctl-telegram.rules.yaml` as the authoritative source.
  Update the trailing notes about `mctl_telegram_flood_wait_events_total` and
  `mctl_oauth_pending_auth_size` (lines 125-133) to say the corresponding alerts
  are defined in the manifest rather than suggesting they should be added. Add a
  short sub-section noting that operators mirror the manifest into `mctl-gitops`
  at `platform-gitops/infra-components/observability/vm-rules/` (where
  `mctl-telegram-alerts.yaml` already lives), and that the VictoriaMetrics
  operator auto-converts the PrometheusRule to a VMRule.
  DoD: `docs/hpa.md` no longer contains any raw alert YAML blocks; a link to
  `deploy/alerts/mctl-telegram.rules.yaml` is present; the gitops mirror path is
  documented.

- [ ] 3. Open PR on `mctlhq/mctl-telegram` with tasks 1-2 (depends on 2) —
  commit message `feat: add PrometheusRule manifest for production alerts (#86)`.
  PR description references issue #86 and notes the follow-up gitops mirror.
  DoD: PR is open, CI passes (`go vet ./...`, `go test ./...`, golangci-lint).

- [ ] 4. (Manual operator step, NOT the implementer) Mirror
  `deploy/alerts/mctl-telegram.rules.yaml` into `mctl-gitops` at
  `platform-gitops/infra-components/observability/vm-rules/` after the
  mctl-telegram PR merges. The VM operator converts it to a VMRule (verified by
  the canary precedent). DoD: rule appears in vmalert; alerts visible in the
  VictoriaMetrics/Grafana UI.

## Tests

- [ ] T1. `promtool check rules deploy/alerts/mctl-telegram.rules.yaml` exits 0.
  This validates PromQL syntax and `for` duration fields without requiring a
  live Prometheus instance.

- [ ] T2. Run `kubectl apply --dry-run=client --validate=true -f
  deploy/alerts/mctl-telegram.rules.yaml` against a cluster (or `kind` instance)
  with Prometheus Operator CRDs. Confirms the manifest is well-formed YAML and
  the CR schema is satisfied.

- [ ] T3. Manual spot-check after the gitops mirror lands: open the
  VictoriaMetrics/vmalert (or Grafana) UI, search for `mctl-telegram.rules`.
  Verify all three new rules are loaded as a VMRule and none show a parse error.

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

**In `mctl-gitops`**: delete or rename the mirrored file under
`platform-gitops/infra-components/observability/vm-rules/` and commit. The VM
operator removes the converted VMRule on the next reconcile (typically within
30 seconds). Alerts that fired before rollback resolve on their own once the
rules disappear. No data is lost.
