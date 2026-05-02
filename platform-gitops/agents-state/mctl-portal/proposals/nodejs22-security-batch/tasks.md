# Tasks: nodejs22-security-batch

- [ ] 1. Identify the current base image tag — open `packages/backend/Dockerfile` (and `packages/app/Dockerfile` if present) and record the current `FROM` line. DoD: the current Node.js base image tag is documented in the PR description.

- [ ] 2. Update the Dockerfile base image (depends on 1) — change the `FROM` directive in `packages/backend/Dockerfile` (and `packages/app/Dockerfile` if it uses a Node.js image) to `node:22.22.2-alpine` (or the equivalent slim variant matching the current flavour). DoD: both Dockerfiles use `node:22.22.2-<flavour>` as the base image; no other changes are made.

- [ ] 3. Build and test the Docker image locally (depends on 2) — run `docker build -t mctl-portal-test packages/backend/` and verify `docker run --rm mctl-portal-test node --version` prints `v22.22.2`. DoD: the image builds successfully and reports the correct Node.js version.

- [ ] 4. Run the CI pipeline (depends on 2) — push the branch and confirm the full CI pipeline passes: TypeScript type-check, unit tests, Playwright e2e tests, and Docker build. DoD: all CI checks are green; no test regressions introduced.

- [ ] 5. Push the production image (depends on 4) — the CI pipeline publishes the new image to the container registry with a new tag. DoD: the image is available in the registry; `docker inspect` shows the base layer digest corresponds to `node:22.22.2`.

- [ ] 6. Deploy to `admins` tenant (depends on 5) — update the image tag in the mctl-gitops Helm values for `mctl-portal` and merge. DoD: ArgoCD reports `Healthy` and `Synced`; the running pod confirms `node --version` returns `v22.22.2` (via `kubectl exec`).

- [ ] 7. Configure automated Node.js patch updates (depends on 6) — add or update a Renovate/Dependabot rule in the repository to open PRs automatically for future `node:22.x.y-alpine` base image updates. DoD: a Renovate `regexManagers` or Dependabot `docker` entry for the Dockerfile is present and tested with a dry-run.

## Tests

- [ ] T1. Image version check — in CI, assert `docker run --rm <image> node --version` outputs `v22.22.2` or higher.
- [ ] T2. CVE scan — run Trivy or the platform's standard image scanner against the new Docker image and assert CVE-2026-21637 and CVE-2026-21710 are absent from the High/Critical findings.
- [ ] T3. Smoke test — after deployment, verify the Backstage home page, catalog list, and one TechDocs page load successfully (manual or Playwright check).
- [ ] T4. Process stability — monitor pod restart count in the `admins` namespace for 30 minutes post-deploy; assert zero unexpected restarts.

## Rollback
1. Revert the image-tag change in mctl-gitops (revert the merge commit or open a revert PR).
2. ArgoCD will re-sync to the previous image tag; the rolling update restores the old pod within one update cycle.
3. The previous image (with the older Node.js base) will be restored; this returns to the vulnerable state, so a P1 incident should be opened immediately to drive a re-attempt.
4. If the Dockerfile change itself caused a build failure, revert the `FROM` line in the Dockerfile and re-trigger CI to confirm the previous build still works.
