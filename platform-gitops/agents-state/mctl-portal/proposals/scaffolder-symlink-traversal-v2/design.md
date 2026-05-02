# Design: scaffolder-symlink-traversal-v2

## Current state
`packages/backend` in the mctl-portal monorepo depends on `@backstage/plugin-scaffolder-backend` at a version below 3.1.5 and `@backstage/backend-defaults` at a version below 0.15.0. The scaffolder executes template actions inside a per-task workspace directory on the Node.js filesystem. Prior to the fix, the action handlers for `debug:log`, `fs:delete`, and archive extraction resolved file paths without checking whether symlinks in the path traversed outside the workspace root, creating a container-escape risk that lets authenticated users reach any file the Node process can access (including Vault-injected secrets mounted in the pod).

The Backstage monorepo uses yarn workspaces. Package versions are pinned in the root `yarn.lock`; bumping a package version requires updating `packages/backend/package.json` and running `yarn install` to update the lockfile.

## Proposed solution
Bump the two vulnerable packages to their patched minimum versions:

| Package | Current (max vulnerable) | Target |
|---|---|---|
| `@backstage/plugin-scaffolder-backend` | < 3.1.5 | ≥ 3.1.5 |
| `@backstage/backend-defaults` | < 0.15.0 | ≥ 0.15.0 |

**Steps:**
1. Update the version constraints in `packages/backend/package.json`.
2. Run `yarn install` to resolve and update `yarn.lock`.
3. Run the full test suite (`yarn tsc --noEmit`, `yarn test`, `yarn playwright test` in CI).
4. Build the Docker image and push to the registry.
5. Update the image tag in the mctl-gitops Helm values for the `admins` tenant and merge — ArgoCD will roll out the new pod.

No application-level code changes are needed. The symlink guardrails are implemented entirely inside the upgraded packages. The scaffolder template catalog in mctl-gitops is unaffected.

## Alternatives

### Option A — Virtual filesystem shim (rejected)
Implement a custom Node.js `fs` shim that intercepts all file calls from scaffolder actions and enforces sandbox boundaries at the application layer. This would work independent of upstream package versions but adds significant maintenance burden and could diverge from upstream behaviour. Rejected in favour of taking the upstream fix.

### Option B — Drop and re-add the scaffolder plugin at a fresh version (rejected)
Remove `@backstage/plugin-scaffolder-backend` entirely, clear the yarn cache, and install the latest version. Functionally equivalent to a version bump but more disruptive and does not follow the standard Backstage upgrade path. Rejected as unnecessarily complex.

### Option C — Network policy isolation of the scaffolder workspace pod (rejected)
Apply a Kubernetes NetworkPolicy and read-only filesystem mount to the backend pod as a defence-in-depth measure only, without bumping the package. This mitigates network exfiltration but does not stop local file reads within the container. Not a complete fix; rejected as the sole remedy but acceptable as an additional layer after the version bump.

## Platform impact

**Migrations:** None. No database schema changes, no Vault secret rotations, no mctl-gitops template changes.

**Backward compatibility:** `@backstage/plugin-scaffolder-backend` 3.1.5 and `@backstage/backend-defaults` 0.15.0 are patch/minor releases with no breaking changes to public APIs used by mctl-portal's custom plugins or template actions.

**Resource impact:** The patched packages introduce a `realpath`/`path.resolve` check per file operation inside a template step. The overhead is negligible (microseconds per call). Memory footprint is unchanged. No impact on the `labs` tenant — this change is scoped to the `admins` tenant deployment of mctl-portal.

**Risks and mitigations:**
- Risk: A transitive dependency introduced by the bump conflicts with another plugin. Mitigation: the full TypeScript type-check and test suite in CI will surface this before the image is pushed.
- Risk: The image rollout causes a brief scaffolder unavailability. Mitigation: ArgoCD performs a rolling update; the old pod remains serving until the new pod passes its readiness probe.
