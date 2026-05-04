# Tasks: backstage-v1-50-4-security-patch

- [ ] 1. Confirm current Backstage version and the list of packages to be bumped — DoD: The current Backstage release version is identified from `packages/backend/package.json` (or root `package.json`); a list of all `@backstage/*` packages in the monorepo that will be affected by the bump is documented in the PR description.
- [ ] 2. Run `yarn backstage-cli versions:bump --release 1.50.4` (depends on 1) — DoD: The command completes without error; the generated diff touches only `@backstage/*` version strings in `package.json` files across the workspace; no other files are modified by the tooling.
- [ ] 3. Review the version bump diff (depends on 2) — DoD: A reviewer confirms that no major or minor version increments are present; all changes are patch-level bumps within `@backstage/*`; no unexpected packages are added or removed.
- [ ] 4. Regenerate the lockfile (depends on 3) — DoD: `yarn install` completes without errors; `yarn.lock` changes are consistent with the package.json diff; no unrelated dependency drift is present.
- [ ] 5. Run TypeScript type-check across the workspace (depends on 4) — DoD: `yarn tsc --noEmit` (or `yarn workspaces foreach run tsc`) completes with zero errors in all packages including `plugins/*`.
- [ ] 6. Run unit and integration tests (depends on 5) — DoD: All unit and integration tests pass with zero failures; test coverage does not decrease below the pre-upgrade baseline.
- [ ] 7. Run playwright e2e tests against the new image (depends on 6) — DoD: All existing playwright e2e tests pass, including catalog browsing, scaffolder execution, and TechDocs rendering scenarios.
- [ ] 8. Run `yarn audit` and review results (depends on 4) — DoD: No high-severity or critical CVEs are reported in the audit output; any medium findings are documented in the PR description with a disposition.
- [ ] 9. Open PR, obtain review, and merge (depends on 5, 6, 7, 8) — DoD: PR is approved by at least one platform engineer; all CI checks pass; PR is merged to main.
- [ ] 10. Verify ArgoCD rollout to `admins` (depends on 9) — DoD: ArgoCD application `mctl-portal` in `admins` shows `Synced/Healthy`; all pods run the new image; catalog health endpoint returns 200; service catalog entities are visible in the UI.

## Tests
- [ ] T1. Security audit assertion: `yarn audit --level high` exits with code 0 on the updated lockfile; no `@backstage/catalog-*` packages report CVEs.
- [ ] T2. Catalog entity load: after deployment, navigate to the catalog UI and verify that all previously registered entities (services, APIs, components) are present and their metadata renders correctly.
- [ ] T3. Catalog facets query: invoke the catalog `/api/catalog/facets` endpoint and verify it returns a valid facets response; measure and compare response time against the pre-upgrade baseline (expect no regression and potentially improvement per v1.50.3 note).
- [ ] T4. Catalog unprocessed entities: if an admin-visible unprocessed-entities endpoint or UI exists, verify it loads without errors after the upgrade.
- [ ] T5. Scaffolder regression: execute a standard mctl onboarding scaffolder template and verify end-to-end completion.
- [ ] T6. Custom plugin smoke test: verify the custom observability plugin loads and renders the Prometheus graphs correctly (checks for unintended API breakage from the Backstage bump).

## Rollback
1. Revert the version-bump commit on the main branch (or open a revert PR).
2. Run `yarn install` against the reverted `package.json` files to restore the previous lockfile state.
3. Rebuild and push the image with the previous package versions.
4. Update the image tag in mctl-gitops Helm values to the previous image and trigger an ArgoCD sync.
5. Confirm `mctl-portal` in `admins` returns to `Synced/Healthy` with the old image.
6. Document the regression encountered, open a follow-up issue, and re-attempt after the upstream fix is confirmed.

No database migrations or schema changes are introduced, so rollback has no data-layer implications.
