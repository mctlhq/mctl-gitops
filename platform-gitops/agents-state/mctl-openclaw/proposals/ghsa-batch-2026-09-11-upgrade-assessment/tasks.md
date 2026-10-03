# Tasks: ghsa-batch-2026-09-11-upgrade-assessment

- [ ] 1. For each of the 10 September 11 GHSA advisories, record affected-version range and patched-version(s) from the primary advisories page — DoD: a table exists mapping each advisory to whether `2026.7.11-beta.2` is in-range, sourced only from `github.com/openclaw/openclaw/security/advisories`.
- [ ] 2. Cross-check the third-party "breaking changes" summary for `2026.9.3` (Node runtime requirements, SDK execution policies, search-result callbacks) against the primary release changelog (depends on 1) — DoD: each claimed breaking change is confirmed, refuted, or marked unconfirmed with the primary source checked.
- [ ] 3. Select the target version (a `2026.9.x` release preferred; `2026.6.35` LTS only as a documented accepted-risk fallback) (depends on 1, 2) — DoD: target version chosen and written down with a one-line justification referencing the advisory table.
- [ ] 4. Check `labs-memory-quota-trend-review` findings for current `labs` headroom before scheduling the `labs` rollout step (depends on 3) — DoD: explicit go/no-go note on whether `labs` has safe headroom for a canary rollout right now.
- [ ] 5. Roll out the target version to `labs`; pause s3-sync canary for rollout duration per ADR-0002, restart with delay after (depends on 3, 4) — DoD: `labs`/openclaw running target version, canary resumed and reporting normally, restore-state probe passed.
- [ ] 6. Observe `labs` for the standard ADR-0001 window (no new incidents, canary healthy, resource usage stable) (depends on 5) — DoD: observation window elapsed with no regressions logged.
- [ ] 7. Roll out to `admins` following the same canary-pause procedure (depends on 6) — DoD: `admins`/openclaw running target version, canary and probe healthy.
- [ ] 8. Roll out to `ovk` following the same canary-pause procedure, only after `admins` is confirmed stable (depends on 7) — DoD: `ovk`/openclaw running target version, canary and probe healthy, no customer-visible disruption.
- [ ] 9. Update `context/current-version.md` with the new version, per-tenant confirmation, and update date; add an ADR if tenants diverge (depends on 8) — DoD: file reflects reality and is dated with this rollout.

## Tests
- [ ] T1. For each fork-relevant advisory (exec-approval, WhatsApp, Discord, Slack), verify the specific reported behavior (e.g., exec approval scoped to reviewed directory; WhatsApp login tool cannot reach non-owner turns) against the patched version in a `labs` smoke test before promoting to `admins`.
- [ ] T2. Confirm the s3-sync canary correctly resumes after each tenant's rollout (no missed-cycle alert storm, no silently-stuck-paused canary).
- [ ] T3. Confirm the restore-state probe passes within its existing (unchanged) timeout on each tenant's rollout, i.e., no channel takes longer to restore auth/sessions on the new version.
- [ ] T4. Re-check `ovk` incidents and s3-sync logs for 24h post-rollout to confirm no new anomalies beyond what is already tracked in the separate `ovk-s3-sync-canary-and-pod-health-investigation` proposal.

## Rollback
If the `labs` rollout shows a regression (failed probe, canary alert storm, functional break in a channel), revert the `labs` image tag to `2026.7.11-beta.2` via mctl-gitops/ArgoCD and do not proceed to `admins`/`ovk`. If a regression is only discovered after `admins` or `ovk` has been upgraded, roll back that tenant's image tag independently (tenants have independent gitops/helm releases per ADR-0001) and pause the canary during the rollback exactly as during a forward rollout, then restart it with the standard delay. Do not roll back `ovk` by restarting the pod without going through the standard rollback-via-gitops path, to preserve the restore-state guarantees from ADR-0002.
