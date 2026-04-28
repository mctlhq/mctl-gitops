# Tasks: techdocs-path-traversal-fix

- [ ] 1. Verify current `@backstage/plugin-techdocs-node` version and confirm
       vulnerability — DoD: version string logged and cross-checked against
       CVE-2026-23947 advisory; a local proof-of-concept symlink test
       reproduces the leak on the current build.

- [ ] 2. Run `yarn backstage-cli versions:bump --release 1.50.3` (depends on 1)
       — DoD: `package.json` files across all workspaces updated; `yarn install`
       completes with no unresolved peer-dependency errors; diff reviewed and
       approved by a second engineer.

- [ ] 3. Build and smoke-test the Docker image locally (depends on 2) — DoD:
       `docker build` succeeds; `@backstage/plugin-techdocs-node` version in
       the image is >=1.13.11; the local PoC symlink test from task 1 no longer
       leaks host file content.

- [ ] 4. Run Playwright e2e suite against a staging deployment of the new image
       (depends on 3) — DoD: all existing e2e tests pass; TechDocs pages for
       the three highest-traffic catalog components render without errors.

- [ ] 5. Update image tag in `mctl-gitops` and open PR (depends on 4) — DoD:
       PR opened, CI passes, approved by at least one reviewer; commit message
       references CVE-2026-23947.

- [ ] 6. Merge PR and verify ArgoCD sync to `admins` namespace (depends on 5)
       — DoD: ArgoCD reports `Synced / Healthy`; new pod is running the
       updated image tag; no error spike in logs or Prometheus alerts within
       15 minutes post-deploy.

- [ ] 7. Close vulnerability tracker finding (depends on 6) — DoD: CVE-2026-23947
       marked remediated; reference commit SHA recorded in the tracker.

## Tests

- [ ] T1. Symlink escape test: create a TechDocs source directory with a
       symlink pointing to `/etc/hostname`; trigger generation; assert that
       the build fails with a symlink-escape error and that `/etc/hostname`
       content does not appear in any generated HTML file.

- [ ] T2. Clean docs regression test: generate TechDocs for three real catalog
       components (no out-of-tree symlinks); assert all pages render correctly
       and no error is logged.

- [ ] T3. Catalog facets smoke test: open the catalog with at least two active
       filters; assert response time is within the SLO (p95 < 500 ms) — this
       validates the bundled facets performance regression fix.

- [ ] T4. Playwright e2e full run in staging: all existing test cases pass with
       zero regressions.

## Rollback
1. Revert the image-tag commit in `mctl-gitops` (single-line change) and push
   directly to the default branch under the emergency-commit policy.
2. ArgoCD detects the revert and re-syncs the previous image within ~2 minutes.
3. Confirm the previous pod is `Running` and serving traffic.
4. Re-open the CVE finding and schedule a follow-up investigation into what
   caused the regression before attempting the upgrade again.
