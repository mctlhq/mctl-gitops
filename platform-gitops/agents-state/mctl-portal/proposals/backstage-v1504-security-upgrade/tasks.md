# Tasks: backstage-v1504-security-upgrade

- [ ] 1. Run `yarn backstage-cli versions:bump --release 1.50.4` in the monorepo root — DoD: all `@backstage/*` packages in package.json files reflect v1.50.4-compatible versions; no unresolved peer-dep warnings.
- [ ] 2. Run `yarn install` and commit updated `yarn.lock` (depends on 1) — DoD: lockfile updated, committed, and CI passes the install step without errors.
- [ ] 3. Fix any TypeScript or lint errors surfaced after the bump (depends on 2) — DoD: `yarn tsc --noEmit` and `yarn backstage-cli repo lint` exit 0.
- [ ] 4. Build Docker image locally and smoke-test (depends on 3) — DoD: backend starts, `/healthcheck` returns 200, Scaffolder and Catalog pages load.
- [ ] 5. Deploy to staging in `admins` namespace and run full Playwright e2e suite (depends on 4) — DoD: all e2e tests pass; Scaffolder onboarding flow completes end-to-end against mctl-gitops staging.
- [ ] 6. 24-hour soak in staging — DoD: no new errors in Loki logs, no increase in error rate vs. baseline.
- [ ] 7. Update image tag in mctl-gitops for production ArgoCD app (depends on 6) — DoD: ArgoCD syncs successfully; production health check passes within 5 minutes.
- [ ] 8. Update `context/current-version.md` to reflect the new Backstage version — DoD: file updated and merged.

## Tests
- [ ] T1. Verify CVE-2026-24046 is not exploitable: create a test template with a symlink pointing to `/etc/passwd`; confirm the action returns an error and does not read the file.
- [ ] T2. Verify CVE-2026-24048 is not exploitable: configure a test backend with an allowlisted external host that redirects to `http://169.254.169.254`; confirm `FetchUrlReader` refuses the redirect.
- [ ] T3. Verify CVE-2026-44374 is not exploitable: call the unprocessed-entity endpoint as a user without ownership rights; confirm HTTP 403.
- [ ] T4. Regression: existing Playwright e2e suite passes with ≥95% pass rate after the upgrade.

## Rollback
1. Revert the image tag in mctl-gitops to the previous digest; ArgoCD will roll back automatically.
2. Revert the `versions:bump` commit and the `yarn.lock` commit on the feature branch; do not merge.
3. Document the regression in the inbox file for the next daily cycle.
