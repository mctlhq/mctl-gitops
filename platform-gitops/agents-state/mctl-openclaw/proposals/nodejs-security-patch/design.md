# Design: nodejs-security-patch

## Current state

The mctl-openclaw Docker image uses a Node.js base image (see `context/architecture.md`; the exact tag is in the service Dockerfile). All Node.js LTS lines currently supported (20.x, 22.x, 24.x) were affected by CVE-2026-21637 and CVE-2026-21710 until the 2026-03-24 security releases:

- **CVE-2026-21637** — `_tls_wrap.js` `loadSNI()` has no try/catch around the SNICallback invocation; a synchronous exception propagates uncaught through Node.js's TLS error handling path and terminates the process. Patched in Node.js 22.22.2, 20.20.2, and 24.x security release.
- **CVE-2026-21710** — `req.headersDistinct` does not guard against a `__proto__` key in HTTP request headers; parsing such a header triggers an uncaught TypeError that terminates the process. Patched in the same security release.

A process crash causes the Kubernetes pod to restart. During the restart, the restore-state readiness probe (ADR-0002) prevents the pod from accepting traffic until state is restored from S3. For `ovk` this window represents real customer-visible channel unavailability.

CVE-2026-21713 (HMAC timing side-channel, medium severity) is also patched in the same Node.js release and is resolved as a side effect with no additional effort.

## Proposed solution

**Bump the `FROM node:...` line in the service Dockerfile** to a patched LTS image. The recommended target is `node:22.22.2-alpine` (or `-slim`/`-bookworm` depending on the current base variant), which is the LTS release that includes all March 2026 security patches and matches the LTS line most likely already in use.

### Why a base image bump only

No application code is changed. The CVEs are in the Node.js runtime itself (TLS and HTTP parsing layers), not in openclaw or the workspace extensions. A pure base image update is the smallest possible change, minimises regression risk, and has negligible RSS delta — there is no memory concern for `labs`.

### Rollout

The same `labs` → `admins` → `ovk` pipeline from ADR-0001 applies. Because this is a CI/CD image rebuild rather than an application change, the rollout is fast: rebuild image, push to registry, update the deployment. The s3-sync canary must be stopped before each tenant rollout and restarted after, per ADR-0002. The restore-state probe gates readiness on each tenant.

Because the only change is the runtime version (not application state, S3 format, or skill layout), the observation window between tenants can be shorter than for an application upgrade — 6 hours for `labs` and `admins` is sufficient, with the full 12-hour window still recommended for `ovk`.

### LTS line selection

If the current Dockerfile already uses Node.js 22.x, target `22.22.2`. If it uses 20.x, target `20.20.2`. If it has already moved to 24.x, verify the equivalent patched 24.x tag. The decision is recorded in the PR description. Moving to a different major LTS line is out of scope for this proposal.

## Alternatives

### A. Wait for the next openclaw upstream release to bundle a patched Node.js image

The openclaw upstream release cadence is not tied to Node.js security releases. Waiting exposes all three tenants to two process-crash vectors for an indeterminate period. Rejected — the fix is a one-line change in our own Dockerfile.

### B. Upgrade to Node.js 24.x LTS as part of this patch

Node.js 24.x ("Krypton") is a new major LTS with feature additions (SQLite RC, `--max-heap-size`, new crypto APIs). A major LTS bump requires extension compatibility validation and carries more regression risk than a patch within the current line. The `--max-heap-size` flag could be useful for `labs`, but that benefit does not justify bundling it here. A separate proposal can address an LTS line upgrade. Rejected for this proposal.

### C. Add a Kubernetes network policy to block malformed TLS/HTTP traffic at the ingress layer

A network policy or WAF rule could reduce the attack surface, but it does not eliminate the underlying vulnerability. An attacker who reaches the pod (e.g., via a compromised upstream service) could still send a crafted request. Defence-in-depth is worthwhile, but patching the root cause is mandatory. This alternative is not a substitute. Rejected as a replacement; may be considered as a complementary control separately.

## Platform impact

### Migrations

None. The Node.js base image bump does not change any application state, S3 state format, or Kubernetes manifest.

### Backward compatibility

The change from an unpatched Node.js 22.x release to 22.22.2 is backward-compatible. The security patches are targeted fixes in `_tls_wrap.js` and HTTP header parsing; no public API changes are introduced.

### Resource impact (`labs`)

Node.js patch releases within an LTS line have negligible RSS changes. No memory concern is expected for `labs`. No RSS gating step is required, though a spot-check after the `labs` rollout is recommended as a sanity measure.

### Risks and mitigations

| Risk | Mitigation |
|---|---|
| Image registry unavailability delays the push | Use the existing registry mirror; fallback to direct pull if the mirror is stale. |
| Restore-state probe times out after pod restart | Same procedure as any rollout: verify timeout is adequate before triggering; roll back if probe fails. |
| Patched Node.js version introduces an unforeseen regression in TLS behaviour | Run existing integration tests (channel connect/reconnect paths) in `labs` before promoting. |
| `ovk` pod restarts during rollout cause brief channel unavailability | Restore-state probe ensures state is loaded before traffic is accepted; planned rollout during low-traffic window recommended. |
