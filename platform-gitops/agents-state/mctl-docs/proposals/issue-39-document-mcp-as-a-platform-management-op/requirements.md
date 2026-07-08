# Document MCP as a Platform Management Option in Onboarding Docs

## Context

MCTL exposes a Model Context Protocol (MCP) server that allows AI clients such as Claude.ai,
Claude Code, and Cursor to manage the platform through natural language. Despite this capability
being central to the product identity (the homepage at `docs/index.md` leads with "AI-Native
Infrastructure Management" and features an explicit "Connect MCP" call-to-action), the connection
between MCP and the first-app deployment flow is not stated as a user-facing framing choice. The
`docs/guides/deploy-first-app.md` guide already contains per-step "Via MCP" subsections and an
"Optional: Manage the platform through MCP" section at its end, and `docs/getting-started/index.md`
is structured as an MCP-first walkthrough. However, neither document contains a dedicated introductory
statement that explicitly presents MCP and the Portal as alternative, complementary management surfaces
and directs new users to the connection docs before they begin.

This issue asks for that gap to be closed with targeted, minimal additions: a short prose callout near
the start of the first-app deployment guide (and by extension the quick-start guide) that names MCP as
a management option, describes what it covers, and links to `docs/mcp/connecting.md`.

## User stories

- AS a new MCTL user reading the first-app deployment guide I WANT to see an upfront statement that I
  can manage the platform through MCP-compatible AI tools SO THAT I understand my interface options
  before I choose how to proceed.
- AS a new MCTL user who prefers a conversational AI workflow I WANT a direct link to the MCP
  connection setup page early in the onboarding flow SO THAT I can configure my AI client without
  hunting through the sidebar.
- AS a new MCTL user who uses the Portal I WANT the docs to clarify that Portal and MCP are
  complementary, not competing, SO THAT I do not assume one replaces the other.

## Acceptance criteria (EARS)

- WHEN a user reads `docs/guides/deploy-first-app.md` THE SYSTEM SHALL present a visible statement
  that MCTL can be managed through MCP-compatible AI tools before the first numbered step.
- WHEN a user reads `docs/guides/deploy-first-app.md` THE SYSTEM SHALL include an inline link to
  `/mcp/connecting` within that MCP statement so the user can set up their AI client without leaving
  the guide.
- WHEN a user reads either the quick-start guide (`docs/getting-started/index.md`) or the first-app
  guide (`docs/guides/deploy-first-app.md`) THE SYSTEM SHALL communicate that Portal and MCP are
  alternative and complementary management surfaces for the platform.
- WHILE the MCP callout is present THE SYSTEM SHALL NOT remove or relocate the existing per-step
  "Via MCP" subsections in `docs/guides/deploy-first-app.md`, as those provide operational detail
  that the callout does not duplicate.
- IF a user is using only the Portal they SHALL be able to follow `docs/guides/deploy-first-app.md`
  without the MCP callout obscuring portal-only instructions.

## Out of scope

- Adding new MCP tools documentation or expanding `docs/mcp/tools-reference.md`.
- Rewriting the per-step "Via MCP" subsections already present in `docs/guides/deploy-first-app.md`.
- Changes to `docs/mcp/connecting.md`, `docs/mcp/overview.md`, or any MCP-section page.
- Adding MCP content to any guide other than the quick-start and first-app deployment pages.
- Navigation or sidebar changes in `.vitepress/config.ts` (MCP is already a top-level nav item).
- Any changes to the homepage (`docs/index.md`), which already surfaces MCP prominently.

## Open questions

- The issue's suggested text says "MCTL can also be managed through MCP-compatible AI tools." The
  word "also" implies the Portal was introduced first. In `docs/guides/deploy-first-app.md` MCP and
  Portal are presented in parallel from step 1. The proposal treats the word "also" as stylistic,
  not structural, and preserves the parallel presentation while adding the intro callout.
- The quick-start guide (`docs/getting-started/index.md`) is already MCP-first; Step 2 is entirely
  about connecting an AI client and never mentions the Portal as an alternative. The issue does not
  explicitly target this file, but AC3 ("Portal and MCP are alternative/complementary") is only
  satisfied in `deploy-first-app.md`. A brief Portal mention in the quick-start is included in this
  proposal as the minimal change needed to satisfy AC3 across both onboarding entry points.
