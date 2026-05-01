# Tasks: upgrade-to-2026-4-29

- [ ] 1. Mark superseded proposals as inactive — DoD: Files `proposals/upgrade-to-2026-4-8/.status.yaml`, `proposals/upgrade-to-2026-4-25/.status.yaml`, `proposals/upgrade-to-2026-4-26/.status.yaml`, and `proposals/upgrade-to-2026-4-27/.status.yaml` each exist and contain `status: superseded` and `superseded-by: upgrade-to-2026-4-29`. (Note: `upgrade-to-2026-4-27/.status.yaml` already exists; verify and update if its content does not match.)

- [ ] 2. Pre-upgrade memory baseline for `labs` — DoD: Pod RSS and heap metrics for the `labs` tenant running 2026.3.14 are recorded and committed to the runbook or an ops note before any image tag change is made. Baseline captured at steady state (not during a rollout).

- [ ] 3. Pre-upgrade audit of `device.token.rotate` consumers — DoD: All internal scripts, CI jobs, and tooling in the mctlhq repo that parse the response body of `device.token.rotate` are identified and listed. Any that read the bearer token value from the response are marked for update before the `ovk` rollout step. (This gate is required before task 11.)

- [ ] 4. Open gitops PR: bump `labs` image tag to `2026.4.29` — DoD: PR exists in mctl-gitops targeting only the `labs` tenant `values.yaml`, changing `image.tag` from `2026.3.14` to `2026.4.29`. PR description references this proposal slug. PR is reviewed and approved but NOT merged until task 5 is complete.

- [ ] 5. Stop `labs` s3-sync canary — DoD: The Argo CronWorkflow for the `labs` s3-sync canary is suspended (`.spec.suspend: true`). Confirmation logged in the ops runbook with timestamp.

- [ ] 6. Merge `labs` gitops PR and confirm ArgoCD rollout — DoD: The `labs` gitops PR is merged. ArgoCD reports the `labs` openclaw deployment as `Healthy` and `Synced`. The restore-state readiness probe has passed (pod is in `Running` state with all containers ready). (Depends on 4, 5.)

- [ ] 7. Restart `labs` s3-sync canary with post-rollout delay — DoD: The Argo CronWorkflow for `labs` is resumed after the delay specified in ADR-0002. First successful canary run is observed and logged. (Depends on 6.)

- [ ] 8. `labs` 24-hour soak — DoD: For 24 hours following task 7, no s3-sync canary failures, no restore-state probe failures, no channel connectivity errors above baseline, and pod RSS delta is within 50 MB of the baseline recorded in task 2. Results logged in the ops runbook. (Depends on 7.)

- [ ] 9. Open gitops PR: bump `admins` image tag to `2026.4.29` — DoD: PR exists in mctl-gitops targeting only the `admins` tenant `values.yaml`. Reviewed and approved but NOT merged until task 10 is complete. (Depends on 8.)

- [ ] 10. Stop `admins` s3-sync canary — DoD: The Argo CronWorkflow for the `admins` s3-sync canary is suspended. Confirmation logged with timestamp. (Depends on 8.)

- [ ] 11. Merge `admins` gitops PR and confirm ArgoCD rollout — DoD: ArgoCD reports the `admins` deployment as `Healthy` and `Synced`. Restore-state probe has passed. (Depends on 9, 10.)

- [ ] 12. Restart `admins` s3-sync canary with post-rollout delay — DoD: Argo CronWorkflow for `admins` resumed; first successful canary run observed and logged. (Depends on 11.)

- [ ] 13. `admins` 24-hour soak — DoD: Same criteria as task 8, applied to `admins`. No failures or regressions over 24 hours. (Depends on 12.)

- [ ] 14. Update `device.token.rotate` consumers if required (gate for `ovk`) — DoD: Any tooling identified in task 3 that parses the bearer-token response has been updated and tested. If no tooling was affected, this task is closed with a note confirming the audit result. (Depends on 3, 13.)

- [ ] 15. Schedule `ovk` rollout in low-traffic maintenance window — DoD: The rollout start time is agreed upon with the `ovk` customer and recorded. The maintenance window is pre-approved. (Depends on 13.)

