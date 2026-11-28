# Design: backstage-security-patch-bump

## Current state
Backstage on yarn workspaces (see context/architecture.md); backend packages in packages/backend. Exact installed versions must be confirmed with `yarn why` as the first task.

## Proposed solution
Use `yarn backstage-cli versions:bump` to the latest patch of the current release line (or at minimum v1.54.6 equivalent), then pin resolutions for any package that still resolves below its fixed version. Add a CI step (`yarn npm audit` or a version-assert script) that checks the four minimum versions. Deploy through mctl-gitops/ArgoCD to tenant `admins`. Because the bump is within the same line, ADR 0001 (no immediate major bumps) is respected.

## Alternatives
- Jump to 1.57.4: includes the fixes but also RBAC and URL-encoding changes (handled in separate proposals); riskier now.
- Yarn resolutions only: leaves the rest of the Backstage package set inconsistent.
- Do nothing: leaves credential-exposure advisories open.

## Platform impact
- Migrations: none expected; verify DB migrations in the scaffolder backend run cleanly on Postgres.
- Backward compatibility: scaffolder 4.x may change task list ordering input validation; verify templates and custom plugins.
- Resource impact: neutral. `labs` is not affected (portal runs in `admins`), no memory increase expected.
- Risks: custom plugin incompatibility; mitigated by staging build, e2e and a quick rollback to the previous image.
