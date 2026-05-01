# Design: backstage-catalog-security-patch

## Current state
mctl-portal is a Backstage monorepo managed with yarn workspaces (`packages/app`, `packages/backend`, `plugins/*`). The portal is containerised and deployed to the `admins` Kubernetes tenant via mctl-gitops and ArgoCD. The current image runs a Backstage version prior to v1.50.4 and therefore contains the unpatched versions of:

- `@backstage/plugin-catalog-backend-module-unprocessed`
- `@backstage/plugin-catalog-unprocessed-entities-common`
- `@backstage/plugin-catalog-unprocessed-entities`

These three packages sit in the catalog plugin family. The vulnerabilities disclosed with the v1.50.4 security advisory affect the unprocessed-entities processing pipeline and the shared common types package, creating risk in the backend catalog ingestion path. See https://github.com/backstage/backstage/releases/tag/v1.50.4 for the full advisory.

The serving stack is: nginx + Docker image → mctl-gitops (GitOps repo) → ArgoCD sync → Kubernetes Deployment in tenant `admins`. The Deployment currently uses a rolling update strategy with `minAvailable: 1`.

## Proposed solution
The patch is a targeted version bump of the three affected packages to v1.50.4. No structural changes to the application or infrastructure are required.

**Step-by-step approach:**

1. Run `yarn backstage-cli versions:bump --pattern '@backstage/plugin-catalog-backend-module-unprocessed @backstage/plugin-catalog-unprocessed-entities-common @backstage/plugin-catalog-unprocessed-entities'` (or equivalent selective bump) in the monorepo root to update `package.json` and `yarn.lock`.
2. Run `yarn install --frozen-lockfile` to validate the lockfile is consistent with the new versions.
3. Run `yarn build` for `packages/backend` (only the backend is affected; the frontend catalog plugin is not listed in the advisory).
4. Build a new Docker image tagged with the Backstage version and a short Git SHA (e.g., `mctl-portal:1.50.4-<sha>`).
5. Push the image to the container registry.
6. Update the image tag in the mctl-gitops GitOps repo.
7. ArgoCD syncs the new image on or after 2026-05-06 (sync window enforced per ADR-0001 community-plugins compat window).
8. Post-deploy: run `yarn audit --level high` to confirm no remaining high/critical advisories in the patched packages.

The existing rolling-update strategy (`minAvailable: 1`) ensures zero downtime during pod replacement.

**Why only these three packages?** The v1.50.4 release is explicitly scoped to the unprocessed-entities catalog subsystem. Bumping unrelated packages (scaffolder, kubernetes, techdocs) on the same PR would mix security and feature changes, complicating rollback attribution and violating the minimal-change principle for security patches.

**Why not wait for the next regular Backstage release cycle?** Security patches should be applied as soon as the compatibility window allows. Delaying to the next biweekly release would leave the vulnerabilities unaddressed for up to two additional weeks.

## Alternatives

### Option A: Full Backstage monorepo bump to v1.50.4
Bump every `@backstage/*` package to v1.50.4 at the same time. This is the approach recommended by the Backstage docs (`backstage-cli versions:bump`).

**Dropped because:** ADR-0001 explicitly warns that community-plugins compatibility lags by 1-2 weeks after a Backstage release. A full bump today (May 1) would violate that constraint and risk breaking the kubernetes, github-actions, or techdocs plugins before community-plugins has published compatible versions. The selective bump limits blast radius to only the patched packages.

### Option B: Patch vendor the packages (fork and patch in-place)
Copy the three affected package sources into `plugins/` and apply the upstream security diff manually, without bumping the registry versions.

**Dropped because:** This approach creates an untracked fork that diverges from upstream with every future Backstage release, increasing maintenance burden and auditability risk. The upstream fix is available as a published package; vendor-patching adds complexity with no benefit.

### Option C: Disable the unprocessed-entities plugin until a safe upgrade window
Remove or disable `plugin-catalog-backend-module-unprocessed` and `plugin-catalog-unprocessed-entities` temporarily to eliminate the attack surface without a code change.

**Dropped because:** Disabling catalog plugins would degrade the catalog ingestion pipeline and the unprocessed-entities visibility UI, affecting developer experience. The compliance cost of a known vulnerability with a disabled mitigation is not lower than applying the patch.

## Platform impact

### Migrations
None. The patch is a drop-in replacement at the package level. No database schema changes, no new environment variables, no changes to the catalog-info.yaml format or the Entity store.

### Backward compatibility
The three patched packages are internally used by the Backstage backend. No public API contract between mctl-portal and downstream consumers (mctl-api, ArgoCD, Vault) is affected. The catalog REST API surface exposed to the frontend `packages/app` remains unchanged.

### Resource impact
The patch introduces no new background workers, caches, or memory allocations. The backend Pod resource requests and limits (CPU, memory) do not need adjustment. The `labs` tenant is not involved — mctl-portal runs exclusively in tenant `admins`.

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|---|---|---|
| community-plugins compat break if any indirect dependency pulls in a conflicting version | Low (patch-only release, no API changes) | Validate with `yarn install --frozen-lockfile` and full `yarn build` in CI before image build. Gate deployment to on/after May 6. |
| Regression in catalog ingestion processing | Low | Run the existing Playwright e2e suite against the staging environment; assert component count matches baseline before promoting to production. |
| Liveness probe failure on rollout | Very low | Kubernetes rolling update with `minAvailable: 1` ensures at least one healthy pod at all times; ArgoCD self-heal rolls back on failed health checks. |
| Patch does not fully close the vulnerability | Very low | Confirm with `yarn audit --level high` post-deploy; cross-reference against the CVE identifiers in the v1.50.4 release notes. |
