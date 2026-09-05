# Tasks: platform-operations-approval-flow

- [ ] 1. Create `docs/reference/operations.md` with the content from
        `proposed-content.md` (section 1). — DoD: file exists, `vitepress build docs`
        is green.
- [ ] 2. Update `docs/guides/gitops-workflows.md` — insert the "Approving agent
        proposals" subsection from `proposed-content.md` (section 2). — DoD: section
        present in the correct location (after the proposal/PR lifecycle content).
- [ ] 3. Update `docs/mcp/tools-reference.md` — add the cross-link from
        `proposed-content.md` (section 3). — DoD: link present in the admin-tools area.
- [ ] 4. Update `.vitepress/config.{js,ts}` — add `operations` under the `reference/`
        sidebar group. — DoD: the new page appears in the navigation.
- [ ] 5. Cross-check the `mctl_list_operations` / `mctl_get_operation` response shape
        and the `mctl_approve_dev_loop` parameter list against `mctl-api` source
        (commits `1c6a746`, `20db091`, `3dee7e9`) and replace the
        `<TODO: confirm with author of <sha>>` markers in `proposed-content.md` with
        confirmed field names. — DoD: no TODO markers remain, or they are explicitly
        deferred with a linked follow-up issue.
- [ ] 6. Run `npm run dev` locally and open both pages. — DoD: they render, links work,
        the mermaid decision-flow diagram renders.
- [ ] 7. Cross-link: check whether `docs/platform/components.md` or
        `docs/reference/troubleshooting.md` should mention the new operations page.
        — DoD: cross-references in place where appropriate.
- [ ] 8. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`, merge.
        — DoD: deployed to docs.mctl.ai.

## Tests

- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the new / changed pages resolves (no 404s), including the new
        `reference/operations` sidebar entry and the cross-link from
        `docs/mcp/tools-reference.md`.
- [ ] T3. The `mctl_get_operation` example call in `docs/reference/operations.md` has
        been hand-checked against a live `mctl_list_operations` response (or flagged as
        unverified if MCP tools are unavailable at review time).
- [ ] T4. Confirm mctl-api version ≥ 4.37.0 is deployed to production before publishing
        (already confirmed in the 2026-09-05 inbox scan via `mctl_list_operations`
        showing `mctl-agents-approve` / `mctl-agents-reconcile` live and via
        mctl-gitops commit `3441a91`; re-verify at merge time).

## Rollback

- Revert the two page changes and the sidebar entry via a revert PR. Low risk —
  markdown and sidebar config only, no code change.
