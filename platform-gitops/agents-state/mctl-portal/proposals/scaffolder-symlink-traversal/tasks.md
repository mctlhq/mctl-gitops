# Tasks: scaffolder-symlink-traversal

- [ ] 1. Identify exact installed versions of `@backstage/backend-defaults` and `@backstage/plugin-scaffolder-backend` — DoD: versions recorded in a PR description comment; confirmed as pre-patch via `yarn why`.
- [ ] 2. Bump `@backstage/backend-defaults` to 0.15.0 and `@backstage/plugin-scaffolder-backend` to 3.1.1 in `packages/backend/package.json` and the root resolutions block (depends on 1) — DoD: `package.json` diff shows only the two target packages changed; no other package versions altered.
- [ ] 3. Run `yarn install` and resolve lockfile; run `yarn dedupe` to eliminate duplicate transitive copies (depends on 2) — DoD: `yarn.lock` committed; `yarn install --immutable` succeeds in CI with zero errors.
- [ ] 4. Build backend locally and confirm no TypeScript compilation errors (depends on 3) — DoD: `yarn tsc` exits 0 in the `packages/backend` workspace.
- [ ] 5. Build and tag Docker image with the updated packages (depends on 4) — DoD: image published to registry with tag `scaffolder-symlink-traversal-<sha>`; `docker sbom` output shows patched package versions.
- [ ] 6. Deploy image to `admins` tenant via ArgoCD sync (depends on 5) — DoD: ArgoCD shows `Synced / Healthy`; Backstage `/healthcheck` endpoint returns 200; scaffolder plugin loads without errors in the UI.
- [ ] 7. Update `context/current-version.md` to reflect new package versions — DoD: file updated with patched `@backstage/backend-defaults` and `@backstage/plugin-scaffolder-backend` versions and today's date.

## Tests

- [ ] T1. Unit test: verify that the patched `@backstage/backend-defaults` version is present — run `yarn why @backstage/backend-defaults` and assert version >= 0.15.0.
- [ ] T2. Unit test: verify that `@backstage/plugin-scaffolder-backend` is at a patched version — run `yarn why @backstage/plugin-scaffolder-backend` and assert version >= 3.1.1.
- [ ] T3. Integration test: run the existing scaffolder integration test suite (`yarn test packages/backend --testPathPattern scaffolder`) and assert all tests pass with no modifications.
- [ ] T4. Security regression test: craft a template that uses `fs:delete` on a path resolved through a symlink pointing to `../../etc/passwd`; assert the workflow step fails with a path-traversal rejection error (not a silent success).
- [ ] T5. End-to-end test: run the standard service-onboarding scaffolder template in a staging environment and confirm it completes successfully, the Argo Workflow triggers, and the resulting repository is created in mctl-gitops.
- [ ] T6. Smoke test post-deploy: navigate to the Scaffolder page in the portal, confirm template list loads, submit a minimal template execution, and assert it reaches the "completed" state.

## Rollback
1. Revert the `package.json` and `yarn.lock` changes in the git branch and merge the revert PR.
2. Trigger an ArgoCD sync to redeploy the previous image tag (the prior tag is retained in the registry for 30 days per registry retention policy).
3. Verify the portal returns to healthy state via `/healthcheck` and manual UI inspection.
4. Open a follow-up issue to re-attempt the upgrade with the root cause of the regression documented.
