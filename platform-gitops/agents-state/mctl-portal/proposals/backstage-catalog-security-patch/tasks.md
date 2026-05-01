# Tasks: backstage-catalog-security-patch

- [ ] 1. Bump the three affected catalog packages to v1.50.4 — DoD: `package.json` entries for `@backstage/plugin-catalog-backend-module-unprocessed`, `@backstage/plugin-catalog-unprocessed-entities-common`, and `@backstage/plugin-catalog-unprocessed-entities` show version `1.50.4`; `yarn.lock` is consistent (`yarn install --frozen-lockfile` exits 0 with no changes).

- [ ] 2. Validate build in CI (depends on 1) — DoD: `yarn build` for `packages/backend` completes without TypeScript errors or missing-module errors in CI; `yarn audit --level high` exits 0 (no high or critical advisories in the three patched packages); the CI pipeline green-lights the branch.

- [ ] 3. Build and push the patched Docker image (depends on 2) — DoD: A new image tagged `mctl-portal:1.50.4-<short-git-sha>` is pushed to the container registry and is visible/pullable from the `admins` cluster nodes; image provenance is recorded in the CI build log.

- [ ] 4. Deploy to staging environment and capture baseline snapshot (depends on 3) — DoD: The patched image is running in staging; catalog ingestion completes within 5 minutes of pod start with no WARN/ERROR log entries in the processor pipeline; a JSON snapshot of all registered component names and kinds is exported and saved as `artifacts/catalog-baseline-staging.json` in the PR artifacts.

- [ ] 5. Update image tag in mctl-gitops GitOps repo, gated to deploy no earlier than 2026-05-06 (depends on 4) — DoD: A PR in mctl-gitops updates the `mctl-portal` image tag to the new value; the ArgoCD Application sync window is configured to prevent auto-sync before 2026-05-06T00:00:00Z; the PR is approved and merged.

- [ ] 6. Confirm production rollout on or after 2026-05-06 (depends on 5) — DoD: ArgoCD reports the Application as `Synced` and `Healthy`; all pods are running the new image tag; no HTTP 5xx errors were observed in the nginx access log during the rolling update window.

- [ ] 7. Post-deploy audit and sign-off (depends on 6) — DoD: `yarn audit --level high` is run against the production-equivalent lockfile and exits 0; a short sign-off comment is posted in the tracking Jira ticket referencing the advisory URL and the deployed image tag.

## Tests

- [ ] T1. Unit/integration — run the existing `packages/backend` test suite (`yarn test`) after the bump: all tests pass with no new failures related to catalog or unprocessed-entities modules.

- [ ] T2. Catalog ingestion smoke test — after staging deploy, call `GET /api/catalog/entities?limit=1` and assert HTTP 200 with a non-empty `items` array; assert total entity count matches the pre-upgrade baseline (within ±0 for a patch-only deploy with no catalog changes).

- [ ] T3. Unprocessed-entities endpoint — call `GET /api/catalog/entities/unprocessed` (or the plugin-specific route) in staging and assert HTTP 200 with a valid JSON body matching the expected schema (fields: `items`, `count`).

- [ ] T4. Playwright e2e — run the full Playwright suite against staging; the Catalog page renders correctly, the component detail view loads, and catalog search returns results; zero test failures.

- [ ] T5. Security audit — `yarn audit --level high` executed in CI and post-deploy in production both exit 0; output is attached to the Jira ticket as evidence.

- [ ] T6. Rolling update zero-downtime — during the staging rollout, run a continuous HTTP probe (`watch -n1 curl -s -o /dev/null -w "%{http_code}" <staging-url>/api/catalog/entities?limit=1`) and assert no 5xx responses are observed at any point during pod replacement.

## Rollback

**Trigger:** ArgoCD health check fails (pod not ready within 3 minutes) OR post-deploy `yarn audit` exits non-zero OR HTTP 5xx rate exceeds threshold in nginx metrics.

**Procedure:**

1. In the mctl-gitops GitOps repo, revert the image tag commit to the previous `mctl-portal` image tag (the one running before this patch).
2. ArgoCD detects the change and syncs back to the previous image automatically (self-heal enabled). The rolling update replaces pods with the old image, maintaining `minAvailable: 1` throughout.
3. Confirm all pods are running the reverted image tag (`kubectl get pods -n admins -l app=mctl-portal -o jsonpath='{.items[*].spec.containers[0].image}'`).
4. Verify catalog endpoints return HTTP 200 and entity counts match the pre-patch baseline.
5. Open a Jira incident ticket documenting the rollback reason, attach the failing logs, and notify the security officer that the patch deployment was deferred.
6. Investigate the root cause of the rollback (dependency conflict, regression, or probe failure) before scheduling a new deployment attempt.

**Maximum expected rollback time:** under 5 minutes (one rolling-update cycle with a single-replica replacement at `minAvailable: 1`).
