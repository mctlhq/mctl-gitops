# Release windows: approval, execution and removal

version-status: unverified, see commit SHA (mctl-api 4.181.0 inferred from mctl-gitops 6665a00; mcp__mctl__* unavailable)

## Context
Between 2026-11-22 and 2026-11-27 mctl-api gained a coherent release (sync) window feature set: an approved window is executed by a single workflow dispatch (549d77b), the sync-window MCP tools are exposed on the shared portal (41b91c1), a new MCP tool `mctl_propose_window_removal` plus REST routes let users propose removing a window (9ad4b97, 452afeb, c50e7a7), the window listing reads configured rather than in-effect windows (95cb4d2), and consent surfaces state that approval queues the PR for merge (7aca28e).

The docs snapshot (2026-04-27) has no page on release windows, and `docs/mcp/tools-reference.md` and `docs/api/index.md` do not mention these tools or routes.

## User stories
- AS a tenant owner I WANT to understand how release windows are proposed, approved and executed SO THAT I can plan deploys.
- AS a developer I WANT to know how to propose removing a window via MCP SO THAT I do not edit gitops by hand.
- AS an approver I WANT to know what approving does (queues the PR for merge) SO THAT I approve knowingly.

## Acceptance criteria (EARS)
- WHEN a reader opens `docs/guides/release-windows.md` THE SYSTEM SHALL describe the lifecycle: propose, approve, execute (single workflow dispatch).
- WHEN a reader looks up window listing THE SYSTEM SHALL state that configured windows are shown, not only those currently in effect (95cb4d2).
- IF a reader wants to remove a window THEN THE SYSTEM SHALL show an example call of `mctl_propose_window_removal` with arguments marked `<TODO: confirm with author of 9ad4b97>`.
- WHEN a reader opens the approval-page section THE SYSTEM SHALL state that approving queues the PR for merge (7aca28e) and that removals use work-item kind `release.window.removal`.
- WHEN a reader opens `docs/mcp/tools-reference.md` THE SYSTEM SHALL list the sync-window tools and `mctl_propose_window_removal`.
- WHEN a reader opens `docs/api/index.md` THE SYSTEM SHALL list the window execute/removal routes (paths `<TODO: confirm with author of 549d77b>`).
- WHILE version status is unverified THE SYSTEM SHALL NOT claim a specific released version on the page.

## Out of scope
- Glovo access flow, ArgoCD sync-window internals, migration guide, localisation.
