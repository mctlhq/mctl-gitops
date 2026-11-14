# Tasks: agent-fixer-guardrails

version-status: unverified, see commit SHA

- [ ] 1. Update `docs/platform/components.md` with the content from `proposed-content.md`. — DoD: file updated, `vitepress build docs` is green.
- [ ] 2. Confirm the page's current mctl-agent block and anchor placement; confirm shipped version via MCP. — DoD: TODOs resolved.
- [ ] 3. Run `npm run dev` and open the page. — DoD: renders, links work.
- [ ] 4. Cross-link from `docs/reference/troubleshooting.md` if it exists. — DoD: link in place.
- [ ] 5. Open a PR against `mctlhq/mctl-docs`, request `@claude review`, merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors or warnings.
- [ ] T2. All links in the changed page resolve.
- [ ] T3. No code snippets requiring validation beyond the YAML example.

## Rollback
- Revert PR. Low risk, markdown only.
