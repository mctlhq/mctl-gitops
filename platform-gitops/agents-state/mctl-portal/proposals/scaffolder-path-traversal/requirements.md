# Close CVE-2026-24046: symlink path traversal in scaffolder

## Context
CVE-2026-24046 describes a symlink-based path traversal vulnerability in scaffolder actions
(`debug:log`, `fs:delete`, archive extraction) of the `@backstage/backend-defaults` and
`plugin-scaffolder-backend` packages. An authenticated user with the right to run templates
can, via specially crafted symlink constructs, read, write and delete arbitrary files on
the server — including Vault secrets mounted via ExternalSecret as files in the backend pod.

In mctl-portal the scaffolder is the central onboarding tool; Vault secrets (Vault token,
Postgres DSN, GitHub App credentials) are mounted in the same pod, making the attack
surface critically broad. Backstage is deployed in the `admins` tenant under ArgoCD; the
change affects only this tenant and does not impact the `labs` tenant.

## User stories
- AS a platform engineer I WANT the scaffolder backend to reject any file operation that
  resolves outside the task workspace SO THAT a malicious template cannot exfiltrate or
  corrupt Vault secrets and other server-side files.
- AS a security officer I WANT all scaffolder dependencies pinned to patched versions in
  the production Docker image SO THAT the CVE-2026-24046 attack surface is fully closed
  after the next deploy.
- AS a developer I WANT the scaffolder to remain fully functional for legitimate templates
  SO THAT onboarding workflows are not disrupted by the security fix.

## Acceptance criteria (EARS)
- WHEN a scaffolder action (`debug:log`, `fs:delete`, or archive extraction) resolves a
  file path that exits the task workspace directory THE SYSTEM SHALL reject the operation
  with an error and abort the template step.
- WHEN a symlink inside an extracted archive points to a path outside the workspace THE
  SYSTEM SHALL refuse to create that symlink and mark the step as failed.
- WHILE a scaffolder task is executing THE SYSTEM SHALL enforce that all file-system
  operations remain within the ephemeral task workspace directory.
- WHEN the backend pod is deployed with `@backstage/backend-defaults` >= 0.12.2 and
  `plugin-scaffolder-backend` >= 3.1.1 THE SYSTEM SHALL pass all existing scaffolder
  integration tests without regressions.
- IF `yarn audit` is run against the production lockfile THEN THE SYSTEM SHALL report no
  critical or high CVEs related to CVE-2026-24046 or CVE-2026-32237.

## Out of scope
- Restricting user permissions to run templates (RBAC) — separate topic.
- Upgrading Backstage itself to v1.50.3 (covered in `integration-scm-credentials`).
- Changes in the `labs` tenant.
- Audit of custom scaffolder plugins for their own path-traversal vulnerabilities.
