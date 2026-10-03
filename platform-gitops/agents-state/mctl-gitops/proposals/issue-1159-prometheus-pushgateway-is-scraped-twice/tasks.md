# Tasks: issue-1159-prometheus-pushgateway-is-scraped-twice

- [ ] 1. Delete `platform-gitops/infra-components/observability/vm-rules/pushgateway-podscrape.yaml`
      (`kind: VMPodScrape`, name `prometheus-pushgateway`, namespace `monitoring`).
      — DoD: the file is gone from the branch; `grep -rn "VMPodScrape" platform-gitops/infra-components`
      returns nothing; no other file in the repo references the filename
      (`grep -rn "pushgateway-podscrape"` returns only historical agents-state notes).

- [ ] 2. Fold the deleted header's history into
      `platform-gitops/infra-components/observability/pushgateway/servicescrape.yaml`
      (depends on 1) — DoD: the file's leading comment block states, in the
      repo's existing comment style: (a) that this is the ONLY scrape of the
      pushgateway and that adding a second one duplicates every pushed series
      and doubles every alert over it (issue #1159, VMPodScrape removed
      2026-09); (b) that a pod-level scrape once existed because the live
      Service carried no labels and an unnamed port — fixed in
      `pushgateway.yaml`, so the correct response to a broken pool is to fix
      the Service, not to add a parallel scrape; (c) that `honorLabels: true`
      is load-bearing because `MctlTelegramCanaryStale` keys off
      `push_time_seconds{job="mctl_telegram_canary"}` and the backup rules key
      off `{job="vmbackup"}`. The `spec` is unchanged: still `port: http`,
      `honorLabels: true`, no `interval`.

- [ ] 3. Make `scripts/check-vm-rules.sh` fail on a non-`VMRule` file under
      `platform-gitops/infra-components/observability/vm-rules/` (depends on 1)
      — DoD: the branch that today prints `skip (kind=$kind): ...` and
      `continue`s now emits a `::error file=...::` annotation naming the
      offending file and sets `fail=1`, in the same style as the existing
      `promtool check rules` failure path; the message tells the author to put
      the object in `platform-gitops/infra-components/observability/<component>/`
      instead. Running `scripts/check-vm-rules.sh` locally exits 0 on the
      branch (every remaining file in `vm-rules/` is `kind: VMRule`).

- [ ] 4. Open the PR against `main` on a feature branch (depends on 1, 2, 3)
      — DoD: branch + PR exist (no direct push to `main`; the bot-commit
      exception in `CLAUDE.md` covers only `image.tag` bumps); PR body links
      issue #1159, states that the `VMServiceScrape` is the survivor, and lists
      the four post-sync verification queries from task 5.

- [ ] 5. After merge, wait for the ArgoCD `monitoring` Application to sync
      (`syncPolicy.automated.prune: true` removes the live `VMPodScrape`) and
      verify in-cluster (depends on 4) — DoD: all four checks below pass and
      the results are recorded as a comment on issue #1159.

## Tests

- [ ] T1. Exactly one pushgateway scrape pool, and it is up: vmagent
      `/api/v1/targets` contains `serviceScrape/monitoring/prometheus-pushgateway/0`
      with `health=up`, and contains no `podScrape/monitoring/prometheus-pushgateway/*`.
      Also confirm `kubectl -n monitoring get vmpodscrape prometheus-pushgateway`
      returns `NotFound` (proves ArgoCD pruned it rather than leaving it orphaned).

- [ ] T2. Duplication is gone: `count by (__name__) ({__name__=~"mctl_telegram_canary_success|vmbackup_last_success_timestamp_seconds"})`
      returns `1` for each name (was `2`). Run after at least one scrape
      interval plus the VM staleness horizon (~6 minutes) so the abandoned
      `endpoint="9091"` series has aged out.

- [ ] T3. `honorLabels` survived: `push_time_seconds{job="mctl_telegram_canary"}`
      and `vmbackup_last_success_timestamp_seconds{job="vmbackup"}` both still
      return a series. This is the check that would catch the scrape
      overwriting the pushed `job` label — the failure mode that would silently
      break `MctlTelegramCanaryStale`, `VictoriaMetricsBackupStale` and
      `VictoriaMetricsBackupMetricAbsent` at once.

- [ ] T4. No alert regression: in vmalert, `MctlTelegramCanaryStale`,
      `MctlTelegramCanaryAbsent`, `MctlTelegramCanaryFailing`,
      `VictoriaMetricsBackupStale` and `VictoriaMetricsBackupMetricAbsent` are
      all `inactive`; and `ScrapePoolHasNoTargets` is not firing for
      `namespace="monitoring"` (that alert routes to the `mctl-agent` receiver
      per `bootstrap/templates/observability/monitoring.yaml` and is the
      safety net for "the one remaining scrape selected nothing"). Check again
      ~30 minutes after the sync so the `[25m]`/`[30m]` lookback windows have
      fully turned over.

- [ ] T5. CI gates pass on the PR: `.github/workflows/validate-manifests.yml`
      is green — specifically the "Check and unit-test alerting rules" step
      (`scripts/check-vm-rules.sh`, now including the new kind check) and the
      kubeconform sweep over `platform-gitops/infra-components`.

- [ ] T6. The new guard actually fires: temporarily place a copy of the deleted
      `VMPodScrape` under `vm-rules/`, confirm `scripts/check-vm-rules.sh`
      exits non-zero with the `::error` annotation, then remove it. (The repo's
      own convention — see the `--selftest` comments in
      `validate-manifests.yml` — is that a detector never seen to fire is not
      known to work.) Do not commit the temporary file.

## Rollback

Single-commit revert. `git revert` the merge commit (or re-add
`platform-gitops/infra-components/observability/vm-rules/pushgateway-podscrape.yaml`
verbatim from `main@{before}`) and merge to `main`; ArgoCD re-creates the
`VMPodScrape` on the next sync of the `monitoring` Application and the second
scrape pool reappears within a scrape interval. No data migration to undo — the
only effect is that pushed metrics resume being written as two series, i.e.
back to the state described in issue #1159.

Emergency, if the pushgateway must be scraped again before a revert can land:
`kubectl -n monitoring apply -f` the old manifest directly. This is drift and
ArgoCD's `selfHeal: true` will prune it again at the next sync, so it buys
minutes, not a resting state — use it only to restore metrics flow while the
revert PR is in flight.

If instead the surviving `VMServiceScrape` turns out to select zero targets
(`ScrapePoolHasNoTargets` for `namespace="monitoring"`), the correct fix is the
Service, not a second scrape: confirm
`kubectl -n monitoring get svc prometheus-pushgateway --show-labels` still
carries `app=prometheus-pushgateway` and that its port is still named `http`,
per `platform-gitops/infra-components/observability/pushgateway/pushgateway.yaml`.
