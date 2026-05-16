# Design: scaffolder-path-traversal-fix

## Current state
mctl-portal is a Backstage-based internal developer portal (see `context/architecture.md`). The backend runs on Node.js 22 inside a Docker container served through nginx, deployed to tenant `admins` via ArgoCD. The Scaffolder plugin (`@backstage/plugin-scaffolder-backend`, `@backstage/plugin-scaffolder-node`, `@backstage/backend-defaults`) drives service-onboarding workflows that commit to mctl-gitops and trigger Argo Workflows. Current package versions are unpinned within the minor lines shipping with the Backstage version in use (root `package.json` version 1.0.1, last synced 2026-04-27).

CVE-2026-24046 exists in all three packages at versions prior to the fix boundaries listed in the advisory (GHSA-rq6q-wr2q-7pgp). The vulnerability is in how workspace path resolution and archive extraction are handled inside Scaffolder action handlers.

## Proposed solution
Bump the three affected packages to their fixed minimum versions in `package.json` and `yarn.lock`, rebuild the Docker image, and deploy via the standard ArgoCD pipeline.

Affected packages and target minimum versions:

| Package | Fixed version (minimum) |
|---|---|
| `@backstage/backend-defaults` | 0.12.2 / 0.13.2 / 0.14.1 / 0.15.0 (match existing minor) |
| `@backstage/plugin-scaffolder-backend` | 2.2.2 / 3.0.2 / 3.1.1 (match existing minor) |
| `@backstage/plugin-scaffolder-node` | 0.11.2 / 0.12.3 (match existing minor) |

The approach is a pure dependency patch — no application code, template definitions, or Kubernetes manifests change. The patched packages resolve the path traversal by enforcing workspace boundary checks in action handlers and by sanitising symlink targets during archive extraction. Because the fix is internal to the libraries, existing Scaffolder templates and the mctl-gitops integration remain unaffected.

Deployment sequence:
1. Update `yarn.lock` and verify with `yarn dedupe`.
2. Run `yarn audit` to confirm no remaining High/Critical findings for the three packages.
3. Build and push a new Docker image tagged with the current semver patch.
4. Update the image tag in the mctl-gitops Helm values for `admins`.
5. ArgoCD syncs and rolls out the new pod; the old pod is terminated only after the new one passes its readiness probe.

## Alternatives

**Option A — Full Backstage version upgrade to v1.50.4.**
The v1.50.4 release contains the same Scaffolder fixes bundled with catalog-module patches. This would pick up additional fixes automatically. Dropped because: a full Backstage upgrade touches far more packages, increasing regression risk, and the ADR in `decisions/` requires waiting approximately one week after a new stable release for community-plugins compatibility. An isolated package bump is faster and lower risk for this security window.

**Option B — Disable the Scaffolder plugin temporarily.**
Disabling the plugin until a full upgrade cycle eliminates the attack surface immediately. Dropped because: the Scaffolder is the primary onboarding mechanism for new services; disabling it causes direct operational impact and is disproportionate when a targeted patch is available.

**Option C — Add a network policy / admission webhook to block archive extraction.**
A Kubernetes admission webhook could block pod execution if an advisory-flagged image is detected. Dropped because: this operates at the wrong layer (the vulnerability is in application code, not the image runtime), adds operational complexity, and does not actually patch the code path.

## Platform impact

**Migrations:** None. No schema, API, or configuration changes.

**Backward compatibility:** The patched package versions are backward compatible — the fix adds input validation inside action handlers. No existing Scaffolder templates require changes.

**Resource impact:** Building and pushing a new Docker image is the only additional resource operation. The running pod's memory and CPU footprint does not change. No impact on the `labs` tenant (this service runs exclusively in `admins`).

**Risks and mitigations:**
- Risk: A transitive dependency of the bumped packages introduces a regression. Mitigation: run the full Playwright e2e suite against a staging deployment before promoting to `admins`.
- Risk: `yarn dedupe` after the bump changes other package versions unexpectedly. Mitigation: review the diff of `yarn.lock` and scope the diff to only the three target packages and their direct dependencies.
- Risk: The new image tag is deployed but the readiness probe fails (e.g., a startup error). Mitigation: ArgoCD progressive rollout — old pod stays up until the new pod is healthy; rollback is a single image tag revert in mctl-gitops.
