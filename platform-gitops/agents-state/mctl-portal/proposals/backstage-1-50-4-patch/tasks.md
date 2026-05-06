# Tasks: backstage-1-50-4-patch

- [ ] 1. Review the Backstage v1.50.4 release notes and changelog for any breaking changes or manual migration steps — DoD: a comment in the PR description confirms "no breaking changes" or lists any required manual steps; the `@backstage/integration` 1.20.1 changelog is reviewed for SCM URL normalisation behaviour changes.
- [ ] 2. Run `yarn backstage-cli versions:bump --release 1.50.4` (or equivalent) in the repository root to update all `@backstage/*` packages (depends on 1) — DoD: all `@backstage/*` entries in `package.json` files across the workspace reflect 1.50.4-aligned versions; `@backstage/integration` is at 1.20.1 or higher.
- [ ] 3. Run `yarn install` to regenerate `yarn.lock` (depends on 2) — DoD: `yarn install` exits with code 0; no unresolved peer-dependency errors; `yarn.lock` is updated and committed.
- [ ] 4. Run `yarn build` for both `packages/app` and `packages/backend` (depends on 3) — DoD: both build steps exit with code 0; no TypeScript compilation errors.
- [ ] 5. Open a Pull Request with all changed `package.json` files and `yarn.lock` (depends on 4) — DoD: PR is open; CI passes (lint + unit tests + playwright e2e); PR description references CVE-2026-29185 and links to the Backstage v1.50.4 release; at least one approver has approved.
- [ ] 6. Merge and promote to `admins` via ArgoCD (depends on 5) — DoD: ArgoCD reports `mctl-portal` as `Synced` and `Healthy`; backend and frontend pods restart cleanly with no error logs at startup.
- [ ] 7. Verify deployed Backstage version (depends on 6) — DoD: `kubectl exec` into the backend pod confirms `node -e "require('@backstage/integration/package.json').version"` outputs `1.20.1` or higher; the Backstage version badge in the portal UI (if present) shows 1.50.4.

## Tests

- [ ] T1. Unit tests: `yarn test` across the workspace passes without modification after the bump.
- [ ] T2. Catalog e2e: playwright suite covers catalog import and entity registration flows; all pass.
- [ ] T3. Scaffolder e2e: at least one full template execution completes successfully end-to-end.
- [ ] T4. SCM URL traversal regression test: submit a catalog import request with an encoded path traversal in the SCM URL (e.g., `https://github.com/org/repo/blob/main/%2E%2E%2F%2E%2E%2Fetc%2Fpasswd`); confirm the system returns an error and does not fetch content outside the repository tree.
- [ ] T5. Integration smoke test: verify that GitHub integration (PR/issue widgets) and Argo Workflows scaffolder hooks function correctly after the upgrade.

## Rollback
Revert the merge commit containing the `package.json` and `yarn.lock` changes. Run `yarn install` on the reverted state to confirm the lock file is consistent. Re-trigger CI to build and push the previous image. Redeploy via ArgoCD using the prior image tag. No database state is modified by this proposal, so rollback is a pure application-layer revert requiring only a pod restart. Ensure the container registry retains the prior image tag (minimum 5-tag retention policy recommended).
