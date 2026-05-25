# Tasks: issue-213-deploy-canary-prometheusrule-to-cluster

All changes are in the `mctlhq/mctl-gitops` repository unless noted otherwise.

- [ ] 1. Verify Pushgateway job label — DoD: confirm the label key/value the
  `cmd/canary` binary (in `mctlhq/mctl-telegram`) uses when pushing to Pushgateway
  (`push_time_seconds{job=?}`) by either reading the canary source or querying the live
  Pushgateway endpoint (`http://prometheus-pushgateway.monitoring.svc.cluster.local:9091/metrics`).
  Record the actual label in a code comment in the new VMRule file. If the label differs
  from `mctl_telegram_canary`, update the `MctlTelegramCanaryStale` expression
  accordingly before creating the manifest.

- [ ] 2. Create `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-canary-alerts.yaml`
  (depends on 1) — DoD: file exists in the repo at that path; contains a single
  `operator.victoriametrics.com/v1beta1 VMRule` named `mctl-telegram-canary` in
  namespace `monitoring` with labels `app.kubernetes.io/part-of: mctl-platform` and
  `app.kubernetes.io/component: mctl-telegram`; includes the three alert rules
  (`MctlTelegramCanaryFailing`, `MctlTelegramCanaryStale`, `MctlTelegramCanaryAbsent`)
  with expressions, `for` durations, severity labels, and runbook annotation URLs
  transcribed from `deploy/alerts/canary.rules.yaml` in `mctlhq/mctl-telegram`; the
  `job` label in `MctlTelegramCanaryStale` matches the value confirmed in task 1.

- [ ] 3. Open and merge PR in mctl-gitops (depends on 2) — DoD: PR opened with
  `feat: deploy canary VMRule to monitoring namespace` title and merge strategy is merge
  commit (not squash/rebase, per project conventions); PR description references issue
  mctlhq/mctl-telegram#213; PR reviewed and merged to `main`.

- [ ] 4. Verify ArgoCD sync (depends on 3) — DoD: ArgoCD `monitoring` Application
  shows Synced/Healthy within 3 minutes of merge; `kubectl -n monitoring get vmrule
  mctl-telegram-canary` returns the resource with `CREATED` timestamp matching the
  merge time; VMAlert logs show the three alert rules loaded.

## Tests

- [ ] T1. Stale alert smoke test: suspend the `mctl-telegram-canary` CronJob in the
  `labs` namespace (`kubectl -n labs patch cronjob mctl-telegram-canary --type merge
  -p '{"spec":{"suspend":true}}'`), wait 15 minutes, and confirm `MctlTelegramCanaryStale`
  appears as FIRING in the AlertManager UI (`https://alertmanager.mctl.ai` or equivalent).
  Unsuspend the CronJob after the test.

- [ ] T2. mctl-agent delivery test: confirm the fired `MctlTelegramCanaryStale` alert
  (from T1) appears as a Telegram message in the configured channel within 5 minutes of
  firing. This validates the full path: VMAlert evaluates rule -> AlertManager routes to
  `mctl-agent` default receiver -> mctl-agent webhook posts to Telegram.

- [ ] T3. Absent alert coverage: delete the metric group from Pushgateway
  (`curl -X DELETE http://prometheus-pushgateway.monitoring.svc.cluster.local:9091/metrics/job/mctl_telegram_canary`)
  and confirm `MctlTelegramCanaryAbsent` fires immediately (for: 0m means no wait
  period). Restore by running or unsuspending the CronJob.

- [ ] T4. Recovery: after re-enabling and running the CronJob, confirm all three canary
  alerts resolve within one VMAlert evaluation cycle (at most 60 seconds after the next
  successful push).

## Rollback

1. Delete `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-canary-alerts.yaml`
   from the `mctl-gitops` repository and merge the deletion to `main`.
2. ArgoCD `monitoring` Application has `prune: true`; it will delete the VMRule from
   the cluster on the next sync cycle (within ~3 minutes).
3. No other cluster state is affected: no Deployment, no ConfigMap, no Alertmanager
   config is changed by this work.
