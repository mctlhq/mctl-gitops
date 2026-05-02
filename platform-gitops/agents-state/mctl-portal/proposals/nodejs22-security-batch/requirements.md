# Node.js 22 security upgrade to v22.22.2

## Context
Node.js v22.22.2 was released to address two High-severity CVEs affecting the runtime used by mctl-portal: CVE-2026-21637 (TLS SNI processing denial-of-service) and CVE-2026-21710 (`__proto__` header injection denial-of-service). Both vulnerabilities can be triggered by malformed incoming requests and are capable of crashing the Backstage backend process without authentication, making them directly exploitable against a public-facing service. The release also patches four Medium CVEs (timing side-channel, HTTP/2 memory leak, HashDoS, Permission Model bypass) and two Low CVEs.

mctl-portal runs Node.js 22 LTS in its Docker base image. The `engines.node` field in `package.json` specifies `22 || 24`, so the runtime is fully compatible with 22.22.2. The fix is a single Docker base-image version bump with no application code changes.

## User stories
- AS a platform engineer I WANT the mctl-portal Docker image to use Node.js v22.22.2 SO THAT the two high-severity DoS CVEs are eliminated from the runtime.
- AS a security officer I WANT all High-severity Node.js CVEs resolved within the platform SLA SO THAT mctl-portal's risk posture is within acceptable bounds.
- AS an on-call engineer I WANT the Backstage backend process to be resilient to malformed TLS and HTTP requests SO THAT a single bad request cannot take down the portal and trigger an incident.

## Acceptance criteria (EARS)
- WHEN the mctl-portal Docker image is built THE SYSTEM SHALL use a Node.js 22 base image at version ≥22.22.2.
- IF the container runtime reports the Node.js version THE SYSTEM SHALL return a value ≥22.22.2 (verified via `node --version`).
- WHEN a CVE scanner is run against the production image THE SYSTEM SHALL produce no findings for CVE-2026-21637 or CVE-2026-21710.
- WHILE the updated image is running in the `admins` tenant THE SYSTEM SHALL serve all Backstage routes without regression.
- WHEN the updated image is deployed via ArgoCD THE SYSTEM SHALL complete the rolling update without any period where zero pods are running.

## Out of scope
- Upgrading Node.js to v24 (a separate proposal; engine constraint already allows it but requires separate validation).
- Patching application-level code for any of the Medium/Low CVEs (all are runtime-level fixes in Node.js itself).
- Changes to the Backstage application dependencies or yarn.lock.
- Any changes to the `labs` tenant — this proposal only affects the `admins` tenant deployment. (Note: if `labs` runs a Node.js service that uses the same base image, it should be assessed separately; any memory impact there must be flagged as risky given `labs` is near its memory limit.)
