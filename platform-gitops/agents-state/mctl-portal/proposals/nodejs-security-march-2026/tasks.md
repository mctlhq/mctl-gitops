# Tasks: nodejs-security-march-2026

- [ ] 1. Confirm the exact base image variant currently in use — DoD: The current `FROM` line (image name, tag, and digest) is documented in the PR description; the variant (bookworm-slim, alpine, distroless, etc.) is confirmed.
- [ ] 2. Update the Dockerfile base image pin to `node:22.22.2` (same variant) (depends on 1) — DoD: The `FROM` line in the Dockerfile references `node:22.22.2-<variant>`; no other lines in the Dockerfile are changed.
- [ ] 3. Build the Docker image locally and verify the runtime version (depends on 2) — DoD: `docker build` completes without errors; `docker run --rm <image> node --version` outputs `v22.22.2`.
- [ ] 4. Run the full CI pipeline against the new image (depends on 3) — DoD: All CI stages pass — lint, TypeScript type-check, unit tests, integration tests, and playwright e2e tests — with zero failures.
- [ ] 5. Update the image tag in mctl-gitops Helm values (depends on 4) — DoD: A PR is opened in the mctl-gitops repository updating only the `mctl-portal` image tag to the newly built and pushed image digest or tag; no other Helm values are changed.
- [ ] 6. Merge the application Dockerfile PR and the mctl-gitops Helm values PR (depends on 5) — DoD: Both PRs are approved by at least one reviewer, all CI checks pass, and both are merged to their respective main branches.
- [ ] 7. Verify ArgoCD rollout to `admins` (depends on 6) — DoD: ArgoCD application `mctl-portal` in the `admins` tenant shows `Synced/Healthy`; all pods are running the new image (verified via `kubectl get pods -o jsonpath`); backend health endpoint returns 200.

## Tests
- [ ] T1. Runtime version assertion: after deployment, exec into a running backend pod and run `node --version`; assert output is `v22.22.2`.
- [ ] T2. TLS DoS smoke test (CVE-2026-21637): send a malformed TLS ClientHello to the backend's HTTPS listener (or the nginx TLS terminator's upstream); verify the backend pod does not crash and continues to serve subsequent valid requests.
- [ ] T3. `__proto__` header smoke test (CVE-2026-21710): send an HTTP request with a `__proto__` header to the backend API; verify the response is a normal HTTP error (400 or similar) and the pod does not crash.
- [ ] T4. Backstage health check: confirm the `/healthcheck` endpoint of the Backstage backend returns `{"status":"ok"}` after rollout.
- [ ] T5. Scaffolder regression: execute a standard mctl onboarding template through the scaffolder UI; verify it completes successfully.
- [ ] T6. Catalog regression: verify the service catalog loads and displays registered components correctly after rollout.

## Rollback
1. Revert the mctl-gitops Helm values PR (or directly push a revert commit to mctl-gitops) restoring the previous image tag/digest.
2. Trigger a manual ArgoCD sync on the `mctl-portal` application in `admins`.
3. Confirm all pods return to the previous image by checking pod image digests.
4. Verify the backend health endpoint returns 200.
5. Investigate the regression (e.g., base image OS library incompatibility) before reattempting the upgrade.

Rollback has no data, schema, or configuration side-effects; it is purely an image tag revert.
