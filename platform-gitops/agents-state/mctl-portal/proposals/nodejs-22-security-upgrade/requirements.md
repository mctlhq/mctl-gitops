# Node.js 22.22.2 Security Upgrade

## Context
The mctl-portal Docker base image is currently pinned to an unpatched Node.js 22 release. Node.js v22.22.2 (released 2026-03-24) patches 8 CVEs against the v22 LTS line. Two are high-severity: CVE-2026-21637 (SNICallback exception bypass leading to process crash) and CVE-2026-21710 (headersDistinct prototype pollution enabling denial-of-service). The January 2026 batch (v22.22.0+) also addressed a buffer memory leak and an HTTP/2 DoS vector. All of these affect the Node.js runtime that directly executes the Backstage backend process.

Running an unpatched runtime exposes the portal backend to process-level crashes that would take the entire `admins` portal offline, and to prototype pollution attacks that could be chained with application-layer vulnerabilities. The fix is a base-image update to `node:22.22.2-alpine` (or a functional equivalent) plus alignment of the CI Node.js version pin.

## User stories
- AS a platform security engineer I WANT the portal Docker base image updated to `node:22.22.2-alpine` SO THAT all 8 CVEs patched in the March 2026 Node.js security release are remediated.
- AS a portal operator I WANT the CI pipeline Node.js version pin updated to match the base image SO THAT CI and production run identical runtime versions and version drift does not reintroduce vulnerabilities.
- AS a platform engineer I WANT the upgrade to stay on the Node.js 22 LTS line SO THAT no engine compatibility changes are needed in Backstage or custom plugins.

## Acceptance criteria (EARS)
- WHEN the Docker image is built THE SYSTEM SHALL use `node:22.22.2-alpine` (or an equivalent image digest pinned to v22.22.2) as the base image.
- WHEN the CI pipeline runs Node.js-dependent steps THE SYSTEM SHALL execute them under Node.js v22.22.2 or higher within the v22 LTS line.
- WHILE the backend pod is running THE SYSTEM SHALL report `process.version` as `v22.22.2` or higher when queried via the health endpoint or `kubectl exec`.
- IF a TLS handshake triggers an SNICallback exception THE SYSTEM SHALL handle the exception without crashing the Node.js process (CVE-2026-21637 regression guard).
- IF HTTP response headers include a property that could pollute `Object.prototype` via headersDistinct THE SYSTEM SHALL not alter the prototype chain of any object in the Node.js process (CVE-2026-21710 regression guard).
- WHEN the updated image is deployed to `admins` THE SYSTEM SHALL pass all existing health checks and the Backstage backend shall start cleanly with no new runtime errors.

## Out of scope
- Upgrading Node.js beyond the v22 LTS line (e.g., to v24).
- Changes to Backstage package versions or Backstage application code.
- Changes to nginx configuration or the frontend container.
- OS-level CVE patching outside the Node.js runtime.
