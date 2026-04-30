# Tasks: nodejs-security-upgrade

- [ ] 1. Identify the exact Node.js version currently running in the deployed pod — DoD: version string (e.g., `v22.14.0`) recorded in the PR description; retrieved via `kubectl exec` on the running backend pod in `admins` namespace.
- [ ] 2. Update `packages/backend/Dockerfile` to pin the base image to `node:22.22.2-bookworm-slim` (or `node:22.22.2-alpine3.20` if Alpine is the current base) — DoD: `FROM` line in the Dockerfile reads the fully pinned version; diff reviewed and approved.
- [ ] 3. Tighten `engines.node` in root `package.json` to `>=22.22.2 <23 || >=24` (depends on 2) — DoD: `package.json` diff shows only the `engines.node` field changed; `yarn install` succeeds locally on Node.js 22.22.2.
- [ ] 4. Update CI workflow node-version matrix to `22.22.2` (depends on 2) — DoD: CI configuration file updated; CI run completes successfully on the pinned version.
- [ ] 5. Build Docker image with the pinned base and verify the runtime version inside the container (depends on 2, 3, 4) — DoD: `docker run --rm <image> node --version` outputs `v22.22.2`; image pushed to registry with tag `nodejs-security-upgrade-<sha>`.
- [ ] 6. Deploy new image to `admins` tenant via ArgoCD image-tag update in mctl-gitops (depends on 5) — DoD: ArgoCD shows `Synced / Healthy`; `/healthcheck` returns 200; `kubectl exec` confirms `node --version` is `v22.22.2` in the running pod.
- [ ] 7. Update `context/current-version.md` to record the new Node.js runtime version and today's date — DoD: file reflects `v22.22.2` and `2026-04-30`.

## Tests

- [ ] T1. Runtime version assertion: inside the built Docker image run `node --version` and assert output is `v22.22.2` (fails if version is lower).
- [ ] T2. CVE-2026-21710 regression test: send an HTTP request with the header name `__proto__` set to `{"polluted":true}` to the backend health endpoint; assert the server returns a valid HTTP response (not a crash/hang) and `Object.prototype.polluted` is undefined in a subsequent request.
- [ ] T3. Full backend unit test suite: run `yarn test` across all workspace packages; assert zero failures.
- [ ] T4. Backstage startup smoke test: start the backend image locally with `docker run`; assert Backstage logs show "Backend started" and the catalog plugin initialises without errors within 30 seconds.
- [ ] T5. CI pipeline: the PR CI run on the pinned Node.js 22.22.2 version must pass all lint, type-check, and test steps — DoD: green CI badge on the PR.
- [ ] T6. Post-deploy health check: after ArgoCD sync, curl `https://app.mctl.ai/healthcheck` from outside the cluster and assert HTTP 200 within 5 minutes of pod Ready.

## Rollback
1. Revert the `Dockerfile` and `package.json` changes in git; merge the revert PR into main.
2. Trigger an ArgoCD sync; the previous image tag (retained in registry) is automatically re-deployed.
3. Confirm `/healthcheck` returns 200 and the portal is operational.
4. Document the regression cause in a follow-up issue; re-attempt the upgrade in a separate branch with the fix applied.
