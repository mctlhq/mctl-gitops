# Tasks: backstage-security-patch-bump

- [ ] 1. Inventory installed versions of the four packages with `yarn why` — DoD: table of current vs fixed versions in PR description.
- [ ] 2. Run `versions:bump` within the current line and add resolutions where needed (depends on 1) — DoD: lockfile resolves all four packages at or above fixed versions.
- [ ] 3. Add a CI version-assert/audit step (depends on 2) — DoD: CI fails if any package is below its minimum.
- [ ] 4. Build, deploy to `admins` via mctl-gitops (depends on 2) — DoD: ArgoCD Healthy, pod stable 30 minutes.
- [ ] 5. Verify scaffolder logs/events redaction and k8s masking manually (depends on 4) — DoD: no secret values visible in a test task.

## Tests
- [ ] T1. Playwright smoke: login via Dex, catalog loads, scaffolder template runs.
- [ ] T2. Proxy path-escape request returns an error.
- [ ] T3. Observability plugin graphs render.

## Rollback
Revert the PR in mctl-gitops to the previous image tag and let ArgoCD sync; the lockfile revert restores prior versions.
