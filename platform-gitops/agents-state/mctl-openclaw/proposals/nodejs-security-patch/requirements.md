# Update Node.js Docker base image to patch two high-severity process-crash CVEs

## Context

The mctl-openclaw service runs openclaw on Node.js inside Docker containers deployed to Kubernetes. All active Node.js LTS lines (20.x, 22.x, 24.x) are affected by two high-severity vulnerabilities patched in the March 2026 security release: CVE-2026-21637 (TLS SNICallback uncaught exception — a synchronous exception in `loadSNI()` bypasses all TLS error handlers and terminates the process) and CVE-2026-21710 (HTTP `__proto__` header — a crafted `__proto__` header triggers an uncaught TypeError through `req.headersDistinct` and crashes the process). Both have been patched since Node.js 22.22.2 / 20.20.2 (released 2026-03-24).

A Node.js process crash in a Kubernetes pod triggers an unplanned pod restart. Before the restore-state readiness probe completes (see ADR-0002), the restarting pod is not ready and channel sessions served by `ovk` are temporarily unavailable — a direct SLA risk for the production customer. Patching requires only a Docker base image bump; no application code changes are needed and RSS impact is negligible.

## User stories

- AS a platform engineer I WANT the Node.js Docker base image updated to a patched LTS release SO THAT CVE-2026-21637 and CVE-2026-21710 cannot be exploited to crash openclaw pods.
- AS an `ovk` operator I WANT process-crash vulnerabilities eliminated SO THAT crafted TLS or HTTP requests cannot cause channel downtime for production customers.
- AS a security officer I WANT to confirm all three tenants run the patched Node.js version SO THAT I can close the CVE tracking tickets.

## Acceptance criteria (EARS)

- WHEN the Docker image for any tenant is rebuilt, THE SYSTEM SHALL use a Node.js base image at version 22.22.2 or later (or the equivalent patched release on the selected LTS line).
- WHEN a pod is restarted on any tenant, THE SYSTEM SHALL NOT crash in response to a TLS connection attempt that triggers an SNICallback exception (CVE-2026-21637).
- WHEN a pod receives an HTTP request containing a `__proto__` header, THE SYSTEM SHALL NOT crash or produce an uncaught TypeError (CVE-2026-21710).
- WHEN the new image is built and pushed, THE SYSTEM SHALL confirm the Node.js version by running `node --version` inside the image as part of the CI build step.
- WHILE the patched image is deployed on `ovk`, THE SYSTEM SHALL maintain restore-state probe continuity: the probe must pass within the configured timeout after each pod restart, confirming S3 state is restored before traffic is accepted.
- IF the restore-state readiness probe does not pass within the configured timeout on any tenant after the image update, THEN THE SYSTEM SHALL NOT mark the rollout successful and SHALL trigger a rollback.
- WHEN the image update is applied to all three tenants, THE SYSTEM SHALL produce a rollout log entry for each tenant confirming the patched Node.js version is running.

## Out of scope

- Upgrading Node.js to a new major LTS line (e.g., moving from 22.x to 24.x); this proposal targets a security patch on the current LTS line only.
- Any changes to application code, workspace extension packages, or Kubernetes manifests beyond the Dockerfile base image line.
- Upgrading the openclaw application version — covered by the separate `openclaw-cve-upgrade` proposal.
- Addressing CVE-2026-21713 (HMAC timing side-channel, medium severity) as a separate effort — it is also fixed by the same patched Node.js release and is resolved as a side effect.
- Changing the rollout order or the S3 canary / restore-state probe setup — ADR-0001 and ADR-0002 procedures apply unchanged.
