# Tasks: labs-memory-quota-trend-review

- [ ] 1. Pull per-service memory/CPU metrics for all 17 services in `labs` for both the 2026-08-22 and 2026-09-19 snapshots — DoD: a per-service table exists with both snapshots side by side.
- [ ] 2. Rank services by contribution to the delta (limits.memory ~60%→~83%, requests.memory ~62%→~76%, limits.cpu →~94%) (depends on 1) — DoD: top 1-3 contributing services identified, or determined the growth is diffuse across many services.
- [ ] 3. Determine whether openclaw itself is among the top contributors (depends on 2) — DoD: explicit yes/no with supporting numbers, since this affects the `ghsa-batch-2026-09-11-upgrade-assessment` rollout's `labs` step.
- [ ] 4. Define an early-warning alert threshold for `labs` memory and CPU quota (percentage below 100%, informed by the historical peak footprint of a `labs` canary rollout) (depends on 2) — DoD: threshold value chosen and written down with rationale.
- [ ] 5. Configure the alert in the existing mctl monitoring/alerting layer (not as new in-namespace workload) to notify on threshold breach with current usage % and top contributor(s) (depends on 4) — DoD: alert rule active and verified to fire on a manual test/simulated breach if the platform supports it, or verified present in config if not testable live.
- [ ] 6. Write up findings and explicitly flag current `labs` headroom status to the `ghsa-batch-2026-09-11-upgrade-assessment` proposal (depends on 2, 3) — DoD: a go/no-go note exists that the GHSA proposal's task 4 can consume directly.

## Tests
- [ ] T1. Confirm the per-service attribution in step 1-2 sums to (approximately) the tenant-wide totals already reported by `mctl` for `labs`, to sanity-check the breakdown.
- [ ] T2. Confirm the new alert rule does not itself consume `labs` namespace quota (it should live in the platform monitoring layer, not as a pod/sidecar inside `labs`).
- [ ] T3. Simulate or historically backtest the chosen threshold against the 2026-08-22 → 2026-09-19 trend to confirm it would have fired with enough lead time before reaching ~83%/~94%.

## Rollback
If the alert threshold proves too noisy (false positives) or too late (fires too close to actual exhaustion), adjust the threshold value in the monitoring config — no infrastructure or `labs` workload change is involved, so rollback is simply reverting or retuning the alert rule. No `labs` service, quota, or deployment is modified by this proposal, so there is nothing else to roll back.
