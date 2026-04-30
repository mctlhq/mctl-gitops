# Design: scaffolder-symlink-traversal

## Current state
mctl-portal is a Backstage-based internal developer portal (see `context/architecture.md`). The scaffolder plugin is used to onboard services into tenants via Argo Workflows and mctl-gitops. The backend runs:

- `@backstage/plugin-scaffolder-backend` — manages scaffolder actions and workspace lifecycle.
- `@backstage/backend-defaults` — provides shared backend utilities including filesystem helpers used by scaffolder actions.

The current installed versions of these packages are on a release line prior to the CVE-2026-24046 fix. Scaffolder actions that operate on files (`debug:log`, `fs:delete`) and archive extraction (tar/zip) do not validate that symlink targets resolve to paths inside the workspace root. A template that places a symlink pointing outside the workspace can therefore cause the backend to read, write, or delete files anywhere the process has access.

The backend container runs as a non-root user (standard Backstage Docker setup), but the workspace volume and backend config files are readable by the process, making arbitrary file reads significant and arbitrary deletes service-disrupting.

## Proposed solution
Upgrade the two affected packages to their patched versions, matching the current Backstage release line deployed in mctl-portal:

| Package | Minimum patched version (latest line) |
|---|---|
| `@backstage/backend-defaults` | 0.15.0 |
| `@backstage/plugin-scaffolder-backend` | 3.1.1 |

The patch in these releases adds symlink resolution checks inside every affected action and inside the archive extraction utility. No action API or configuration interface changes — the upgrade is a drop-in replacement.

Steps:
1. Update `packages/backend/package.json` (and root `package.json` resolutions block if pinned) to specify the patched versions.
2. Run `yarn install` and resolve any transitive dependency conflicts using `yarn why`.
3. Build the backend locally and run the scaffolder integration test suite.
4. Build and push the Docker image with the new packages.
5. Update the ArgoCD application manifest (via mctl-gitops) to reference the new image tag.
6. Deploy to `admins` tenant via ArgoCD sync and confirm scaffolder health.

The symlink validation is fully handled inside the library — no application-level code changes are required.

## Alternatives

**Option A — Disable affected actions via policy**: Block `debug:log`, `fs:delete`, and archive actions in the scaffolder permission framework until the patch is available. This would break all onboarding templates that use file operations, causing significant user disruption. Rejected because the upstream fix is already available and the disruption is not justified.

**Option B — Sandbox the workspace with a restrictive seccomp/AppArmor profile**: Confine symlink following at the OS level by denying `readlink`/`follow_symlinks` syscalls for the backend process. This is complex to tune without breaking legitimate scaffolder behaviour and does not fix the underlying library bug. Rejected because it is harder to implement correctly, harder to test, and does not remove the CVE from the dependency tree.

**Option C — Upgrade the full Backstage release to v1.50.4**: v1.50.4 was released 2026-04-29 and bundles the patched scaffolder packages. However, a full Backstage version bump carries broader regression risk and the ADR in `context/decisions/` discourages upgrading on patch-day without a one-week community-plugins compatibility window. Rejected in favour of the targeted two-package upgrade.

## Platform impact

**Migrations**: None. No database schema changes, no configuration file changes.

**Backward compatibility**: The patched packages introduce no API changes. All existing scaffolder templates continue to work unless they relied on symlink traversal (which would be malicious or erroneous behaviour). No changes to Argo Workflow templates, mctl-gitops, or catalog configuration.

**Resource impact**: Negligible. The symlink resolution check is O(depth of path) and adds no measurable CPU or memory overhead. The `labs` tenant is not affected — mctl-portal runs exclusively under `admins`.

**Risks and mitigations**:
- Risk: A transitive dependency of the upgraded packages introduces a regression. Mitigation: pin exact versions in the resolutions block and run the full scaffolder integration test suite before deploying.
- Risk: The patch changes workspace root detection in a way that breaks templates using nested archive extraction. Mitigation: run existing onboarding templates end-to-end in a staging environment before promoting to production.
- Risk: Image build fails due to a yarn lockfile conflict. Mitigation: run `yarn dedupe` after upgrade and commit the updated lockfile.
