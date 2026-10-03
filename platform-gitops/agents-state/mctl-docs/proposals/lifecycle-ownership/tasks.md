# Tasks: lifecycle-ownership

- [ ] 1. Create `docs/platform/lifecycle-ownership.md` with the content from
        `proposed-content.md` (block 1). — DoD: file exists, `vitepress build
        docs` is green.
- [ ] 2. Update `docs/api/index.md` — insert the new `## Lifecycle
        Ownership` section from `proposed-content.md` (block 2) after
        `## Operations` and before `## MCP Endpoint`. — DoD: section renders,
        table formatting matches the rest of the page.
- [ ] 3. Update `docs/mcp/tools-reference.md` — insert the new
        `## Lifecycle Ownership` section from `proposed-content.md` (block 3).
        — DoD: section renders; tool-count banner at the top of the page is
        bumped (coordinate with `proposals/mcp-portal-tool-exposure/` so the
        count is only bumped once for both new tools combined).
- [ ] 4. Update `docs/mcp/examples.md` — insert the new `## Lifecycle
        Ownership` example from `proposed-content.md` (block 4).
        — DoD: example renders in the existing style.
- [ ] 5. Update `docs/platform/architecture.md` — add the one-line
        cross-reference from `proposed-content.md` (block 5) to the
        `mctl-api` description or Request Flow section.
        — DoD: link resolves to `/platform/lifecycle-ownership`.
- [ ] 6. Update `.vitepress/config.ts` — add `{ text: 'Lifecycle Ownership',
        link: '/platform/lifecycle-ownership' }` to the `Platform` sidebar
        group, after `Components`. — DoD: the new page appears in the
        navigation sidebar.
- [ ] 7. Run `npm run dev` locally and open `/platform/lifecycle-ownership`,
        the updated `/api/`, `/mcp/tools-reference`, `/mcp/examples`, and
        `/platform/architecture` pages. — DoD: all render, internal links
        work, no console errors.
- [ ] 8. Cross-link: check whether `docs/reference/troubleshooting.md`
        should mention "an owner looks stuck / stale" as a diagnosable
        symptom, pointing at the new concept page. — DoD: either a new
        Troubleshooting entry is added, or a note is left in the PR
        explaining why it was judged unnecessary this cycle.
- [ ] 9. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`,
        merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the new / changed pages resolves (no 404s),
        including the new sidebar entry and the cross-references between
        the concept page, the API reference, and the MCP tools reference.
- [ ] T3. The REST examples in the `docs/api/index.md` "Lifecycle
        Ownership" section have been hand-checked against the actual
        `mctl-api` route table (`internal/api/router.go` on `main`) —
        method, path, and query-parameter names must match exactly.
- [ ] T4. The MCP tool parameter table in `docs/mcp/tools-reference.md`
        matches the `mcplib.NewTool("mctl_get_lifecycle_ownership", ...)`
        definition in `internal/mcp/lifecycle.go` on `main` (parameter
        names, which are required with `id`/`pr_url`, defaults for
        `include_events`/`include_legacy`).

## Rollback
- Delete the new file and revert the four page edits + the sidebar entry
  via a revert PR. Low risk — markdown and one sidebar-config line only, no
  code or infra changes.
