# Tasks: deploy-image-user-and-hardening

- [ ] 1. Apply `proposed-content.md` to the target page(s). — DoD: files updated, `vitepress build docs` is green.
- [ ] 2. Resolve every `<TODO: confirm with author ...>` marker (or remove the sentence). — DoD: no TODO markers remain.
- [ ] 3. (If a new page) Add the sidebar/nav entry in `.vitepress/config`. — DoD: page appears in navigation.
- [ ] 4. Run `npm run dev` and open the page. — DoD: renders, links work.
- [ ] 5. Cross-link from 1-2 related pages.
- [ ] 6. Open a PR against `mctlhq/mctl-docs`, request `@claude review`, merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors/warnings.
- [ ] T2. All links resolve.
- [ ] T3. Code snippets hand-checked (`jq .` for JSON).

## Rollback
Revert PR; markdown only, low risk.
