# Design: nodejs-22-security-upgrade

## Current state
The mctl-portal backend is containerised using a multi-stage Dockerfile (see `context/architecture.md`). The build stage and the runtime stage both reference a Node.js 22 base image, currently pinned to a version prior to v22.22.2. The CI pipeline (GitHub Actions or equivalent) also pins a Node.js version for `yarn install`, `yarn build`, and test steps. The `engines.node` field in `package.json` is `22 || 24`, so both the image and CI pin are within the declared range, but neither is at the patched version.

CVEs CVE-2026-21637, CVE-2026-21710, and the January 2026 buffer/HTTP2 batch all exist in the runtime binary itself — they cannot be addressed at the application layer. The only correct fix is to replace the runtime binary by updating the base image tag.

## Proposed solution
Update the Dockerfile `FROM` directive in the runtime stage (and the build stage if it is a separate image) to `node:22.22.2-alpine`. Alpine is already the variant in use (small footprint, no unnecessary OS packages). Pin by tag; optionally also add a `# digest: sha256:...` comment for supply-chain auditability.

Update the CI Node.js version matrix (`.github/workflows/*.yml` or equivalent) to `22.22.2`. This ensures yarn install, lint, unit tests, and playwright e2e all run on the same patched runtime as production, eliminating version drift.

No changes to application code, Backstage packages, or infrastructure manifests are needed. After the Dockerfile change, the standard CI build produces a new image that ArgoCD deploys to the `admins` tenant.

## Alternatives

**Option A — Upgrade to Node.js 24 LTS.**
Node.js 24 is within the declared `engines.node` range. However, a major runtime upgrade has a larger testing surface (native module compatibility, V8 behaviour changes) and is not necessary to close the specific CVEs. A dedicated Node.js 24 migration proposal is a better vehicle for this. Dropped to keep blast radius minimal.

**Option B — Apply OS-level patches to the existing Alpine image without changing the Node.js version.**
Alpine `apk upgrade` could patch some Alpine-layer CVEs but cannot patch the Node.js binary itself, which is installed from the upstream Node.js Docker layer, not from Alpine's package index. This approach does not address any of the 8 Node.js CVEs. Dropped as ineffective.

**Option C — Use a Distroless or UBI-based Node.js 22.22.2 image.**
A Distroless or Red Hat UBI image would also carry the patched runtime. However, mctl-portal's existing Dockerfile already uses Alpine and benefits from Alpine's small attack surface. Switching base image family introduces untested differences in shell tooling used during the Docker build steps. Dropped in favour of the minimal change: stay on Alpine, just bump the version tag.

## Platform impact

**Migrations:** None. No filesystem layout changes, no new environment variables, no Kubernetes manifest changes.

**Backward compatibility:** Node.js patch releases within the same major line (v22) are binary-compatible. All npm/yarn packages, native addons (if any), and Backstage plugins will continue to function without modification.

**Resource impact:** Alpine base image size may change by a few MB between patch versions; this is negligible. CPU and memory footprint of the backend pod in tenant `admins` are unchanged. No `labs` tenant resources are affected.

**Risks and mitigations:**
- Risk: a subtle behaviour change in the patched V8 or libuv triggers a runtime error in a Backstage plugin. Mitigation: the full playwright e2e suite runs in CI against the new image before promotion; rollback is a one-line Dockerfile change.
- Risk: Alpine package pinning conflicts with the new node version layer. Mitigation: the Alpine Linux packages in the runtime stage are not pinned to specific versions, so the Alpine layer is independent of the Node.js version tag.
- Risk: CI and image are updated separately and create a window of drift. Mitigation: update both the Dockerfile and CI pin in the same PR so they are always in sync.
