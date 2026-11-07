# Tasks: agent-scopes-run-tokens

version-status: unverified, see commit SHA

- [ ] 1. Read current `docs/security/authorization.md`; apply the section from `proposed-content.md`. - DoD: file updated, `vitepress build docs` green.
- [ ] 2. No sidebar change needed. - DoD: confirmed.
- [ ] 3. Run `npm run dev` and open the page. - DoD: renders, tables and anchors work.
- [ ] 4. Cross-link with `docs/api/index.md` action-approvals section (proposal `action-approvals-execution-bound`). - DoD: links resolve.
- [ ] 5. Resolve all `<TODO>` markers with the author of 352f9f5 / confirm prod rollout; open PR against `mctlhq/mctl-docs`, request `@claude review`, merge. - DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors/warnings.
- [ ] T2. All links resolve.
- [ ] T3. Route table checked against mctl-api `docs/implement-agent-scope.md`.

## Rollback
- Revert PR (markdown only).
