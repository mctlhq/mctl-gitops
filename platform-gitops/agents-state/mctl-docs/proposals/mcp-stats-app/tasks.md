# Tasks: mcp-stats-app

- [ ] 1. Create `docs/mcp/stats-app.md` from `proposed-content.md`; resolve TODOs with the author of db5757f. — DoD: file exists, `vitepress build docs` green.
- [ ] 2. Add sidebar entry under MCP in `.vitepress/config`. — DoD: page in navigation.
- [ ] 3. Run `npm run dev`, open the page. — DoD: renders, links work.
- [ ] 4. Cross-link from `docs/mcp/overview.md` and `docs/mcp/tools-reference.md`. — DoD: links in place.
- [ ] 5. Open PR against `mctlhq/mctl-docs`, request `@claude review`, merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` clean.
- [ ] T2. Links resolve.
- [ ] T3. Snippets hand-checked.

## Rollback
Revert PR; markdown only.
