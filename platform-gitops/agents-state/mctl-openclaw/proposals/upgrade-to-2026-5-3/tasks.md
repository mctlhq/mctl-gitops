# Tasks: upgrade-to-2026-5-3

## Pre-rollout

- [ ] 1. Verify v2026.5.3 upstream release — DoD: Confirm the `2026.5.3` Docker image is published on the openclaw upstream registry; confirm upstream release notes list resolution of the v2026.5.2 gateway-crash and Feishu regressions; confirm all six target CVEs are listed as fixed.
- [ ] 2. Audit internal tooling for `device.token.rotate` response format (depends on 1) — DoD: All scripts or services that consume the `device.token.rotate` API response have been inspected; any that parse the bearer-token field have been updated to match the corrected format introduced in the 2026.4.x series; findings are documented.
- [ ] 3. Audit log-based monitoring rules (depends on 1) — DoD: Any alerting or monitoring rule that pattern-matches on credential strings in logs has been identified and updated to account for the credential-redaction behaviour present since v2026.5.2; no monitoring rule is expected to silently break post-upgrade.
- [ ] 4. Confirm `git:` plugin install is disabled in all tenant configurations (depends on 1) — DoD: All three tenants' Helm values and extension configs explicitly disable or omit the `git:` plugin install feature; no tenant has the feature inadvertently enabled.

## labs rollout

- [ ] 5. Stop s3-sync canary for `labs` (depends on 1) — DoD: The Argo CronWorkflow for the `labs` s3-sync canary has `.spec.suspend: true` applied; no further canary cycles execute until step 8.
- [ ] 6. Open and merge gitops PR for `labs` (depends on 5) — DoD: The `labs` tenant `values.yaml` `image.tag` is set to `2026.5.3`; the PR is reviewed and merged; ArgoCD begins sync.
- [ ] 7. Confirm `labs` restore-state probe passes (depends on 6) — DoD: ArgoCD marks the `labs` rollout as `Healthy`/`Synced`; the `restore-state` readiness probe has passed within the configured timeout; pod RSS memory baseline is recorded.
- [ ] 8. Restart s3-sync canary for `labs` with post-rollout delay (depends on 7) — DoD: The `labs` s3-sync canary CronWorkflow has `.spec.suspend: false` applied after the delay specified in ADR-0002; the first canary cycle completes successfully.
- [ ] 9. `labs` 24-hour soak (depends on 8) — DoD: All of the following are true at the end of 24 hours: (a) s3-sync canary has had zero consecutive failures exceeding two cycles; (b) pod RSS memory has not increased more than 50 MB above the pre-upgrade baseline recorded in step 7; (c) all active channels respond without errors (connectivity check run at 1 h, 6 h, 24 h); (d) gateway uptime has passed the 12-hour mark without a crash; (e) Feishu channel authentication produces no errors; (f) no restore-state probe failures have been observed.

## admins rollout

- [ ] 10. Stop s3-sync canary for `admins` (depends on 9) — DoD: The Argo CronWorkflow for the `admins` s3-sync canary has `.spec.suspend: true` applied.
- [ ] 11. Open and merge gitops PR for `admins` (depends on 10) — DoD: The `admins` tenant `values.yaml` `image.tag` is set to `2026.5.3`; the PR is reviewed and merged; ArgoCD begins sync.
- [ ] 12. Confirm `admins` restore-state probe passes (depends on 11) — DoD: ArgoCD marks the `admins` rollout as `Healthy`/`Synced`; the `restore-state` readiness probe has passed; pod RSS baseline is recorded.
- [ ] 13. Restart s3-sync canary for `admins` with post-rollout delay (depends on 12) — DoD: The `admins` s3-sync canary CronWorkflow has `.spec.suspend: false` applied after the ADR-0002 delay; first canary cycle completes successfully.
- [ ] 14. Complete `device.token.rotate` tooling audit gate (depends on 2, 13) — DoD: All findings from task 2 are resolved and verified against the running `admins` instance; the rotated-token API response is parsed correctly by all consumers.
- [ ] 15. `admins` 24-hour soak (depends on 13, 14) — DoD: Same criteria as step 9, applied to `admins`; additionally, `device.token.rotate` tooling has been verified functional on the live `admins` instance.

## ovk rollout

