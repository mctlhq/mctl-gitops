# Document container hardening defaults and the pre-commit image-user check

version-status: unverified, see commit SHA

## Context
On 2026-10-16 `mctl-gitops` changed how services run and deploy. The `base-service` chart now defaults to seccomp `RuntimeDefault`, no privilege escalation and all capabilities dropped (2db594d), and offers opt-in `runAsNonRoot` / `readOnlyRootFilesystem` with `writablePaths` emptyDir mounts (c8448e0, 23b9f10). The `deploy-service` workflow gained a `check-image-user` step between build and commit (187a366) that fails early when the image USER cannot satisfy `runAsNonRoot`. `docs/guides/services.md` and `docs/reference/troubleshooting.md` do not mention any of this.

## User stories
- AS a developer I WANT to know why my deploy failed at `check-image-user` SO THAT I can fix my Dockerfile.
- AS a tenant owner I WANT to know the default container security settings SO THAT I can predict whether my app runs.

## Acceptance criteria (EARS)
- WHEN a reader opens docs/guides/services.md THE SYSTEM SHALL describe the default security context and the opt-in `runAsNonRoot` / `readOnlyRootFilesystem` / `writablePaths` values.
- IF the image USER is root or a non-numeric name and `runAsNonRoot` is applied THEN THE SYSTEM SHALL document that deploy fails at `check-image-user`, and show a Dockerfile fix (numeric `USER 1000`).
- WHEN `runAsNonRoot` is not applied THE SYSTEM SHALL state that the check only warns.
- WHEN the action is `update-config` THE SYSTEM SHALL state the check is skipped.
- WHEN a reader opens troubleshooting THE SYSTEM SHALL list the `CreateContainerConfigError` symptom and link to the guide.

## Out of scope
- Platform-internal services' hardening rollout (temporal-web, mctl-agent values).
- Pod Security Standards policy for tenant namespaces.
