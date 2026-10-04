# Docs: "Connect your first client" page, leading with the Telegram surface

## Context
Issue mctlhq/mctl-docs#124 asks for a single "Connect your first client" page for a new user who has just been given access to the MCTL platform. Two connection paths are equally supported: the Telegram surface (`/mctl link`, then `/mctl work`) and the remote MCP connector (`https://api.mctl.ai/mcp`, OAuth) from a desktop AI client. The page must lead with exactly one of them. That product decision was resolved by the issue author (clarification `hir-7c4d34f04aae6b8f`): **the page leads with the Telegram surface**; the MCP connector is presented as the secondary path and links to the existing `/mcp/connecting` page.

Today the docs have no Telegram onboarding content at all: `/mctl link` and `/mctl work` appear nowhere in `docs/`, Telegram is only mentioned as an operator notification channel (`docs/platform/components.md`, `docs/reference/troubleshooting.md`) and as a not-yet-shipped human-input surface (`docs/human-input/surface-identity.md`, `docs/human-input/architecture.md`). Every onboarding page (`docs/getting-started/index.md`, `docs/guides/first-user-checklist.md`) assumes an MCP client. A new user who is handed Telegram access therefore has no entry point. Note: the issue is a controlled test for the human-input E2E (mctlhq/mctl-agents#473) and states the proposal must not be approved or implemented; this proposal is complete regardless so the E2E can assert on it.

## User stories
- AS a new platform user who has just been given access I WANT one page that tells me how to connect my first client SO THAT I can start working without reading the whole docs set.
- AS a new user who lives in Telegram I WANT step-by-step `/mctl link` and `/mctl work` instructions SO THAT I can link my GitHub identity to the bot and start a work session.
- AS a new user who prefers a desktop AI client I WANT a clearly marked alternative path SO THAT I can connect via the remote MCP connector instead.
- AS a docs maintainer I WANT the page to follow existing sidebar, tone and container conventions SO THAT it does not drift from the rest of the site.

## Acceptance criteria (EARS)
- WHEN the site is built with `bun run build` THE SYSTEM SHALL render a page at `/getting-started/connect-first-client` without build errors or dead-link warnings.
- WHEN a reader opens the "Getting Started" sidebar group in `docs/.vitepress/config.ts` THE SYSTEM SHALL list "Connect your first client" directly after "Quick Start".
- WHEN a reader opens the page THE SYSTEM SHALL present the Telegram surface as the first and primary path, before any mention of MCP connector setup steps.
- WHEN the reader follows the Telegram section THE SYSTEM SHALL describe, in order: prerequisites, opening the MCTL bot, running `/mctl link` to link the Telegram account to the reader's GitHub identity, verifying the link, and running `/mctl work`.
- WHEN the page describes linking THE SYSTEM SHALL be consistent with the possession-proof flow in `docs/human-input/surface-identity.md` (one-time code, 10-minute validity, single use, `telegram:<id> <-> github:<login>` link) and link to that page for details.
- WHEN the reader reaches the alternative path section THE SYSTEM SHALL describe the remote MCP connector at `https://api.mctl.ai/mcp` with OAuth only briefly and link to `/mcp/connecting` rather than duplicating its client-specific setup.
- WHILE the Telegram surface or surface-identity linking is not yet generally available on `api.mctl.ai` THE SYSTEM SHALL show a VitePress `::: warning Status` container stating so, matching the style used in `docs/human-input/surface-identity.md`.
- IF linking fails (expired, used or wrong-surface code; identity already linked) THEN THE SYSTEM SHALL tell the reader what to do, mapped to the `403 challenge_invalid` and `409 link_conflict` outcomes documented in `docs/human-input/surface-identity.md`.
- WHEN `docs/getting-started/index.md` (Step 2) and `docs/guides/first-user-checklist.md` refer to connecting a client THE SYSTEM SHALL link to the new page.
- WHILE writing the page THE SYSTEM SHALL use English, no emoji, and the existing `::: tip` / `::: warning` container conventions.

## Out of scope
- Any change to the Telegram bot (mctl-telegram), mctl-api, or the `McpSetup.vue` component.
- Rewriting `docs/mcp/connecting.md` or `docs/getting-started/index.md` beyond adding cross-links.
- Screenshots of the Telegram client. The docs tree currently ships no raster images (`docs/public/` holds only SVG brand assets and llms files); text and code blocks are used instead. Screenshots can follow in a separate change.
- Documenting the full `/mctl` command set beyond `link` and `work`.
- Implementing or approving this proposal (the issue is a controlled E2E test).

## Open questions
- RESOLVED: lead path is the Telegram surface (`/mctl link`, then `/mctl work`), per clarification `hir-7c4d34f04aae6b8f`.
- The exact UX of `/mctl link` and `/mctl work` (bot handle, whether the user pastes a code obtained from the portal/API or the bot issues a link URL, what `/mctl work` returns) is not documented in this repository. The implementer must source it from mctlhq/mctl-telegram at implementation time. Assumption: `/mctl link` follows the code-based possession proof in `docs/human-input/surface-identity.md`.
- Release status: `docs/human-input/surface-identity.md` states surface identity is merged but not deployed. The implementer should confirm current status and either keep or drop the Status warning.
