# Design: deploy-image-user-and-hardening

## Source commits
- mctl-gitops:187a366 — feat(deploy-service): check the image user before committing
- mctl-gitops:dd920da — fix(deploy): bound the image-user registry read, reject bad repos
- mctl-gitops:c8448e0 — feat(base-service): opt-in non-root and read-only root filesystem
- mctl-gitops:2db594d — fix(base-service): default seccomp, no privilege escalation, drop ALL
- mctl-gitops:23b9f10 — fix(base-service): dedupe writablePaths and fail on name collisions

## Current state of documentation
- docs/guides/services.md (Service Deployment): no security-context section.
- docs/reference/troubleshooting.md: no entry for a failed image-user check or CreateContainerConfigError.

## Proposed solution
Add a "Container security" section to docs/guides/services.md and a troubleshooting entry. Whether tenants can set these chart values themselves via MCP/deploy params is unclear: <TODO: confirm with author of c8448e0>.

## Alternatives
- New standalone page `docs/guides/container-security.md`: rejected, content is short and tied to deploy flow.

## Impact
No sidebar change. A small mermaid flow (validate → build → check-image-user → commit) is optional.