- [ ] 16. Schedule `ovk` rollout in pre-approved maintenance window (depends on 15) — DoD: A maintenance window has been communicated to relevant stakeholders; the rollout is confirmed for a low-traffic period.
- [ ] 17. Stop s3-sync canary for `ovk` (depends on 16) — DoD: The Argo CronWorkflow for the `ovk` s3-sync canary has `.spec.suspend: true` applied.
- [ ] 18. Open and merge gitops PR for `ovk` (depends on 17) — DoD: The `ovk` tenant `values.yaml` `image.tag` is set to `2026.5.3`; the PR is reviewed and merged; ArgoCD begins sync.
- [ ] 19. Confirm `ovk` restore-state probe passes (depends on 18) — DoD: ArgoCD marks the `ovk` rollout as `Healthy`/`Synced`; the `restore-state` readiness probe has passed; pod RSS baseline is recorded.
- [ ] 20. Restart s3-sync canary for `ovk` with post-rollout delay (depends on 19) — DoD: The `ovk` s3-sync canary CronWorkflow has `.spec.suspend: false` applied after the ADR-0002 delay; first canary cycle completes successfully.
- [ ] 21. `ovk` post-rollout verification (depends on 20) — DoD: All active channels respond without errors; gateway uptime passes the 12-hour mark without a crash; Feishu authentication produces no errors; s3-sync canary has had no consecutive failures; pod RSS is within 50 MB of pre-upgrade baseline; no restore-state probe failures observed for 24 hours.

## Post-rollout

- [ ] 22. Update `context/current-version.md` to reflect v2026.5.3 on all tenants (depends on 21) — DoD: `context/current-version.md` records `2026.5.3` as the active version for `labs`, `admins`, and `ovk`; the document is committed to the repository. Note: `context/` is read-only for the spec-writer; this task must be executed by the operator.
- [ ] 23. Mark prior upgrade proposals as superseded (depends on 21) — DoD: `proposals/upgrade-to-2026-5-2/` is annotated as superseded by this proposal.

## Tests

- [ ] T1. Restore-state probe regression test — For each tenant immediately after rollout: confirm the pod reaches `Ready` state within the configured readiness probe timeout. Fail criteria: timeout exceeded or probe never passes.
- [ ] T2. S3 write health test — For each tenant, after the s3-sync canary is restarted: confirm the first two canary cycles complete without failure. Fail criteria: one or more canary cycles fail.
- [ ] T3. CVE-2026-41394 regression test — Against the `labs` instance, send an unauthenticated request to a plugin-auth HTTP route that previously granted operator write scope; confirm the response is an authentication error (4xx). Fail criteria: route returns 2xx or operator-scope response.
- [ ] T4. CVE-2026-42422 regression test — Against the `labs` instance, attempt `device.token.rotate` with a request that previously exploited the role bypass; confirm the operation is rejected. Fail criteria: operation succeeds without proper role.
- [ ] T5. CVE-2026-33579 regression test — Against the `labs` instance, submit a device-pairing request containing a path-traversal sequence; confirm the request is rejected. Fail criteria: traversal is not rejected.
- [ ] T6. CVE-2026-41390 regression test — Against the `labs` instance, attempt an exec command using a shell-script wrapper that was previously on the bypass list; confirm the command is blocked. Fail criteria: command executes.
- [ ] T7. Feishu channel regression test — During `labs` and `admins` soaks: confirm Feishu channel authentication completes without errors. Fail criteria: Feishu auth errors observed.
- [ ] T8. 12-hour uptime test — For each tenant: monitor gateway process for a full 12 hours post-rollout; confirm no crash or unexpected restart. Fail criteria: gateway crashes at or around the 12-hour mark.
- [ ] T9. Memory baseline test for `labs` — Record pod RSS at 1 h, 6 h, and 24 h post-upgrade; confirm each measurement is within 50 MB of the pre-upgrade baseline. Fail criteria: delta exceeds 50 MB at any measurement point.
- [ ] T10. Channel connectivity test — Run a full channel connectivity check (all active channels) at the end of the `labs` soak and the `admins` soak; confirm no error-rate increase. Fail criteria: error rate increase observed on any channel.

## Rollback

If any step in the rollout fails (restore-state probe does not pass, s3-sync canary fails, gateway crash, memory overage, CVE regression test fails):

1. **Immediately revert the image tag** in the affected tenant's `values.yaml` to `2026.3.14` via a gitops PR; merge and allow ArgoCD to sync.
2. **Stop the s3-sync canary** for the affected tenant before the revert pod starts (same ADR-0002 procedure).
3. **Wait for the `restore-state` probe** to pass on the reverted pod. Do not advance to the next step manually.
4. **Restart the s3-sync canary** with the post-rollout delay.
5. **Open an incident** documenting the failure mode, the step at which it was detected, and the tenant affected.
6. **Do not promote** to the next tenant (`admins` or `ovk`) until the incident is resolved and a root cause is identified. If the `labs` rollback succeeds, `admins` and `ovk` remain on v2026.3.14 and are unaffected.

Since v2026.5.3 introduces no S3 schema changes, reverting the image tag is sufficient to restore the prior state. No S3 data migration or manual session reconstruction is required for rollback.
