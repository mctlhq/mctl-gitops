# Tasks: mcp-oauth-flow-fixes

- [ ] 1. Update `docs/security/authentication.md` with the content from
        `proposed-content.md` (block 1). — DoD: file updated, `vitepress
        build docs` is green.
- [ ] 2. Update `docs/reference/troubleshooting.md` with the content from
        `proposed-content.md` (block 2). — DoD: new entry renders under
        `## Authentication`, consistent with the existing entry style.
- [ ] 3. Run `npm run dev` locally and open `/security/authentication` and
        `/reference/troubleshooting`. — DoD: both render, no broken links.
- [ ] 4. Cross-link: check `docs/mcp/connecting.md`'s existing
        "Troubleshooting" pointer still correctly routes a reader here (it
        already links to `/reference/troubleshooting`, so this should need
        no edit — confirm rather than assume). — DoD: link confirmed
        correct, or fixed if not.
- [ ] 5. Coordinate with `proposals/mcp-oauth-client-lifetime/` if both are
        being implemented in the same cycle, to avoid two PRs editing
        overlapping sections of `docs/reference/troubleshooting.md` at
        once. — DoD: either sequenced, or confirmed non-overlapping
        (different entries under the same `## Authentication` heading is
        fine; same entry text is not).
- [ ] 6. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`,
        merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the changed pages resolves (no 404s).
- [ ] T3. The new prose does not state an exact grace-window value as a
        guaranteed contract (the commit explicitly treats the current
        value as tunable) — hand-checked against `proposed-content.md`
        before merge.

## Rollback
- Revert the two page edits via a revert PR. Low risk — markdown only.
