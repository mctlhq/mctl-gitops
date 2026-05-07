# Tasks: nodejs-security-patch

- [ ] 1. Identify the current Node.js base image tag in the service Dockerfile — DoD: The exact `FROM node:...` line is recorded in the PR description, including LTS line (20.x, 22.x, or 24.x) and variant (alpine, slim, bookworm, etc.).

- [ ] 2. Determine the correct patched base image tag for the current LTS line (depends on 1) — DoD: Target tag is confirmed: `node:22.22.2-<variant>` for 22.x, `node:20.20.2-<variant>` for 20.x, or the equivalent 24.x security release. Tag is verified to exist in the registry.

- [ ] 3. Update the `FROM` line in the Dockerfile to the patched base image (depends on 2) — DoD: Dockerfile PR created with the single-line change; no other modifications; PR reviewed and approved.

- [ ] 4. Rebuild the Docker image and run CI (depends on 3) — DoD: CI build passes; `node --version` step inside the image reports the patched version; image pushed to the mctl registry with a new tag.

- [ ] 5. Execute `labs` rollout per ADR-0002 procedure (depends on 4) — DoD: s3-sync canary suspended for `labs`; ArgoCD syncs the updated image; restore-state readiness probe passes within timeout; pod is running and marked ready.

- [ ] 6. Observe `labs` stability window and restart canary (depends on 5) — DoD: `labs` stable for at least 6 hours; s3-sync canary restarted; at least one successful canary cycle confirmed; spot-check RSS shows no unexpected increase.

- [ ] 7. Execute `admins` rollout per ADR-0002 procedure (depends on 6) — DoD: s3-sync canary suspended for `admins`; ArgoCD syncs; restore-state probe passes; pod marked ready.

- [ ] 8. Observe `admins` stability window and restart canary (depends on 7) — DoD: `admins` stable for at least 6 hours; s3-sync canary restarted; at least one successful canary cycle confirmed.

- [ ] 9. Execute `ovk` rollout per ADR-0002 procedure (depends on 8) — DoD: s3-sync canary suspended for `ovk`; rollout scheduled during a low-traffic window; ArgoCD syncs; restore-state probe passes within timeout; pod marked ready; no customer-visible channel loss.

- [ ] 10. Observe `ovk` stability window and restart canary (depends on 9) — DoD: `ovk` stable for at least 12 hours; s3-sync canary restarted; at least one successful canary cycle confirmed.

- [ ] 11. Close CVE tracking tickets and update rollout log (depends on 10) — DoD: CVE-2026-21637, CVE-2026-21710, and CVE-2026-21713 tracking tickets marked resolved; rollout log PR merged with per-tenant confirmation entries.

## Tests

- [ ] T1. Version check: `docker run --rm <new-image> node --version` reports the patched Node.js version (22.22.2 or equivalent).
- [ ] T2. CVE-2026-21637 regression check (`labs`): Send a TLS connection with a synthetic SNICallback that throws synchronously; confirm the pod does NOT crash (process stays up, error is handled gracefully).
- [ ] T3. CVE-2026-21710 regression check (`labs`): Send an HTTP request with a `__proto__` header to the pod; confirm the pod does NOT crash and returns an appropriate error response.
- [ ] T4. Restore-state probe (`labs`): After rollout, readiness probe passes within the configured timeout; verified via `kubectl describe pod` events showing `Readiness probe succeeded`.
- [ ] T5. Restore-state probe (`admins`): Same as T4 for `admins` tenant.
- [ ] T6. Restore-state probe (`ovk`): Same as T4 for `ovk` tenant.
- [ ] T7. S3 canary smoke test (all tenants): After canary restart on each tenant, at least one successful write-timestamp check is logged within two canary cycles.
- [ ] T8. Channel session continuity (`ovk`): At least one previously-active channel reconnects successfully after the rollout without re-authentication, confirming S3 state was restored intact.

## Rollback

**Per-tenant rollback procedure:**

1. Revert the Dockerfile to the previous base image tag (or revert the mctl-gitops image tag reference directly).
2. Rebuild the image (or reference the previous image already in the registry).
3. Stop the s3-sync canary for the affected tenant before ArgoCD applies the revert.
4. Let ArgoCD sync the rollback; wait for the restore-state readiness probe to pass.
5. Restart the s3-sync canary with the post-rollout delay; confirm at least one successful cycle.

Because the only change is the Node.js base image version (not application state or S3 format), rolling back restores the previous runtime without any state manipulation. S3 state written by the patched Node.js version is fully compatible with the previous version.

**Note:** Rolling back re-exposes the service to CVE-2026-21637 and CVE-2026-21710. A rollback should be treated as a temporary measure; the root cause of the failure must be diagnosed and a corrected image produced as soon as possible.
