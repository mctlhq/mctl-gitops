# Design: catalog-facets-perf-fix

## Current state
mctl-portal is a Backstage-based internal developer portal (see `context/architecture.md`).
The catalog backend exposes a facets endpoint (`/api/catalog/entity-facets`) that the frontend
search and filter components poll to populate filter dropdowns. A performance regression
introduced in the v1.50.x line causes this endpoint to execute more expensive queries than
necessary, increasing backend CPU consumption and raising response latency under load.

The service runs Backstage packages at a pre-v1.50.3 pin, deployed to tenant `admins` via
ArgoCD. The catalog database backend is Postgres (sessions and catalog state). The facets
query is executed on the Backstage backend Node.js process.

## Proposed solution
Bump all `@backstage/*` packages to **v1.50.4** (the latest patch on the 1.50.x line as of
2026-05-03). v1.50.3 contains the facets performance fix; v1.50.4 is the security patch
released immediately after and is a strict superset of v1.50.3. Upgrading to v1.50.4 in a
single step captures the performance fix along with the security fixes in
`catalog-unprocessed-security-patch`, reducing the number of deployments needed.

The bump is performed by updating `package.json` version constraints and regenerating
`yarn.lock` via `yarn install`. No configuration changes to the catalog plugin, Postgres
schema, or ArgoCD manifests are required.

This approach is intentionally narrow: we follow the Backstage coordinated-release model
(all packages move together) and do not attempt selective patching of individual catalog
packages, which would create peer-dependency drift.

Relationship to `catalog-unprocessed-security-patch`: both proposals target the same version
bump (to v1.50.4). In practice they are applied as a single PR and deployment. They are kept
as separate proposals because they address distinct concerns (performance vs. security) and
may be reviewed or prioritised independently.

## Alternatives

**1. Upgrade to Backstage v1.51.x**
Would include this fix and additional improvements, but v1.51.0 is in the next/pre-release
channel as of 2026-05-03, with unknown community-plugins compatibility. Dropped per platform
ADR: do not propose major bumps on or shortly after release day.

**2. Apply a cherry-picked patch to the catalog-backend source**
The performance fix is an upstream change to Backstage internals. Forking or patching
vendor code would require ongoing maintenance as Backstage evolves. Dropped — complexity
outweighs the benefit of avoiding a version bump.

**3. Add a caching layer in front of the facets endpoint (e.g., Redis cache)**
Could mitigate the regression's impact on latency without upgrading, but does not fix the
root cause and adds operational complexity. Dropped as a workaround rather than a fix.

## Platform impact

- **Migrations:** None. This is a patch-level bump with no Postgres schema changes and no
  changes to the catalog-info.yaml format.
- **Backward compatibility:** The facets endpoint API contract (`/api/catalog/entity-facets`)
  does not change. All existing filter queries from the frontend remain valid.
- **Resource impact (`labs`):** This proposal deploys only to tenant `admins`. No `labs`
  workloads are affected. The performance fix is expected to reduce — not increase — backend
  CPU usage under load. No `labs` risk.
- **Risks and mitigations:**
  - Risk: the upstream fix introduces a subtle query change that breaks a custom filter used
    by mctl-portal's observability custom plugin.
    Mitigation: integration tests covering the facets endpoint are run in CI before merge;
    a staging smoke test with the observability plugin active confirms no regressions.
  - Risk: peer-dependency conflicts when bumping from the current baseline to v1.50.4.
    Mitigation: `yarn install --check-resolutions` is enforced in CI; any conflict fails
    the build before it reaches staging.
