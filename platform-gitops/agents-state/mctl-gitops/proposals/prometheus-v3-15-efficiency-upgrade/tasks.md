# Tasks: prometheus-v3-15-efficiency-upgrade

- [ ] 1. Review the v3.15.0 release notes/upgrade guide for TSDB/chunk-encoding
  compatibility notes and any breaking changes — DoD: written confirmation that existing
  on-disk TSDB blocks remain readable under v3.15.0, or documented migration step if not.
- [ ] 2. Record baseline `labs` and `admins` Prometheus-related CPU/memory/network usage before
  the upgrade (depends on nothing) — DoD: baseline metrics snapshot captured and saved
  alongside this proposal for later before/after comparison.
- [ ] 3. Bump the Prometheus version pin in `platform-gitops` to v3.15.0 (depends on 1) — DoD:
  version bump merged, ArgoCD sync healthy in a non-`labs` environment first if one exists,
  otherwise `labs` with heightened monitoring per the staged-rollout plan.
- [ ] 4. Enable zstd scrape-response compression in scrape configs where exporters support it
  (depends on 3) — DoD: configuration merged, confirmed via scrape-target debug output that
  compression is negotiated for at least one supporting exporter.
- [ ] 5. Adopt OM2.0 scrape format where compatible (depends on 3) — DoD: configuration merged
  and verified scrapes continue to succeed with no parse errors in Prometheus logs.
- [ ] 6. Evaluate whether AWS SD is in use on this platform and adopt the AWS SD efficiency
  improvements if applicable (depends on 3) — DoD: written conclusion (adopted / not
  applicable) recorded in this proposal.
- [ ] 7. Roll out to `labs` (if not already the first environment in task 3) with monitoring,
  then measure post-upgrade CPU/memory/network usage against the task-2 baseline (depends on
  3, 4, 5, 6) — DoD: before/after comparison recorded; if usage increased rather than decreased,
  flag as a regression and proceed to rollback.
- [ ] 8. Roll out to `admins` once `labs` is confirmed stable (depends on 7) — DoD: ArgoCD sync
  healthy, no new alerts fired attributable to the upgrade.

## Tests
- [ ] T1. Scrape-coverage regression test: all previously-scraped targets in both `admins` and
  `labs` continue reporting `up == 1` after the upgrade, with no sustained data gaps.
- [ ] T2. Alerting/dashboard regression test: existing alert rules and dashboard queries return
  expected results post-upgrade (spot-check a representative sample).
- [ ] T3. Compression verification test: confirm at least one exporter negotiates zstd
  compression post-upgrade (e.g. via scrape debug endpoint or response headers).
- [ ] T4. Resource-impact test: `labs` CPU/memory usage measured post-upgrade shows no increase
  relative to the task-2 baseline (ideally a measurable decrease).
- [ ] T5. TSDB read-compatibility test: existing historical data (pre-upgrade blocks) remains
  queryable after the upgrade.

## Rollback
This is a version-pin change local to `platform-gitops`: if the upgrade causes scrape failures,
alerting regressions, or an unexpected `labs` resource-usage increase, revert the version-pin
commit (task 3) and any accompanying scrape-config changes (tasks 4-6), then re-sync via
ArgoCD back to the prior tracked version. No TSDB data migration occurs, so no data-loss risk
is expected on rollback, but task 1's compatibility findings should be reviewed to confirm
downgrade compatibility before reverting if the chunk-encoding format has already written new
blocks under v3.15.0.
