# Tasks: catalog-facets-perf-fix

Note: this upgrade targets Backstage v1.50.4, which is a superset of v1.50.3 (the release
containing the facets performance fix). It is intended to be applied in the same PR and
deployment as `catalog-unprocessed-security-patch`. The tasks below assume a combined bump;
if the two proposals are applied separately, the target version in task 1 is v1.50.3.

- [ ] 1. Bump all `@backstage/*` packages to v1.50.4 — DoD: `package.json` files reference
  `^1.50.4` (or equivalent exact pins), `yarn install` completes without errors, and
  `yarn.lock` is committed. No unresolved peer-dependency warnings remain. (This task is
  shared with `catalog-unprocessed-security-patch` task 1; do not duplicate the lockfile
  change.)

- [ ] 2. Establish a pre-upgrade facets latency baseline (depends on 1, staging environment) —
  DoD: p50 and p95 latency for `GET /api/catalog/entity-facets` recorded from Prometheus
  on the staging pod running the pre-upgrade image, documented in the PR description.

- [ ] 3. Run CI pipeline on updated lockfile (depends on 1) — DoD: all unit and integration
  tests in `packages/backend` pass; Docker image builds successfully.

- [ ] 4. Deploy to staging and measure facets latency (depends on 3) — DoD: staging pod
  is running the v1.50.4 image; p95 latency for `/api/catalog/entity-facets` is measured
  under representative load (at minimum 20 concurrent filter queries) and is no worse than
  the baseline recorded in task 2.

- [ ] 5. Confirm no CPU regression in staging (depends on 4) — DoD: backend pod CPU usage
  during the load test in task 4 does not exceed the pre-regression baseline. Observation
  period: at least 10 minutes of sustained traffic.

- [ ] 6. Promote to production via ArgoCD (depends on 4, 5) — DoD: ArgoCD sync completes;
  production `/healthcheck` returns 200; Prometheus shows facets p95 latency within SLO
  for 15 minutes post-deploy; no error-rate spike in Loki.

## Tests

- [ ] T1. `yarn workspaces foreach run test` passes on the updated lockfile with zero
  failing test suites in `packages/backend`.
- [ ] T2. Facets endpoint functional test: issue a GET to `/api/catalog/entity-facets?facet=kind`
  and verify the response contains at least the expected entity kinds (Component, API,
  System) with non-zero counts.
- [ ] T3. Facets endpoint load test: 20 concurrent requests to `/api/catalog/entity-facets`
  over 60 seconds; assert p95 < 500 ms and 0 error responses (HTTP 5xx).
- [ ] T4. Observability plugin smoke test: open the observability custom plugin in a browser
  against staging and confirm that catalog-backed entity selectors populate correctly.

## Rollback
1. Revert the `package.json` and `yarn.lock` changes in git (shared revert commit with
   `catalog-unprocessed-security-patch` if applied together).
2. Trigger a new CI build from the reverted commit to produce the previous Docker image tag.
3. In ArgoCD, update the image tag in the `admins` app manifest to the last known-good tag
   and sync. ArgoCD will replace the running pod(s).
4. Confirm `/healthcheck` returns 200 and catalog facets load without errors in production.
5. Re-evaluate: if the rollback was due to the performance fix itself, open an upstream
   Backstage issue before re-attempting.
