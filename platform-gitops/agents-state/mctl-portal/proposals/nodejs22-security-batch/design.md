# Design: nodejs22-security-batch

## Current state
The mctl-portal Dockerfile uses a Node.js 22 LTS base image. The exact version is pinned (or floated on a minor/patch tag) in the `Dockerfile` in `packages/backend/`. The current base image version is below 22.22.2, meaning the running container is exposed to:

- **CVE-2026-21637** (High): A crafted TLS ClientHello with a malformed SNI extension triggers an unhandled exception in the TLS stack, crashing the Node.js process.
- **CVE-2026-21710** (High): An HTTP request containing a `__proto__` header bypasses property sanitisation and corrupts the prototype chain of the request object, causing a process crash or unexpected behaviour.
- 4 Medium CVEs: HTTP/2 memory leak under sustained load, timing side-channel in crypto comparison, HashDoS via crafted URL parameters, Permission Model bypass.
- 2 Low CVEs: informational.

Because mctl-portal is publicly reachable at `https://app.mctl.ai`, the High-severity DoS vectors are directly exploitable by unauthenticated network actors.

## Proposed solution
Update the Docker base image in `packages/backend/Dockerfile` (and `packages/app/Dockerfile` if it also uses a Node.js image) from the current `node:22-alpine` (or `node:22-bookworm-slim`, depending on what the Dockerfile uses) to `node:22.22.2-alpine` (or the equivalent slim variant).

**Pinning strategy:** Use the explicit patch version tag (`node:22.22.2-alpine`) rather than a floating tag (`node:22-alpine`) to make future audits and CVE reports deterministic. A Renovate or Dependabot rule should be configured to auto-open PRs for future Node.js patch releases.

**Why this approach:**
The fix is entirely in the Node.js runtime layer. No application code, Backstage configuration, or yarn dependencies change. The base-image bump is the minimal, lowest-risk intervention.

## Alternatives

### Option A — Upgrade to Node.js 24 (deferred)
Node.js 24 is already in the `engines.node` constraint and would also resolve these CVEs. However, a major runtime version change requires broader compatibility validation (native addons, TypeScript target, ESM behaviour changes). This is appropriate as a separate, planned proposal rather than a security-patch fix. Deferred.

### Option B — Float on `node:22-alpine` and rely on nightly rebuilds (rejected)
Accept that the CI pipeline rebuilds the image nightly using `node:22-alpine`, which would eventually pull a patched version. This is non-deterministic and does not guarantee the patched version is deployed within the security SLA. Rejected.

### Option C — Runtime WAF/reverse-proxy filtering of malformed TLS/HTTP (rejected)
Deploy an ingress-layer WAF (e.g., ModSecurity) to drop malformed TLS SNI and `__proto__` header requests before they reach Node.js. This adds infrastructure complexity, is difficult to tune without false positives, and does not fix the underlying runtime vulnerability. Rejected as the sole remedy; acceptable as defence-in-depth after the base image is patched.

## Platform impact

**Migrations:** None. The application code, database schema, and configuration are unchanged.

**Backward compatibility:** Node.js 22.22.2 is a patch release. No breaking API changes. All npm packages and native addons compatible with Node.js 22.x remain compatible.

**Resource impact:** Node.js 22.22.2 carries no significant memory or CPU changes relative to the previous 22.x patch. The HTTP/2 memory leak fix (Medium CVE) may marginally reduce memory consumption under sustained TechDocs or proxy traffic. No negative memory impact on the `labs` tenant — this change only affects the `admins` tenant Docker image. If the same base image is shared with any `labs` workload, the memory-leak fix is net-positive, but any deployment change to `labs` should be reviewed separately given its proximity to the memory limit.

**Risks and mitigations:**
- Risk: The new base image has a different digest and triggers an unrelated OS-layer change (e.g., Alpine patch). Mitigation: review the image diff in the PR; any unexpected OS package changes should be verified against the CVE scanner.
- Risk: A native npm package (if any) has a prebuilt binary for Node 22.x that is not compatible with 22.22.2. Mitigation: `yarn install --frozen-lockfile` in the Docker build will rebuild any native modules; CI will surface failures.
- Risk: The rolling update leaves a brief window with mixed image versions. Mitigation: ArgoCD's default rolling update strategy ensures at least one healthy pod is always running; readiness probes gate traffic to the new pod.
