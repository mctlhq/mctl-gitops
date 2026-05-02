# Backstage Scaffolder symlink path traversal — CVE-2026-24046

## Context
CVE-2026-24046 is a high-severity path traversal vulnerability in the Backstage Scaffolder backend. Authenticated users who can trigger scaffolder templates can craft inputs that cause the `debug:log`, `fs:delete`, and archive-extraction actions to follow symlinks and access, overwrite, or delete files outside the intended workspace sandbox. Because the scaffolder is the core onboarding engine for mctl-portal — committing to mctl-gitops and invoking Argo Workflows — any user with template execution rights can potentially corrupt infrastructure-as-code artifacts or exfiltrate secrets stored alongside the workspace.

The vulnerability is fixed in `@backstage/plugin-scaffolder-backend` ≥3.1.5 and `@backstage/backend-defaults` ≥0.15.0. Both packages are direct dependencies of `packages/backend` in the mctl-portal monorepo. The fix is a version bump with no breaking API changes.

## User stories
- AS a platform engineer I WANT the scaffolder workspace to be strictly sandboxed SO THAT no template execution can read or modify files outside its designated directory.
- AS a security officer I WANT CVE-2026-24046 remediated within the SLA for high-severity findings SO THAT mctl-portal remains compliant with the platform security policy.
- AS an end user I WANT to continue running scaffolder templates without disruption SO THAT my onboarding workflows are unaffected by the security fix.

## Acceptance criteria (EARS)
- WHEN a scaffolder action attempts to follow a symlink that resolves to a path outside the workspace root THE SYSTEM SHALL reject the operation and return an error to the template execution log.
- WHEN archive extraction encounters a symlink entry pointing outside the workspace root THE SYSTEM SHALL skip that entry and emit a warning rather than extracting it.
- WHEN `fs:delete` is called with a path that, after symlink resolution, exits the workspace sandbox THE SYSTEM SHALL throw a sandbox violation error and halt the template step.
- WHILE a scaffolder template is executing THE SYSTEM SHALL enforce that all file-system operations remain within the task workspace directory.
- IF `@backstage/plugin-scaffolder-backend` is at version ≥3.1.5 and `@backstage/backend-defaults` is at version ≥0.15.0 THEN THE SYSTEM SHALL apply the upstream symlink-resolution guardrails introduced by those releases.
- WHEN the patched packages are deployed THE SYSTEM SHALL continue to process all existing scaffolder templates without regression.

## Out of scope
- Changes to scaffolder template definitions stored in mctl-gitops.
- RBAC restriction of which users can execute templates (addressed separately by the permissions framework).
- Auditing or logging of historical template executions that may have exploited the vulnerability before the fix.
- Any upgrade of other Backstage plugins beyond the two packages listed.
