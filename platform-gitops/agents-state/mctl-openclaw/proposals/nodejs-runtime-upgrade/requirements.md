# Upgrade Node.js runtime to a safe version + audit lockfile for malicious packages

## Context

The Node.js January 2026 Security Release closed eight CVEs, three of them rated High:
CVE-2025-55131 (buffer non-zerofilled — heap data leak via uninitialised buffers),
CVE-2025-55130 (symlink bypass — circumvents symlink restrictions during file I/O),
CVE-2025-59465 (HTTP/2 DoS — resource exhaustion via crafted HTTP/2 requests). Safe versions:
v20.20.0+, v22.22.0+, v24.13.0+. If the openclaw base Docker image uses Node.js below these
versions — all three vectors are active in production.

In parallel, two malicious npm packages were disclosed in late 2025: `lotusbail` (a Baileys
fork that steals WhatsApp auth tokens, intercepts messages, 56k+ downloads) and
`discord.js-user` (GHSA-69r6-7h4f-9p7q, CVSS 9.8, exfiltrates the Discord token). Both can
be present in transitive dependencies due to wrong package.json entries or typosquatting.
The focus of this proposal differs from `npm-supply-chain-audit` (which is about poisoned
packages as a class): here the scope is limited to those two specific known packages plus
a Node.js runtime bump in the Dockerfile.

## User stories

- AS a platform security engineer I WANT the openclaw Docker base image upgraded to a Node.js
  version >= v22.22.0 SO THAT three High CVEs from the January security release are not
  active in the production runtime
- AS a platform operator I WANT the CI step `npm audit --audit-level=high` in the openclaw
  image pipeline SO THAT new High/Critical dependency vulnerabilities block the build before
  reaching deploy
- AS a security engineer I WANT an automatic check of the lockfile for the presence of
  `lotusbail` and `discord.js-user` SO THAT malicious supply-chain packages are caught before
  a deploy to any tenant
- AS a labs tenant operator I WANT the Node.js runtime upgrade not to increase RAM consumption
  SO THAT the labs tenant does not approach OOM after the base image bump

## Acceptance criteria (EARS)

- WHEN the openclaw Docker image is built in CI THE SYSTEM SHALL use a Node.js base image
  no older than v22.22.0 LTS (or v20.20.0 / v24.13.0 depending on the chosen LTS line)
- WHEN CI builds the openclaw image THE SYSTEM SHALL run `npm audit --audit-level=high`
  and fail the build if High or Critical vulnerabilities are found
- WHEN CI builds the openclaw image THE SYSTEM SHALL inspect `package-lock.json` for the
  presence of the names `lotusbail` and `discord.js-user` (direct and transitive dependencies)
  and fail the build on detection
- IF the Node.js runtime upgrade causes incompatibility with openclaw code or its plugins
  THEN THE SYSTEM SHALL not promote the image to admins and ovk until the incompatibility is fixed
- WHILE a new image is deployed in labs THE SYSTEM SHALL not increase the openclaw pod's RAM
  consumption by more than 20MB compared to the baseline (Node.js minor bump, not major)
- WHEN an image with the updated Node.js runtime is deployed in labs THE SYSTEM SHALL pass
  the restore-state probe within the standard timeout (ADR 0002)
- WHEN `npm audit` or the malicious-package grep detect an issue in CI THE SYSTEM SHALL
  notify the team via the alert channel and block merge/deploy

## Out of scope

- Upgrading Node.js to a major version (v22 → v24) — requires a separate compatibility
  validation; a patch to a safe minor on the current LTS line suffices
- Wide audit of the entire supply chain (every potentially malicious package) — covered by the
  separate `npm-supply-chain-audit` proposal
- Upgrading TypeScript to 6.x (no security CVE, no urgency)
- Upgrading Baileys, discord.js, node-slack-sdk (separate proposals as needed)
- Changes to openclaw configuration or skills
- Changes to pod resource limits (if the RAM delta is within bounds)
