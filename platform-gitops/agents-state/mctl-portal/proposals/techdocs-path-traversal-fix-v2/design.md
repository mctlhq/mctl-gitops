# Design: techdocs-path-traversal-fix-v2

## Current state
mctl-portal uses the TechDocs plugin (`techdocs` in the plugin list in `context/architecture.md`) to generate and serve markdown-based documentation for catalog entities. The TechDocs backend pipeline involves `@backstage/plugin-techdocs-node`, which orchestrates the MkDocs process. In `local` generator mode, MkDocs runs inside the same container as the Backstage backend and reads files from the entity's `docs/` directory as checked out from its source repository.

CVE-2026-25152 affects `@backstage/plugin-techdocs-node` versions >=1.14.0 and <1.14.1, and >=1.13.0 and <1.13.11. In these versions, the Node.js wrapper does not validate symlinks before invoking MkDocs. Because MkDocs itself follows filesystem symlinks, a symlink in `docs/` that points to an arbitrary host path (e.g., `/etc/secrets`, `/var/run/secrets/kubernetes.io/serviceaccount/token`) results in that content being rendered into the generated HTML and served to all TechDocs viewers with access to that entity.

## Proposed solution
Bump `@backstage/plugin-techdocs-node` to the patched version in `package.json` and `yarn.lock`, rebuild the Docker image, and deploy via the standard ArgoCD pipeline.

Target versions:

| Current minor line | Fixed minimum version |
|---|---|
| 1.14.x | 1.14.1 |
| 1.13.x | 1.13.11 |

The patched package adds a symlink resolution check in the Node.js wrapper before handing the docs directory to MkDocs. Symlinks that resolve to paths outside the docs root are rejected with an error; legitimate in-tree symlinks (pointing within `docs/`) continue to work.

This is a pure dependency patch — no `app-config.yaml`, Kubernetes manifest, or documentation source changes are required. The fix applies to both the `local` and `docker` generator modes because the validation is in the Node.js wrapper, not in MkDocs itself.

Deployment sequence:
1. Update `@backstage/plugin-techdocs-node` to the patched version in `package.json`.
2. Run `yarn install` and `yarn dedupe`; review `yarn.lock` diff.
3. Run `yarn audit --level moderate` to confirm CVE-2026-25152 is resolved.
4. Build and tag a new Docker image.
5. Deploy to staging; verify TechDocs renders existing documentation correctly.
6. Update the image tag in mctl-gitops Helm values for `admins`; ArgoCD syncs.

## Alternatives

**Option A — Switch `techdocs.generator.runIn` from `local` to `docker`.**
Running MkDocs in a separate Docker container rather than directly in the backend process provides stronger isolation; MkDocs can only access what is mounted into its container. Dropped because: this is a larger operational change (requires Docker-in-Docker or a Docker socket in the pod), increases resource usage per TechDocs build, and is a separate architectural decision. The immediate goal is to patch the known CVE with minimal scope.

**Option B — Full Backstage upgrade to v1.50.4.**
Backstage v1.50.4 bundles the `@backstage/plugin-techdocs-node` fix alongside catalog-module patches. Dropped because: a full Backstage upgrade is a broader change with more regression surface. An isolated package bump closes the CVE faster and with less risk.

**Option C — Disable TechDocs temporarily.**
Removing the TechDocs plugin until a full upgrade cycle eliminates the attack surface. Dropped because: TechDocs is a core feature of the portal used across all catalog entities; disabling it causes direct user impact and is disproportionate when a targeted patch is available.

## Platform impact

**Migrations:** None. No schema, API, or configuration changes. Existing generated TechDocs assets (if cached) remain valid.

**Backward compatibility:** The patched package is backward compatible. Legitimate TechDocs builds (no out-of-tree symlinks) are unaffected. Builds that relied on out-of-tree symlinks (if any exist in practice) will now fail with an explicit error — this is the intended security behavior, not a regression.

**Resource impact:** No change in runtime resource consumption. The fix adds a symlink validation step before MkDocs invocation, which is negligible in CPU and memory. No impact on the `labs` tenant — mctl-portal runs exclusively in `admins`.

**Risks and mitigations:**
- Risk: A documentation repository in the catalog uses a legitimate out-of-tree symlink (e.g., linking to a shared `../common/` directory). The patched version will reject it and break that entity's TechDocs build. Mitigation: audit existing `docs/` directories for symlinks before deploying; if found, resolve them by copying the linked content inline or restructuring the docs layout. Document the change in the portal changelog.
- Risk: `yarn dedupe` after the bump changes other package versions. Mitigation: review the full `yarn.lock` diff and scope any unexpected changes before merging.
- Risk: The new pod fails its readiness probe after rollout. Mitigation: ArgoCD rolling update keeps the old pod running until the new pod is healthy; rollback is a one-line image tag revert in mctl-gitops.
