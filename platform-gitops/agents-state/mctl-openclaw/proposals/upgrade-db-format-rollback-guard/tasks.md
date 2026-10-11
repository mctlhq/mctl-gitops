# Tasks: upgrade-db-format-rollback-guard

- [ ] 1. Write snapshot and verify runbook — DoD: reviewed by owner.
- [ ] 2. Dry-run on `labs` (depends on 1) — DoD: snapshot verified, restore tested into a scratch prefix.
- [ ] 3. Define retention and cleanup protection (depends on 1) — DoD: documented.
- [ ] 4. Wire into the 2026.9.9 plan as a gate (depends on 2) — DoD: plan references the step.

## Tests
- [ ] T1. Corrupted copy is detected by checksum.
- [ ] T2. Restored snapshot passes the restore-state probe.

## Rollback
Delete the snapshot prefix only after the observation period; the guard itself changes no live state.
