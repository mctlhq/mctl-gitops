# Tasks: mcp-roadmap-control-plane

- [ ] 1. Create `docs/platform/roadmap-control-plane.md` with the content
        from `proposed-content.md` (Block 1). — DoD: file exists,
        `vitepress build docs` is green.
- [ ] 2. Update `docs/api/index.md` — insert the new `## Roadmap` section
        from `proposed-content.md` (Block 2) after `## Human Input` and
        before `## MCP Endpoint`. — DoD: section renders, table formatting
        matches the rest of the page.
- [ ] 3. Update `docs/mcp/tools-reference.md` — insert the new `## Roadmap
        Control Plane` section from `proposed-content.md` (Block 3).
        — DoD: section renders; tool-count banner bumped by +4, coordinated
        with `proposals/lifecycle-ownership/` and
        `proposals/lifecycle-recovery-tools/` so the count is only bumped
        once for the cumulative total of all three (see design.md Impact).
- [ ] 4. Update `docs/mcp/examples.md` — insert the new `## Roadmap Control
        Plane` example from `proposed-content.md` (Block 4).
        — DoD: example renders in the existing style.
- [ ] 5. Update `docs/platform/architecture.md` — add the one-line
        cross-reference from `proposed-content.md` (Block 5) to the Request
        Flow section. — DoD: link resolves to `/platform/roadmap-control-plane`.
- [ ] 6. Update `.vitepress/config.ts` — add `{ text: 'Roadmap Control
        Plane', link: '/platform/roadmap-control-plane' }` to the
        `Platform` sidebar group, after `Components`. — DoD: the new page
        appears in the navigation sidebar.
- [ ] 7. Run `npm run dev` locally and open the new/updated pages. — DoD:
        all render, internal links work, no console errors, mermaid block
        (if the optional sequence diagram is added) renders.
- [ ] 8. Cross-link: check whether `docs/reference/troubleshooting.md`
        should mention "a wave failed with `plan_stale` /
        `publication_too_old` / `invalid_selection`" as a diagnosable
        symptom, pointing at the new concept page. — DoD: either a new
        Troubleshooting entry is added, or a note is left in the PR
        explaining why it was judged unnecessary this cycle.
- [ ] 9. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`,
        merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the new / changed pages resolves (no 404s),
        including the new sidebar entry and cross-references between the
        concept page, the API reference, and the MCP tools reference.
- [ ] T3. The REST examples in `docs/api/index.md`'s new `## Roadmap`
        section have been hand-checked against `internal/api/router.go` and
        `internal/openapi/openapi.yaml` on `mctl-api` `main` — method,
        path, and query-parameter names must match exactly (`jq .` the
        `openapi.yaml` roadmap paths if in doubt).
- [ ] T4. The MCP tool parameter tables in `docs/mcp/tools-reference.md`
        match `internal/mcp/roadmap.go` and `internal/mcp/roadmap_wave.go`
        on `main` exactly (required vs. optional parameters, default for
        `required_only`).

## Rollback
- Delete the new file and revert the four page edits + the sidebar entry
  via a revert PR. Low risk — markdown and one sidebar-config line only, no
  code or infra changes.
