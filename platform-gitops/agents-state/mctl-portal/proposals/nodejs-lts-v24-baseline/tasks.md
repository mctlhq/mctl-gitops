# Tasks: nodejs-lts-v24-baseline

- [ ] 1. Update Dockerfile base image from `node:22-alpine` to `node:24-alpine` — DoD: Dockerfile builds successfully locally with no layer errors.
- [ ] 2. Update CI workflow node-version from `22` to `24` (depends on 1) — DoD: CI config file updated; pipeline triggers on the feature branch.
- [ ] 3. Update `.nvmrc` or `.node-version` to `24` — DoD: `nvm use` / `fnm use` in the repo root activates Node.js v24.
- [ ] 4. Run `yarn install` under Node.js v24 and verify no incompatible-engines warnings (depends on 1, 2, 3) — DoD: `yarn install` exits 0; no `engines` mismatch warnings.
- [ ] 5. Run full CI pipeline on the feature branch (depends on 2, 4) — DoD: build, lint, type-check, and unit tests all pass on Node.js v24.
- [ ] 6. Deploy to staging using the v24 image (depends on 5) — DoD: staging deployment healthy; Backstage backend `/healthcheck` returns 200.
- [ ] 7. Run Playwright e2e suite against staging (depends on 6) — DoD: all e2e tests pass; no new errors in Loki logs after 1-hour soak.
- [ ] 8. Update `package.json` engines field to `"24"` and merge the feature branch (depends on 7) — DoD: PR merged; ArgoCD syncs production; production health check passes.

## Tests
- [ ] T1. `node --version` in the Docker container returns `v24.x.x`.
- [ ] T2. `yarn install` produces no engines-incompatibility warnings under Node.js v24.
- [ ] T3. All existing unit tests pass on Node.js v24 in CI.
- [ ] T4. Playwright e2e suite passes on staging with Node.js v24 backend.

## Rollback
1. Revert the Dockerfile and CI config changes; rebuild and redeploy the previous image.
2. Restore `.nvmrc` to `22`.
3. ArgoCD will redeploy the previous image digest automatically on revert merge.
