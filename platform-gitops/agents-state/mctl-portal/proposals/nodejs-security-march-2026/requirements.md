# Node.js 22 March 2026 Security Releases (CVE-2026-21637, CVE-2026-21710)

## Context
mctl-portal runs on Node.js 22 in production (pinned in the Docker base image). The Node.js project published its March 2026 security batch, which addresses nine CVEs including two rated High severity: CVE-2026-21637 (remote TLS denial-of-service via malformed ClientHello records) and CVE-2026-21710 (HTTP header `__proto__` injection DoS). Both vulnerabilities are reachable from the public-facing Backstage backend (`https://app.mctl.ai`). The patched runtime is Node.js 22.22.2 LTS, a drop-in replacement that requires only the base image pin to be updated and CI to be re-run.

Additionally, five Medium-severity CVEs are resolved in the same release: an HTTP/2 memory leak, a HashDoS in the URL parser, and an HMAC timing side-channel. Remaining on the current Node.js 22 pin exposes mctl-portal's backend to availability attacks that require no authentication and can be triggered from the internet.

## User stories
- AS a platform security officer I WANT mctl-portal's Node.js runtime updated to 22.22.2 SO THAT the two High-severity DoS vulnerabilities are no longer reachable from the public-facing backend.
- AS a portal engineer I WANT the runtime upgrade applied solely as a base image change SO THAT no application code modifications are required and existing functionality is preserved.
- AS an on-call engineer I WANT the updated image delivered through the standard mctl-gitops/ArgoCD pipeline SO THAT the change is auditable, observable, and rollbackable.

## Acceptance criteria (EARS)
- WHEN the mctl-portal backend container starts THE SYSTEM SHALL report a Node.js version of 22.22.2 or higher.
- WHEN a TLS ClientHello crafted to trigger CVE-2026-21637 is received by the backend THE SYSTEM SHALL handle it without crashing or entering an unresponsive state.
- WHEN an HTTP request containing a `__proto__` header targeting CVE-2026-21710 is received THE SYSTEM SHALL handle it without crashing or entering an unresponsive state.
- WHILE the new image is being rolled out THE SYSTEM SHALL maintain at least one healthy backend pod available to serve traffic (rolling update strategy).
- IF the post-deployment health check fails THE SYSTEM SHALL halt the rollout and ArgoCD SHALL report the application as `Degraded`, enabling immediate rollback.
- WHEN the updated image is deployed to the `admins` tenant THE SYSTEM SHALL pass all existing unit, integration, and end-to-end tests with no regressions.
- WHEN the base image is updated THE SYSTEM SHALL NOT increase the memory or CPU resource requests or limits for any pod in the `admins` or `labs` tenants.

## Out of scope
- Upgrading Node.js beyond the 22.x LTS line (e.g., to Node.js 24) — that is a separate upgrade proposal.
- Changes to application code, Backstage plugins, or scaffolder templates.
- Changes to the `labs` tenant workloads (mctl-portal is not deployed there).
- Operating system or system-library patches beyond what is included in the updated base image.
- Remediation of CVEs in npm dependencies (addressed separately).
