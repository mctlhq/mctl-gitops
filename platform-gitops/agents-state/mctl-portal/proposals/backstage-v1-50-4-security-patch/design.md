# Design: backstage-v1-50-4-security-patch

## Current state
mctl-portal is a Backstage monorepo (`packages/app`, `packages/backend`, `plugins/*`) running a version prior to v1.50.4 (see `context/architecture.md`). Backstage packages are versioned as a cohesive set managed by the `backstage-cli` toolchain and the `@backstage/core-*` / `@backstage/plugin-*` package family. The catalog backend (`@backstage/plugin-catalog-backend`) depends on `@backstage/catalog-model` and the `catalog-unprocessed-entities` package family; these are the packages with disclosed CVEs in this advisory.

The Backstage project maintains a consistent versioning strategy for patch releases: all `@backstage/*` packages in a release share the same version bump, and the `backstage-cli versions:bump` command is the standard mechanism to apply them atomically.

## Proposed solution
Run `yarn backstage-cli versions:bump --release 1.50.4` (or equivalent) to update all `@backstage/*` package references across `packages/app/package.json`, `packages/backend/package.json`, and any `plugins/*/package.json` files that depend on core Backstage packages.

Steps:
1. Execute `yarn backstage-cli versions:bump --release 1.50.4` in the monorepo root.
2. Review the generated diff: confirm only `@backstage/*` package versions are changed; confirm no major or minor version change is introduced.
3. Run `yarn install` to regenerate the lockfile.
4. Run `yarn tsc --noEmit` across the workspace to catch any type-check regressions.
5. Run the full test suite (unit, integration, playwright e2e).
6. Open a PR, pass CI, request review.
7. Merge; mctl-gitops picks up the new image tag; ArgoCD delivers the rolling update to `admins`.

This approach mirrors all prior Backstage patch bumps applied to mctl-portal and is the lowest-risk, most auditable path.

## Alternatives

### 1. Selectively bump only the affected `catalog-unprocessed-entities` packages
Backstage packages are designed to be upgraded as a cohesive set. Selectively bumping only the catalog-related packages risks version skew between packages that share internal interfaces, which can produce subtle runtime errors. Rejected in favour of the full coordinated bump.

### 2. Wait for v1.51.0 (next minor) and combine
The next minor release would include v1.50.4 fixes plus additional changes. Minor releases require more testing and may trigger the ADR review period. Waiting also leaves the CVEs unpatched in the interim. Rejected because the patch release is available now at lower risk.

### 3. Cherry-pick the upstream CVE fix commits into the current pinned version
Backstage is a large monorepo; cherry-picking specific commits is error-prone and produces a non-standard fork of the packages that is hard to maintain and audit. Rejected.

## Platform impact

### Migrations
None. Backstage patch releases do not include database schema migrations. The Postgres session store and catalog database are unaffected.

### Backward compatibility
Backstage patch releases are API-compatible within the minor version line. All existing plugins (catalog, scaffolder, kubernetes, techdocs, search, observability, kubernetes-permissions, proxy, github-actions, github) should function without modification. Any type-check incompatibility will be caught by CI before deployment.

### Resource impact (especially for `labs`)
This is a pure package version bump; the Docker image size may change marginally (within noise). No changes to memory or CPU resource requests or limits are required. The `labs` tenant does not run mctl-portal; resource impact on `labs` is nil. This upgrade is rated as having minimal resource impact.

### Risks and mitigations
- **Risk:** A custom plugin in `plugins/*` uses an internal Backstage API that changed between the current version and v1.50.4. **Mitigation:** `yarn tsc --noEmit` will catch this at CI time before deployment; fix the affected plugin before merging.
- **Risk:** The v1.50.3 facets-endpoint performance change alters catalog query response shapes in a way that breaks the frontend. **Mitigation:** The playwright e2e tests cover catalog browsing; run them against the staging deployment before promoting to production.
- **Risk:** The lockfile upgrade pulls in a new transitive dependency with its own CVE. **Mitigation:** Run `yarn audit` in CI as part of the PR; treat any high-severity finding as a blocker.
