# Node.js v24 LTS Baseline

## Context
mctl-portal's `package.json` declares `"engines": { "node": "22 || 24" }`, but the Dockerfile base image and CI pipeline currently target Node.js 22. Node.js v24 ('Krypton') became the Active LTS on 2026-04-15 with release v24.15.0. Node.js 22 will reach End-of-Life in April 2027; migrating to v24 now avoids a time-pressured upgrade under EOL conditions. v24 also introduces security-relevant additions (raw key format in crypto APIs, new HTTP/2 configuration options) and performance improvements that benefit the Backstage Node backend.

## User stories
- AS a platform engineer I WANT the mctl-portal Docker image and CI pipeline to run on Node.js v24 LTS SO THAT the service uses the Active LTS runtime with up-to-date security patches.
- AS a developer I WANT the local development environment to default to Node.js v24 SO THAT parity between local and production is maintained.
- AS an ops engineer I WANT the engines field in package.json to reflect the actual production runtime SO THAT dependency audits and version-check tooling give accurate results.

## Acceptance criteria (EARS)
- WHEN the Docker image is built THE SYSTEM SHALL use a `node:24-alpine` (or equivalent) base image.
- WHEN CI runs the build, test, or lint jobs THE SYSTEM SHALL invoke Node.js v24.
- WHEN a developer runs `node --version` in a shell where the project's `.nvmrc` or `.node-version` is active THE SYSTEM SHALL report a v24.x version.
- WHILE the service is running on Node.js v24 in staging THE SYSTEM SHALL pass all existing Playwright e2e tests and health checks before promotion to production.
- IF a transitive dependency is incompatible with Node.js v24 THE SYSTEM SHALL surface the incompatibility as a CI failure and block promotion until resolved.

## Out of scope
- Upgrading to Node.js v26 (released 2026-05-07 as "current", not yet LTS).
- Changes to application code to use Node.js v24-exclusive APIs.
- Updating tenant `labs` workloads (mctl-portal runs in tenant `admins` only).
