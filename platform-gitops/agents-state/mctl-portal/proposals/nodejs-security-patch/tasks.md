# Tasks: nodejs-security-patch

- [ ] 1. Identify the exact Node.js 22 LTS patch version from the March 2026
       security release — DoD: exact version string (e.g., `22.x.y`)
       documented in the PR description; cross-referenced with
       https://nodejs.org/en/blog/vulnerability/march-2026-security-releases
       to confirm all three CVEs (CVE-2026-21710, CVE-2026-21711,
       CVE-2026-21637) are fixed in that version.

- [ ] 2. Update the `FROM` line in the mctl-portal Dockerfile (depends on 1)
       — DoD: `FROM node:22.x.y-bookworm-slim` (or the appropriate slim
       variant) updated to the confirmed patch version; diff reviewed and
       no other lines changed by this PR.

- [ ] 3. Build the Docker image locally and run `trivy image` (depends on 2)
       — DoD: `docker build` succeeds; `trivy image` reports zero HIGH or
       CRITICAL CVEs against the Node.js runtime; any new OS-level findings
       are reviewed and accepted or mitigated.

- [ ] 4. Run smoke tests against the locally built image (depends on 3) — DoD:
       portal starts successfully; catalog, scaffolder, and TechDocs pages
       load without errors in a local dev environment.

- [ ] 5. Assess coordination with Backstage v1.50.3 bump (depends on 2) —
       DoD: decision recorded in the PR description: either (a) this Dockerfile
       change is folded into the same PR as the Backstage bump, or (b) it is
       shipped as a standalone PR; rationale documented.

- [ ] 6. Run Playwright e2e suite in staging against the new image (depends on
       4, 5) — DoD: all existing e2e tests pass with zero regressions.

- [ ] 7. Update image tag in `mctl-gitops` and open PR (depends on 6) — DoD:
       PR opened; CI passes; approved by at least one reviewer; commit message
       references CVE-2026-21710, CVE-2026-21711, CVE-2026-21637.

- [ ] 8. Merge PR and verify ArgoCD sync to `admins` namespace (depends on 7)
       — DoD: ArgoCD reports `Synced / Healthy`; new pod running the updated
       image; `kubectl exec` into the pod confirms `node --version` returns
       the patched version string; no error spike in logs or Prometheus alerts
       within 15 minutes post-deploy.

- [ ] 9. Close vulnerability tracker findings (depends on 8) — DoD: all three
       CVEs (CVE-2026-21710, CVE-2026-21711, CVE-2026-21637) marked
       remediated; Node.js version and commit SHA recorded for each finding.

## Tests

- [ ] T1. Runtime version assertion: after deployment, run
       `kubectl exec -n admins <pod> -- node --version` and assert the output
       matches the patched version from task 1.

- [ ] T2. `trivy` image scan: assert zero HIGH or CRITICAL CVEs against the
       Node.js runtime in the promoted image.

- [ ] T3. HTTP header handling test: send a request with a `__proto__` header
       to the portal health endpoint; assert the response is normal (200 or
       401) and pod memory does not spike (check Prometheus `container_memory_working_set_bytes`
       over a 5-minute window after the test).

- [ ] T4. TLS handshake test: use `openssl s_client` with a malformed SNI to
       the portal ingress; assert the connection is rejected gracefully and
       the pod does not restart.

- [ ] T5. Playwright e2e full run in staging: all existing test cases pass.

## Rollback
1. Revert the image-tag commit in `mctl-gitops` (single-line change) and push
   under the emergency-commit policy.
2. ArgoCD detects the revert and re-syncs the previous image within ~2 minutes.
3. Confirm the previous pod is `Running` and `node --version` returns the
   prior version string.
4. Re-open the CVE findings and schedule a follow-up investigation before
   attempting the upgrade again.
5. If the Node.js patch was combined into the same image as the Backstage
   v1.50.3 bump, rolling back this image also rolls back the Backstage
   changes — coordinate with the owners of the other two CVE proposals.
