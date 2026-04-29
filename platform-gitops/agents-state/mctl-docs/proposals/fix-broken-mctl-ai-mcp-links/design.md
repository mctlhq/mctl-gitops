# Design — Replace broken mctl.ai/mcp links with /mcp/connecting

## Audit
A grep run on the working tree of mctl-docs (today's main) finds every
literal occurrence of `mctl.ai/mcp` (case-sensitive, no trailing path
component beyond `/mcp` — i.e. NOT `api.mctl.ai/mcp`). The 6 user-
facing instances that need rewriting:

| File                              | Line | Sentence (abridged)                               | Action |
|-----------------------------------|------|---------------------------------------------------|--------|
| docs/getting-started/index.md     | 34   | `1. Visit [mctl.ai/mcp](https://mctl.ai/mcp)`     | rewrite to `/mcp/connecting` |
| docs/getting-started/index.md     | 46   | `Get your token at [mctl.ai/mcp](...)`            | rewrite to `/mcp/connecting` |
| docs/reference/troubleshooting.md | 11   | `1. Sign in again at [mctl.ai/mcp](...)`          | rewrite to `/mcp/connecting` |
| docs/reference/troubleshooting.md | 33   | `OAuth flow at \`mctl.ai/mcp\``                   | rewrite to `/mcp/connecting` |
| docs/reference/troubleshooting.md | 43   | `3. Reconnect via [mctl.ai/mcp](...)`             | rewrite to `/mcp/connecting` |
| docs/platform/components.md       | 27   | `MCP OAuth connector at \`mctl.ai/mcp\``          | LEAVE — this is product-description, not a user click target. |

Out-of-scope mentions (do not rewrite):
- `api.mctl.ai/mcp` — the actual MCP Streamable HTTP endpoint, used in
  per-client config snippets. Stays.
- `https://api.mctl.ai/mcp` literals inside `<McpSetup />` Vue component
  — endpoint constants. Stay.

## Link form
Use VitePress relative links: `[Connecting](/mcp/connecting)`. Do not
prefix with `https://docs.mctl.ai/` — that bypasses the dev server and
breaks `vitepress dev`. Keep markdown style consistent with the
existing `See [Connecting](/mcp/connecting)` line that already lives
in getting-started/index.md line 50.

## File-by-file plan

### `docs/getting-started/index.md`
- Line 34: rewrite `1. Visit [mctl.ai/mcp](https://mctl.ai/mcp)` to
  `1. Open the [Connecting](/mcp/connecting) page in these docs`.
- Line 46: rewrite `Get your token at [mctl.ai/mcp](https://mctl.ai/mcp) after signing in.` to
  `Get your token at the [Connecting](/mcp/connecting) page after signing in.`
- Line 50 already says `See [Connecting](/mcp/connecting) for
  configuration snippets...` — drop the redundant duplicate or
  fold it into the Cursor / VS Code subsection. Trim if reasonable;
  do not introduce new content.

### `docs/reference/troubleshooting.md`
- Line 11: rewrite `1. Sign in again at [mctl.ai/mcp](https://mctl.ai/mcp)` to
  `1. Sign in again from the [Connecting](/mcp/connecting) page`.
- Line 33 (token-type table row): rewrite `OAuth flow at \`mctl.ai/mcp\`` to
  `OAuth flow on the [Connecting](/mcp/connecting) page`.
- Line 43: rewrite `3. Reconnect via [mctl.ai/mcp](https://mctl.ai/mcp)` to
  `3. Reconnect from the [Connecting](/mcp/connecting) page`.

### `docs/platform/components.md`
- Line 27: leave as-is. The sentence describes the deployed component
  ("MCP OAuth connector at mctl.ai/mcp") — that is what the deployment
  is INTENDED to be, even if the worker currently 404s for that path.
  Fixing the worker is out of scope; rewriting this sentence would
  mis-describe the platform.

## Why /mcp/connecting and not mctl.ai
Two alternatives were considered and rejected:
1. Rewrite to `https://mctl.ai/` (homepage). Rejected: the homepage
   does not have a Connect-with-Claude.ai button visible from a
   non-authenticated state; users still bounce.
2. Rewrite to `mctl.ai/connect`. Rejected: same Cloudflare fallback
   bug — `/connect` returns the homepage too. Verified by curl.

The in-docs `/mcp/connecting` page is the only place that currently
has a working OAuth flow + GitHub-PAT generator + per-client config
snippets. Sending users there is the correct fix until mctl-web
ships an actual `/mcp` page.

## Risk
Low. The change is a string replacement in three Markdown files. No
runtime, no styling, no navigation changes. VitePress' link checker
will validate `/mcp/connecting` resolves at build time.

The only behavioural delta a user might notice: clicking "Visit
mctl.ai/mcp" used to open the marketing site in a new tab; clicking
"Connecting" stays inside docs.mctl.ai. That is a feature, not a
regression.

## Tests
- `pnpm docs:build` (or `vitepress build`) finishes with no
  dead-link warnings.
- `pnpm lint` (if configured) still passes.
- Manual smoke: open docs/getting-started after build; click the
  Step 2 link; confirm the browser stays on docs.mctl.ai and lands
  on the connecting page with the McpSetup component visible.
