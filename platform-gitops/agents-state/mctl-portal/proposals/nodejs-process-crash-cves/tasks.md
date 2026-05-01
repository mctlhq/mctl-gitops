# Tasks: nodejs-process-crash-cves

- [ ] 1. Identify the patched Node.js 22.x image tag — Cross-reference the Node.js March 24, 2026 security release blog post (https://nodejs.org/en/blog/vulnerability/march-2026-security-releases) with the official Docker Hub `node` image manifest to confirm the exact `node:22.x.y-alpine` (or `-slim`) tag that includes patches for CVE-2026-21637, CVE-2026-21713, CVE-2026-21714, and CVE-2026-21717. DoD: A single verified image tag is recorded in the PR description, confirmed via `docker manifest inspect` or equivalent, showing the Node.js binary version string that matches the patched release.

- [ ] 2. Update `FROM` in the Dockerfile (depends on 1) — Change the base image line in the project Dockerfile from the current `node:22.x-alpine` tag to the verified patched tag identified in task 1. DoD: The Dockerfile diff shows exactly one line changed (the `FROM` line), the new tag is pinned to the full patch version (not a floating `22-alpine`), and the change is committed to a feature branch.

- [ ] 3. Run CI build and smoke tests (depends on 2) — Push the feature branch; confirm the CI pipeline builds the Docker image successfully using the updated base, starts the container, and executes the existing smoke test suite (health-check endpoint, auth redirect, catalog API call). DoD: All CI stages pass with a green status; the build log shows the Node.js version string matching the patched release; no regression is reported by the smoke tests.

- [ ] 4. Update image tag reference in mctl-gitops (depends on 3) — If the CD pipeline does not automatically pick up the new image digest, open a pull request in `mctl-gitops` to update the image tag in the Kubernetes manifests or Helm values for the `admins` tenant deployment. DoD: The `mctl-gitops` PR references the new image tag, passes any manifest validation checks, and is reviewed by a second engineer.

- [ ] 5. ArgoCD sync and rollout verification on `admins` tenant (depends on 4) — Merge the `mctl-gitops` PR and confirm ArgoCD performs a rolling update. After rollout completes, verify the running pod reports the patched Node.js version. DoD: `kubectl exec` (or equivalent) into the new pod returns the patched Node.js version string; the portal health-check endpoint returns HTTP 200; no error spike is visible in the Prometheus/Grafana observability dashboard; ArgoCD application status is `Synced` and `Healthy`.

- [ ] 6. Close the CVE tracking items (depends on 5) — Update the security tracker (issue, ticket, or JIRA) for CVE-2026-21637, CVE-2026-21713, CVE-2026-21714, and CVE-2026-21717 to reflect the deployed fix, including the image tag, deployment date, and a link to the merged PRs. DoD: All four CVE items are marked as resolved with evidence of the deployed fix attached.

## Tests

- [ ] T1. Node.js version assertion — After the rollout, run `node --version` inside the production container and assert the output matches the expected patched release string (e.g., `v22.14.1` or the confirmed patch tag). Fail the test if the version is older.

- [ ] T2. SNICallback robustness smoke test (CVE-2026-21637) — Send a TLS ClientHello with a malformed/unexpected `servername` extension to the backend port (bypassing nginx, directly to the Node.js TLS listener if exposed internally, or via a test harness). Assert that the portal process continues to respond to subsequent requests and does not restart. DoD: Process PID remains unchanged after the malformed TLS handshake attempt; health endpoint returns HTTP 200 immediately after.

- [ ] T3. HTTP/2 session GC regression test (CVE-2026-21714) — Using an HTTP/2 client (e.g., `h2load` or a custom Node.js script), send a burst of requests that trigger WINDOW_UPDATE on stream 0 and then close sessions. After the burst, query the runtime heap stats (via `--inspect` or a metrics endpoint) and assert that Http2Session objects are not accumulating. DoD: Heap snapshot taken before and after the burst shows no unbounded growth in Http2Session-related allocations.

- [ ] T4. Playwright e2e regression suite — Run the full Playwright end-to-end suite against the staging or preview environment built on the patched image. DoD: All existing Playwright tests pass; no new failures are introduced by the runtime upgrade.

- [ ] T5. Health-check and catalog API post-deploy verification — After the ArgoCD rollout on `admins`, execute automated checks: (a) portal root returns HTTP 200, (b) `/api/catalog/entities` returns a valid JSON response, (c) auth redirect to Dex works. DoD: All three checks pass within 60 seconds of the rollout completing.

## Rollback

If any of tasks 3–5 produce failures that cannot be resolved within the change window:

1. **Dockerfile rollback** — Revert the `FROM` line change in the feature branch or open a revert PR targeting the previous Node.js 22.x image tag. The previous tag must be preserved in the container registry (do not delete it).

2. **mctl-gitops rollback** — Revert the image tag PR in `mctl-gitops` to restore the previous image tag in the Kubernetes manifests.

3. **ArgoCD forced sync** — Trigger an ArgoCD sync on the `admins` application with the reverted manifests. ArgoCD will perform a rolling update back to the previous image.

4. **Verification** — Confirm that the portal pod is running the previous Node.js image version (`node --version` inside the pod), health-check returns HTTP 200, and no error spike is present in the observability dashboard.

5. **Post-mortem** — Open a follow-up issue documenting what caused the regression, and re-plan the upgrade with the additional fix before re-attempting.

The rollback restores the previous state within one ArgoCD sync cycle (typically under 5 minutes). Because no database migrations, secret rotations, or API contract changes are part of this proposal, there is no data-plane risk in either direction.
