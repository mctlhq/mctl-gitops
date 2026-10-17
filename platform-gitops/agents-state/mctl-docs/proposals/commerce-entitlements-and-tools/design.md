# Design: commerce-entitlements-and-tools

## Source commits
- mctl-api:4fbee56 — feat(commerce): add finite service entitlements and unit allocation
- mctl-api:44a1961 — fix(commerce): move entitlement gating before reservation and fix replay
- mctl-api:197575d — fix(commerce): release holds on denied auth and gate on exhaustion
- mctl-api:847b5cc — fix(commerce): add entitlement retire path and terms validation
- mctl-gitops:e3d8b48 — chore(portal): record api's three disabled commerce tools (portal exposure only)

## Current state of documentation
Page missing. docs/mcp/tools-reference.md has no commerce section.

## Proposed solution
Create docs/guides/commerce.md and add a short "Commerce" block to docs/mcp/tools-reference.md linking to it. REST routes and exact entitlement response fields are not visible in the reviewed diff: marked TODO. Tool parameters taken from tool schemas.

## Alternatives
- Only a tools-reference block: rejected, entitlement concepts need prose.

## Impact
Sidebar entry under Guides. Optional mermaid flow for quote → reserve → commit.
