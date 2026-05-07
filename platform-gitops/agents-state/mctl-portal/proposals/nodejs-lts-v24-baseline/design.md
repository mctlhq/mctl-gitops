# Design: nodejs-lts-v24-baseline

## Current state
The `Dockerfile` in the repository uses a `node:22-alpine` base image (or equivalent). CI workflow files reference Node.js 22. The `package.json` `engines` field already declares `"node": "22 || 24"`, anticipating this migration. No application code uses Node.js 22-specific or v24-incompatible APIs.

## Proposed solution
Three coordinated changes:

1. **Dockerfile:** Replace `FROM node:22-alpine` with `FROM node:24-alpine` (or the exact digest of the latest v24.15.x LTS image for reproducibility).
2. **CI pipeline:** Update the `node-version` matrix/input in GitHub Actions (or the equivalent CI config) from `22` to `24`.
3. **`.nvmrc` / `.node-version`:** Update the version pin file used by nvm/fnm to `24`.

Optionally, narrow the `engines` field from `"22 || 24"` to `"24"` once staging validation passes, to make the constraint explicit.

The change is low-risk: Backstage's own CI runs on Node.js 22 and 24; v24 support is well-tested in the ecosystem. No code changes are required — the migration is purely an infrastructure/tooling update.

## Alternatives

### A. Keep Node.js 22 until closer to EOL (April 2027)
Defers effort but creates a time-pressured upgrade in ~11 months. Also means missing v24 security patches (raw key format hardening, HTTP/2 improvements) in the interim. Dropped.

### B. Upgrade directly to Node.js v26
v26 was released 2026-05-07 as "current" (non-LTS). It introduces breaking changes (Temporal API by default, Undici 8.0, V8 14.6) and has no LTS support window yet. Dropped as premature; revisit when v26 becomes LTS (~October 2026).

### C. Support both v22 and v24 in CI matrix
Running two CI lanes costs more CI minutes and adds maintenance overhead. The `engines` field already permits v24; the goal is to standardise on it, not maintain dual support. Dropped.

## Platform impact
- **Migrations:** No application code changes required. Docker base image and CI config only.
- **Backward compatibility:** `package.json` engines field already permits v24. Backstage packages are tested on v24 by the upstream project.
- **Resource impact:** No meaningful change in memory or CPU footprint. Tenant `labs` is unaffected.
- **Risks and mitigations:**
  - *Transitive dep incompatibility:* Mitigated by running `yarn install` and the full test suite on v24 in CI before merging.
  - *Native addons:* Backstage's standard plugin set does not use native Node addons; risk is negligible.
  - *Docker image availability:* `node:24-alpine` is available on Docker Hub; no custom registry changes needed.
