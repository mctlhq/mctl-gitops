# Backstage Scaffolder Symlink Path Traversal (CVE-2026-24046)

## Context
mctl-portal actively uses the Backstage scaffolder plugin to onboard new services into the platform. A path traversal vulnerability (CVE-2026-24046, GHSA-rq6q-wr2q-7pgp) has been disclosed in three scaffolder-related packages: `@backstage/plugin-scaffolder-backend`, `@backstage/backend-defaults`, and `@backstage/plugin-scaffolder-node`. Any user with template creation or execution access can craft symlinks inside a scaffold workspace and use the `debug:log`, `fs:delete`, or archive extraction actions to read, delete, or overwrite files outside the sandbox directory on the backend host.

If left unpatched, the vulnerability exposes the backend container filesystem and — critically — the mctl-gitops commit credentials stored on that filesystem or injected as environment variables. The fix is a patch-version bump of the three affected packages with no breaking API changes, making the cost of remediation very low.

## User stories
- AS a platform security officer I WANT the scaffolder backend packages patched to the versions that resolve CVE-2026-24046 SO THAT no user can escape the scaffold workspace sandbox and access backend filesystem resources.
- AS a portal engineer I WANT the patch applied with no API or template changes SO THAT existing onboarding templates continue to work without modification.
- AS an on-call engineer I WANT the patched image deployed via the standard mctl-gitops/ArgoCD pipeline SO THAT the fix is auditable and rollback is straightforward.

## Acceptance criteria (EARS)
- WHEN a scaffolder action attempts to resolve a symlink that points outside the workspace sandbox directory THE SYSTEM SHALL reject the operation and return an error to the template executor.
- WHEN the three patched packages (`@backstage/plugin-scaffolder-backend`, `@backstage/backend-defaults`, `@backstage/plugin-scaffolder-node`) are installed THE SYSTEM SHALL report package versions at or above the minimum patched versions that resolve CVE-2026-24046.
- WHILE a scaffold task is executing THE SYSTEM SHALL confine all file-system operations to the designated per-task workspace directory and its descendants.
- IF a crafted archive entry or `fs:delete` path resolves to a location outside the workspace sandbox THE SYSTEM SHALL abort the action step and log a security warning containing the offending path.
- WHEN the patched backend image is deployed to the `admins` tenant THE SYSTEM SHALL pass all existing scaffolder integration tests with no regressions.
- IF the deployment health check fails after image rollout THE SYSTEM SHALL automatically roll back to the previous image via ArgoCD sync.

## Out of scope
- Changes to scaffolder templates or Argo Workflow definitions.
- Broader sandboxing improvements (e.g., running scaffolder actions inside an isolated container or VM).
- Permission model changes for template execution access.
- Upgrades to packages not listed in the CVE advisory.
- Any changes to the `labs` tenant workloads.
