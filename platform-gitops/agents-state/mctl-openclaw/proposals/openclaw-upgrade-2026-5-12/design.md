# Design: openclaw-upgrade-2026-5-12

## Current state

All three tenants (`labs`, `admins`, `ovk`) pin openclaw at **2026.3.14** (see
`context/current-version.md`). The Docker image is built from a pinned upstream tarball /
git ref in `mctl-gitops`; ArgoCD applies the manifests per tenant. The rollout order is
`labs` → `admins` → `ovk` per ADR-0001. S3 state protection (canary + restore-state probe)
is in place per ADR-0002.

A previous proposal (`openclaw-upgrade-cve-batch`) was written targeting v2026.5.6. This
design supersedes that target with v2026.5.12 — the current stable release — which carries
all fixes from every intermediate patch release including the four "Claw Chain" CVEs.

## Proposed solution

### 1. Image build change

Update the single pin point in `mctl-gitops` (e.g. `ARG OPENCLAW_VERSION` in the shared
Dockerfile or the equivalent `image.tag` in the Helm values) from `2026.3.14` to `2026.5.12`.
No application-code changes are required; the version bump is infrastructure-only.

### 2. Rollout sequence (per ADR-0001)

```
labs → observation 24 h → admins → observation 24 h → ovk
```

Each tenant step:
1. **Pause** the s3-sync Argo CronWorkflow for the target tenant.
2. **Deploy** the new image via ArgoCD sync.
3. **Wait** for the restore-state readiness probe to pass (ADR-0002 timeout).
4. **Resume** the s3-sync CronWorkflow with the configured post-rollout delay.
5. **Observe** mctl metrics for memory (especially `labs`) and error rates.

### 3. Memory impact for `labs`

v2026.5.12 moves WhatsApp/Baileys, Slack, Amazon Bedrock, and Anthropic Vertex dependency
cones out of the core runtime module graph. These packages are loaded lazily only when the
corresponding channel or provider is activated. The `labs` tenant must have all four channels
confirmed **disabled** (or confirmed as already lazy-loaded) before the rollout; otherwise
the footprint gain is not realised.

Measure: capture the pod's RSS immediately before the upgrade (via `kubectl top pod`) and
again 15 minutes after the restore-state probe passes. Gate the rollout to `admins` on
`labs` memory staying within 90 % of the configured limit.

### 4. Security validation

After each tenant upgrade, run the OpenShell CVE smoke tests (to be written in
`tasks.md`). These are lightweight CLI invocations that confirm:
- Mount-root writes are rejected outside the sandbox (CVE-2026-44112).
- Mount-root reads are rejected outside the sandbox (CVE-2026-44113).
- Shell-expansion tokens in here-doc bodies are blocked (CVE-2026-44115).
- Unauthenticated loopback config calls are rejected (CVE-2026-44118).

## Alternatives

### A. Upgrade to v2026.5.6 only (previous proposal target)
v2026.5.6 was the original fix target for an earlier CVE batch. It does not include fixes for
CVE-2026-44112 and CVE-2026-44113 (TOCTOU sandbox escapes disclosed in May 2026).
**Dropped**: upgrading to v2026.5.6 leaves two of the four Claw Chain CVEs unpatched.

### B. Cherry-pick CVE patches onto 2026.3.14
The OpenShell sandbox fixes touch core session-routing internals. A selective backport onto
the 2026.3.x branch would require maintaining a private fork and validating every touched
path across all 20+ channels. Cost far exceeds a clean upstream version bump.
**Dropped**: maintenance burden is disproportionate.

### C. Wait for v2026.5.14-stable
v2026.5.14-beta.2 was released May 15 and adds voice-call support (Telnyx) and WhatsApp
status reactions. Beta releases are not appropriate for production tenants. The currently
available stable is v2026.5.12.
**Dropped**: CVE severity (CVSS 9.6) does not allow waiting for the next stable.

## Platform impact

### Migrations
None. v2026.5.12 is backward-compatible with the existing S3 state schema and YAML skill
format. No data migrations required.

### Backward compatibility
Externalized provider packages (Baileys, Slack SDK, Bedrock, Vertex) remain installed as
optional dependencies; channels already configured continue to function. Skills are
hot-reloaded and unaffected by the core version bump.

### Resource impact
- **`labs`**: Expected net **decrease** in RSS due to provider externalisation. Must be
  confirmed empirically; block `admins` rollout if `labs` memory exceeds 90 % of limit.
- **`admins`** and **`ovk`**: No memory limit concerns; same positive trend expected.
- No new persistent volumes, external services, or S3 bucket changes.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Restore-state probe timeout on `ovk` (slow channel auth restore) | Low | ADR-0002 probe timeout already tuned; verify it is still sufficient before upgrade |
| s3-sync canary fires false alert during rollout | Medium | Pause canary before rollout, resume with delay (ADR-0002 runbook) |
| Provider externalisation breaks a disabled channel on `labs` | Low | Confirm channel disabled status before rollout; test on `admins` before `ovk` |
| Upstream regression in 2026.5.12 | Low | 24 h observation window on `labs` and `admins` before `ovk` |
