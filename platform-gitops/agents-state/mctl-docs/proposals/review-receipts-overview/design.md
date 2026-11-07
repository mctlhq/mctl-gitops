# Design: review-receipts-overview

version-status: unverified, see commit SHA

## Source commits
- mctl-api:30ae621 - feat(mcp): enable review assertion on the shared portal
- mctl-api:857a2b8 - feat(agents): issue-917 review: enable autonomous worker receipts (context; adds docs/review-receipts.md changes)
- mctl-api:9435c0f - feat(review): accept we_<uuid> execution ids in Tier B (context only)

## Current state of documentation
- `docs/mcp/tools-reference.md` exists; no mention of review receipts or `mctl_submit_review_assertion` (per docs-tree; content not re-read).

## Proposed solution
UPDATE `docs/mcp/tools-reference.md` with one minimal, flagged tool entry. Verification result: tool name and the enabling change are confirmed from the 30ae621 diff; prod availability and argument schema are NOT confirmed, so proposed-content is minimal and marked do-not-merge-until-confirmed.

## Alternatives
- Standalone review-receipts page: dropped, bodies of the series not fully read and many parts are flag-gated.
- Skip entirely: dropped, the tool is a user-visible write for admins; a minimal flagged entry preserves the spec.

## Impact
- Sidebar/nav: none. Mermaid: none.
- Versioning: mctl-api release containing 30ae621; confirm prod version first.
