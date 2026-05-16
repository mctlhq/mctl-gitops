# Tasks: mcp-active-incidents-filter

## Implementation tasks

- [ ] 1. Read the current `docs/mcp/tools-reference.md` in `mctlhq/mctl-docs`.
        Locate the incidents / alerts listing tool entry (search for
        `mctl_list_incidents`, `list_incidents`, `list_alerts`, or similar).
        — DoD: tool name and current parameter table confirmed.

- [ ] 2. Confirm the exact public MCP tool names for (a) the incidents/alerts
        listing tool and (b) the workflow retrieval tool with the author of
        `mctl-api:a8cdba5` if the current tools-reference page does not already
        name them.
        — DoD: tool names confirmed or TODO marker left inline if unresolvable.

- [ ] 3. Update the `status` parameter row in the incidents/alerts listing tool
        entry using the diff from `proposed-content.md`:
        - Add `active` as a documented value with "(default, all non-terminal
          states)" annotation.
        - State that omitting `status` is equivalent to `status=active`.
        — DoD: parameter table updated, `active` value documented.

- [ ] 4. Add the `env_vars` redaction note to the workflow retrieval tool entry
        using the callout from `proposed-content.md`.
        — DoD: note present, mentions mctl-api 4.18.4.

- [ ] 5. (If needed) Update `.vitepress/config.{js,ts}` — sidebar / nav entry.
        No structural change expected; verify and skip if not needed.
        — DoD: confirmed no sidebar change required.

- [ ] 6. Run `npm run dev` locally and open `docs/mcp/tools-reference.md`.
        — DoD: page renders, parameter tables display correctly, no broken
        anchors.

- [ ] 7. Cross-link check: if `docs/mcp/examples.md` contains an example that
        calls the incidents-listing tool without a `status` parameter, update it
        or add a comment noting the new default behaviour.
        — DoD: examples page consistent with tools reference.

- [ ] 8. Open a PR against `mctlhq/mctl-docs`, run codex review, merge.
        — DoD: changes deployed to docs.mctl.ai.

## Tests

- [ ] T1. `vitepress build docs` completes with no errors and no warnings.
- [ ] T2. Every internal link in `docs/mcp/tools-reference.md` resolves (no
          404s). Check anchor links to individual tool sections.
- [ ] T3. The `status=active` example invocation has been confirmed against the
          mctl-api staging environment or verified by the commit author that the
          parameter name and value are correct as documented.

## Rollback

Revert the PR. Changes are markdown only. Low risk.
