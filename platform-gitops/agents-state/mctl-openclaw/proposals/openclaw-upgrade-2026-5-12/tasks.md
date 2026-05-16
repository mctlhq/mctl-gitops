# Tasks: openclaw-upgrade-2026-5-12

- [ ] 1. **Confirm v2026.5.12 fixes all four Claw Chain CVEs** — Read the upstream release notes
  and changelog for v2026.5.12 and cross-reference each CVE (CVE-2026-44112, -44113, -44115,
  -44118) against the commit list. Record confirmation in a comment on this task.
  DoD: Each CVE explicitly referenced in the upstream changelog or security advisory as fixed
  in ≤ 2026.5.12.

- [ ] 2. **Check `labs` channel configuration for provider externalisation impact** (depends on 1)
  — Verify which of WhatsApp/Baileys, Slack, Bedrock, Anthropic Vertex are enabled in the
  `labs` tenant. Document the expected memory delta.
  DoD: Written confirmation that disabled channels will not load the externalised packages at
  pod startup.

- [ ] 3. **Update the openclaw version pin in `mctl-gitops`** (depends on 1) — Change
  `OPENCLAW_VERSION` (or equivalent `image.tag` in Helm values) from `2026.3.14` to
  `2026.5.12` in the shared Dockerfile / Helm chart. Open a PR to `mctl-gitops`.
  DoD: PR open, CI passes, diff shows only the version string changed.

- [ ] 4. **Pre-rollout: record `labs` baseline memory** (depends on 3) — Run
  `kubectl top pod -n labs` and record the current RSS for the openclaw pod.
  DoD: Baseline RSS value recorded in the PR or a linked note.

- [ ] 5. **Pre-rollout: pause `labs` s3-sync CronWorkflow** (depends on 3) — Follow the
  ADR-0002 runbook to suspend the Argo CronWorkflow for the `labs` tenant.
  DoD: CronWorkflow status shows `Suspended: true`.

- [ ] 6. **Deploy to `labs`** (depends on 4, 5) — Trigger ArgoCD sync for the `labs` tenant.
  Monitor the restore-state readiness probe until it passes.
  DoD: All `labs` openclaw pods Running + Ready; ArgoCD shows `Synced / Healthy`.

- [ ] 7. **Post-rollout `labs`: resume s3-sync canary and measure memory** (depends on 6) —
  Resume the Argo CronWorkflow with the configured post-rollout delay. Capture
  `kubectl top pod -n labs` at 5 min and 15 min after pod ready. Confirm memory ≤ 90 % of limit.
  DoD: RSS at 15 min recorded; value < 90 % of `labs` memory limit; canary shows first
  successful cycle.

- [ ] 8. **Run OpenShell CVE smoke tests on `labs`** (depends on 6) — Execute the four
  targeted CLI/API checks:
  - (CVE-2026-44112) Attempt a sandbox write to a path outside mount root → must be rejected.
  - (CVE-2026-44113) Attempt a sandbox read from a path outside mount root → must be rejected.
  - (CVE-2026-44115) Submit a here-doc body with `$(evil)` shell expansion → must be blocked.
  - (CVE-2026-44118) Call a gateway config endpoint from an unauthenticated loopback client → must receive 401/403.
  DoD: All four checks return the expected rejection response; results logged.

- [ ] 9. **Observe `labs` for 24 h** (depends on 7, 8) — Monitor error rate, channel
  connectivity, and s3-sync canary success in mctl metrics.
  DoD: Zero s3-sync canary failures; no channel reconnect loops; error rate within baseline.

- [ ] 10. **Deploy to `admins`** (depends on 9) — Repeat steps 5–8 for the `admins` tenant
  (pause canary → sync → probe → resume canary → CVE smoke tests).
  DoD: All `admins` openclaw pods Running + Ready; CVE smoke tests pass.

- [ ] 11. **Observe `admins` for 24 h** (depends on 10) — Same criteria as step 9.
  DoD: No regressions observed in `admins`.

- [ ] 12. **Deploy to `ovk`** (depends on 11) — Repeat steps 5–8 for the `ovk` tenant.
  Verify restore-state probe passes within timeout before marking ArgoCD healthy.
  DoD: All `ovk` pods Running + Ready; CVE smoke tests pass; s3-sync canary active.

- [ ] 13. **Update `context/current-version.md`** (depends on 12) — Change the version to
  `2026.5.12` for all three tenants. Add an ADR entry in `context/decisions/` documenting
  the upgrade decision (required by CLAUDE.md).
  DoD: `current-version.md` reflects 2026.5.12 for all tenants; new ADR file committed.

## Tests

- [ ] T1. **Restore-state probe timing regression** — On `labs`, time the seconds between pod
  start and probe passing. Must be ≤ the configured timeout minus 20 % safety margin.
- [ ] T2. **s3-sync canary first cycle** — After resume, the first CronWorkflow run must
  succeed (S3 timestamp is fresh). Check within 2× the canary interval.
- [ ] T3. **OpenShell CVE smoke tests** — All four checks from task 8 pass on every tenant.
- [ ] T4. **Channel connectivity after upgrade** — On each tenant, send a test message via
  at least one active channel (e.g. WhatsApp on `ovk`) and confirm delivery round-trip.
- [ ] T5. **Memory gate** — `labs` RSS at T+15 min is below 90 % of the configured limit.

## Rollback

If any step fails on a tenant, rollback immediately:

1. **Pause** the s3-sync CronWorkflow for the affected tenant (if not already paused).
2. Revert the Helm values / Dockerfile pin to `2026.3.14` and trigger an ArgoCD sync.
3. Wait for the restore-state probe to pass (the S3 state is compatible with 2026.3.14 —
   the upgrade makes no schema changes).
4. **Resume** the s3-sync CronWorkflow.
5. Page the on-call engineer with the rollback reason and the failing task number.
6. Do **not** proceed to the next tenant until the regression is understood and resolved.

**Do not roll back `ovk` without first rolling back `admins` and `labs`** to maintain
consistent state across the trio.
