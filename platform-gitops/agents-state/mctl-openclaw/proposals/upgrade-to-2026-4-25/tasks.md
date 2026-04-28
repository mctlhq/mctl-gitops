# Tasks: upgrade-to-2026-4-25

- [ ] 1. Read the CHANGELOG 2026.3.14 → 2026.4.25 for breaking changes in the Plugin SDK, S3 state schema, channel configs — DoD: a review-summary document is created (or a "no breaking changes" note), all breaking changes are accounted for in the plan
- [ ] 2. Pre-flight RAM check: run a test pod with the 2026.4.25 image in an isolated environment with the labs resource limits (depends on 1) — DoD: pod RSS and working set after the restore-state probe are recorded; if the delta exceeds 50MB — a ticket is opened to raise the labs limit and subsequent steps are blocked
- [ ] 3. Update the image tag to `2026.4.25` in the labs gitops manifest (depends on 2) — DoD: a PR is opened in mctl-gitops, passes review; ArgoCD applies the change; the restore-state probe passes; the s3-sync canary is resumed with a 60s delay
- [ ] 4. Observe labs for 1 hour after rollout (depends on 3) — DoD: no errors in logs, WhatsApp/Telegram/Discord sessions are active, the s3-sync canary completes at least 2 cycles, RAM does not exceed the limit
- [ ] 5. Update the image tag to `2026.4.25` in the admins gitops manifest (depends on 4) — DoD: ArgoCD applies the change; the restore-state probe passes; the s3-sync canary is resumed; no errors in logs for 30 minutes
- [ ] 6. Update the image tag to `2026.4.25` in the ovk gitops manifest within a maintenance window (depends on 5) — DoD: ArgoCD applies the change; the restore-state probe passes; the s3-sync canary is resumed; the production client confirms the main channels work
- [ ] 7. Close the security findings CVE-2026-41349, CVE-2026-41361, CVE-2026-41359, CVE-2026-41353, CVE-2026-41348 in the tracker (depends on 6) — DoD: all 5 CVEs are marked resolved with version 2026.4.25 and the ovk deploy date

## Tests
- [ ] T1. Smoke test labs: WhatsApp, Telegram, Discord — send and receive a test message through each channel after rollout
- [ ] T2. Smoke test labs: run a test agentic skill with explicit execution approval — confirm the consent bypass (CVE-2026-41349) is not reproducible
- [ ] T3. Smoke test labs: check the SSRF guard with a test request to an IPv6 special-use address (e.g. `::1`) — confirm the request is rejected (CVE-2026-41361)
- [ ] T4. Smoke test labs: verify the Telegram send endpoint does not allow operator-write scope to reach admin-class config (CVE-2026-41359) — verify via API with restricted credentials
- [ ] T5. Restore-state probe: confirm that after a simulated pod restart in labs sessions are restored from S3 within timeout
- [ ] T6. S3-sync canary: confirm the canary resumes and successfully completes an S3 write cycle after each rollout (labs, admins, ovk)
- [ ] T7. Labs RAM monitoring: capture pod memory usage at 5 minutes, 30 minutes, and 1 hour after rollout — values must not exceed the pre-flight baseline + 50MB

## Rollback
On a restore-state probe failure in any tenant ArgoCD automatically rolls the deploy back to the previous version (2026.3.14). If the auto-rollback does not trigger:
1. Manually revert `image.tag` in the gitops manifest back to `2026.3.14` and open a PR
2. After it is applied: confirm the restore-state probe passes, the s3-sync canary resumes
3. Capture the failure cause in the incident log before retrying
4. For ovk: on a manual rollback, notify the client about the brief maintenance
