# Scaffolder Path Traversal Fix (CVE-2026-24046)

## Context
CVE-2026-24046 (CVSS 7.1, High) is a symlink path traversal vulnerability in the Backstage Scaffolder backend. Attackers who can create and execute Scaffolder templates can read arbitrary files on the backend host via the `debug:log` action, delete files via `fs:delete`, and write to arbitrary locations on the filesystem by embedding malicious symlinks inside tar or zip archives processed during template execution.

mctl-portal actively uses the Scaffolder for service onboarding into tenant namespaces and exposes template authoring to a defined set of portal users. Patched versions of all affected packages (`@backstage/backend-defaults`, `@backstage/plugin-scaffolder-backend`, `@backstage/plugin-scaffolder-node`) are already published, making the remediation a dependency version bump with no API or behavioral changes.

## User stories
- AS a platform engineer I WANT the Scaffolder packages patched to their fixed versions SO THAT no portal user can exploit path traversal to read, overwrite, or delete files on the backend host.
- AS a security team member I WANT evidence that the vulnerability is resolved SO THAT the service passes the next security review without an open High finding.
- AS a developer using the Scaffolder I WANT onboarding templates to continue working unchanged after the patch SO THAT my workflow is not disrupted.

## Acceptance criteria (EARS)
- WHEN `@backstage/backend-defaults` is updated THEN THE SYSTEM SHALL resolve to version 0.12.2 or later (or 0.13.2 / 0.14.1 / 0.15.0 on the respective minor lines).
- WHEN `@backstage/plugin-scaffolder-backend` is updated THEN THE SYSTEM SHALL resolve to version 2.2.2, 3.0.2, or 3.1.1 or later on the matching minor line.
- WHEN `@backstage/plugin-scaffolder-node` is updated THEN THE SYSTEM SHALL resolve to version 0.11.2 or 0.12.3 or later on the matching minor line.
- WHEN a Scaffolder template action processes a tar or zip archive containing a symlink pointing outside the workspace THEN THE SYSTEM SHALL reject the file and abort the task without following the symlink.
- WHILE a Scaffolder task is executing THEN THE SYSTEM SHALL confine all filesystem reads and writes to the task workspace directory.
- IF the `debug:log` action is invoked with a path argument that resolves outside the workspace THEN THE SYSTEM SHALL return an error to the task log and not expose file contents.
- WHEN the patched packages are deployed THEN THE SYSTEM SHALL pass all existing Scaffolder end-to-end tests without regression.
- WHEN a new Docker image is built after the patch THEN THE SYSTEM SHALL produce a clean `yarn audit` output with no High or Critical findings related to CVE-2026-24046.

## Out of scope
- Changes to Scaffolder template RBAC or permission policies (separate concern).
- Patching unrelated CVEs discovered during the audit (tracked separately).
- Migration of templates to a new action API — the fix is a version bump only.
- Changes to the mctl-gitops scaffolder workflow templates.
