# Tasks: upgrade-to-2026-9-9-plan

- [ ] 1. Confirm deployed version per tenant from gitops — DoD: version table recorded.
- [ ] 2. Read full 2026.9.9 changelog and list config impacts (depends on 1) — DoD: checklist covers breaking changes.
- [ ] 3. Take S3 snapshots per tenant (depends on 1; see rollback-guard) — DoD: snapshot IDs recorded.
- [ ] 4. Upgrade `labs` (via 2026.9.5 + `doctor --fix` if needed) (depends on 2, 3) — DoD: probe passes, memory below baseline, canary green.
- [ ] 5. Observe `labs` for the agreed period — DoD: no incidents.
- [ ] 6. Upgrade `admins`, then `ovk` (depends on 5) — DoD: probe passes, channels connected.
- [ ] 7. Update version records and write ADR (depends on 6) — DoD: merged.

## Tests
- [ ] T1. Telegram `/controlui` opens the Mini App on `labs`.
- [ ] T2. Scheduled jobs run after upgrade.
- [ ] T3. Pod restart restores sessions from S3.

## Rollback
Pre-DB-migration only: restore image tag and S3 snapshot. After migration, downgrade is unsupported: restore the snapshot into the old version.
