# Tasks: tenant-network-egress-default

- [ ] 1. Update `docs/guides/tenants.md` with the content from
        `proposed-content.md` (new "Network Policy" subsection under
        "Create a Tenant"). — DoD: file updated, `vitepress build docs` is
        green.
- [ ] 2. No `.vitepress/config.{js,ts}` change needed — existing page,
        no new nav entry. — DoD: n/a, skip.
- [ ] 3. Run `npm run dev` locally and open `/guides/tenants`. — DoD: the
        new subsection renders between "Create a Tenant" and "List
        Tenants", the MCP example block renders as a code fence, no
        broken layout.
- [ ] 4. Cross-link: check `docs/mcp/tools-reference.md`'s
        `mctl_create_tenant` entry (if the tool table has room for a
        one-line note) and `docs/security/authorization.md` for whether a
        pointer back to the new subsection is warranted. — DoD:
        cross-reference added only if it reads naturally; otherwise
        explicitly skip with a one-line note in the PR description.
- [ ] 5. Open a PR against `mctlhq/mctl-docs`, request a `@claude review`,
        merge. — DoD: deployed to docs.mctl.ai.

## Tests
- [ ] T1. `vitepress build docs` with no errors and no warnings.
- [ ] T2. Every link in the changed page resolves (no 404s).
- [ ] T3. The MCP example command block matches the style of the existing
        examples on the page (plain fenced block, no language tag, per
        the existing "Create a Tenant" / "List Tenants" examples).

## Rollback
- Delete the added subsection via a revert PR. Low risk — markdown only,
  no config/sidebar changes to undo.
