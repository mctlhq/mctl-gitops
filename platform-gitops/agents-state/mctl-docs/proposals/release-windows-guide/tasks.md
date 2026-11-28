# Tasks: release-windows-guide

- [ ] 1. Create `docs/guides/release-windows.md` from `proposed-content.md`; resolve all TODO markers with the author of 549d77b / 9ad4b97. — DoD: file exists, `vitepress build docs` green.
- [ ] 2. Add sidebar entry under Guides in `.vitepress/config`. — DoD: page appears in nav.
- [ ] 3. Run `npm run dev`, open the page. — DoD: renders, links work, mermaid renders.
- [ ] 4. Cross-link from `docs/mcp/tools-reference.md` (add tool entries) and `docs/api/index.md` (routes). — DoD: cross-references in place.
- [ ] 5. Open PR against `mctlhq/mctl-docs`, request `@claude review`, merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors/warnings.
- [ ] T2. All links resolve.
- [ ] T3. Any JSON/curl snippets hand-checked with `jq .`.

## Rollback
Revert PR; markdown only.
