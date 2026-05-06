# Tasks: nodejs-22-security-upgrade

- [ ] 1. Locate all `FROM node:` directives in the Dockerfile(s) under the repository root — DoD: a list of file paths and line numbers of every `FROM node:` directive is documented in the PR description.
- [ ] 2. Update every `FROM node:` directive identified in task 1 to `node:22.22.2-alpine` (depends on 1) — DoD: `grep -r "FROM node:" .` in the repository returns only lines referencing `22.22.2-alpine` (or a pinned digest of that tag); no other `node:22` tag variant remains.
- [ ] 3. Update the CI pipeline Node.js version pin to `22.22.2` in all relevant workflow files (depends on 1) — DoD: every `node-version:` or equivalent field in CI config files references `22.22.2`; no other v22 pin remains.
- [ ] 4. Run `docker build` locally (or in CI) with the updated Dockerfile (depends on 2, 3) — DoD: the build exits with code 0 and `docker run --rm <image> node --version` outputs `v22.22.2`.
- [ ] 5. Open a Pull Request containing the Dockerfile and CI config changes (depends on 4) — DoD: PR is open, CI passes (lint + unit tests + playwright e2e run under Node.js 22.22.2), and has at least one approver.
- [ ] 6. Merge and promote the new image to `admins` via ArgoCD (depends on 5) — DoD: ArgoCD reports `mctl-portal` as `Synced` and `Healthy`; the backend pod restarts cleanly.
- [ ] 7. Verify the running Node.js version in the deployed pod (depends on 6) — DoD: `kubectl exec -n admins <backend-pod> -- node --version` outputs `v22.22.2`.

## Tests

- [ ] T1. Build verification: `docker run --rm <new-image> node --version` returns `v22.22.2`.
- [ ] T2. Unit tests: `yarn test` passes inside a container built from the new image.
- [ ] T3. E2E tests: playwright suite runs successfully in CI using Node.js 22.22.2.
- [ ] T4. Backend smoke test post-deployment: Backstage `/healthcheck` endpoint returns HTTP 200 after pod restart.
- [ ] T5. Runtime version check: `kubectl exec` into the running backend pod confirms `process.version === 'v22.22.2'` (or higher patch within v22).

## Rollback
Revert the Dockerfile and CI config changes by reverting the merge commit. Re-trigger the CI build to produce an image from the reverted Dockerfile. Redeploy via ArgoCD using the previous image tag. Because no application code or database state is modified, rollback completes in a single pod restart cycle. If the previous image tag was not retained in the container registry, the prior git commit's CI run artifact (image) must be available — ensure the registry retention policy keeps at least the last 5 tags.
