# Tasks: backstage-security-patch-bundle

- [ ] 1. Record current versions from backstage.json and `yarn why` for affected packages — DoD: table of current vs fixed versions in the PR.
- [ ] 2. Run `versions:bump` to 1.56.3 (depends on 1) — DoD: lockfile updated, `yarn tsc` and `yarn build:all` pass.
- [ ] 3. Fix API deprecations / custom plugin breakage (depends on 2) — DoD: observability plugin builds and renders.
- [ ] 4. Verify fixed versions of all CVE-listed packages (depends on 2) — DoD: `yarn why` shows only fixed versions.
- [ ] 5. Deploy to admins via mctl-gitops (depends on 3, 4) — DoD: ArgoCD healthy, pod stable.

## Tests
- [ ] T1. Playwright e2e suite green.
- [ ] T2. Scaffolder onboarding dry-run succeeds; cross-user task read is denied.
- [ ] T3. Kubernetes viewer loads and masked values stay masked.
- [ ] T4. Dex login round-trip works.

## Rollback
Revert the PR and let ArgoCD sync the previous image; if the k8s-reader token breaks after restart, see the stale-token footgun in architecture.md.
