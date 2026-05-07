# Design: backstage-v1504-security-upgrade

## Current state
mctl-portal is a Backstage monorepo (yarn workspaces: `packages/app`, `packages/backend`, `plugins/*`) built with `backstage-cli`. The root `package.json` version is 1.0.1 (updated 2026-04-27). Backstage package versions are managed via `backstage-cli versions:bump`. The service is deployed as a Docker image (nginx + Node backend) to tenant `admins` via mctl-gitops → ArgoCD.

The current installed Backstage version is behind v1.50.4, which carries fixes for CVE-2026-24046 (High), CVE-2026-24048 (High), CVE-2026-44374 (Medium), and CVE-2026-29185 (Low).

## Proposed solution
Run `yarn backstage-cli versions:bump --release 1.50.4` to update all `@backstage/*` packages to the versions bundled with the v1.50.4 release. This is the standard Backstage upgrade path and is non-breaking within a minor series.

Steps:
1. Run `backstage-cli versions:bump --release 1.50.4` in the monorepo root.
2. Run `yarn install` to update the lockfile.
3. Run `yarn tsc --noEmit` and `yarn backstage-cli repo lint` to catch any type or lint regressions.
4. Run Playwright e2e suite against a staging deployment to verify Scaffolder, Catalog, and TechDocs flows.
5. Build the Docker image and deploy to staging (`admins` namespace, non-production).
6. After 24-hour soak in staging, promote to production via ArgoCD image tag update in mctl-gitops.

No custom plugin changes are expected; v1.50.4 is a patch release with no API surface changes.

## Alternatives

### A. Pin only the affected packages manually
Update only `@backstage/plugin-scaffolder-backend`, `@backstage/backend-defaults`, `@backstage/plugin-catalog-backend-module-unprocessed`, and `@backstage/integration` to their patched versions without bumping the full monorepo. Dropped: Backstage packages have tight peer-dependency coupling; partial updates routinely cause version-mismatch runtime errors. The `versions:bump` tooling is the supported path.

### B. Wait for v1.51.0 stable
v1.51.0-next.2 is available but not yet stable. The architecture decision rules out upgrading on patch-day of a major release. Additionally, delaying leaves two High CVEs unpatched. Dropped.

### C. Hotpatch the CVEs without upgrading
Apply community-contributed patches directly to node_modules at build time. Dropped: unmaintainable, breaks reproducible builds, and offers no long-term security guarantees.

## Platform impact
- **Migrations:** None expected for a patch release. If a breaking change is discovered during `tsc`, it will be documented and fixed before staging promotion.
- **Backward compatibility:** All existing scaffolder templates, catalog-info.yaml files, and custom plugin APIs are expected to remain compatible.
- **Resource impact:** No measurable change in CPU or memory footprint. Tenant `labs` is unaffected — mctl-portal runs in tenant `admins`.
- **Risks and mitigations:**
  - *Regression in Scaffolder templates:* Mitigated by full Playwright e2e run including onboarding flow before production deploy.
  - *Lockfile conflicts:* Mitigated by running `yarn install` in CI and checking for unexpected transitive version changes.
  - *Deployment downtime:* ArgoCD rolling update; Backstage supports zero-downtime restarts under normal conditions.
