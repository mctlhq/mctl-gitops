# Tasks: deploy-rollback-owner-grant

- [ ] 1. Read `docs/guides/rollbacks.md`, then apply `proposed-content.md` (UPDATE) and remove stale statements. — DoD: no statement contradicts the new behaviour; `vitepress build docs` is green.
- [ ] 2. Add `mctl_rollback_deployment` entry to `docs/mcp/tools-reference.md`. — DoD: entry present.
- [ ] 3. Resolve every `<TODO: confirm ...>` marker with the author of 8780f98 (request body, response fields, error codes). — DoD: no TODO remains.
- [ ] 4. Run `npm run dev` and open both pages. — DoD: renders, links work, mermaid renders.
- [ ] 5. Cross-link from `docs/guides/gitops-workflows.md` and `docs/security/authorization.md`. — DoD: links in place.
- [ ] 6. Open PR against `mctlhq/mctl-docs`, request `@claude review`, merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. All links resolve.
- [ ] T3. Code snippets hand-checked (JSON parses with `jq .`).

## Rollback
- Revert PR. Markdown only, low risk.
