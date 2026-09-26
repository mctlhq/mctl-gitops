# Tasks: openclaw-upstream-upgrade-assessment

- [ ] 1. Enumerate `2026.7.11-beta.2`'s exposure against all currently-published GHSA advisories (primary advisories page only) — DoD: table of advisory ID → affected/not-affected with citation for each.
- [ ] 2. Cross-reference the CCB Belgium RCE advisory, Infosecurity "six new vulnerabilities" article, and betterclaw.io CVE-count aggregate to specific GHSA/CVE IDs — DoD: each signal resolved to a GHSA/CVE ID + version range, or explicitly logged as unconfirmed/non-actionable.
- [ ] 3. Evaluate candidate targets `2026.8.1`, `2026.7.35` (LTS), `2026.9.6` (mainline) against plugin-sdk/channel-extension compatibility and S3 state-layout compatibility (depends on 1, 2) — DoD: written recommendation with chosen target and rationale.
- [ ] 4. Reconcile with existing overlapping proposals (`ghsa-batch-2026-09-11-upgrade-assessment`, `openclaw-cve-upgrade`, `openclaw-upgrade-cve-batch`, `openclaw-upgrade-2026-5-12`) (depends on 3) — DoD: decision recorded on which proposal is authoritative going forward; superseded ones marked closed.
- [ ] 5. Capture `labs` memory/CPU baseline immediately before rollout (depends on 3) — DoD: baseline numbers recorded (limits.memory, requests.memory, CPU, pod count) against the 14Gi/16-CPU quota.
- [ ] 6. Roll out to `labs` per ADR-0001/ADR-0002 (canary pause, restore-state probe intact) (depends on 5) — DoD: `labs` on target version, healthy, s3-sync canary resumed, memory/CPU delta vs. baseline documented and within threshold.
- [ ] 7. Observation window in `labs` (depends on 6) — DoD: agreed observation period elapsed with no memory regression, no canary/probe failures, no new incidents.
- [ ] 8. Roll out to `admins` (depends on 7) — DoD: `admins` on target version, healthy, canary/probe intact.
- [ ] 9. Roll out to `ovk` (depends on 8) — DoD: `ovk` on target version, healthy, canary/probe intact, no unplanned downtime.
- [ ] 10. Update `context/current-version.md` with new version, per-tenant confirmation, date (depends on 9) — DoD: file updated and accurate.

## Tests
- [ ] T1. Confirm restore-state probe passes within timeout on the target version in `labs` before promoting to `admins`.
- [ ] T2. Confirm the s3-sync canary resumes and reports fresh timestamps within N cycles after each tenant's rollout.
- [ ] T3. Diff `labs` memory/CPU usage pre- vs. post-upgrade; fail the gate if usage increases beyond the agreed threshold.
- [ ] T4. Smoke-test each channel (WhatsApp, Discord, Slack, Telegram, etc.) pairing/session-restore in `labs` post-upgrade.
- [ ] T5. Verify no plugin-sdk breaking-change regressions in `extensions/*` against the target version's changelog.

## Rollback
If the `labs` canary shows a memory/CPU regression, a canary/probe failure,
or a channel regression: halt promotion to `admins`/`ovk` immediately,
revert `labs`'s Helm values to `2026.7.11-beta.2` via ArgoCD, confirm the
s3-sync canary and restore-state probe report healthy on the reverted
version, and re-run Phase A with the failure documented before attempting a
different target. If a regression surfaces only after `admins` or `ovk`
promotion, revert that tenant's image tag the same way, in reverse rollout
order, without touching tenants that have not regressed.
