# Tasks: platform-skills-catalog

- [ ] 1. Create `docs/platform/skills.md` with the content from `proposed-content.md`
        (section 1). — DoD: file exists, `vitepress build docs` is green.
- [ ] 2. Update `docs/mcp/tools-reference.md` — add the cross-link from
        `proposed-content.md` (section 2). — DoD: link present in the tools reference.
- [ ] 3. Update `.vitepress/config.{js,ts}` — add `skills` under the `platform/`
        sidebar group. — DoD: the new page appears in the navigation.
- [ ] 4. Cross-check the exact parameter shapes of `mctl_list_platform_skills`,
        `mctl_enable_tenant_skill`, `mctl_disable_tenant_skill`,
        `mctl_read_platform_skill`, and `mctl_list_tenant_skill_bindings` against
        `mctl-api`/`mctl-gitops` source, and resolve the `<TODO: confirm with author of
        <sha>>` markers in `proposed-content.md`. — DoD: no TODO markers remain, or
        they are explicitly deferred with a linked follow-up issue.
- [ ] 5. Confirm the "tenant" visibility tier semantics
        (`<TODO: confirm with author of fc35b55>` in `proposed-content.md`) with the
        commit author before publishing — this affects the accuracy of the tiers
        table. — DoD: tier definitions verified or explicitly flagged as unverified in
        the published page.
- [ ] 6. Run `npm run dev` locally and open the page. — DoD: it renders, links work,
        the visibility-tier mermaid diagram renders.
- [ ] 7. Cross-link: check whether `docs/platform/overview.md` or
        `docs/platform/components.md` should mention platform skills as a concept.
        — DoD: cross-references in place where appropriate.
- [ ] 8. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`, merge.
        — DoD: deployed to docs.mctl.ai.

## Tests

- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the new / changed page resolves (no 404s), including the
        `platform/skills` sidebar entry and the cross-link from
        `docs/mcp/tools-reference.md`.
- [ ] T3. The `mctl_list_platform_skills` example call output has been hand-checked
        against a live response (`jq .` parses cleanly), or flagged as unverified if
        MCP tools are unavailable at review time.
- [ ] T4. Confirm the "known skills" table (review-watch, archify-diagrams) still
        matches `mctl_list_platform_skills` output at merge time — the catalog can
        change between proposal-writing and publishing.

## Rollback

- Delete `docs/platform/skills.md` and revert the sidebar/cross-link changes via a
  revert PR. Low risk — markdown and sidebar config only, no code change.
