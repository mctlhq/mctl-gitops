# Tasks: backstage-1-54-7-oauth-normalization

- [ ] 1. Confirm the exact upstream package(s)/commit implementing the OAuth profile
      normalization fix in Backstage v1.54.7 — DoD: changelog/PR reference recorded in
      this proposal or a linked issue.
- [ ] 2. Bump Backstage core auth dependencies (and release line, if unified) to
      v1.54.7 in a feature branch (depends on 1) — DoD: `yarn install` and workspace
      build succeed with no unresolved dependency conflicts.
- [ ] 3. Run full yarn workspace build + lint + existing unit/integration tests
      (depends on 2) — DoD: CI green on the feature branch.
- [ ] 4. Run Playwright e2e suite plus a manual Dex login smoke test against a lower
      environment (depends on 3) — DoD: login succeeds, catalog user entity resolves
      correctly for a test account with a verified and an unverified email.
- [ ] 5. Smoke-test custom plugins (kubernetes, observability, scaffolder, techdocs,
      kubernetes-permissions) against the upgraded backend (depends on 3) — DoD: no
      401s/regressions observed beyond the known k8s-reader stale-token footgun.
- [ ] 6. Promote via Docker build → mctl-gitops → ArgoCD to `admins` (depends on 4, 5)
      — DoD: ArgoCD status Healthy/Synced on the new revision, no auth-related
      incident opened within 24h.
- [ ] 7. Update `context/current-version.md` with the new Backstage/patch version
      (depends on 6) — DoD: file reflects v1.54.7 and the date of rollout.

## Tests
- [ ] T1. Unit/integration tests covering OAuth profile normalization for both
      verified and unverified email claims from Dex.
- [ ] T2. Playwright e2e regression covering full login flow end to end.
- [ ] T3. Manual verification that existing sessions/users are unaffected (no
      unexpected re-authentication or identity mismatch) post-deploy.

## Rollback
Revert the dependency bump commit in mctl-gitops and let ArgoCD sync back to the
previously-deployed revision (currently 2.6.3). Since no database migration or
session-storage change is introduced, rollback is a plain redeploy of the prior
container image with no data cleanup required.