- [ ] 16. Open gitops PR: bump `ovk` image tag to `2026.4.29` — DoD: PR exists targeting only the `ovk` tenant `values.yaml`. Reviewed and approved. (Depends on 14, 15.)

- [ ] 17. Stop `ovk` s3-sync canary — DoD: Argo CronWorkflow for `ovk` suspended. Timestamp logged. (Depends on 15.)

- [ ] 18. Merge `ovk` gitops PR and confirm ArgoCD rollout — DoD: ArgoCD reports `ovk` as `Healthy` and `Synced`. Restore-state probe passed. All active `ovk` channels confirmed connected. (Depends on 16, 17.)

- [ ] 19. Restart `ovk` s3-sync canary with post-rollout delay — DoD: Argo CronWorkflow for `ovk` resumed; first successful canary run observed. (Depends on 18.)

- [ ] 20. Post-upgrade validation and closure — DoD: `context/current-version.md` is updated to reflect `2026.4.29` on all three tenants. An ADR entry is added to `context/decisions/` noting the upgrade rationale and CVE closure. All seven CVEs are confirmed resolved with no open critical/high CVEs in the 2026.3.14 → 2026.4.29 range. This proposal is marked `status: completed`. (Depends on 19.)

## Tests

- [ ] T1. Restore-state probe smoke test on `labs`: after the `labs` rollout (task 6), delete and reschedule the `labs` pod once to verify S3 restore completes within the configured probe timeout. Confirm pod reaches `Ready` without manual intervention.
- [ ] T2. Memory regression check on `labs`: at 1 hour, 6 hours, and 24 hours after the `labs` rollout, record pod RSS. Confirm no single measurement exceeds the baseline (task 2) by more than 50 MB.
- [ ] T3. S3-sync canary health on `labs`: confirm at least three consecutive successful canary cycles after the post-rollout restart (task 7). No false alerts or missed cycles.
- [ ] T4. Channel connectivity check on `labs` and `admins`: send a test message through at least the following channels on each soak tenant — WhatsApp, Telegram, Slack, Discord — and confirm delivery within normal latency bounds.
- [ ] T5. CVE surface verification: after the `ovk` rollout (task 18), run the mctl dependency scanner against the `2026.4.29` image and confirm CVE-2026-42422, CVE-2026-42426, CVE-2026-42428, CVE-2026-42429, CVE-2026-42423, CVE-2026-41912, and CVE-2026-41914 are no longer reported.
- [ ] T6. `device.token.rotate` response format: call `device.token.rotate` on `labs` after upgrade and verify the response format matches expectations; confirm any updated tooling (task 14) behaves correctly.
- [ ] T7. SSRF policy enforcement: verify that the SSRF policy bypass (CVE-2026-41912) is no longer reproducible using the upstream PoC or equivalent controlled test on the `labs` tenant.

## Rollback

If any tenant rollout fails (restore-state probe does not pass within timeout, memory regression > 50 MB, or critical channel outage during soak), revert as follows:

1. **Stop the s3-sync canary** for the affected tenant immediately (if not already stopped).
2. Open a gitops PR reverting `image.tag` to `2026.3.14` for the affected tenant only. Merge and allow ArgoCD to sync.
3. Monitor the restore-state readiness probe on the reverted pod. The S3 state has not changed during the failed upgrade attempt, so session restore should succeed.
4. Restart the s3-sync canary with the post-rollout delay (ADR-0002).
5. Log the incident, capture diagnostics (probe logs, memory metrics, canary logs) before rolling back to preserve evidence for root-cause analysis.
6. Do NOT roll back `labs` and `admins` or `admins` and `ovk` simultaneously — revert one tenant at a time in reverse promotion order (`ovk` first if both are affected, then `admins`, then `labs`).
7. Hold all further promotion steps until the root cause is identified and a fix or mitigation is confirmed upstream or locally.

Note: Because no S3 schema migrations occur in this upgrade, rollback to 2026.3.14 does not require any S3 state manipulation. The restored pod will read the existing S3 state without modification.
