# Design: issue-39-document-mcp-as-a-platform-management-op

## Current state

### docs/guides/deploy-first-app.md

The guide opens with a two-sentence introduction (lines 1-8) that states:

> This guide walks you through taking a GitHub-hosted application from source code to a running,
> publicly accessible service on MCTL. It covers both the portal-based path and the MCP-based path
> for each step.

A "Before you begin" block follows (lines 10-18). It lists three prerequisites, the third being:

> An AI client connected to MCTL via MCP if you intend to use the MCP path. See
> [Connecting](/mcp/connecting) for setup instructions.

The remainder of the guide (Steps 1-8 plus two optional sections) structures each step with "Via the
portal" and "Via MCP" subsections. Step 4 ("Grant MCTL access to the repository") provides only a
"Via MCP" subsection with a tip noting the portal path is not yet documented. The final optional
section (lines 268-282) is titled "Optional: Manage the platform through MCP" and lists four
post-deploy management actions (deploy new version, scale, roll back, view logs), linking to
`/mcp/tools-reference` and `/mcp/examples`.

There is no standalone section between the intro and "Before you begin" that frames MCP as a named
management interface alongside the Portal, nor does any passage use the specific framing the issue
requests ("inspect tenants, deploy services, check workflow status, operate the platform
conversationally") in a summary form.

### docs/getting-started/index.md

The quick-start guide opens with "No Kubernetes experience required" and two prerequisites:

- A GitHub account
- An AI client that supports MCP

Step 2 ("Connect your AI client") provides Claude.ai, Claude Code, and Cursor/VS Code MCP setup
instructions. There is no mention of the Portal as an alternative entry point, nor any statement
that Portal and MCP serve the same underlying platform management surface. The "What's next" table
at the end links to guides, the tools reference, the REST API, and troubleshooting, but does not
include a row or callout for the Portal.

### docs/mcp/connecting.md

The connecting page exists at `docs/mcp/connecting.md` and is already linked from the sidebar
("MCP Server > Connecting") and from `docs/guides/deploy-first-app.md` line 17. The page provides
token types, a `<McpSetup />` component for client-specific config, and a verification prompt.

### Navigation

`.vitepress/config.ts` places MCP as a top-level nav item (`{ text: 'MCP', link: '/mcp/overview' }`)
and the sidebar lists it as "MCP Server" with four items. The "Guides" sidebar group lists "Deploy
your first app" as the first entry. No sidebar entry cross-references the two sections.

---

## Proposed solution

### Change 1 — docs/guides/deploy-first-app.md: add an MCP intro callout

Insert a VitePress `:::info` callout block between the existing intro paragraph and the
"Before you begin" heading. The callout introduces MCP as a management option, describes what
operations it covers (to match the issue's suggested text), and links directly to
`/mcp/connecting`:

```markdown
::: info Managing MCTL through MCP
MCTL can also be managed through MCP-compatible AI tools such as Claude, Cursor, and VS Code.
You can use MCP to inspect tenants, deploy services, check workflow status, and operate the
platform conversationally. Each step in this guide includes both a portal path and an MCP path.

To use the MCP path, connect your AI client first: [Connecting to MCTL MCP](/mcp/connecting).
:::
```

Placement after the intro paragraph and before "Before you begin" ensures the callout is visible
on the first screen of the guide without pushing the prerequisites or Step 1 below the fold on
typical viewports. The `:::info` block renders as a visually distinct blue-bordered aside in the
MCTL VitePress theme, making it scannable without interrupting the main flow for portal users.

This change satisfies AC1 (MCP mentioned with its own callout), AC2 (inline link to
`/mcp/connecting`), and AC3 (explicit statement that both paths are available for each step).

### Change 2 — docs/getting-started/index.md: add a Portal alternative note

Insert a short paragraph or `:::tip` after the opening sentence of the quick-start guide, before
Step 1, noting that the Portal is an alternative to the MCP-first flow:

```markdown
::: tip Portal alternative
Prefer a graphical interface? The [MCTL Portal](https://app.mctl.ai) at `app.mctl.ai` provides
a Backstage-powered service catalog and dashboard for the same operations. The MCP and Portal
interfaces are complementary — you can switch between them at any time.
:::
```

This is a minimal single-callout addition that closes the AC3 gap in the quick-start without
restructuring the existing MCP-first walkthrough. The quick-start can remain MCP-first because
MCTL's positioning is AI-native; the addition simply ensures users know a Portal exists.

### What is not changed

- The per-step "Via MCP" and "Via the portal" subsections in `deploy-first-app.md` are left intact.
- The "Optional: Manage the platform through MCP" section at the end of `deploy-first-app.md` is
  left intact (it covers post-deploy operations the new callout does not duplicate).
- `docs/mcp/connecting.md` is not changed.
- `.vitepress/config.ts` is not changed.

---

## Alternatives

### A. Expand the "Before you begin" prerequisite entry

Modify the existing bullet in `deploy-first-app.md` to read more like the issue's suggested text,
rather than adding a dedicated callout block.

Rejected because: the "Before you begin" section reads as a checklist. Embedding a prose description
of MCP capabilities there is stylistically inconsistent and would make the prerequisite list harder
to scan. The issue explicitly asks for "a short section", which implies a visually distinct block,
not an expanded list item.

### B. Add a dedicated "MCP vs Portal" comparison page and link to it

Create a new page (e.g. `docs/guides/mcp-vs-portal.md`) that explains the two management surfaces
in depth, then link to it from the onboarding docs.

Rejected because: the issue's scope is a short addition to existing onboarding docs, not a new
reference page. A dedicated comparison page would be out of scope for this issue, would require
sidebar and nav changes, and is unnecessary when the content fits in a two-sentence callout.

### C. Move MCP introduction to the top of the page (above the main intro paragraph)

Place the callout as the very first content block, before "This guide walks you through...".

Rejected because: the existing intro paragraph establishes what the guide does and is the right
context-setting first sentence. Putting the MCP callout above it would create an odd reading order
where a meta-note about management interfaces appears before the reader knows what the guide covers.
The proposed placement (between the intro and "Before you begin") is the natural reading order:
guide purpose, then interface choice, then prerequisites.

---

## Platform impact

### Migrations and backward compatibility

Both changes are additive Markdown edits to existing files. No existing prose, headings, anchors,
or links are removed or renamed. The `:::info` and `:::tip` VitePress container syntax is already
used elsewhere in the docs (`deploy-first-app.md` lines 126-130 and 147-150 use `:::tip`), so
no new theme or plugin dependency is introduced.

### Build impact

VitePress builds are fully static. Adding two short callout blocks adds negligible build time and
output size. No Dockerfile or nginx.conf changes are required.

### Risk

Low. The changes are purely additive documentation edits to two files. No component, config, or
navigation changes are made. The only risk is tone or wording inconsistency with surrounding
content, which is mitigated by matching the existing `:::tip` style already present in
`deploy-first-app.md`.

### Rollback

Revert the two file edits (or revert the merge commit on `main`). Because the changes are additive,
rollback restores the prior state with no residual artifacts.
