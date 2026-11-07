# Design: action-approvals-execution-bound

version-status: unverified, see commit SHA

## Source commits
- mctl-api:5962165 - feat(approvals): execution-bound action approvals for agent run tokens
- mctl-api:3487bdb - fix(api): refuse a bound DevLoop approve when no grant exists
- mctl-api:0196447 - fix(approvals): scoped tokens only, service-requested grant, no key-conflict leak (supporting: scoped-only rule)
- mctl-api:df43377 - docs(approvals): agent approval access needs a scoped run token (supporting)

## Current state of documentation
- `docs/api/index.md` exists; no action-approvals coverage (per docs-tree 2026-04-27; contents not re-read).

## Proposed solution
UPDATE `docs/api/index.md`: add a section "Action approvals". Cross-link from `docs/security/authorization.md` (proposal `agent-scopes-run-tokens`). Route rules come from openapi.yaml descriptions at 5962165 (amended by df43377).

## Alternatives
- New page `docs/api/action-approvals.md`: reasonable if index.md is short-form; would need a sidebar entry. Dropped for now to avoid structural change.
- Link only to OpenAPI: dropped, rules are behavioural.

## Impact
- Sidebar/nav: none for update (a new page would need `.vitepress/config`).
- Mermaid: one sequence diagram (flow).
- Versioning: mctl-api release containing 5962165 (unverified).
