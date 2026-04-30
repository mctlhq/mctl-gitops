# Design: nodejs-security-upgrade

## Current state
mctl-portal is deployed as a Docker container (nginx + Node.js backend) managed by ArgoCD under the `admins` tenant (see `context/architecture.md`). The `package.json` declares `engines.node: "22 || 24"`. The Dockerfile (in `packages/backend/`) uses a Node.js 22 base image; the exact patch version in use is not pinned (typically `node:22-bookworm-slim` or similar floating tag), meaning the running patch version depends on when the image was last rebuilt.

CVE-2026-21710 affects the HTTP header parsing layer of Node.js itself, below the application and framework level. No application-level workaround (middleware, input validation) fully mitigates a vulnerability in the runtime's own HTTP parser. The only reliable fix is upgrading the runtime binary.

## Proposed solution
Pin the Node.js base image in `packages/backend/Dockerfile` (and any CI build matrix) to `node:22.22.2-bookworm-slim` (or the equivalent Alpine variant if Alpine is currently used). Additionally, tighten the `engines.node` field to `>=22.22.2 <23.0.0 || >=24.0.0` to prevent accidental use of vulnerable patch versions in local development or CI runners.

Change summary:
- `packages/backend/Dockerfile`: replace the base image `FROM` line with the pinned `node:22.22.2-bookworm-slim`.
- Root `package.json` → `engines.node`: tighten to `>=22.22.2 <23 || >=24`.
- CI workflow (`.github/workflows/*.yml` or equivalent): ensure the `node-version` matrix entry is set to `22.22.2`.
- After the image is built, verify `node --version` inside the container equals `v22.22.2`.
- Deploy via the standard ArgoCD image-tag update in mctl-gitops.

No Backstage application code, no plugin configuration, and no Kubernetes manifests beyond the image tag need to change.

## Alternatives

**Option A — Do not pin; rely on floating `node:22-bookworm-slim` tag and periodic image rebuilds**: The current implicit approach. Rebuilding the image today would pull the latest patch, which may already be 22.22.2. However, this provides no guarantee — a rebuild tomorrow could pull a newer (potentially broken) release, and there is no audit trail proving CVE-2026-21710 is resolved. Rejected because it does not satisfy the security officer's requirement for a documented, verifiable fix.

**Option B — Upgrade to Node.js 24 LTS at the same time**: Node.js 24 is listed in `engines.node` as already supported. A jump to 24 would also resolve the CVEs. However, it is a new major version and carries a higher risk of native addon or Backstage plugin incompatibilities. Rejected for this proposal; a separate proposal can evaluate a v24 migration when v22 reaches EOL.

**Option C — Apply a runtime-level HTTP header filter via a reverse proxy (nginx)**: Strip `__proto__` headers in the nginx layer before they reach the Node.js backend. This would mitigate CVE-2026-21710 specifically but leaves the other seven CVEs unaddressed and introduces ongoing operational complexity. Rejected because the proper fix is the runtime upgrade.

## Platform impact

**Migrations**: None. No database changes, no schema changes, no configuration changes beyond the Dockerfile and `engines.node` pin.

**Backward compatibility**: Node.js 22.22.2 is a patch release; all APIs remain stable. No Backstage or plugin code changes are required. All `yarn` workspaces and native addons (if any) that work on Node.js 22.x will continue to work on 22.22.2.

**Resource impact**: Node.js 22.22.2 has no documented increase in memory or CPU footprint compared to earlier 22.x releases. The `labs` tenant is not affected — mctl-portal is deployed exclusively under `admins`. No resource risk flagged.

**Risks and mitigations**:
- Risk: The pinned base image `node:22.22.2-bookworm-slim` is later found to have an OS-layer CVE. Mitigation: schedule a quarterly base-image refresh cadence independent of Node.js releases.
- Risk: A native addon (`better-sqlite3` or similar) fails to compile against the new binary ABI. Mitigation: Node.js 22.22.2 uses the same V8 and libuv ABI as 22.x; run `yarn install --force` in the image build to trigger any compilation step and fail fast.
- Risk: CI node-version matrix produces different behaviour at 22.22.2 vs. the previous version. Mitigation: run the full test suite on the pinned version in a PR before merging.
