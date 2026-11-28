# Tasks: govulncheck-ci-gate

- [ ] 1. Add CI job with pinned govulncheck — DoD: runs on PRs.
- [ ] 2. Add waiver file and wrapper (depends on 1) — DoD: expired waivers fail.
- [ ] 3. Add nightly schedule and notification (depends on 1) — DoD: nightly run visible.

## Tests
- [ ] T1. Seed a known-vulnerable dependency on a branch; job fails.
- [ ] T2. Waiver with past expiry fails.

## Rollback
Remove the CI job; no runtime effect.
