# Design: nodejs-security-march-2026

## Current state
mctl-portal is containerised as a Dockerfile-based image (see `context/architecture.md`). The `FROM` line in the Dockerfile pins a specific Node.js 22.x base image (e.g., `node:22.x.x-bookworm-slim` or equivalent). The application's `package.json` declares `"engines": { "node": "22 || 24" }`, so the runtime version contract already allows 22.22.2. The built image is pushed to the container registry, referenced in the mctl-gitops Helm values, and deployed to the `admins` tenant via ArgoCD.

Currently two High-severity CVEs are exploitable in the running runtime:
- **CVE-2026-21637** — TLS layer: a malformed ClientHello packet can trigger a memory corruption path in the TLS implementation, causing the Node.js process to crash (DoS).
- **CVE-2026-21710** — HTTP parser: a header named `__proto__` or containing prototype-pollution characters can cause the HTTP server to hang or crash.

Both vulnerabilities are reachable without authentication from the internet via `https://app.mctl.ai`.

## Proposed solution
Update the Docker base image pin from the current Node.js 22 patch version to `node:22.22.2-bookworm-slim` (or the equivalent Alpine/distroless variant in use). This is the only change required; no application code, npm dependencies, Helm chart, or Kubernetes resource changes are needed.

Delivery steps:
1. Update the `FROM` line in the `Dockerfile` (or the base image ARG if parameterised) to `node:22.22.2-bookworm-slim`.
2. Verify the `engines.node` field in `package.json` satisfies `22.22.2` (it already does via `"22 || 24"`).
3. Build the Docker image locally; run `node --version` inside the image to confirm `v22.22.2`.
4. Run the full CI pipeline (lint, type-check, unit tests, integration tests, playwright e2e).
5. Push the image to the registry with a new tag; update the image tag in the mctl-gitops Helm values.
6. Merge to main; ArgoCD rolling-update delivers the new pod while keeping at least one old pod alive.

This is the minimal-risk approach: a single-line Dockerfile change, no npm changes, no code changes.

## Alternatives

### 1. Upgrade to Node.js 24 LTS
Node.js 24 is also within the declared engine range. A major runtime upgrade would deliver future security patches proactively. Rejected for this proposal because a major Node.js version change warrants dedicated testing (native addon compatibility, V8 behavioural differences, etc.) and is disproportionate to the goal of patching two known CVEs quickly. Deferred to a separate proposal.

### 2. Apply OS-level patches without changing the base image tag
Some base image distributions receive backported runtime patches as OS packages. Running `apt-get upgrade` inside the Dockerfile could theoretically pull in a patched Node.js binary. Rejected because this approach produces a non-deterministic build; the patched binary availability depends on the apt mirror state at build time, and the result is not reproducible.

### 3. Upgrade only the affected Node.js built-ins via npm overrides
There is no npm-level equivalent for Node.js core CVEs; the vulnerability lives in the compiled runtime binary. This option is not technically feasible.

## Platform impact

### Migrations
None. The application code, database schema, and Kubernetes resource definitions are unchanged.

### Backward compatibility
Node.js patch releases within the same major version are guaranteed backward compatible by the Node.js release policy. The `engines.node` field already permits 22.22.2. No API or behaviour changes are expected.

### Resource impact (especially for `labs`)
The base image change is a runtime-only upgrade. CPU and memory footprint of Node.js 22.22.2 is not meaningfully different from the prior 22.x patch. Resource requests and limits in the Helm chart are unchanged. The `labs` tenant does not run mctl-portal; there is no resource impact on `labs`. This upgrade is rated neutral for resource consumption.

### Risks and mitigations
- **Risk:** The new base image includes OS package updates that introduce a regression in a system library used by a native Node addon (e.g., `better-sqlite3`, `canvas`). **Mitigation:** Run the full integration and e2e test suite against the new image before deployment; review the base image changelog for library versions.
- **Risk:** A rolling restart causes a brief period of mixed Node.js versions in the pod fleet. **Mitigation:** Both versions handle the same application code identically; mixed-version windows are expected to be under 2 minutes given the pod count.
- **Risk:** ArgoCD image tag update in mctl-gitops triggers an unrelated sync of other resources. **Mitigation:** Scope the mctl-gitops PR to only the image tag field in the Helm values file.
