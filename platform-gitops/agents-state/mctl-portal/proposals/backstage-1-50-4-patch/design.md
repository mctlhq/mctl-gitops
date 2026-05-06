# Design: backstage-1-50-4-patch

## Current state
mctl-portal is at Backstage version 1.50.x, last updated 2026-04-27 (see `context/current-version.md`). Backstage v1.50.4 was released 2026-04-29, two days after the last recorded update, meaning the current deployment is running on 1.50.3 or earlier. The root `package.json` references `@backstage/cli` and `@backstage/*` core packages at their 1.50.x versions. The Backstage monorepo uses `backstage-cli versions:bump` to keep all `@backstage/*` packages in sync across the yarn workspace.

`@backstage/integration` at a pre-1.20.1 version contains CVE-2026-29185: an encoded SCM URL (e.g., `%2E%2E%2F` sequences) is not fully normalised before path resolution, allowing a caller to traverse outside the intended SCM base path. This affects catalog import and scaffolder fetch actions that resolve SCM URLs. The affected module is consumed by both `packages/backend` and potentially by custom plugins in `plugins/` that use the integration helpers.

## Proposed solution
Run `yarn backstage-cli versions:bump --release 1.50.4` (or the equivalent manual bump) to update all `@backstage/*` packages to their 1.50.4 counterparts in a single pass. This is the standard upgrade path documented by Backstage and ensures no package is left on a mixed version. The command updates `package.json` files across the workspace and regenerates `yarn.lock`.

Key package upgrades included:
- `@backstage/integration` 1.20.1 — CVE-2026-29185 fix
- `@backstage/plugin-catalog-backend-module-unprocessed` — security patch
- All other `@backstage/*` packages to their 1.50.4 patch equivalents

After the bump, run `yarn install`, `yarn build`, and the full test suite. Review any breaking changes listed in the v1.50.4 changelog (patch releases on a stable minor should have none, but the changelog is checked as standard practice). Deploy via the existing CI/ArgoCD pipeline to tenant `admins`.

The solution deliberately uses `backstage-cli versions:bump` rather than manual per-package edits to avoid version skew between interdependent `@backstage/*` packages, which is a known source of runtime errors.

## Alternatives

**Option A — Manually bump only the two affected packages (`@backstage/integration` and `@backstage/plugin-catalog-backend-module-unprocessed`).**
Selective bumping risks leaving interdependent `@backstage/*` packages at mismatched versions. Backstage's own tooling warns against this pattern. If a peer dependency between e.g. `@backstage/backend-common` and `@backstage/integration` changes at 1.50.4, a selective bump would silently run mismatched versions. Dropped in favour of the full workspace bump.

**Option B — Wait for v1.50.5 or v1.51.x and bundle multiple patches.**
Delaying the patch while CVE-2026-29185 is publicly disclosed increases compliance risk. The 1.50.4 patch is available now and safe to apply. There is no operational benefit to waiting. Dropped.

**Option C — Pin only `@backstage/integration` via `resolutions` in the root `package.json`.**
Yarn resolutions can force `@backstage/integration` to 1.20.1 without a full workspace bump. However, this approach is fragile (resolutions bypass peer-dependency checks), creates a non-standard dependency tree that is harder to audit, and does not patch `@backstage/plugin-catalog-backend-module-unprocessed`. Dropped in favour of the clean workspace bump.

## Platform impact

**Migrations:** None. Backstage patch releases within the same minor do not introduce database schema migrations. The Postgres session store schema is unchanged.

**Backward compatibility:** Patch releases on the 1.50.x line are backward-compatible by the Backstage versioning policy. Community-plugins installed from `@backstage-community/` are compatible with the 1.50.x core and do not require updates. Per ADR-0001, only major bumps require community-plugins re-validation.

**Resource impact:** The package bundle size may change by a negligible amount. CPU and memory footprint of the backend pod in tenant `admins` are not materially affected. No `labs` tenant resources are affected.

**Risks and mitigations:**
- Risk: a bug introduced in one of the 1.50.4 package patches causes a catalog or scaffolder regression. Mitigation: the full playwright e2e suite is mandatory in CI before merge; the previous `yarn.lock` is recoverable via git revert for a fast rollback.
- Risk: `backstage-cli versions:bump` updates a package that has a transitive conflict with a community-plugin pinned at a lower version. Mitigation: run `yarn install` with `--check-resolutions` and address any peer-dependency warnings before merging.
- Risk: the `@backstage/integration` 1.20.1 change alters the URL normalisation behaviour in a way that breaks a custom plugin that relies on the previous (buggy) behaviour. Mitigation: review the `@backstage/integration` 1.20.1 changelog; test all SCM-touching workflows in the e2e suite.
