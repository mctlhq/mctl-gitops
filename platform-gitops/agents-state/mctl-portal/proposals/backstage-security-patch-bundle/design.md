# Design: backstage-security-patch-bundle

## Current state
Backstage on yarn workspaces (packages/app, packages/backend, plugins/*), see context/architecture.md. Exact current Backstage version is not recorded in context/current-version.md (only app 1.0.1); must be read from backstage.json.

## Proposed solution
Run `yarn backstage-cli versions:bump` to the 1.56.x line (target 1.56.3), then verify affected packages with `yarn why`. Fixed-version minima are listed in requirements.md. Build, run e2e, smoke-test scaffolder, k8s viewer, TechDocs, Dex login. Deploy to admins via mctl-gitops/ArgoCD. If currently on an older release line, use the backport fixes (1.49.7 / 1.54.7 for auth-node) rather than skipping releases blindly.

## Alternatives
- Targeted per-package pins via resolutions: smaller diff, but risks version skew between Backstage packages.
- Wait for next release: leaves a 9.6 CVE open; rejected.

## Platform impact
- Migrations: follow release notes for any API deprecations between current and 1.56.3.
- Backward compatibility: custom observability plugin must be re-validated.
- Resource impact: neutral; portal runs in `admins`, nothing added to `labs`.
- Risks: community-plugins lag — mitigate by checking compat before merging; this is not a major bump, consistent with ADR 0001.
