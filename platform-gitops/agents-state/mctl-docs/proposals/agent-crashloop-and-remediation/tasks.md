# Tasks: agent-crashloop-and-remediation

- [ ] 1. Apply the patches in `proposed-content.md` to the four pages; resolve TODOs with mctl-agent authors. — DoD: files updated, `vitepress build docs` green.
- [ ] 2. Sidebar: no change expected. — DoD: confirmed.
- [ ] 3. Run `npm run dev` and open each page. — DoD: renders, links work.
- [ ] 4. Cross-link components.md to troubleshooting, rollbacks and scaling. — DoD: references in place.
- [ ] 5. Open PR against `mctlhq/mctl-docs`, request `@claude review`, merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` clean.
- [ ] T2. Links resolve.
- [ ] T3. Snippets hand-checked.

## Rollback
Revert PR; markdown only.
