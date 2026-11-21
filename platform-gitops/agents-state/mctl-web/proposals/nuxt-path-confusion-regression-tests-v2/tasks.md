# Tasks: nuxt-path-confusion-regression-tests-v2

- [ ] 1. Define probe path list and expected results — DoD: table in script.
- [ ] 2. Write the script (depends on 1) — DoD: runs locally and passes on current build.
- [ ] 3. Wire into deploy.yml before deploy (depends on 2) — DoD: failing probe blocks deploy.

## Tests
- [ ] T1. Script fails against a deliberately broken expectation.
- [ ] T2. Script completes in under 60 s.

## Rollback
Revert the PR and redeploy the previous build (Worker: wrangler rollback).
