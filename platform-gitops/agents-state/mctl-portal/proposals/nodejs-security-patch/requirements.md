# Node.js 22 LTS Security Patch (March 2026 Release)

## Context
The Node.js project published its March 2026 security release for the 22 LTS
line, addressing three CVEs that affect the Node.js runtime itself:

- **CVE-2026-21710** — crafted `__proto__` header values in HTTP/1.1 requests
  can trigger excessive memory allocation, causing a Denial-of-Service.
- **CVE-2026-21711** — the permission model incorrectly allows binding and
  listening on Unix Domain Sockets (UDS) that fall outside the permitted
  scope, enabling a partial permission-model bypass.
- **CVE-2026-21637** (follow-up) — the original SNI error-handling fix in a
  previous release was incomplete; crafted TLS ClientHello messages with
  certain SNI lengths can still crash the TLS stack.

mctl-portal's Dockerfile pins Node.js 22 LTS as its base image. The portal
backend is a publicly reachable HTTPS service, making CVE-2026-21710 (HTTP
DoS) and CVE-2026-21637 (TLS crash) directly exploitable. The fix is to
update the Node.js 22 LTS pin in the Dockerfile to the latest security
release that incorporates all three patches.

## User stories
- AS a platform engineer I WANT the mctl-portal container to run the latest
  patched Node.js 22 LTS release SO THAT the three March 2026 CVEs are
  not present in the production runtime.
- AS a site reliability engineer I WANT the portal to remain stable and
  available after the base-image update SO THAT the security patch does not
  introduce a regression.
- AS a security officer I WANT evidence that the Node.js CVEs are remediated
  SO THAT the findings can be closed in the vulnerability tracker.

## Acceptance criteria (EARS notation)
- WHEN the mctl-portal Docker image is built THE SYSTEM SHALL use a Node.js
  22 LTS base image at a version that includes patches for CVE-2026-21710,
  CVE-2026-21711, and CVE-2026-21637.
- WHEN the portal backend receives an HTTP request containing a crafted
  `__proto__` header THE SYSTEM SHALL process or reject the request normally
  without unbounded memory growth.
- WHEN a TLS ClientHello with a malformed SNI field is received THE SYSTEM
  SHALL handle the error gracefully without crashing the Node.js process.
- WHILE the base-image update is being rolled out THE SYSTEM SHALL continue
  serving requests using the existing image until the new image passes smoke
  tests and is promoted by ArgoCD.
- IF a `trivy` or equivalent image scan of the new image reports any
  remaining HIGH or CRITICAL CVEs against the Node.js runtime THEN the
  deployment SHALL be blocked until those findings are reviewed.

## Out of scope
- Upgrading from Node.js 22 to Node.js 24 — a separate upgrade proposal.
- CVE-2026-21711 permission-model bypass: mctl-portal does not use the
  Node.js permission model (`--experimental-permission`), so this CVE has
  no exploitable surface; patching is still required for defense-in-depth.
- Operating-system-level CVEs in the base image (e.g., Debian/Alpine) beyond
  the Node.js runtime — out of scope for this proposal.
- Changes to Backstage application code or dependencies.
