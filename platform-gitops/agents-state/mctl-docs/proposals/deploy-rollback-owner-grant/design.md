# Design: deploy-rollback-owner-grant

version-status: unverified, see commit SHA

## Source commits
- mctl-api:8780f98 — feat(deploy): rollback_deployment behind an owner's grant
- mctl-api:46694e8 — fix(deploy): rollback apply drops deployment_id; governed workspaces need a grant
- mctl-gitops:c6f49f9 — fix(workflows): rollback-service restores tag and digest together
- mctl-gitops:ad65613 — fix(workflows): rollback-image-ref fails closed on unobservable history
- mctl-gitops:7fc94b6 — fix(workflows): rollback-image-ref distrusts a digest shared across tags
- mctl-gitops:6fd14e2 — fix(workflows): leftover digest must not veto an operator's explicit digest
- mctl-gitops:8d09fb4 — fix(workflows): rollback-image-ref never echoes a git remote URL

## Current state of documentation
- `docs/guides/rollbacks.md` ("Rollbacks") exists; body not read by the researcher (title-only snapshot of 2026-04-27). Likely describes tag-only rollback without owner grant. Implementer must read it and replace stale statements.
- `docs/mcp/tools-reference.md` exists; `mctl_rollback_deployment` is likely missing.

## Proposed solution
UPDATE `docs/guides/rollbacks.md`: add a "Production rollback (owner grant)" section and a "What a rollback restores" section; fix any statement that a rollback is a single unapproved tag change. UPDATE `docs/mcp/tools-reference.md`: add a tool entry. See `proposed-content.md`. Anything not evidenced in the commits is marked TODO.

## Alternatives
- New standalone page `docs/guides/rollback-grants.md`: dropped, splits one topic across two pages.
- Only touch tools-reference: dropped, leaves the guide wrong.

## Impact
- No sidebar/nav change.
- Optional mermaid sequence diagram (included).
- Applies to the main branch; no doc versioning known.
- Related proposals: `deploy-analyze-and-plan`, `devloop-grant-approval` (same grant model); cross-link.
