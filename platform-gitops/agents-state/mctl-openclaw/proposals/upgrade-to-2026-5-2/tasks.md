# Tasks: upgrade-to-2026-5-2

- [ ] 1. Mark superseded proposals as inactive — DoD: Files `proposals/upgrade-to-2026-4-8/.status.yaml`, `proposals/upgrade-to-2026-4-25/.status.yaml`, `proposals/upgrade-to-2026-4-26/.status.yaml`, `proposals/upgrade-to-2026-4-27/.status.yaml`, and `proposals/upgrade-to-2026-4-29/.status.yaml` each exist and contain `status: superseded` and `superseded-by: upgrade-to-2026-5-2`. (Note: `upgrade-to-2026-4-27/.status.yaml` already exists; verify and update its content if it does not match this proposal.)

- [ ] 2. Pre-upgrade memory baseline for `labs` — DoD: Pod RSS and heap metrics for the `labs` tenant running 2026.3.14 are recorded and committed to the runbook or an ops note before any image tag change is made. Baseline captured at steady state (not during a rollout).

- [ ] 3. Pre-upgrade audit of `device.token.rotate` consumers — DoD: All internal scripts, CI jobs, and tooling in the mctlhq repo that parse the response body of `device.token.rotate` are identified and listed. Any that read the bearer token value from the response are marked for update before the `ovk` rollout step. (This audit is a gate for task 14.)

- [ ] 4. Pre-upgrade audit of log-based monitoring rules — DoD: All monitoring or alerting rules that pattern-match on credential strings (passwords, tokens, Authorization header values) in openclaw log output are identified. Any that would silently break or false-fire after CWE-532 redaction is applied are flagged and updated before the `labs` rollout begins.

- [ ] 5. Confirm `git:` plugin install is disabled in all tenant configurations — DoD: All three tenant `values.yaml` files (or equivalent overlay configs) in mctl-gitops are inspected and confirmed to have `git:` plugin install capability disabled or absent. Confirmation logged in the ops runbook before any gitops PR is opened.

- [ ] 6. Open gitops PR: bump `labs` image tag to `2026.5.2` — DoD: PR exists in mctl-gitops targeting only the `labs` tenant `values.yaml`, changing `image.tag` from `2026.3.14` to `2026.5.2`. PR description references this proposal slug. PR is reviewed and approved but NOT merged until task 7 is complete.

- [ ] 7. Stop `labs` s3-sync canary — DoD: The Argo CronWorkflow for the `labs` s3-sync canary is suspended (`.spec.suspend: true`). Confirmation logged in the ops runbook with timestamp.

- [ ] 8. Merge `labs` gitops PR and confirm ArgoCD rollout — DoD: The `labs` gitops PR is merged. ArgoCD reports the `labs` openclaw deployment as `Healthy` and `Synced`. The restore-state readiness probe has passed (pod is in `Running` state with all containers ready). (Depends on 6, 7.)

- [ ] 9. Restart `labs` s3-sync canary with post-rollout delay — DoD: The Argo CronWorkflow for `labs` is resumed after the delay specified in ADR-0002. First successful canary run is observed and logged. (Depends on 8.)

- [ ] 10. `labs` 24-hour soak — DoD: For 24 hours following task 9, all of the following hold: no s3-sync canary failures; no restore-state probe failures; no channel connectivity errors above pre-upgrade baseline; pod RSS delta is within 50 MB of the baseline recorded in task 2; log output is confirmed to contain no plain-text `?password=`, `?token=`, or `Authorization:` header values. Results logged in the ops runbook. (Depends on 9.)

- [ ] 11. Open gitops PR: bump `admins` image tag to `2026.5.2` — DoD: PR exists in mctl-gitops targeting only the `admins` tenant `values.yaml`. Reviewed and approved but NOT merged until task 12 is complete. (Depends on 10.)

- [ ] 12. Stop `admins` s3-sync canary — DoD: The Argo CronWorkflow for the `admins` s3-sync canary is suspended. Confirmation logged with timestamp. (Depends on 10.)

- [ ] 13. Merge `admins` gitops PR and confirm ArgoCD rollout — DoD: ArgoCD reports the `admins` deployment as `Healthy` and `Synced`. Restore-state probe has passed. (Depends on 11, 12.)

- [ ] 14. Restart `admins` s3-sync canary with post-rollout delay — DoD: Argo CronWorkflow for `admins` resumed; first successful canary run observed and logged. (Depends on 13.)

- [ ] 15. `admins` 24-hour soak — DoD: Same criteria as task 10, applied to `admins`. No failures or regressions over 24 hours. (Depends on 14.)

- [ ] 16. Update `device.token.rotate` consumers if required (gate for `ovk`) — DoD: Any tooling identified in task 3 that parses the bearer-token response has been updated and tested. If no tooling was affected, this task is closed with a note confirming the audit result. (Depends on 3, 15.)

