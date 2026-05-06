# Tasks: upgrade-to-2026-5-4

## Staging and pre-flight

- [ ] 1. Review upstream changelog from 2026.3.14 to 2026.5.4 — DoD: a written
  summary (comment in the gitops PR or a shared doc) confirms whether any
  breaking changes exist in config keys, environment variables, or plugin SDK
  interfaces; any breaking changes are listed with their required gitops
  remediation.

- [ ] 2. Verify plugin SDK compatibility for all extensions in `extensions/*`
  against openclaw 2026.5.4 (depends on 1) — DoD: each extension that imports
  `openclaw/plugin-sdk/*` has been checked against the 2026.5.4 SDK changelog;
  any required changes are committed to the gitops repository before the `labs`
  PR is merged.

- [ ] 3. Open gitops PR for `labs`: set `image.tag` to `2026.5.4` in the `labs`
  Helm release values (depends on 1, 2) — DoD: PR is open, reviewed by at
  least one operator, and includes any config-key or extension changes
  identified in tasks 1–2.

## labs rollout

- [ ] 4. Stop the `s3-sync-canary-labs` Argo CronWorkflow (depends on 3) —
  DoD: CronWorkflow is suspended; suspension is confirmed via `kubectl get
  cronworkflow` or mctl; a status note is posted to the on-call channel so
  engineers are aware the canary is suspended.

- [ ] 5. Merge the `labs` gitops PR and wait for ArgoCD to mark the rollout
  `Healthy` (depends on 4) — DoD: ArgoCD reports `Healthy` for the `labs`
  openclaw application; the restore-state readiness probe has passed; the pod
  is running image tag `2026.5.4`.

- [ ] 6. Measure peak memory in `labs` over a minimum 30-minute observation
  window after the pod is ready (depends on 5) — DoD: peak RSS is recorded
  (via `kubectl top pod` or mctl metrics); the value is documented in the PR or
  tracking issue; the value is confirmed to be below the `labs` memory limit.
  **RISKY: if peak RSS meets or exceeds the memory limit, halt and raise a
  blocking issue — do not proceed to task 7.**

- [ ] 7. Restart `s3-sync-canary-labs` after at least one full canary cycle
  has elapsed since pod readiness (depends on 5, 6) — DoD: CronWorkflow is
  resumed; at least one successful canary cycle is observed; no false alerts
  are firing for `labs`.

## admins rollout

- [ ] 8. Open gitops PR for `admins`: set `image.tag` to `2026.5.4` in the
  `admins` Helm release values (depends on 7) — DoD: PR is open and reviewed.

- [ ] 9. Stop `s3-sync-canary-admins` (depends on 8) — DoD: CronWorkflow is
  suspended; suspension confirmed; on-call channel notified.

- [ ] 10. Merge the `admins` gitops PR and wait for ArgoCD `Healthy` (depends
  on 9) — DoD: ArgoCD reports `Healthy` for `admins`; restore-state probe
  passed; pod running `2026.5.4`.

- [ ] 11. Restart `s3-sync-canary-admins` after at least one full canary cycle
  (depends on 10) — DoD: CronWorkflow resumed; at least one successful cycle
  observed; no false alerts.

## ovk rollout

- [ ] 12. Open gitops PR for `ovk`: set `image.tag` to `2026.5.4` in the `ovk`
  Helm release values (depends on 11) — DoD: PR is open and reviewed; the
  on-call SRE for `ovk` has been notified of the upcoming maintenance window.

- [ ] 13. Stop `s3-sync-canary-ovk` (depends on 12) — DoD: CronWorkflow is
  suspended; suspension confirmed; on-call channel notified.

- [ ] 14. Merge the `ovk` gitops PR and wait for ArgoCD `Healthy` (depends on
  13) — DoD: ArgoCD reports `Healthy` for `ovk`; restore-state probe passed;
  pod running `2026.5.4`; no customer-visible disruption to channel
  connectivity.

- [ ] 15. Restart `s3-sync-canary-ovk` after at least one full canary cycle
  (depends on 14) — DoD: CronWorkflow resumed; at least one successful cycle
  observed; no false alerts.

## Post-rollout

- [ ] 16. Update `context/current-version.md` to reflect version `2026.5.4`
  across all three tenants and set the last-update date to 2026-05-06 (depends
  on 15) — DoD: file updated via a PR; `context/` is read-only for agents but
  updated by the operator following the post-rollout procedure.

- [ ] 17. Add an ADR under `context/decisions/` documenting the upgrade
  decision, CVE rationale, and memory-validation outcome for `labs` (depends
  on 16) — DoD: ADR file committed with status `accepted`, dated 2026-05-06,
  referencing ADR-0001 and ADR-0002, listing the closed CVEs, and noting the
  observed `labs` peak RSS.

## Tests

- [ ] T1. Restore-state probe passes within configured timeout on `labs` —
  confirm via ArgoCD rollout status that the pod reaches `Ready` without manual
  intervention after the 2026.5.4 image is scheduled.

- [ ] T2. s3-sync canary resumes without false alerts on `labs` — after
  restarting `s3-sync-canary-labs`, observe at least two consecutive successful
  cycles (no alert fired) before declaring the canary healthy.

- [ ] T3. Channel connectivity spot-check on `labs` after rollout — send a
  test message on at least one channel (e.g., WhatsApp or Telegram) via `labs`
  and confirm it is received and responded to; verify that the session was
  restored from S3 (not re-authenticated from scratch).

- [ ] T4. Memory regression check on `labs` — verify that peak RSS observed
  during the 30-minute window (task 6) is no higher than the value recorded
  before the upgrade; document both the pre-upgrade and post-upgrade figures.

- [ ] T5. CVE closure verification — confirm that the deployed `labs` image
  reports version `2026.5.4` via the openclaw health/version endpoint or
  `kubectl describe pod`; cross-reference that 2026.5.4 >= 2026.4.14 (the
  highest-numbered fix release for the three CVEs).

- [ ] T6. End-to-end smoke test on `ovk` after rollout — confirm that `ovk`
  channel connectivity is intact and no incidents are open immediately after
  the restore-state probe passes; check mctl incident dashboard for 30 minutes
  post-rollout.

## Rollback

If any rollout step fails (ArgoCD reports `Degraded`, probe does not pass,
memory limit breached, or canary fires repeatedly after restart), execute the
following steps for the affected tenant:

1. **Stop the canary** — suspend `s3-sync-canary-<tenant>` immediately to
   prevent false-alert noise during the rollback.
2. **Revert the gitops tag** — open and merge a revert PR in mctl-gitops that
   restores `image.tag` to `2026.3.14` for the affected tenant only. Do not
   touch other tenants.
3. **Wait for ArgoCD** — wait for ArgoCD to report `Healthy` on the reverted
   deployment and for the restore-state readiness probe to pass.
4. **Restart the canary** — resume `s3-sync-canary-<tenant>` after at least
   one full canary cycle has elapsed since pod readiness.
5. **Post mortem** — document the failure mode before re-attempting the
   upgrade. Do not re-attempt without a root-cause explanation and a mitigation
   plan approved by at least one operator.

Note: because each tenant has an independent gitops PR, rolling back `labs`
does not require rolling back `admins` or `ovk`, and vice versa. Tenants that
have already successfully upgraded remain at 2026.5.4.
