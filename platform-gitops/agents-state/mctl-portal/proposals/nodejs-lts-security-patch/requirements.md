# Bump Node.js 22.x/24.x to latest patched LTS

## Context
mctl-portal's `engines.node` field targets Node 22 || 24 (`context/architecture.md`,
`context/current-version.md`). The June and July 2026 Node.js security releases fix
several HIGH-severity vulnerabilities directly relevant to a Backstage backend
service: unbounded memory growth in `node:http2` clients (CVE-2026-48619, a DoS
vector — relevant since Backstage backend handles many HTTP/2-capable connections),
a permission-model bypass (CVE-2026-48617), and an mTLS SNI authorization bypass
(CVE-2026-48928), among others (CVE-2026-48933, CVE-2026-48618, CVE-2026-48615,
CVE-2026-48937). These land in Node 22.23.2 and 24.18.1/24.20.0.

This is a low-effort, patch-version runtime bump within the already-supported 22/24
lines — no `engines` field change, no code changes expected. Given the DoS and
authorization-bypass nature of the fixed CVEs, and that mctl-portal is an
internet-facing developer portal (`https://app.mctl.ai`), staying current on Node
LTS security patches is a baseline hygiene item.

## User stories
- AS a platform security engineer I WANT mctl-portal's runtime to run the latest
  patched Node.js 22.x/24.x LTS SO THAT known HTTP/2, permission-model, and TLS
  authorization vulnerabilities are closed.
- AS an SRE I WANT the Node.js bump to be a drop-in runtime change SO THAT no
  application code needs to be touched or re-validated beyond standard CI.
- AS a mctl-portal maintainer I WANT this tracked and repeatable SO THAT future
  Node.js security releases can be picked up with the same low-effort process.

## Acceptance criteria (EARS)
- WHEN the CI/CD pipeline builds the mctl-portal Docker image THE SYSTEM SHALL use a
  base image pinned to Node 22.23.2 or newer within the 22.x line, or Node 24.18.1 /
  24.20.0 or newer within the 24.x line.
- WHEN the application starts on the upgraded Node runtime THE SYSTEM SHALL pass the
  full existing test suite (unit, integration, and e2e) without modification to
  application source code.
- WHILE running on the upgraded Node version THE SYSTEM SHALL continue to satisfy the
  `engines` field constraint declared in `package.json` (Node 22 || 24) — the bump
  stays within the same major lines, no `engines` field change is required.
- IF a future Node.js LTS security release (22.x or 24.x) is published THEN THE
  SYSTEM SHALL be able to adopt it via the same base-image-pin bump process with no
  additional design work.
- IF the CI test suite fails on the new Node version THEN THE SYSTEM SHALL NOT be
  deployed until the failure is triaged and resolved.

## Out of scope
- Moving to Node 26.x (current/non-LTS line) — informational only per the researcher,
  not an LTS line, not adopted.
- Any change to the `engines` field's major-version range (22 || 24) — this proposal
  stays within already-supported majors.
- Application code changes to adopt new Node 24.x features (e.g. `using` scopes for
  AsyncLocalStorage, JSPI for WebAssembly) — tracked as a separate, future
  enhancement if ever pursued.
