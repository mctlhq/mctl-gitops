# Design: issue-124-docs-connect-your-first-client-page-huma

## Current state
- Site: VitePress 1.6 (`package.json`: `vitepress ^1.6.0`), content in `docs/`, config in `docs/.vitepress/config.ts` (note: the repo CLAUDE.md says `.vitepress/config.ts`, but the actual path is under `docs/`). `cleanUrls: true`, local search, single global `sidebar` array.
- Sidebar group "Getting Started" contains only `{ text: 'Quick Start', link: '/getting-started/' }` (`docs/getting-started/index.md`). The "Guides" group starts with "First-user checklist" (`docs/guides/first-user-checklist.md`).
- Onboarding is MCP-only:
  - `docs/getting-started/index.md` Prerequisites require "An AI client that supports MCP"; "Step 2: Connect your AI client" covers Claude.ai, Claude Code, Cursor/VS Code and defers to `/mcp/connecting`.
  - `docs/mcp/connecting.md` embeds the `<McpSetup />` component (`docs/.vitepress/theme/components/McpSetup.vue`) for OAuth and per-client config, plus a token-type table.
  - `docs/guides/first-user-checklist.md` item 8 "Manage your platform via MCP" points to `/mcp/overview` and `/mcp/connecting`.
- Telegram: no user-facing onboarding. `/mctl link` and `/mctl work` occur nowhere in `docs/`. The linking mechanism exists only as API-level docs in `docs/human-input/surface-identity.md` (challenge `POST /api/v1/surface-identities/challenges`, redeem by `surface:telegram`, 10-minute single-use code, `403 challenge_invalid`, `409 link_conflict`, list/revoke endpoints) under a `::: warning Status` container saying it is merged but not deployed.
- Build: `bun run build` runs `scripts/generate-llms-full.ts` (recursively bundles every `docs/**/*.md` into `docs/public/llms-full.txt`, so a new page is picked up automatically) then `vitepress build docs`. `docs/public/llms.txt` is hand-maintained and lists key pages.
- Assets: no PNG/JPG/WebP anywhere under `docs/`; pages use text, code blocks, tables and mermaid fences (rendered by the custom fence rule in `config.ts`).

## Proposed solution
Add one new page and wire it in, leading with Telegram as decided by the issue author.

1. New file `docs/getting-started/connect-first-client.md` (URL `/getting-started/connect-first-client`), structure:
   - H1 "Connect your first client" and a 2-3 sentence intro: two supported paths; this page leads with Telegram; the MCP connector is the alternative.
   - `::: warning Status` container (same pattern as `docs/human-input/surface-identity.md`) if Telegram linking is not yet generally available when the page ships.
   - "## Prerequisites (Telegram)": a GitHub account with access to an MCTL tenant (cross-link `/guides/first-user-checklist`), a Telegram account, access to the MCTL bot.
   - "## Step 1: Open the MCTL bot".
   - "## Step 2: Link your account with `/mctl link`": what the command does, the one-time code (10 minutes, single use, bound to you and to Telegram), the resulting `telegram:<id> <-> github:<login>` link; link to `/human-input/surface-identity` for the mechanism.
   - "## Step 3: Start working with `/mctl work`": what it starts and a first example interaction; note that actions run as the linked human with their tenant access, never admin (from surface-identity "Relay").
   - "## If linking fails": table mapping `403 challenge_invalid` (expired/used/wrong code -> request a new code) and `409 link_conflict` (identity already linked -> revoke the old link first) to user actions; how to list/revoke links.
   - "## Alternative: connect a desktop AI client over MCP": short paragraph on the remote connector `https://api.mctl.ai/mcp` with OAuth, verify with "Who am I on MCTL?", and a link to `/mcp/connecting` for per-client configuration. No duplication of `<McpSetup />`.
   - "## Next steps": `/guides/deploy-first-app`, `/guides/first-user-checklist`.
   - Exact command UX (bot handle, prompts, replies) is taken from mctlhq/mctl-telegram at implementation time; nothing is invented.
2. `docs/.vitepress/config.ts`: add `{ text: 'Connect your first client', link: '/getting-started/connect-first-client' }` to the "Getting Started" group after "Quick Start".
3. Cross-links (one sentence each, no restructuring):
   - `docs/getting-started/index.md` Step 2: a `::: tip` pointing to the new page for the Telegram path.
   - `docs/guides/first-user-checklist.md` item 8: mention the new page as the starting point for connecting a client.
4. `docs/public/llms.txt`: add the page under "Key Documentation Links" (llms-full.txt regenerates automatically).

Why this way: Getting Started is where a newly onboarded user lands (nav "Getting Started" -> `/getting-started/`), it currently has one page, and a sibling page keeps the Quick Start MCP flow intact while giving Telegram a first-class entry. Linking to `/mcp/connecting` and `/human-input/surface-identity` keeps each fact in one place.

## Alternatives
- Put the page under "Guides" (`docs/guides/connect-first-client.md`) next to "First-user checklist". Dropped: Guides are task deep-dives; first contact belongs in Getting Started, which the top nav links to.
- Rewrite `docs/getting-started/index.md` Step 2 to lead with Telegram. Dropped: the issue asks for a single dedicated page, and the Quick Start's later steps (natural-language MCP prompts, `mctl_whoami`, deploy) are MCP-specific; restructuring it widens scope and risk.
- Lead with the MCP connector, Telegram as alternative. Dropped: contradicts the author's resolved product decision.
- Tabbed page with both paths equal (VitePress code-group style). Dropped: the issue requires leading with exactly one path.

## Platform impact
- Migrations: none. Static content only; no change to nginx, Dockerfile or theme.
- Backward compatibility: purely additive; no existing URL changes.
- Resources: one more static HTML page; `llms-full.txt` grows by roughly 1-2k tokens.
- Risks and mitigations:
  - Documenting commands whose behavior lives in another repo may drift. Mitigation: source text from mctl-telegram at implementation time, cite the mctl-telegram issue/PR in the PR description, and keep the mechanism details delegated to `/human-input/surface-identity`.
  - Leading with a surface that may not yet be deployed could strand users. Mitigation: the Status warning plus a prominent link to the MCP alternative on the same page.
  - Dead links fail the VitePress build. Mitigation: build locally before merging.
- Note: the issue is a controlled E2E fixture and says not to approve or implement; this design is complete but should stay unapproved.
