# Tasks: nodejs-lts-security-patch

- [ ] 1. Confirm current Node.js base image pin in the Dockerfile/CI config and
      determine target version (22.23.2+ if on the 22.x line, or 24.20.0+ if on the
      24.x line) — DoD: current and target versions documented in the PR
      description.
- [ ] 2. Update the Docker base image tag (and `.nvmrc`/CI runtime pin if present) to
      the target version (depends on 1) — DoD: image builds successfully in CI.
- [ ] 3. Run the full test suite (unit, integration, e2e) against the rebuilt image
      (depends on 2) — DoD: all tests pass with no new failures attributable to the
      Node.js version bump.
- [ ] 4. Smoke test in staging: Dex JWT login, one mctl-api read call, one
      Vault-backed ExternalSecret-derived config fetch (depends on 2) — DoD: all
      three flows succeed with no new errors or warnings in logs.
- [ ] 5. Deploy via mctl-gitops → ArgoCD to tenant `admins` (depends on 3, 4) —
      DoD: ArgoCD reports Healthy/Synced on the new revision; no new incidents
      opened for `mctl-portal` in the 24h following deploy.

## Tests
- [ ] T1. CI: full unit/integration/e2e suite green on the new Node.js version.
- [ ] T2. Manual: Dex JWT login flow succeeds post-deploy.
- [ ] T3. Manual: an mctl-api-backed page (e.g. tenant/status view) loads correctly.
- [ ] T4. Manual: a Vault-backed secret is fetched/used correctly (e.g. an
      integration relying on an ExternalSecret-sourced credential still works).
- [ ] T5. Post-deploy: no new incidents or elevated error logs for `mctl-portal` in
      the 24h following rollout.

## Rollback
Revert the Docker base image tag (and any `.nvmrc`/CI pin) to the previous Node.js
version, rebuild via CI, and redeploy through mctl-gitops → ArgoCD. Since this is a
runtime version pin change with no data migration or schema change, rollback is a
plain image-tag revert and redeploy.
