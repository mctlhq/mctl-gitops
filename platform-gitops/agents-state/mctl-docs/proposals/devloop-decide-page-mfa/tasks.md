# Tasks: devloop-decide-page-mfa

- [ ] 1. Read the three target pages and apply `proposed-content.md` (UPDATE). — DoD: `vitepress build docs` is green.
- [ ] 2. Check overlap with proposals `devloop-grant-approval`, `action-approvals-execution-bound`, `approve-content-digest`; merge wording. — DoD: no duplicate or conflicting statements.
- [ ] 3. Resolve TODO markers with the author of 2019361 / 7ae67a4 (break-glass visibility, final ledger text). — DoD: no TODO remains.
- [ ] 4. Run `npm run dev`, open the pages. — DoD: renders, links work, mermaid renders.
- [ ] 5. Cross-link Authorization, Tools Reference and GitOps Workflows. — DoD: links in place.
- [ ] 6. Open PR against `mctlhq/mctl-docs`, request `@claude review`, merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` clean.
- [ ] T2. All links resolve.
- [ ] T3. Snippets hand-checked.

## Rollback
- Revert PR. Markdown only.
