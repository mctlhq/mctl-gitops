# Tasks: catalog-unprocessed-security-patch

Note: this upgrade targets Backstage v1.50.4. It is intended to be applied in the same PR
and deployment as `catalog-facets-perf-fix` (v1.50.3 fixes), since v1.50.4 is a superset.
The tasks below assume a combined bump; if the two proposals are applied separately, adjust
the target version in task 1 accordingly.

- [ ] 1. Bump all `@backstage/*` packages to v1.50.4 — DoD: `package.json` files reference
  `^1.50.4` (or equivalent exact pins), `yarn install` completes without errors, and
  `yarn.lock` is committed. No unresolved peer-dependency warnings remain.

- [ ] 2. Verify dependency audit (depends on 1) — DoD: `yarn npm audit` (or `npm audit` on
  the lock) reports no known CVEs against the `@backstage/plugin-catalog-backend-module-unprocessed`,
  `@backstage/plugin-catalog-unprocessed-entities-common`, or
  `@backstage/plugin-catalog-unprocessed-entities` packages at v1.50.4.

- [ ] 3. Run CI pipeline (depends on 1) — DoD: all unit and integration tests in `packages/backend`
  pass on the updated lockfile; build step produces a Docker image successfully.

- [ ] 4. Deploy to staging and run smoke tests (depends on 3) — DoD: the portal backend starts,
  `/healthcheck` returns 200, at least five catalog entities are ingested and visible in the
  UI, and the unprocessed-entities admin panel loads without errors.

- [ ] 5. Promote to production via ArgoCD (depends on 4) — DoD: ArgoCD sync completes
  successfully; production `/healthcheck` returns 200; no error spike in Loki logs within
  15 minutes post-deploy; catalog entity count in production matches pre-deploy baseline
  within 5%.

## Tests

- [ ] T1. `yarn workspaces foreach run test` passes on the updated lockfile with zero
  failing test suites in `packages/backend`.
- [ ] T2. Catalog integration test: POST a new `catalog-info.yaml` via the catalog-import
  plugin and verify the entity appears in the catalog within the normal ingestion window.
- [ ] T3. Unprocessed-entities endpoint smoke test: call the unprocessed-entities API endpoint
  and confirm it returns a valid JSON response with no 5xx error.
- [ ] T4. `yarn npm audit --all` produces no HIGH or CRITICAL findings for any
  `@backstage/plugin-catalog-*` package.

## Rollback
1. Revert the `package.json` and `yarn.lock` changes in git (a single revert commit or PR).
2. Trigger a new CI build from the reverted commit to produce the previous Docker image tag.
3. In ArgoCD, update the image tag in the `admins` app manifest to the last known-good tag
   and sync. ArgoCD will replace the running pod(s) with the previous version.
4. Confirm `/healthcheck` returns 200 and catalog entity pages load in production.
5. Open an incident to track why the rollback was needed before re-attempting the upgrade.
