# Design: starter-workspace-profile

## Source commits
- mctl-api:8081830 — feat(signup): fund only the bounded starter profile
- mctl-api:0244bac — fix(signup): reserve CPU for starter deployment workflows
- mctl-api:b5394f6 — feat: administer invitations with funded workspace reservations
- mctl-portal:de6387a — feat(signup): create customers with the starter profile

## Current state of documentation
- `docs/platform/tenants.md` (if it exists; verify against the live tree, `context/docs-tree.md` is a 2026-04-27 snapshot) describes quotas without profiles.
- `docs/mcp/tools-reference.md` lacks the signup tools.

## Proposed solution
Add a "Workspace profiles" section to `docs/platform/tenants.md` and the three tools plus the `workspace_profile` parameter to `docs/mcp/tools-reference.md`. Mark the invitation program as admin-operated and invite-only.

## Risks
- Starter CPU request value is not stated in the sources reviewed (commit 0244bac adjusts it); it is intentionally omitted. <TODO: confirm with author starter CPU request>
