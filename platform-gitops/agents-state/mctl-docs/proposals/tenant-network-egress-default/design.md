# Design: tenant-network-egress-default

## Source commits
- mctl-api:6cc17bb — fix(tenant): default internet egress to closed, and let MCP set it
- mctl-gitops:ae6ff96 — ROADMAP.md cross-reference only (already marks this item `[x]` done; no separate doc content needed from this commit, cited for corroboration)

## Current state of documentation
- Existing page: `docs/guides/tenants.md` — covers "Create a Tenant" (via
  MCP and via self-service form), "List Tenants", "Get Tenant Details",
  "Delete a Tenant", "Tenant Naming", "Resource Quotas". It never mentions
  network policy, egress, or `allow_internet_egress` — confirmed via a
  full-text read and grep for `egress|network|internet` (zero matches).

## Proposed solution
Add a new "Network Policy" subsection to `docs/guides/tenants.md`, placed
directly under "Create a Tenant" (after the "Via MCP (Natural Language)"
block, before "Via Self-Service Form"), since network policy is decided at
creation time. Content:
- State the default: outbound internet egress is denied for new tenants
  unless `allow_internet_egress` is set to `"true"`.
- Show the natural-language MCP example for overriding it.
- Note the Argo Workflow pod exception (builds/deploys always have
  internet access).

No structural/sidebar change — this is a content addition to an existing
page already in the nav.

## Alternatives
1. **New standalone page `docs/guides/network-policy.md`.** Dropped — the
   topic is small (one default + one override), doesn't warrant a new nav
   entry, and readers looking for it will look at the tenant-creation page
   first, not a separate networking page.
2. **Add to `docs/security/authorization.md`.** Dropped — that page covers
   who-can-access-what (RBAC/groups), not tenant-creation-time network
   configuration. Keeping it next to the `mctl_create_tenant` flow it
   affects is more discoverable.

## Impact
- Does it touch the VitePress sidebar / nav config? No — existing page.
- Does it need diagrams (mermaid)? No — a short paragraph + one example is
  sufficient; no multi-step flow to visualize.
- Documentation versioning: none (this site has no versioned docs per
  `context/architecture.md`'s known limitations). Applies to current
  `main`/production docs immediately.
