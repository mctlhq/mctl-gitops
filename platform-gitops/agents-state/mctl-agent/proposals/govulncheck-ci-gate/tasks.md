# Tasks: govulncheck-ci-gate

- [ ] 1. Add PR workflow running pinned govulncheck — DoD: check appears and fails on a seeded vulnerable dep in a test branch.
- [ ] 2. Add weekly scheduled workflow (depends on 1) — DoD: manual dispatch run creates an issue on findings.
- [ ] 3. Add exclusion list with expiry convention (depends on 1) — DoD: documented and honoured.
- [ ] 4. Triage current findings (depends on 1) — DoD: each fixed or excluded.

## Tests
- [ ] T1. Seeded vulnerable dependency fails the gate.
- [ ] T2. Clean main passes.

## Rollback
Remove the workflow files or mark the check non-required.