- [ ] 17. Schedule `ovk` rollout in low-traffic maintenance window — DoD: The rollout start time is agreed upon with the `ovk` customer and recorded in the ops runbook. The maintenance window is pre-approved. (Depends on 15.)

- [ ] 18. Open gitops PR: bump `ovk` image tag to `2026.5.2` — DoD: PR exists targeting only the `ovk` tenant `values.yaml`. Reviewed and approved. (Depends on 16, 17.)

- [ ] 19. Stop `ovk` s3-sync canary — DoD: Argo CronWorkflow for `ovk` suspended. Timestamp logged. (Depends on 17.)

- [ ] 20. Merge `ovk` gitops PR and confirm ArgoCD rollout — DoD: ArgoCD reports `ovk` as `Healthy` and `Synced`. Restore-state probe passed. All active `ovk` channels confirmed connected. (Depends on 18, 19.)

- [ ] 21. Restart `ovk` s3-sync canary with post-rollout delay — DoD: Argo CronWorkflow for `ovk` resumed; first successful canary run observed and logged. (Depends on 20.)

- [ ] 22. Post-upgrade validation and closure — DoD: `context/current-version.md` is updated to reflect `2026.5.2` on all three tenants. An ADR entry is added to `context/decisions/` noting the upgrade rationale and CVE/CWE closure. All ten CVEs and the CWE-532 defect are confirmed resolved with no open critical or high CVEs in the 2026.3.14 → 2026.5.2 range. This proposal is marked `status: completed`. (Depends on 21.)

## Tests

- [ ] T1. Restore-state probe smoke test on `labs`: after the `labs` rollout (task 8), delete and reschedule the `labs` pod once to verify S3 restore completes within the configured probe timeout. Confirm pod reaches `Ready` without manual intervention.
- [ ] T2. Memory regression check on `labs`: at 1 hour, 6 hours, and 24 hours after the `labs` rollout, record pod RSS. Confirm no single measurement exceeds the baseline (task 2) by more than 50 MB. Record the actual delta; if the delta is negative, document the measured footprint reduction.
- [ ] T3. S3-sync canary health on `labs`: confirm at least three consecutive successful canary cycles after the post-rollout restart (task 9). No false alerts or missed cycles.
- [ ] T4. CWE-532 log redaction on `labs`: after the `labs` rollout, issue a request that would previously have included a `?password=` or `?token=` query parameter or an `Authorization:` header, and confirm that the log output contains the redacted marker and not the credential value.
- [ ] T5. Channel connectivity check on `labs` and `admins`: send a test message through at least the following channels on each soak tenant — WhatsApp, Telegram, Slack, Discord — and confirm delivery within normal latency bounds.
- [ ] T6. CVE surface verification: after the `ovk` rollout (task 20), run the mctl dependency scanner against the `2026.5.2` image and confirm all ten CVEs (CVE-2026-42422, CVE-2026-42426, CVE-2026-42428, CVE-2026-42429, CVE-2026-42423, CVE-2026-41912, CVE-2026-41914, CVE-2026-41394, CVE-2026-41395, CVE-2026-41390) are no longer reported.
- [ ] T7. `device.token.rotate` response format: call `device.token.rotate` on `labs` after upgrade and verify the response format matches expectations; confirm any updated tooling (task 16) behaves correctly.
- [ ] T8. `git:` plugin install disabled: after the upgrade on each tenant, confirm via the openclaw admin API or config inspection that `git:` plugin installs remain disabled on all three tenants.
- [ ] T9. Startup latency on `labs`: measure the time from pod scheduling to the restore-state probe passing before and after the upgrade. Confirm the post-upgrade time is not greater than the pre-upgrade time (the secrets-preflight skip in v2026.5.2 should maintain or improve latency).

## Rollback

If any tenant rollout fails (restore-state probe does not pass within timeout, memory regression exceeding 50 MB, critical channel outage, or log redaction test fails indicating a defective build), revert as follows:

1. **Stop the s3-sync canary** for the affected tenant immediately (if not already suspended).
2. Open a gitops PR reverting `image.tag` to `2026.3.14` for the affected tenant only. Merge and allow ArgoCD to sync.
3. Monitor the restore-state readiness probe on the reverted pod. No S3 schema changes occurred during the upgrade, so session restore should succeed without S3 manipulation.
4. Restart the s3-sync canary with the post-rollout delay (ADR-0002).
5. Log the incident and capture diagnostics (probe logs, memory metrics, canary logs, any sample log output) before rolling back, to preserve evidence for root-cause analysis.
6. Do NOT roll back multiple tenants simultaneously — revert one tenant at a time in reverse promotion order (`ovk` first if both `admins` and `ovk` are affected, then `admins`, then `labs`).
7. Hold all further promotion steps until the root cause is identified and a fix or mitigation is confirmed upstream or in a patched fork build.

Note: Because no S3 schema migrations occur in this upgrade, rollback to 2026.3.14 does not require any S3 state manipulation. Log redaction will cease on rollback; this is expected and acceptable. Inform the security team if rollback occurs so that the pre-upgrade log exposure window is documented.
