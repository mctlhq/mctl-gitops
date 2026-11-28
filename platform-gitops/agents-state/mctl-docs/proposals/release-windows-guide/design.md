# Design: release-windows-guide

version-status: unverified, see commit SHA

## Source commits
- mctl-api:549d77b — feat(release-window): execute an approved window by one workflow dispatch (S3); follow-ups 07942f8, fbe1210, eec20ff (settle state after client disconnect, report expired claims)
- mctl-api:41b91c1 — feat(mcp): expose the sync-window tools on the shared portal
- mctl-api:9ad4b97 — feat(api,mcp): mctl_propose_window_removal, routes and a removal-aware decide page (+ 452afeb, c50e7a7, 7a636ae, 94e264e)
- mctl-api:95cb4d2 — fix(argocd): read the configured sync windows, not the ones in effect
- mctl-api:7aca28e — feat(release-window): say on the consent surfaces that the approval queues the PR for merge

## Current state of documentation
No page on release/sync windows. `docs/mcp/tools-reference.md` and `docs/api/index.md` exist but predate these tools (per docs-tree snapshot 2026-04-27; not re-verified).

## Proposed solution
- CREATE `docs/guides/release-windows.md` (see proposed-content.md).
- UPDATE `docs/mcp/tools-reference.md`: add tool entries.
- UPDATE `docs/api/index.md`: add route list once paths are confirmed.
- Sidebar: add "Release windows" under Guides in `.vitepress/config`.

## Alternatives
- Put everything in tools-reference.md: dropped, the lifecycle story would be fragmented.
- Wait for more author detail: dropped, TODO markers make gaps explicit.

## Impact
- Sidebar change: yes (Guides).
- Mermaid: one sequence/flow diagram.
- Versioning: none; applies to main.
