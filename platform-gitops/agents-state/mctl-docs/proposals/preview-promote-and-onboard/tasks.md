# Tasks: preview-promote-and-onboard

- [ ] 1. Read `docs/guides/previews.md`, apply `proposed-content.md` (UPDATE). — DoD: `vitepress build docs` green.
- [ ] 2. Resolve TODO markers with authors of db4dda2 and d45bcc4 (request bodies, MCP params, onboard plan fields). — DoD: no TODO remains.
- [ ] 3. Run `npm run dev`, open the page. — DoD: renders, links work, mermaid renders.
- [ ] 4. Cross-link from `docs/guides/services.md`, `docs/mcp/tools-reference.md` (add `mctl_promote_deployment`) and `docs/guides/rollbacks.md`. — DoD: links in place.
- [ ] 5. Open PR against `mctlhq/mctl-docs`, request `@claude review`, merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` clean.
- [ ] T2. All links resolve.
- [ ] T3. Snippets hand-checked.

## Rollback
- Revert PR. Markdown only.
