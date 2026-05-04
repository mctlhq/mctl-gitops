# Design: scaffolder-symlink-cve

## Current state
mctl-portal is a Backstage monorepo (see `context/architecture.md`) with `packages/app` and `packages/backend`. The scaffolder plugin is a critical path: it accepts template definitions stored in the catalog, executes action steps inside a per-task temp directory, and commits results to mctl-gitops via Argo Workflow.

The three affected packages are declared as dependencies of `packages/backend`:
- `@backstage/plugin-scaffolder-backend` — the backend plugin that orchestrates task execution and action dispatch.
- `@backstage/backend-defaults` — shared backend utilities including file-handling helpers used by multiple action implementations.
- `@backstage/plugin-scaffolder-node` — the node execution runtime for scaffolder actions.

In the vulnerable versions, symlink resolution in `debug:log`, `fs:delete`, and archive extraction does not verify that the resolved absolute path remains inside the task workspace directory. A crafted template can therefore traverse to `/`, environment-variable files, or mounted secrets.

## Proposed solution
Bump the three packages to their patched patch versions in `packages/backend/package.json` (and the root `package.json` resolutions block if present). The Backstage project has confirmed these are drop-in patch releases with no breaking API changes.

Steps:
1. Update `@backstage/plugin-scaffolder-backend`, `@backstage/backend-defaults`, and `@backstage/plugin-scaffolder-node` to the minimum patched versions resolving CVE-2026-24046 in `packages/backend/package.json`.
2. Add or update the `resolutions` block in the root `package.json` to pin these versions and prevent transitive re-introduction of the vulnerable versions.
3. Run `yarn install` to regenerate the lockfile.
4. Build and test locally; run the existing scaffolder integration test suite.
5. Commit, open a PR, merge to main, and let mctl-gitops/ArgoCD deliver the new image to the `admins` tenant.

This approach is chosen because it is purely additive at the dependency level — no code changes, no template changes, no migration scripts.

## Alternatives

### 1. Disable affected scaffolder actions immediately, patch later
Disabling `debug:log`, `fs:delete`, and archive extraction actions would eliminate the attack surface at the cost of breaking existing onboarding templates. Rejected because template breakage has higher operational impact than a same-day patch bump.

### 2. Apply a runtime path-validation wrapper in custom plugin code
Writing a wrapper that validates every action's file path at the application layer would provide defense-in-depth. However, it is more complex, slower to deliver, and unnecessary given that the upstream fix is already available as a patch version. Rejected for now; may be revisited as a defense-in-depth measure separately.

### 3. Restrict template execution to a dedicated service account with reduced filesystem access
Using a read-only root filesystem or a more restrictive securityContext for the backend pod would limit blast radius. Rejected for this proposal because it is a significant platform change that deserves its own ADR and is out of scope for a targeted security patch.

## Platform impact

### Migrations
None. The patch packages are API-compatible. No database schema changes. No template changes.

### Backward compatibility
Full backward compatibility. Existing scaffolder templates, Argo Workflow integrations, and mctl-gitops commit flows are unaffected.

### Resource impact (especially for `labs`)
The three package bumps add no measurable runtime memory or CPU overhead. The `labs` tenant does not run mctl-portal; this service is deployed exclusively in the `admins` tenant. Resource impact on `labs` is nil.

### Risks and mitigations
- **Risk:** A transitive dependency of the patched packages introduces a regression. **Mitigation:** Lockfile diff review in the PR; full CI (unit + integration + playwright e2e) must pass before merge.
- **Risk:** The patched version has not yet been released to npm at time of implementation. **Mitigation:** Pin the exact patched version tag; if unavailable, track the Backstage security advisory for the release date and treat this as P0 until patched.
- **Risk:** ArgoCD sync window delays deployment. **Mitigation:** Trigger an out-of-band sync for the `admins` application after merge given the security severity.
