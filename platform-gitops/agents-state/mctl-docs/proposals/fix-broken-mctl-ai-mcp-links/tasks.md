# Tasks: fix-broken-mctl-ai-mcp-links

- [ ] 1. Edit `docs/getting-started/index.md`:
  - Replace the Step 2 line `1. Visit [mctl.ai/mcp](https://mctl.ai/mcp)`
    with `1. Open the [Connecting](/mcp/connecting) page in these docs`.
  - Replace `Get your token at [mctl.ai/mcp](https://mctl.ai/mcp) after
    signing in.` with `Get your token at the
    [Connecting](/mcp/connecting) page after signing in.`
  - Leave the existing `See [Connecting](/mcp/connecting)` line in the
    Cursor / VS Code subsection alone (already correct).
  - DoD: `grep -n 'mctl\.ai/mcp' docs/getting-started/index.md` returns
    no matches.
- [ ] 2. Edit `docs/reference/troubleshooting.md`:
  - Replace `1. Sign in again at [mctl.ai/mcp](https://mctl.ai/mcp)`
    with `1. Sign in again from the [Connecting](/mcp/connecting) page`.
  - Replace the token-type table row text `OAuth flow at \`mctl.ai/mcp\``
    with `OAuth flow on the [Connecting](/mcp/connecting) page`.
  - Replace `3. Reconnect via [mctl.ai/mcp](https://mctl.ai/mcp)` with
    `3. Reconnect from the [Connecting](/mcp/connecting) page`.
  - DoD: `grep -n 'mctl\.ai/mcp' docs/reference/troubleshooting.md`
    returns no matches.
- [ ] 3. Do NOT touch `docs/platform/components.md`. The line "MCP OAuth
  connector at `mctl.ai/mcp`" describes the deployed component's
  intended URL and is product-description, not a user click target.
  - DoD: `git diff docs/platform/components.md` is empty.
- [ ] 4. Do NOT touch any `api.mctl.ai/mcp` mention. That is the
  Streamable-HTTP MCP endpoint and is unrelated to the broken
  connector page.
  - DoD: `git diff` shows zero changes to lines containing
    `api.mctl.ai/mcp`.
- [ ] 5. Build the site to confirm no dead-link warnings.
  - DoD: `pnpm install && pnpm docs:build` succeeds with no
    `[vitepress] dead link` warnings in stderr.
- [ ] 6. Commit using a single conventional-commit message:
  `fix(docs): point users at /mcp/connecting instead of broken
  mctl.ai/mcp`. Body explains the SPA-fallback root cause and lists
  the rewritten files.

## Tests
- [ ] T1. `grep -rn 'mctl\.ai/mcp' docs/` returns only:
  - `docs/platform/components.md` (product description, untouched)
  - `docs/.vitepress/theme/components/McpSetup.vue` (`api.mctl.ai/mcp`,
    a different URL — untouched)
  - any `api.mctl.ai/mcp` mention (different URL — untouched)
  No remaining user-facing `mctl.ai/mcp` instructions.
- [ ] T2. `pnpm docs:build` finishes with exit 0 and no dead-link
  warning in stderr.

## Rollback
1. `git revert <commit>` on the implementer-opened PR if any user
   reports the rewrites read worse than before.
2. The mctl-web side (the actual Cloudflare Worker `/mcp` endpoint)
   is unaffected by this proposal — there is nothing to roll back
   on that side.
