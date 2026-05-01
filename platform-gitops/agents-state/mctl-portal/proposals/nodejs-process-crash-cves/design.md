# Design: nodejs-process-crash-cves

## Current state
mctl-portal runs on Node.js 22.x as declared in `package.json` (`engines.node: "22 || 24"`). The Docker image is built from a pinned `node:22.x-alpine` (or equivalent) base. The serving stack is: nginx reverse-proxy → Node.js backend container → ArgoCD-managed deployment on the `admins` tenant in Kubernetes. See `context/architecture.md` for the full stack description.

The Node.js 22 build currently in use predates the March 24, 2026 security release and therefore contains:
- CVE-2026-21637: SNICallback lacks try/catch — synchronous exceptions on unexpected TLS servername crash the process.
- CVE-2026-21713: HMAC verification uses non-constant-time `memcmp`, enabling timing side-channel MAC forgery.
- CVE-2026-21714: HTTP/2 WINDOW_UPDATE on stream 0 prevents `Http2Session` GC, leading to memory exhaustion and DoS.
- CVE-2026-21717: V8 computes integer-like string hashes in a predictable manner, allowing HashDoS via `JSON.parse` on attacker-controlled input.

The companion proposal `nodejs-security-upgrade` addressed CVE-2026-21710 (__proto__ header crash) but explicitly did not cover these four CVEs.

## Proposed solution
The remediation is a single-artifact change: bump the Node.js base image tag in the project Dockerfile to the first Node.js 22.x release that includes patches for all four CVEs (expected to be the build published alongside the March 24, 2026 security release, e.g., `node:22.14.1-alpine` or the equivalent patched build — the exact tag must be confirmed against https://nodejs.org/en/blog/vulnerability/march-2026-security-releases before merging).

No application code changes are required. The CVEs are all in the Node.js runtime itself (TLS stack, crypto module, HTTP/2 session management, V8 engine). Once the base image is updated, all four patches are inherited automatically.

Delivery path:
1. Update `FROM node:22.x-alpine` in the Dockerfile to the verified patched tag.
2. Commit to the mctl-portal repository; CI builds and runs smoke tests.
3. On success, the new image is pushed to the registry with the bumped tag.
4. Update the image tag reference in `mctl-gitops` (or let the CD pipeline pick it up if using digest pinning).
5. ArgoCD detects the change and performs a rolling update on the `admins` tenant.

This approach minimises blast radius: only the base image changes. Application code, plugin versions, Backstage version, and nginx config are untouched.

## Alternatives

### Alternative 1: Application-level workarounds per CVE
Add try/catch around all SNICallback invocations in application code, replace HMAC calls with constant-time equivalents, add HTTP/2 session tracking, and validate JSON keys before parse. This would remediate each CVE in user-space without a runtime upgrade.

Rejected because: (a) not all code paths are under mctl-portal's direct control — Backstage core and plugins also use these runtime facilities; (b) the workarounds would diverge from upstream fixes and require ongoing maintenance; (c) a runtime image bump is lower-effort (Effort: 1) and more complete.

### Alternative 2: Upgrade to Node.js 24.x
Node.js 24 is already in the `engines.node` declaration and would also receive these patches. Moving to 24.x would future-proof the runtime.

Rejected for this proposal because: a major runtime version change introduces compatibility risk with Backstage plugins and requires broader regression testing. That upgrade should be its own proposal scoped to compatibility validation. This proposal targets the fastest, lowest-risk path to patching the four CVEs.

### Alternative 3: Defer until next scheduled dependency cycle
Bundle the fix with the next routine Backstage or dependency upgrade cycle.

Rejected because: CVE-2026-21637 is rated HIGH (process crash reachable from a TLS connection) and CVE-2026-21714 enables memory exhaustion DoS. Both are remotely exploitable. Deferral is not acceptable for HIGH/MEDIUM-impact crash vectors.

## Platform impact

### Migrations
None. The image tag change is backward-compatible; no database schema, API contract, or secret format is modified.

### Backward compatibility
The patched Node.js 22.x build maintains full API and ABI compatibility with the current 22.x line. No code changes, plugin updates, or configuration adjustments are expected.

### Resource impact
The patched Node.js 22.x image is approximately the same size as the current image. No change to CPU or memory resource requests/limits is required.

CVE-2026-21714 (HTTP/2 session GC) may slightly reduce steady-state memory usage on the `admins` tenant once patched, as previously leaked `Http2Session` objects are correctly released. This is a net positive for the tenant.

Tenant `labs` is not involved in this proposal and its memory pressure is unaffected.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| Patched image tag not yet published at merge time | Low | CI gate verifies the exact tag resolves from the registry before building |
| Subtle behavioural change in patched Node.js build breaks a Backstage plugin | Low | Existing CI smoke tests and Playwright e2e suite cover critical paths; rollback procedure documented in tasks.md |
| ArgoCD sync fails mid-rollout | Very low | Rolling update strategy retains previous ReplicaSet; ArgoCD sync failure leaves old pods running |
