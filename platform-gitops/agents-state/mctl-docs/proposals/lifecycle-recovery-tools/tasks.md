# Tasks: lifecycle-recovery-tools

- [ ] 0. **Prerequisite**: confirm `proposals/lifecycle-ownership/` has
        landed (its four pages are merged and deployed) before starting
        task 1. — DoD: `docs/platform/lifecycle-ownership.md`,
        `docs/api/index.md`'s `## Lifecycle Ownership` section, and
        `docs/mcp/tools-reference.md`'s `## Lifecycle Ownership` section
        all exist on `main`.
- [ ] 1. Append the `## Recovery` subsection from `proposed-content.md`
        (Block 1) to `docs/platform/lifecycle-ownership.md`, immediately
        before its `## Where to find it` section. — DoD: section renders,
        `vitepress build docs` is green.
- [ ] 2. Extend the `## Lifecycle Ownership` section of `docs/api/index.md`
        with the five endpoints from `proposed-content.md` (Block 2).
        — DoD: section renders, table formatting matches the rest of the
        page.
- [ ] 3. Extend the `## Lifecycle Ownership` section of
        `docs/mcp/tools-reference.md` with the five tools from
        `proposed-content.md` (Block 3). — DoD: section renders; tool-count
        banner bumped by +5, coordinated with `proposals/lifecycle-ownership/`
        and `proposals/mcp-roadmap-control-plane/` per their design.md notes.
- [ ] 4. Extend `docs/mcp/examples.md` with the recovery example from
        `proposed-content.md` (Block 4). — DoD: example renders in the
        existing style.
- [ ] 5. Run `npm run dev` locally and open the updated pages. — DoD: all
        render, internal links work, no console errors.
- [ ] 6. Cross-link: check whether `docs/reference/troubleshooting.md`
        should mention "a lifecycle owner looks stuck/dead" pointing at the
        Recovery section specifically (not just the base concept page).
        — DoD: either added, or a note left in the PR explaining why not.
- [ ] 7. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`,
        merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the changed sections resolves (no 404s), including
        the anchor links between the Recovery subsection, the API
        reference, and the MCP tools reference.
- [ ] T3. The REST request-body examples in `docs/api/index.md` have been
        hand-checked against `internal/api/handlers_lifecycle_recovery.go`
        and `handlers_lifecycle_conflict.go` on `mctl-api` `main` — field
        names (`expected_owner_type`, `expected_epoch` as an integer, etc.)
        must match exactly (`jq .` the example JSON bodies).
- [ ] T4. The MCP tool parameter tables match
        `internal/mcp/lifecycle_recovery.go` on `main` exactly, including
        which tools require `confirm="yes"`.

## Rollback
- Revert the four section-append edits via a revert PR. Low risk —
  markdown only, no code or infra changes. If `proposals/lifecycle-ownership/`
  has not yet landed when this would be rolled back, there is nothing to
  revert on the target page since it was never appended.
