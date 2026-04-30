# Patch Backstage Scaffolder Symlink Path Traversal (CVE-2026-24046)

## Context
CVE-2026-24046 (High severity) affects the Backstage scaffolder. Multiple scaffolder actions — including `debug:log`, `fs:delete`, and archive extraction (tar/zip) — are vulnerable to symlink-based path traversal. A crafted template containing symbolic links can escape the designated workspace sandbox, giving an attacker arbitrary read, write, or delete access to the host filesystem at the privilege level of the backend process.

mctl-portal uses the scaffolder as its primary mechanism for onboarding new services into tenants (via Argo Workflows and mctl-gitops). Any user with permission to submit a scaffolder template — or any template pulled from a compromised source repository — can exploit this vulnerability. The fix is a targeted upgrade of `@backstage/backend-defaults` and `@backstage/plugin-scaffolder-backend` with no breaking API changes.

## User stories
- AS a platform engineer I WANT the scaffolder to reject symlinks that point outside the workspace SO THAT malicious or misconfigured templates cannot read or modify arbitrary files on the backend host.
- AS a security officer I WANT CVE-2026-24046 patched and documented SO THAT the portal is not in a known-vulnerable state against a publicly disclosed high-severity finding.
- AS a developer I WANT scaffolder onboarding forms to continue working identically after the patch SO THAT service onboarding is not disrupted.

## Acceptance criteria (EARS)
- WHEN a scaffolder action (`debug:log`, `fs:delete`, or archive extraction) encounters a symlink whose resolved target falls outside the workspace root THE SYSTEM SHALL reject the operation and fail the workflow step with an explicit error.
- WHEN an archive (tar or zip) is extracted as part of a scaffolder step THE SYSTEM SHALL resolve all symlink entries before writing and refuse to write any entry whose resolved path is outside the workspace.
- WHILE the scaffolder backend is running THE SYSTEM SHALL use `@backstage/backend-defaults` at version 0.15.0 (or the minimum patched version applicable to the deployed Backstage line) or higher.
- WHILE the scaffolder backend is running THE SYSTEM SHALL use `@backstage/plugin-scaffolder-backend` at version 3.1.1 (or the minimum patched version applicable to the deployed Backstage line) or higher.
- IF a scaffolder workflow step fails due to the symlink check THE SYSTEM SHALL surface the failure in the Backstage UI with a message indicating the template was rejected for security reasons.
- WHEN the upgraded packages are deployed THE SYSTEM SHALL pass all existing scaffolder integration tests without modification.

## Out of scope
- Auditing or modifying third-party template repositories for pre-existing symlinks (operational concern, not a code change).
- Changes to the scaffolder UI or workflow definitions.
- Upgrades to any Backstage package beyond `@backstage/backend-defaults` and `@backstage/plugin-scaffolder-backend`.
- Rate-limiting or quota controls on scaffolder executions.
