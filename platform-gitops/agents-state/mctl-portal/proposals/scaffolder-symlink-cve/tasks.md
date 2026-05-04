# Tasks: scaffolder-symlink-cve

- [ ] 1. Identify exact patched package versions — DoD: Confirmed minimum versions of `@backstage/plugin-scaffolder-backend`, `@backstage/backend-defaults`, and `@backstage/plugin-scaffolder-node` that resolve CVE-2026-24046 are recorded in the PR description, cross-referenced against the GHSA-rq6q-wr2q-7pgp advisory.
- [ ] 2. Update `packages/backend/package.json` with the patched versions (depends on 1) — DoD: All three package entries in `packages/backend/package.json` reference the patched versions; diff is reviewed and contains only the three version bumps.
- [ ] 3. Add or update `resolutions` block in root `package.json` (depends on 2) — DoD: Root `package.json` resolutions block pins the three packages to the patched versions, preventing transitive re-introduction of the vulnerable versions.
- [ ] 4. Regenerate lockfile (depends on 3) — DoD: `yarn install` completes without errors; `yarn.lock` diff shows only changes for the three patched packages and their direct dependencies; no unrelated version drift.
- [ ] 5. Run local build and unit tests (depends on 4) — DoD: `yarn tsc` and `yarn test` pass with zero failures in `packages/backend` and any plugin touching scaffolder logic.
- [ ] 6. Run scaffolder integration tests (depends on 5) — DoD: All existing scaffolder integration tests pass; no new test failures introduced.
- [ ] 7. Open PR and request security review (depends on 6) — DoD: PR is raised with the CVE reference in the title, includes lockfile diff, passes all CI checks (lint, type-check, unit tests, integration tests, playwright e2e), and is approved by at least one platform-security reviewer.
- [ ] 8. Merge and verify ArgoCD rollout to `admins` (depends on 7) — DoD: New image is deployed to the `admins` tenant; ArgoCD application shows `Synced/Healthy`; scaffolder health endpoint returns 200; at least one test scaffold task completes successfully in the staging environment.

## Tests
- [ ] T1. Symlink escape attempt: craft a scaffolder template that creates a symlink pointing to `/etc/passwd` and invokes `debug:log` on it; verify the backend rejects the action with an error and does not return file contents.
- [ ] T2. Archive traversal attempt: submit a `.tar.gz` archive containing a `../../../etc/passwd` entry via an archive-extraction action; verify the backend rejects the entry and logs a security warning.
- [ ] T3. `fs:delete` path traversal attempt: invoke `fs:delete` with a path that resolves outside the workspace directory via `../../`; verify the backend rejects the operation.
- [ ] T4. Regression — existing onboarding template: execute the standard mctl service-onboarding scaffolder template end-to-end; verify it completes successfully and commits to mctl-gitops.
- [ ] T5. Package version assertion: add or update a CI check that reads the installed package versions and asserts they meet the minimum patched versions; verify this check is part of the security gate.

## Rollback
1. Revert the PR (or revert the specific commit bumping the three packages) on the main branch.
2. Trigger a manual ArgoCD sync to redeploy the previous image from the `admins` application.
3. Verify the rollback by confirming the old image digest is running and the scaffolder health endpoint returns 200.
4. Re-open the CVE remediation work as a new branch and investigate the regression before re-attempting.

Note: Because this is a pure package version bump with no schema or API changes, rollback has no data-migration implications.
