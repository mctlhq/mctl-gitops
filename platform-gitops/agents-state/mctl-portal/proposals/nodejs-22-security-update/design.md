# Design: nodejs-22-security-update

## Current state
mctl-portal is built as a Docker image and deployed to tenant `admins` via nginx + ArgoCD (see `context/architecture.md`). The Dockerfile uses an official Node.js 22 base image. The exact current patch tag is not pinned in this record but it predates v22.22.3 (released 2026-05-13). The `engines.node` field in `package.json` declares `"22 || 24"`.

The vulnerabilities addressed in v22.22.3 are runtime-level:
- **Zlib use-after-free** — can cause memory corruption or crash under specific compression workloads.
- **HTTP2 FileHandle leak** — gradual memory leak under sustained HTTP/2 traffic.
- **URL parser crash** — a malformed UNC hostname in a URL can crash the Node.js process.
- **HTTP keep-alive race** — may result in corrupted responses or dropped connections.
- **OpenSSL 3.5.5 → 3.5.6** — incremental security fix in the TLS layer.
- **Root certificates refreshed** — NSS 3.121 trust store update.

None of these require application code changes; they are fixed by running on a patched runtime.

## Proposed solution
Update the `FROM` line in the mctl-portal `Dockerfile` to reference `node:22.22.3-alpine` (or the slim/distroless variant currently in use), rebuild the image, push it to the registry, update the image tag in the mctl-gitops Helm values for `admins`, and let ArgoCD roll out the change.

The change is exactly one line in the Dockerfile. The rest of the build — yarn install, TypeScript compilation, nginx configuration, and the entrypoint — is unchanged. Because the Node.js version stays on the same major.minor line, no application code adjustments are needed.

Deployment sequence:
1. Update `FROM node:22.X.X-<variant>` to `FROM node:22.22.3-<variant>` in the Dockerfile.
2. Build and tag the new image (e.g., `mctl-portal:1.0.1-node22.22.3`).
3. Run container-level smoke checks (health endpoint, version assertion).
4. Push to the container registry.
5. Update the image tag in mctl-gitops Helm values for `admins`.
6. ArgoCD syncs; rolling update replaces the pod with zero downtime.

## Alternatives

**Option A — Use a floating tag (`node:22-alpine`).**
A floating tag would pull the latest Node.js 22 patch automatically on each build. Dropped because: floating tags make builds non-reproducible and are inconsistent with the pinning strategy already used for other dependencies. Explicit pinning to `22.22.3` is safer and auditable.

**Option B — Upgrade to Node.js 24.**
`engines.node` already allows `"22 || 24"` and Node.js 24 is available. Dropped because: a major runtime upgrade (22 → 24) carries broader compatibility risk (native addons, subtle V8 behavior changes) and needs its own proposal and test cycle. The security goal here is met by patching within the Node.js 22 line.

**Option C — Apply patches via OS package manager inside the existing base image.**
Some teams overlay a base image and install Node.js from a package manager rather than using the official Node.js Docker image. Dropped because: mctl-portal already uses the official Node.js Docker image which bundles Node.js natively; switching to OS-level package management adds complexity and diverges from the upstream image supply chain.

## Platform impact

**Migrations:** None. No schema, API, configuration, or Kubernetes manifest changes.

**Backward compatibility:** Node.js 22.22.3 is backward compatible with all 22.x application code. No breaking changes in the Node.js 22 LTS changelog between the previous patch and 22.22.3.

**Resource impact:** The new base image may differ slightly in size (Alpine/slim layer). CPU and memory footprint of the running service is not expected to change materially. No impact on the `labs` tenant — mctl-portal runs exclusively in `admins`.

**Risks and mitigations:**
- Risk: The new base image has a different Alpine/Debian version that removes or changes a system library depended on by a native Node.js module. Mitigation: verify `yarn install` and `node_modules` native rebuild succeed in the Docker build step; check build logs for any `gyp` errors.
- Risk: OpenSSL 3.5.6 changes TLS behaviour that breaks an external integration (Dex, Vault, GitHub). Mitigation: run the Playwright e2e suite in staging, which exercises the auth flow and external API calls.
- Risk: Deployment fails and the new pod never becomes healthy. Mitigation: ArgoCD rolling update — old pod stays up until readiness probe passes; rollback is a one-line image tag revert in mctl-gitops.
