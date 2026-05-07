# Tasks: mcp-agent-runs-cron-source

- [ ] 1. Update `docs/mcp/tools-reference.md` with the content from
        `proposed-content.md` (UPDATE mode — before/after diff for the
        `mctl_list_recent_agent_runs` section). — DoD: file exists,
        `vitepress build docs` is green.
- [ ] 2. Confirm that no sidebar or nav config change is needed
        (the page is already linked). — DoD: verified in
        `.vitepress/config.{js,ts}`.
- [ ] 3. Run `npm run dev` locally and open `docs/mcp/tools-reference.md`.
        — DoD: page renders, example JSON block displays correctly,
        version-status admonition is visible.
- [ ] 4. Cross-link check: verify that `docs/mcp/overview.md` and
        `docs/mcp/examples.md` do not describe `mctl_list_recent_agent_runs`
        in a way that contradicts the new merged-list behavior; update if
        needed. — DoD: no contradictions.
- [ ] 5. Once mctl-gitops image bump for mctl-api ≥ 2026-05-07 is merged,
        remove the version-status note from the page. — DoD: clean prod
        docs without the unverified marker.
- [ ] 6. Open a PR against `mctlhq/mctl-docs`, run codex review, merge.
        — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the updated section resolves (no 404s).
- [ ] T3. Example JSON in the proposed-content parses cleanly with
        `echo '<json>' | python3 -m json.tool` — no syntax errors.

## Rollback
- Revert the change via a PR. Low risk — markdown-only edit to one page.
  No sidebar or nav changes to undo.
