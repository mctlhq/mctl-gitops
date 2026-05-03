# Design: catalog-unprocessed-security-patch

## Current state
mctl-portal is a Backstage-based internal developer portal (see `context/architecture.md`).
The service runs on Backstage 1.50.x with Node.js 22 LTS, managed as a yarn workspaces
monorepo (`packages/app`, `packages/backend`, `plugins/*`). The catalog stack includes
`@backstage/plugin-catalog-backend-module-unprocessed` and its companion packages, currently
pinned to a pre-v1.50.4 release. Backstage's release cadence is approximately every two weeks;
patch releases on an active minor line (1.50.x) are published as needed for security fixes.

The service is deployed to tenant `admins` on Kubernetes via ArgoCD (mctl-gitops). Docker
images are built in CI from the lockfile.

## Proposed solution
Bump all `@backstage/*` packages from the current 1.50.x baseline to **v1.50.4** by updating
`package.json` version ranges and re-running `yarn install` to regenerate `yarn.lock`. Because
Backstage uses a coordinated release model where all packages share the same version tag, a
single `yarn up '@backstage/*@^1.50.4'` command (or equivalent lockfile edit) updates the
affected packages atomically.

The change is applied in the same step as `catalog-facets-perf-fix` (which targets v1.50.3):
since v1.50.4 is a superset of v1.50.3, a single bump from the current baseline to v1.50.4
captures both the performance fix and these security fixes in one deployment, reducing
deployment risk and rollout overhead.

Why patch-in-place rather than skip to v1.51.x: v1.51.x is on the next/pre-release channel
as of 2026-05-03. Per the platform ADR (do not propose major bumps on or shortly after
release day), and given community-plugins compatibility lag, staying on 1.50.x is the
correct approach.

## Alternatives

**1. Skip to Backstage v1.51.x**
Provides a larger feature set and future security coverage, but v1.51.0 is in the next channel
with an unpublished full changelog and no confirmed community-plugins compatibility. Dropped
due to ADR constraints and elevated risk.

**2. Patch only the three affected packages, pin others**
Technically possible but Backstage's inter-package peer-dependency graph makes selective pinning
fragile. Coordinator scripts (`yarn backstage-cli versions:bump`) are designed for coordinated
upgrades. Dropped — maintenance overhead outweighs the benefit of a smaller diff.

**3. Do nothing until a broader quarterly upgrade**
Leaves a known-patched security release unapplied, violating the platform security SLA.
Dropped unconditionally.

## Platform impact

- **Migrations:** None. This is a patch-level bump with no data schema changes or API breaks.
- **Backward compatibility:** All existing catalog-info.yaml files, scaffolder templates, and
  plugin configurations remain valid. The unprocessed-entities module's REST API contract does
  not change between patch versions.
- **Resource impact (`labs`):** This proposal is deployed to tenant `admins`; no changes are
  made to `labs`. The bump does not add new services or materially change memory/CPU
  consumption. No `labs` risk.
- **Risks and mitigations:**
  - Risk: a transitive dependency pulled in by v1.50.4 introduces a peer-dep conflict.
    Mitigation: run `yarn install --check-resolutions` in CI and fail the build if conflicts
    are detected before merging.
  - Risk: regression in catalog entity processing after the patch.
    Mitigation: existing catalog integration tests must pass in CI; a smoke test against the
    staging environment validates entity ingestion end-to-end before ArgoCD promotes to
    production.
