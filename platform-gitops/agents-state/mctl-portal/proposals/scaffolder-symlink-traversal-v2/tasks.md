# Tasks: scaffolder-symlink-traversal-v2

- [ ] 1. Bump package versions in `packages/backend/package.json` — set `@backstage/plugin-scaffolder-backend` to `^3.1.5` and `@backstage/backend-defaults` to `^0.15.0`. DoD: both constraints appear in `packages/backend/package.json` and no other files are edited.

- [ ] 2. Resolve the lockfile (depends on 1) — run `yarn install` in the monorepo root. DoD: `yarn.lock` is updated, `node_modules` resolves without errors, and `yarn why @backstage/plugin-scaffolder-backend` reports a version ≥3.1.5.

- [ ] 3. Type-check and unit-test (depends on 2) — run `yarn tsc --noEmit` and `yarn test --passWithNoTests`. DoD: zero TypeScript errors; all existing unit tests pass in CI.

- [ ] 4. Build and push Docker image (depends on 3) — trigger the CI pipeline to build the production Docker image and push it to the container registry with a new tag. DoD: image tag is available in the registry and the image manifest shows the patched package versions (`docker run --rm <image> node -e "require('@backstage/plugin-scaffolder-backend/package.json').version"` prints ≥3.1.5).

- [ ] 5. Deploy to `admins` tenant (depends on 4) — update the image tag in the mctl-gitops Helm values file for `mctl-portal` in the `admins` namespace and merge the PR. DoD: ArgoCD reports the application as `Healthy` and `Synced`; the running pod's image digest matches the new tag.

- [ ] 6. Post-deploy smoke test (depends on 5) — execute one scaffolder template end-to-end in the staging/prod environment. DoD: template completes successfully; no errors in the pod logs related to workspace isolation; the CVE scanner on the new image no longer flags CVE-2026-24046.

## Tests

- [ ] T1. Unit — verify that `fs:delete` with a symlink-based path outside the workspace throws a sandbox violation error (test in `packages/backend` or a dedicated scaffolder-actions test file).
- [ ] T2. Unit — verify that archive extraction skips symlink entries resolving outside the workspace and emits a warning log.
- [ ] T3. Integration — run `yarn playwright test` in CI against the deployed environment to confirm the scaffolder UI and at least one template workflow are functional after the upgrade.
- [ ] T4. CVE scan — run Trivy or the platform's standard image scanner against the new Docker image and confirm CVE-2026-24046 is absent from the report.

## Rollback
1. Revert the image-tag change in mctl-gitops (revert the merge commit or push a revert PR).
2. ArgoCD will automatically re-sync to the previous image tag on the next sync cycle, or trigger a manual sync.
3. The previous image (with the vulnerable package versions) will be restored within one rolling-update cycle.
4. Pin the vulnerable version range in `packages/backend/package.json` with a comment marking it as temporary until a re-attempt, and open a follow-up ticket.
