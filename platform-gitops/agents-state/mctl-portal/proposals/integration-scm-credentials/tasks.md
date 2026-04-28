# Tasks: integration-scm-credentials

- [ ] 1. Run `yarn backstage-cli versions:bump --release 1.50.3` at the monorepo root —
  DoD: every `@backstage/*` package is updated to the versions in the 1.50.3 release
  manifest, including `@backstage/integration` >= 1.20.1; `yarn.lock` is updated; `yarn install`
  finishes without errors.

- [ ] 2. Run `yarn backstage-cli versions:check` and resolve peer conflicts (depends on 1) —
  DoD: the command emits no warnings about version mismatches; particular attention to the
  custom observability plugin in `plugins/`.

- [ ] 3. Run `yarn backstage-cli repo build` (depends on 2) — DoD: TypeScript compilation
  of every package (`packages/app`, `packages/backend`, `plugins/*`) finishes without errors.

- [ ] 4. Run playwright smoke tests in staging (depends on 3) — DoD: tests pass for
  catalog-import (component registration via URL), the scaffolder onboarding template,
  and the github-actions panel (CI status display).

- [ ] 5. Review the Backstage 1.50.3 CHANGELOG and community-plugins for deprecated/breaking
  changes (depends on 1, in parallel with 2–3) — DoD: every API used per
  `context/architecture.md` (catalog, scaffolder, kubernetes, techdocs, search,
  github-actions) is confirmed compatible or adapted.

- [ ] 6. Build the backend Docker image and update the tag in the ArgoCD manifest of the
  `admins` tenant (depends on 4 and 5) — DoD: ArgoCD shows `Synced` and `Healthy`; the pod
  has restarted on the new Backstage v1.50.3 image.

- [ ] 7. Run `yarn audit --level high` (depends on 6) — DoD: no high/critical CVEs related
  to CVE-2026-29185.

- [ ] 8. Rotate GitHub App credentials after the deploy — DoD: a new GitHub App private
  key and App ID are written to Vault; ExternalSecret has updated the Kubernetes Secret;
  the pod has restarted with the new credentials; old credentials are revoked in GitHub
  Organization settings; the GitHub audit log is reviewed for suspicious API calls.

## Tests

- [ ] T1. Integration test: submit a URL with a path-traversal sequence (`%2F..%2F`) to
  catalog-import — confirm the backend returns a validation error and does not issue an
  outbound request to the GitHub API.
- [ ] T2. Integration test: scaffolder git action `publish:github` with a `repoUrl`
  containing `%252F` (double-encoded) — confirm rejection with an error before the
  token-bearing request is sent.
- [ ] T3. Smoke test: catalog-import with a valid GitHub URL successfully registers a component.
- [ ] T4. Smoke test: a scaffolder onboarding template with a valid `repoUrl` finishes
  successfully.
- [ ] T5. Smoke test: the github-actions plugin shows CI status for a registered component.
- [ ] T6. Smoke test: the custom observability plugin loads Prometheus charts without errors.
- [ ] T7. `yarn audit` in the CI pipeline fails the build at severity >= high.

## Rollback
1. Restore the previous Docker image tag in the ArgoCD manifest of the `admins` tenant.
2. Run `argocd app sync mctl-portal --prune` — the pod returns to Backstage 1.0.1.
3. The CVE-2026-29185 vulnerability returns; as a temporary mitigation — disable
   catalog-import and restrict scaffolder git actions through the Backstage permission
   framework until the patch is redeployed.
4. If the GitHub App credential rotation (task 8) has already been performed — no rollback
   is needed for it; the old credentials are already revoked, the new ones remain in force.
