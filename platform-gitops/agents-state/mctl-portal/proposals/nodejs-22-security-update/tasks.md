# Tasks: nodejs-22-security-update

- [ ] 1. Identify the current base image tag in the Dockerfile — DoD: the current `FROM` line is documented (tag and variant, e.g., `node:22.X.X-alpine`) in the PR description.
- [ ] 2. Update `FROM` line in the Dockerfile to `node:22.22.3-<variant>` (depends on 1) — DoD: `Dockerfile` diff shows exactly one changed line (`FROM node:22.22.3-<variant>`); no other lines are modified.
- [ ] 3. Build the Docker image locally (depends on 2) — DoD: `docker build` exits 0; the image is tagged (e.g., `mctl-portal:1.0.1-node22.22.3`); build log contains no `gyp` errors or missing native library errors.
- [ ] 4. Verify Node.js version and OpenSSL version inside the built image (depends on 3) — DoD: `docker run --rm <image> node --version` outputs `v22.22.3`; `docker run --rm <image> node -e "console.log(process.versions.openssl)"` outputs `3.5.6` or later.
- [ ] 5. Run a container-level health check (depends on 3) — DoD: the container starts and `GET /healthcheck` returns HTTP 200 within 60 s.
- [ ] 6. Deploy to staging and run Playwright e2e suite (depends on 5) — DoD: all existing Playwright tests pass, including tests that exercise authenticated routes (Dex SSO), Vault-backed secrets, and external API integrations.
- [ ] 7. Run a container image vulnerability scan on the new image (depends on 3) — DoD: the scan report shows zero High or Critical CVEs in the Node.js runtime layer that were present in the previous image; the CVEs listed in the Node.js v22.22.3 release notes are absent.
- [ ] 8. Push the new image to the container registry and update the image tag in mctl-gitops Helm values for `admins` (depends on 6, 7) — DoD: PR to mctl-gitops is merged; ArgoCD reports `mctl-portal` as `Synced` and `Healthy`; `kubectl get pods -n admins` shows no CrashLoopBackOff.
- [ ] 9. Confirm production health post-deployment (depends on 8) — DoD: `GET /healthcheck` returns 200; no runtime-level errors (Zlib, HTTP2, URL parser) appear in backend logs within 10 minutes of the rollout completing.

## Tests

- [ ] T1. Node.js version assertion — `docker run --rm <image> node --version` outputs `v22.22.3`.
- [ ] T2. OpenSSL version assertion — `docker run --rm <image> node -e "console.log(process.versions.openssl)"` outputs `3.5.6` or later.
- [ ] T3. Health endpoint — `GET /healthcheck` returns HTTP 200 within 60 s of container start.
- [ ] T4. Playwright e2e suite — all tests pass in staging, including auth flows using Dex JWT and Vault-backed secrets.
- [ ] T5. Container image scan — no High/Critical CVEs in the Node.js runtime layer that were present in the previous base image.
- [ ] T6. ArgoCD health gate — `mctl-portal` in `admins` reports `Healthy` after sync; no unexpected pod restarts.

## Rollback
1. Revert the image tag in the mctl-gitops Helm values to the previous tag.
2. Commit and push to mctl-gitops; ArgoCD re-syncs and restores the previous pod.
3. The previous image (with the older Node.js version) will be running again — the runtime CVEs will be re-open. Escalate to security team and expedite a new fix attempt.
4. Preserve logs from the failed rollout and the image digest of the new image for post-mortem.
