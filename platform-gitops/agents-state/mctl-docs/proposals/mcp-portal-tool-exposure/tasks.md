# Tasks: mcp-portal-tool-exposure

- [ ] 1. Update `docs/mcp/overview.md` with the content from
        `proposed-content.md` (block 1). — DoD: file updated, `vitepress
        build docs` is green.
- [ ] 2. Update `docs/mcp/tools-reference.md` with the content from
        `proposed-content.md` (block 2). — DoD: new tool entry renders;
        tool-count banner bumped in coordination with
        `proposals/lifecycle-ownership/` (bump once, to reflect both new
        tools together, not twice).
- [ ] 3. (Optional, pending the `mctl-portal`/Cloudflare-portal
        relationship TODO in `design.md`) Update
        `docs/platform/components.md`'s `mctl-portal` entry with a
        cross-link to the new overview subsection. — DoD: confirmed with a
        human reviewer before merging; skip if unconfirmed rather than
        guessing.
- [ ] 4. Run `npm run dev` locally and open `/mcp/overview` and
        `/mcp/tools-reference`. — DoD: both render, the new subsection and
        tool entry are visible, links resolve.
- [ ] 5. Cross-link: check whether `docs/reference/faq.md`'s "How many
        tools are available?" entry needs its count updated alongside the
        banner bump in task 2. — DoD: count is consistent across
        `overview.md`, `tools-reference.md`, and `faq.md`.
- [ ] 6. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`,
        merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the changed pages resolves (no 404s).
- [ ] T3. The `mctl_trigger_portal_server_auth_apply` example has been
        hand-checked against `internal/mcp/server.go` / the tool
        registration in `mctl-api@f95ce9b` (tool name, no-parameter shape,
        return value).

## Rollback
- Revert the two page edits (and the optional third) via a revert PR. Low
  risk — markdown only.
