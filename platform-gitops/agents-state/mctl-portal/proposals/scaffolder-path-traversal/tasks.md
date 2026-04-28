# Tasks: scaffolder-path-traversal

- [ ] 1. Update `@backstage/backend-defaults` to ^0.12.2 and `plugin-scaffolder-backend`
  to ^3.1.1 in `packages/backend/package.json` and the root `package.json` — DoD: `yarn
  install` finishes without errors; `yarn backstage-cli versions:check` reports no
  peer conflicts; `yarn.lock` records versions >= 0.12.2 and >= 3.1.1 respectively.

- [ ] 2. Run `yarn backstage-cli repo build` (depends on 1) — DoD: the build finishes
  without TypeScript errors and without warnings about deprecated APIs.

- [ ] 3. Run a playwright smoke test of the create-service template in staging
  (depends on 2) — DoD: the test passes; the scaffolder successfully creates a test
  component via the onboarding form.

- [ ] 4. Build a new backend Docker image and update the tag in the ArgoCD manifest of
  the `admins` tenant (depends on 3) — DoD: ArgoCD shows `Synced` and `Healthy`; the
  pod has restarted on the new image.

- [ ] 5. Run `yarn audit --level high` against the production lockfile (depends on 4) —
  DoD: no critical or high CVEs related to CVE-2026-24046 or CVE-2026-32237.

## Tests

- [ ] T1. Integration test: load an archive containing a symlink like
  `../../../../etc/passwd` into the scaffolder, and confirm the scaffolder returns a step
  error without creating the file outside the workspace.
- [ ] T2. Integration test: invoke `fs:delete` with the path `../../secret`; confirm the
  action finishes with an error `path traversal detected` and the file outside the
  workspace is untouched.
- [ ] T3. Smoke test: a full run of the create-service template (standard onboarding)
  finishes successfully without regressions.
- [ ] T4. `yarn audit` in the CI pipeline must fail the build on severity >= high CVEs.

## Rollback
1. Restore the previous Docker image tag in the ArgoCD manifest of the `admins` tenant.
2. Run `argocd app sync mctl-portal --prune` — the pod returns to the previous version.
3. The vulnerability returns; as a temporary mitigation — disable scaffolder access via
   the Backstage permission framework (deny role `scaffolder.template.execute` for every
   group until the patch is redeployed).
