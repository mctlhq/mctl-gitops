# Tasks: action-approvals-execution-bound

version-status: unverified, see commit SHA

- [ ] 1. Update `docs/api/index.md` with `proposed-content.md`. - DoD: `vitepress build docs` green.
- [ ] 2. No sidebar change (unless the standalone-page alternative is chosen). - DoD: confirmed.
- [ ] 3. `npm run dev`; open page. - DoD: renders, mermaid renders, links work.
- [ ] 4. Cross-link from `docs/security/authorization.md`. - DoD: anchors resolve.
- [ ] 5. Resolve TODOs (route list path, 3487bdb error code, request bodies) with author; PR against `mctlhq/mctl-docs`, `@claude review`, merge. - DoD: deployed.

## Tests
- [ ] T1. `vitepress build docs` clean.
- [ ] T2. Links resolve.
- [ ] T3. curl examples checked against openapi.yaml; JSON parses with `jq .`.

## Rollback
- Revert PR (markdown only).
