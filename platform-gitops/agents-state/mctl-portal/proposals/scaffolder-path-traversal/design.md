# Design: scaffolder-path-traversal

## Current state
According to `context/architecture.md`, mctl-portal runs on Backstage latest (the root
`package.json` pins `1.0.1`). The scaffolder is the `plugin-scaffolder-backend` plugin,
which mounts actions from `@backstage/backend-defaults`. The backend pod runs in the
`admins` tenant; Vault secrets are mounted via ExternalSecret as environment variables and
files. The current `plugin-scaffolder-backend` version is below 3.1.1 and
`@backstage/backend-defaults` is below 0.12.2 — i.e. vulnerable to CVE-2026-24046.

There is no symlink guard: when calling `fs:delete` or extracting an archive, the
scaffolder engine resolves the path without checking that it stays within the task
workspace (`/tmp/scaffolder-<uuid>/`).

## Proposed solution
Upgrade two packages to fixed versions in a single PR:

```
@backstage/backend-defaults  ^0.12.2
plugin-scaffolder-backend    ^3.1.1
```

The upstream fix introduces a `realpath` check after each path resolution within actions:
if the resulting absolute path does not start with the workspace root — the operation is
aborted with an error. Symlinks inside archives are rejected outright.

Upgrade steps:
1. `yarn up @backstage/backend-defaults@^0.12.2 plugin-scaffolder-backend@^3.1.1` at the
   monorepo root.
2. Verify that `yarn.lock` did not pull transitive dependencies with incompatible peer
   versions (backstage-cli and platform versions must match).
3. Run `yarn backstage-cli repo build` and a playwright smoke test for the create-service template.
4. Update the Docker image; ArgoCD sync in `admins` applies the new manifest.

Because `plugin-scaffolder-backend` 3.1.1 also closes CVE-2026-32237
(scaffolder-secret-leak), both CVEs are closed in a single PR — detailed rationale in
`proposals/scaffolder-secret-leak/design.md`.

## Alternatives

**A. WAF/network policy blocking path-traversal requests**
Would require parsing the scaffolder HTTP response body; not applicable to internal
file-system calls (the vulnerability lives at Node.js fs layer, not HTTP). Rejected.

**B. Run each scaffolder task in a separate ephemeral container**
Isolates the file system at the OS level. Eliminates the vulnerability regardless of
package version. However, it requires significant architectural rework (Job/Pod per task,
separate SA, artefact transfer), disproportionate to the Effort:2 of this CVE. Rejected
as over-engineering; can be considered in a separate proposal.

**C. Forbid loading templates from external URLs and check every symlink manually
in custom middleware**
Does not close the vulnerability in built-in actions (`debug:log`, `fs:delete`). Rejected.

## Platform impact

### Migration
No schema or data migrations. Changes are limited to `yarn.lock` and `package.json`.

### Backward compatibility
`@backstage/backend-defaults` 0.12.2 and `plugin-scaffolder-backend` 3.1.1 are released as
patch versions; the public API does not change. Existing templates not relying on path
traversal continue to work unchanged.

### Resource impact
The patch does not introduce new high-memory dependencies. The `labs` tenant is not
affected (Backstage is deployed only in `admins`).

### Risks and mitigations
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Peer-dependency conflict with other backstage packages on `yarn up` | Medium | Run `yarn backstage-cli versions:check` before merge; on conflict — bump the transitive packages explicitly |
| Regression in scaffolder templates | Low | Playwright smoke test of the onboarding template before merge |
| ArgoCD sync race with another simultaneous change | Low | Deploy in a maintenance window; ArgoCD sync with `--prune` |
