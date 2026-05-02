# Tasks: fetchurlreader-ssrf

- [ ] 1. Audit `app-config.yaml` allow-list — review `backend.reading.allow` entries and cross-check against all known TechDocs sources and catalog-import origins in use. DoD: a list of any missing allowed hosts is documented in the PR description; missing entries are added to `app-config.yaml` before the package bump lands.

- [ ] 2. Bump `@backstage/backend-defaults` in `packages/backend/package.json` (depends on 1) — set the constraint to `^0.15.0`. DoD: the updated constraint appears in `packages/backend/package.json`. (If scaffolder-symlink-traversal-v2 is being merged concurrently, this task and that proposal's task 1 may be combined into a single branch.)

- [ ] 3. Resolve the lockfile (depends on 2) — run `yarn install` in the monorepo root. DoD: `yarn.lock` is updated without errors and `yarn why @backstage/backend-defaults` reports a version ≥0.15.0.

- [ ] 4. Type-check and unit-test (depends on 3) — run `yarn tsc --noEmit` and `yarn test --passWithNoTests`. DoD: zero TypeScript errors; all existing unit tests pass in CI.

- [ ] 5. Build and push Docker image (depends on 4) — trigger the CI pipeline to build the production Docker image and push it to the container registry with a new tag. DoD: image tag is available in the registry and the CVE scanner no longer reports CVE-2026-24048 against the image.

- [ ] 6. Deploy to `admins` tenant (depends on 5) — update the image tag in the mctl-gitops Helm values for `mctl-portal` in the `admins` namespace and merge the PR. DoD: ArgoCD reports `Healthy` and `Synced`; the running pod's image digest matches the new tag.

- [ ] 7. Post-deploy validation (depends on 6) — verify catalog-import and TechDocs from at least one external source complete successfully; check backend logs for unexpected blocked-redirect warnings. DoD: no regressions observed; any new warn-level blocked-redirect entries are triaged and resolved.

## Tests

- [ ] T1. Unit — add a test for `FetchUrlReader` (or the relevant backend-defaults utility) that issues a mock HTTP redirect to an internal address not in the allow-list and asserts that the reader throws an SSRF error rather than following the redirect.
- [ ] T2. Unit — assert that a redirect to a URL that IS in the allow-list is followed successfully.
- [ ] T3. Integration — import a catalog-info.yaml from a real external GitHub URL in the staging environment to confirm end-to-end catalog-import still works after the upgrade.
- [ ] T4. CVE scan — run Trivy or the platform's standard image scanner against the new Docker image and confirm CVE-2026-24048 is absent.

## Rollback
1. Revert the image-tag change in mctl-gitops (revert the merge commit or push a revert PR).
2. ArgoCD will re-sync to the previous image tag within one sync cycle, or trigger a manual sync.
3. If the allow-list was extended in step 1, decide whether to revert those entries — they are safe to leave in place since they were already legitimate sources.
4. Open a follow-up ticket to re-attempt the fix with a pinned temporary version constraint and a comment explaining the reason for the revert.
