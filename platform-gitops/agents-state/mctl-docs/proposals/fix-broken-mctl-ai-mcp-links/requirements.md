# Replace broken mctl.ai/mcp links with /mcp/connecting

## Context
The mctl-web Cloudflare Worker uses an SPA-style fallback that returns the
landing page HTML for every path. Curl confirms it: `mctl.ai/mcp`,
`mctl.ai/connect`, and `mctl.ai/foo123` all return the same 2309-byte
homepage with `<title>MCTL — Kubernetes Platform for Growing Product
Teams</title>`. There is no dedicated `/mcp` page on mctl.ai — the
documentation has been telling users to "Visit mctl.ai/mcp" but that
sends them to the homepage, which has no Connect button or OAuth flow.

The actual connecting experience lives at `docs.mctl.ai/mcp/connecting`
(`docs/mcp/connecting.md` in this repo). That page already embeds the
`<McpSetup />` Vue component — the real OAuth-flow + GitHub-PAT
generator + per-client config snippets — and is the page users should
land on. It is correctly cross-linked from `getting-started/index.md`
("See [Connecting](/mcp/connecting) for configuration snippets...") and
from `index.md` and `reference/faq.md`, but those cross-links are
secondary; the primary instruction in Step 2 of getting-started still
sends people to the broken `mctl.ai/mcp`.

This proposal replaces every doc-facing `mctl.ai/mcp` reference with
`/mcp/connecting` so users actually land on the working page. The
instances where `mctl.ai/mcp` describes a deployed deliverable (e.g.
"MCP OAuth connector at `mctl.ai/mcp`" in platform/components.md
which is product description, not a user instruction) stay as-is —
that text describes intent, not a link the user should click today.

## User stories
- AS a new MCTL user reading getting-started I WANT Step 2 to take me
  to a page that actually has a Connect button SO THAT I do not bounce
  off the landing page wondering where the connector is.
- AS a user troubleshooting a stale token I WANT the "Sign in again"
  link to take me to the working flow SO THAT I can actually re-auth
  without manually figuring out the URL.
- AS the mctl-docs maintainer I WANT obviously-broken external links
  fixed in one focused PR SO THAT the rest of the docs stay coherent
  and the fix lands without conflict.

## Acceptance criteria (EARS)
- WHEN a user reads `docs/getting-started/index.md` Step 2 THE SYSTEM
  SHALL link the "fastest way to connect" instruction to
  `/mcp/connecting` (the in-docs page), not `https://mctl.ai/mcp`.
- WHEN a user reads `docs/reference/troubleshooting.md` and follows
  the "Sign in again" / "Reconnect" instructions THE SYSTEM SHALL
  link them to `/mcp/connecting`, not `https://mctl.ai/mcp`.
- WHEN VitePress builds the site THE SYSTEM SHALL produce no warnings
  about dead internal links (i.e. `/mcp/connecting` resolves cleanly
  in the new locations).
- WHILE replacing links THE SYSTEM SHALL leave product-description
  text alone — `platform/components.md` line that says "MCP OAuth
  connector at `mctl.ai/mcp`" is describing a deployed component's
  intended URL, not a link a reader should click, and should not be
  rewritten in this proposal.
- IF a `mctl.ai/mcp` reference is genuinely about the OAuth callback
  endpoint hosted by mctl-web (not mctl-docs) THE SYSTEM SHALL leave
  it. Use the surrounding sentence to decide: if it tells the reader
  "click here to sign in" the link target is wrong; if it explains
  "OAuth runs at mctl.ai/mcp" the text is correct.

## Out of scope
- Fixing the mctl-web Cloudflare Worker so `/mcp` actually serves a
  page. That is a separate concern in a different repo and changes
  the contract; this proposal only fixes what is locally fixable in
  mctl-docs.
- Adding new content to `docs/mcp/connecting.md`. The page already
  has the working `<McpSetup />` component; this proposal only
  changes other pages to link to it.
- Changing the navigation order or sidebar of the docs site.
- Anything that requires regenerating the OpenAPI examples or the
  REST docs.
