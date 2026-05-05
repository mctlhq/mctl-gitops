# Tasks: techdocs-mkdocs-code-exec

- [ ] 1. Bump `@backstage/plugin-techdocs-node` to `^1.14.3` in `packages/backend/package.json` — DoD: `yarn.lock` resolves `@backstage/plugin-techdocs-node` to 1.14.3 or higher; no other `plugin-techdocs-node` entries at a lower version exist in the lock-file after `yarn dedupe`.

- [ ] 2. Run `yarn install && yarn dedupe` and commit updated `yarn.lock` (depends on 1) — DoD: `yarn install --frozen-lockfile` passes in CI; no duplicate `plugin-techdocs-node` entries in lock-file.

- [ ] 3. Add dependency-audit step to CI (depends on 2) — DoD: a `yarn audit --level high` (or equivalent) step is present in the CI pipeline and set to fail the build on HIGH or CRITICAL findings; step is enforced on every PR targeting `main`.

- [ ] 4. Create a malicious-fixture test in the security test suite (depends on 1) — DoD: a test `mkdocs.yml` containing a non-allowlisted `hooks` entry is submitted to the TechDocs build pipeline in the test environment; the build exits non-zero and the log contains `ERROR` without executing the injected callable.

- [ ] 5. Run full staging dry-run of TechDocs builds across all catalog components (depends on 2) — DoD: all pre-existing TechDocs builds that passed before the bump either still pass or fail with a documented reason (unlisted plugin); no regressions introduced by the version bump itself.

- [ ] 6. Deploy to production via ArgoCD (depends on 3, 4, 5) — DoD: ArgoCD sync completes; `@backstage/plugin-techdocs-node` version confirmed as 1.14.3+ in the running pod via `yarn list --pattern plugin-techdocs-node`; no error-rate spike in Grafana for 30 minutes post-deploy.

## Tests

- [ ] T1. Unit test: valid `mkdocs.yml` (allowlisted plugins only) — build completes, exit code 0.
- [ ] T2. Security test: `mkdocs.yml` with non-allowlisted `hooks` entry — build exits non-zero, log line matches `ERROR.*allowlist`.
- [ ] T3. Security test: `mkdocs.yml` with non-allowlisted `plugins` entry — same behaviour as T2.
- [ ] T4. Playwright e2e: navigate to a catalog component's TechDocs page and confirm rendered HTML is present — confirms the happy path still works end-to-end after the bump.
- [ ] T5. CI audit gate: introduce a synthetic HIGH vulnerability into a test package and confirm the audit step blocks the build.

## Rollback
1. Revert the `packages/backend/package.json` change and restore the previous `yarn.lock` via a Git revert PR.
2. ArgoCD will detect the new image tag from the reverted commit and re-sync automatically.
3. The previous image is retained in the container registry for at least 7 days (standard mctl-gitops retention policy), so a direct image-tag rollback via ArgoCD override is also available without a code revert if speed is needed.
4. After rollback, immediately restrict catalog write access as a temporary mitigation and file an incident per the security runbook until the fix can be re-applied cleanly.
