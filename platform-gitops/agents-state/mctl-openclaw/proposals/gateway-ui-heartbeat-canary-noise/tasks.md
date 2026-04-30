# Tasks: gateway-ui-heartbeat-canary-noise

- [ ] 1. **Confirm pre-regression `heartbeat.intervalMs` default from upstream history** — Check the openclaw changelog or git history between the last known-good release and 2026.4.27 for the heartbeat interval default change. Confirm the correct pre-regression value (expected: 30000 ms). — DoD: Value confirmed and linked to upstream commit/issue comment; documented in the PR description.

- [ ] 2. **Add `heartbeat.intervalMs` override to Helm values for `labs`** (depends on 1) — Open a gitops PR adding `openclaw.config.heartbeat.intervalMs: 30000` to the `labs` Helm values. This is a hot-config reload; no pod restart needed. — DoD: PR reviewed and approved; ArgoCD applies the config; no pod restart triggered.

- [ ] 3. **Verify canary noise reduction in `labs` over 1-hour window** (depends on 2) — Monitor the `labs` s3-sync canary for 1 hour after the config change. Count spurious alert firings before and after. — DoD: Zero spurious canary alerts in the 1-hour post-change window; genuine S3-sync writes confirmed by checking the S3 bucket timestamp directly.

- [ ] 4. **Roll out `heartbeat.intervalMs` override to `admins` and `ovk`** (depends on 3) — Open gitops PRs for `admins` and `ovk` with the same config change. Apply sequentially per ADR-0001 promotion order. — DoD: Both tenants have the config applied; canary and Telegram channel connectivity confirmed healthy for each.

- [ ] 5. **Add startup warning log for the override** (depends on 4) — In the YAML skills layer (Layer 2, hot-reload), add a skill or hook that checks at startup whether `heartbeat.intervalMs` is set to a non-default value and logs a `WARN`-level structured message: `{ "event": "workaround-active", "workaround": "heartbeat-interval-override", "value": <configured-ms> }`. — DoD: Log entry appears on next config reload for all three tenants; visible in the tenant's log stream.

- [ ] 6. **Open tracking issue to remove the workaround when upstream #73836 is fixed** — File an internal ticket (or GitHub issue in mctl-gitops) titled "Remove heartbeat.intervalMs workaround after upstream #73836 fix". Link to the upstream issue and this proposal. Assign to the on-call rotation. — DoD: Tracking issue created and linked from the gitops PR; the daily researcher cycle will detect the upstream release that includes the fix.

- [ ] 7. **FUTURE: Remove workaround when upstream fix lands** (triggered by researcher detecting the fix in a future release) — Remove the `heartbeat.intervalMs` override from all three Helm values files in the same PR that bumps the openclaw image tag containing the fix. Confirm the startup warning log no longer appears. — DoD: Override absent from all values files; no startup warning in any tenant log; canary and Telegram typing confirmed clean.

## Tests

- [ ] T1. After task 2: run `kubectl exec -n labs <pod> -- curl -s localhost:<port>/config | jq .heartbeat.intervalMs` and confirm it returns `30000`.
- [ ] T2. After task 3: confirm s3-sync canary reports no alerts for 1 hour; check S3 bucket directly for fresh timestamps every 5 minutes during the window.
- [ ] T3. After task 4: same canary check for `admins` and `ovk`; additionally, send a Telegram message in `ovk` and confirm no user-visible typing indicator gap.
- [ ] T4. After task 5: trigger a config reload and verify the `workaround-active` log entry appears in the log stream for each tenant.
- [ ] T5. (Regression test) Simulate a real S3-sync failure by temporarily blocking S3 writes in `labs` (test environment only) and confirm the canary still fires within its configured threshold — the workaround must not blind the canary.

## Rollback

If the `heartbeat.intervalMs` override causes unexpected behavior (e.g., the lower poll rate masks real connectivity loss):

1. Revert the Helm values change in a gitops PR; ArgoCD applies without a pod restart.
2. Restore the regression-elevated value as a temporary intermediate until upstream #73836 is fixed.
3. Increase the canary cycle miss threshold by one cycle as a last resort (requires explicit security review, per ADR-0002).
