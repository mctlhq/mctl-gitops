# Document commerce budget/receipt tools and finite service entitlements

version-status: unverified, see commit SHA (mctl-api 4.86.0+ per gitops bump 4163272)

## Context
`mctl-api` exposes commerce read tools over MCP (`mctl_get_commerce_budget`, `mctl_get_commerce_receipt`, `mctl_list_commerce_invocations`) and, since 2026-10-13, finite service entitlements: admins grant a tenant a package of units for a capability with an invoice reference and expiry; tenants can list and read them (4fbee56). Entitlement gating now precedes budget reservation and holds are released on denied authorization (44a1961, 197575d). None of this appears in docs/mcp/tools-reference.md or docs-tree.

## User stories
- AS a tenant owner I WANT to see my budget, receipts and entitlements SO THAT I understand spend and remaining units.
- AS a platform admin I WANT to know how to grant an entitlement SO THAT I can fulfil a paid package.

## Acceptance criteria (EARS)
- WHEN a reader opens tools-reference THE SYSTEM SHALL list the three commerce read tools with parameters.
- WHEN a reader opens the commerce guide THE SYSTEM SHALL explain budget fields (available, reserved, committed, pending liability) and the `funds_mode` field.
- IF a reader is an admin THEN THE SYSTEM SHALL show the grant-entitlement request body.
- WHILE the commerce feature set is in preview THE SYSTEM SHALL say so. <TODO: confirm status with author>

## Out of scope
- Payment proof formats, paid-capability gateway internals (mctl-agents), pricing.
