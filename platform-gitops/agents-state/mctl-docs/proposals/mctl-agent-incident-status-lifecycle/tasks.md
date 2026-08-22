# Tasks: mctl-agent-incident-status-lifecycle

- [ ] 1. Update `docs/reference/troubleshooting.md`'s "Self-Healing Agent"
        section with the "Incident Status Values" subsection from
        `proposed-content.md`. — DoD: file updated, `vitepress build docs`
        is green.
- [ ] 2. Add the one-line cross-link to `docs/mcp/tools-reference.md`'s
        "Incidents" section from `proposed-content.md`. — DoD: link
        present and resolves.
- [ ] 3. No `.vitepress/config.{js,ts}` change needed — both pages already
        exist and are in the nav. — DoD: n/a, skip.
- [ ] 4. Run `npm run dev` locally and open `/reference/troubleshooting`
        and `/mcp/tools-reference`. — DoD: the new table renders, the
        cross-link works both directions conceptually (troubleshooting
        has the table; tools-reference points at it).
- [ ] 5. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`,
        merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in both changed pages resolves (no 404s).
- [ ] T3. The status list (`open`, `analyzing`, `escalated`,
        `fix_proposed`, `resolved`, `suppressed`, `acknowledged`) matches
        `ticket.Status*` constants in `mctl-agent` at merge time —
        re-verify against the repo before merging in case a status was
        added/renamed since this proposal was written.

## Rollback
- Revert the two file changes via a revert PR. Low risk — markdown only.
