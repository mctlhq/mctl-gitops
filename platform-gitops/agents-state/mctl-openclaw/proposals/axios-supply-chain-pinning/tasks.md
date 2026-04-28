# Tasks: axios-supply-chain-pinning

- [ ] 1. Run full dependency-tree audit for Axios across all workspace packages —
  DoD: `npm ls axios --all` (run from the monorepo root and from each workspace
  root) completes without error; output is saved as an artifact (`axios-audit-<date>.txt`).
  Every occurrence of `axios` in the tree is visible and reviewed.

- [ ] 2. Determine whether any path resolves `axios@1.14.1` or `axios@0.30.4`
  (depends on 1) —
  DoD: a clear YES/NO determination is recorded. If YES, the affected workspace
  package(s) and dependency path(s) are listed. If NO, the clean result is logged
  with the audit artifact and the remaining tasks are marked not-required.

- [ ] 3. Add npm `overrides` entry to pin Axios away from backdoored versions
  (depends on 2, only if backdoored versions are found) —
  DoD: the relevant `package.json`(s) contain an `overrides` block that prevents
  resolution of `1.14.1` or `0.30.4`; the change is committed to the repo.

- [ ] 4. Regenerate lockfile and verify clean resolution (depends on 3) —
  DoD: `npm install` completes without errors; `npm ls axios --all` no longer
  shows `1.14.1` or `0.30.4` at any depth; `grep` on the lockfile for the strings
  `1.14.1` and `0.30.4` returns no matches.

- [ ] 5. Run CI and confirm all tests pass (depends on 4) —
  DoD: CI pipeline passes green with no new test failures introduced by the
  lockfile change.

- [ ] 6. Open an incident if backdoored versions were found (depends on 2,
  triggered only if step 2 result is YES) —
  DoD: an incident is opened in the mctl tracking system; credential rotation
  (S3 keys, channel OAuth tokens, API keys) is initiated as a separate out-of-band
  action; this proposal's tasks do not gate on the incident resolution.

## Tests

- [ ] T1. Lockfile grep: `grep -F "\"axios\"" package-lock.json` (or
  `yarn.lock`/`pnpm-lock.yaml`) shows no version `1.14.1` and no version `0.30.4`.
- [ ] T2. `npm ls axios --all` after the change: confirm output contains no line
  ending in `axios@1.14.1` or `axios@0.30.4`.
- [ ] T3. Existing channel integration tests (Slack, and any other channel that
  uses Axios internally) pass without modification after the lockfile regeneration.
- [ ] T4. `labs` memory metric: record before and after; confirm no increase
  (expected zero delta since no new package is introduced).

## Rollback

This proposal introduces only a lockfile and `package.json` change — no runtime
configuration is modified. Rollback procedure:

1. Revert the `package.json` and lockfile commit in git.
2. Run `npm install` to restore the previous lockfile state.
3. Re-deploy from the reverted commit via the standard ArgoCD sync.
4. Note: rolling back means reinstating the backdoored version in the dependency
   tree if it was present. Rolling back is only justified if the pinning change
   itself breaks the build in a way that cannot be quickly fixed. In that case,
   prioritise fixing the pin over reverting.
