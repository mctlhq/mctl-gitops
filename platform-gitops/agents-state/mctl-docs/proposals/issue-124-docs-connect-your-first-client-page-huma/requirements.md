# Add a "Connect your first client" docs page

## Context
Issue mctlhq/mctl-docs#124 asks for a single "Connect your first client" page for a
new user who has just been given access to MCTL. Two connection paths are equally
supported: the remote MCP connector (`https://api.mctl.ai/mcp`, OAuth) from a desktop
AI client, and the Telegram surface (`/mctl link`, then `/mctl work`). The page must
lead with exactly one of them and present the other as the alternative.

Which path leads is a product decision that is not recorded in this repository. Today
the docs are MCP-first: `docs/getting-started/index.md` (Step 2 "Connect your AI
client"), `docs/mcp/connecting.md` (the `<McpSetup />` OAuth flow) and
`docs/guides/first-user-checklist.md` all assume an MCP client, and no page documents
the `/mctl link` or `/mctl work` Telegram commands. This proposal therefore proceeds
with the MCP connector as the lead path (consistent with existing docs) and keeps the
page structured so the lead can be swapped with a localized edit once the decision is
made. The issue is a controlled test for the human-input E2E (mctlhq/mctl-agents#473)
and states that the proposal must not be approved or implemented.

## User stories
- AS a newly onboarded MCTL user I WANT one page that tells me how to connect my first
  client SO THAT I can run my first command without reading several reference pages.
- AS a user who prefers chat I WANT the Telegram path described on the same page SO THAT
  I know it is an equally supported alternative.
- AS a docs maintainer I WANT the page to reuse existing reference pages instead of
  duplicating them SO THAT connection details have a single source of truth.

## Acceptance criteria (EARS)
- WHEN the docs site is built THE SYSTEM SHALL serve a page at
  `/guides/connect-first-client` titled "Connect your first client".
- WHEN a reader opens the Guides sidebar THE SYSTEM SHALL list "Connect your first
  client" between "First-user checklist" and "Deploy your first app".
- WHILE the page is rendered THE SYSTEM SHALL present exactly one lead path as the
  primary, numbered procedure, and the other path in a single clearly labelled
  "Alternative" section.
- WHEN the lead path is the MCP connector THE SYSTEM SHALL document the endpoint
  `https://api.mctl.ai/mcp`, the OAuth sign-in via the [Connecting](/mcp/connecting)
  page, and verification with "Who am I on MCTL?" (`mctl_whoami`).
- WHEN the Telegram path is described THE SYSTEM SHALL document `/mctl link` followed by
  `/mctl work`, in that order.
- IF a statement about Telegram command behaviour cannot be confirmed from a source
  (mctl-telegram repository or platform team) THEN THE SYSTEM SHALL NOT invent details
  beyond the command names and order given in the issue.
- WHEN the page is added THE SYSTEM SHALL include it in `docs/public/llms.txt` and in the
  generated `docs/public/llms-full.txt` (via `bun run build`).
- WHILE the page is rendered THE SYSTEM SHALL contain no emoji and be written in English,
  per `.claude/CLAUDE.md`.
- WHEN `bun run build` runs THE SYSTEM SHALL complete with no dead-link errors.

## Out of scope
- Screenshots: no page in `docs/` currently embeds images, and the asset set depends on
  the lead-path decision. Text-only for this proposal.
- Changes to `docs/mcp/connecting.md`, the `McpSetup.vue` component, or
  `docs/getting-started/index.md` beyond an optional cross-link.
- Any change to the Telegram bot, mctl-api, or OAuth flow.
- Approving or implementing this proposal (the issue is a controlled E2E test).

## Open questions
- BLOCKING: Which path should the page lead with, the remote MCP connector or the
  Telegram surface? The issue states this is an unrecorded product decision that changes
  structure, prerequisites and screenshots. Filed as the single clarification question.
  Assumed for this proposal: the MCP connector leads, because every existing onboarding
  page (`getting-started/index.md`, `mcp/connecting.md`, `guides/first-user-checklist.md`)
  is MCP-first and the Telegram commands are undocumented here.
- What exactly do `/mctl link` and `/mctl work` do and what does the user see? Not
  documented in this repo; `docs/human-input/surface-identity.md` describes a one-time
  code link flow that may underlie `/mctl link`, but it states no surface uses it yet.
- Where does a new user find the Telegram bot (bot handle)? Not recorded in this repo.
