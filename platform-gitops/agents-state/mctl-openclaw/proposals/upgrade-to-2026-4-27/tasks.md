# Tasks: upgrade-to-2026-4-27

- [ ] 1. **Pre-upgrade audit: internal tooling for `device.token.rotate` response parsing** — Review all internal scripts, CI jobs, and extension code that call `device.token.rotate` and parse the response body. Patch any that read the rotated token directly from the response (the bearer-token echo is removed in 2026.4.26). — DoD: No code in the workspace reads the echoed token from a `device.token.rotate` response; reviewed by a second engineer.

- [ ] 2. **Pre-upgrade memory baseline: `labs` tenant** — Record current memory usage (RSS, heap) for the `labs` openclaw pod over a 1-hour window before the upgrade. Store the baseline in a PR comment for later comparison. — DoD: Baseline numbers documented and linked from the upgrade PR.

- [ ] 3. **gitops PR: bump `labs` image tag to `2026.4.27`** (depends on 1, 2) — Open a PR in mctl-gitops targeting only the `labs` Helm values file. Set `image.tag: 2026.4.27`. Include the pre-upgrade memory baseline in the PR description. — DoD: PR reviewed and approved; CI passes; ArgoCD sync plan shows only the image tag diff.

- [ ] 4. **`labs` rollout: stop canary → apply → verify probe → restart canary** (depends on 3) — (a) Stop the `labs` s3-sync canary CronWorkflow. (b) Merge the gitops PR and let ArgoCD sync. (c) Wait for the `restore-state` readiness probe to pass and ArgoCD to mark the rollout successful. (d) Restart the canary with the configured post-rollout delay. — DoD: `labs` pod running 2026.4.27; readiness probe green; canary restarted; no false alerts in the first 30 minutes post-restart.

- [ ] 5. **`labs` soak: 24-hour observation** (depends on 4) — Monitor: (a) s3-sync canary — no alerts. (b) Memory delta vs baseline (flag if > 50 MB). (c) Telegram and Slack channel connectivity. (d) OpenTelemetry spans visible in tracing backend. — DoD: 24 h elapsed, no incidents, memory delta documented, channel connectivity confirmed.

- [ ] 6. **gitops PR: bump `admins` image tag to `2026.4.27`** (depends on 5, memory delta acceptable) — Same as task 3 but for the `admins` values file. — DoD: PR approved; CI passes.

- [ ] 7. **`admins` rollout: stop canary → apply → verify probe → restart canary** (depends on 6) — Same four-step procedure as task 4, for the `admins` tenant. — DoD: `admins` pod running 2026.4.27; readiness probe green; canary restarted.

- [ ] 8. **`admins` soak: 24-hour observation** (depends on 7) — Same checks as task 5 for `admins`. — DoD: 24 h elapsed, no incidents.

- [ ] 9. **gitops PR: bump `ovk` image tag to `2026.4.27`** (depends on 8) — Same as task 3 but for the `ovk` values file. — DoD: PR reviewed, approved by on-call engineer; CI passes; ovk-specific channel connectivity pre-check documented.

- [ ] 10. **`ovk` rollout: stop canary → apply → verify probe → restart canary** (depends on 9) — Same four-step procedure as task 4, for the `ovk` tenant. Monitor the `restore-state` probe especially carefully: WhatsApp Web and iMessage sessions may take longer to restore. — DoD: `ovk` pod running 2026.4.27; readiness probe green; canary restarted; production channel connectivity confirmed.

- [ ] 11. **Update `context/current-version.md`** (depends on 10) — Set all three per-tenant versions to 2026.4.27; update "Last update" date. — DoD: File updated, PR merged to main.

- [ ] 12. **Add ADR for this upgrade** (depends on 11) — Create `context/decisions/0003-upgrade-to-2026-4-27.md` documenting the CVE context and why 2026.4.27 was chosen as the target. — DoD: ADR merged; links to CVE references included.

## Tests

- [ ] T1. After each tenant rollout, run `curl -s <gateway>/health | jq .version` and confirm it returns `2026.4.27`.
- [ ] T2. After `labs` rollout, confirm memory RSS does not exceed baseline + 50 MB (checked via `kubectl top pod`).
- [ ] T3. After each tenant rollout, trigger a manual s3-sync canary check and confirm it reports a fresh timestamp.
- [ ] T4. After `ovk` rollout, send a test message on each active channel (Telegram, Slack, WhatsApp) and confirm delivery.
- [ ] T5. Call `device.token.rotate` on a test token and confirm the response body does NOT echo the new token value (2026.4.26 fix).
- [ ] T6. Confirm OpenTelemetry spans appear in the tracing backend for at least one model call per tenant after upgrade.

## Rollback

If any tenant rollout fails (readiness probe timeout, critical regression, or memory overage):

1. Stop the s3-sync canary for the affected tenant.
2. Revert the image tag to `2026.3.14` in the gitops values file and merge immediately.
3. Let ArgoCD sync back to 2026.3.14; wait for the readiness probe to pass (S3 state is forward-compatible — sessions written by 2026.4.27 are readable by 2026.3.14 within the same S3 schema).
4. Restart the s3-sync canary with the post-rollout delay.
5. Open an incident report documenting the failure before re-attempting the upgrade.

> ⚠️ `ovk` rollback note: If production channels lost auth during a failed ovk upgrade, perform an emergency auth restore from the pre-upgrade S3 snapshot before restarting the canary.
