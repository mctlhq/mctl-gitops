# Document the platform skills catalog and visibility tiers

## Context

On 2026-09-01, `mctl-gitops` published a new platform-wide skill, "review-watch"
(admin-only visibility), to the platform skills catalog, via commits `fc35b55`,
`cae7549`, and `6d0c3d0`. This is confirmed live in production: `mctl_list_platform_skills`
returns it today, alongside a second skill, "archify-diagrams" (public visibility),
also added this week per the catalog's `lastModified` timestamps. This is not an
isolated feature addition — it exposes a structurally new, entirely undocumented
concept on the platform: **platform skills**, a catalog of reusable capabilities that
can be published at different visibility tiers (public, tenant, admin) and enabled or
disabled per tenant.

Today, docs.mctl.ai has no page describing what a platform skill is, how the
public/tenant/admin visibility tiers work, or how a tenant owner discovers, enables, or
disables a skill for their tenant. The relevant MCP tools —
`mctl_list_platform_skills`, `mctl_enable_tenant_skill`, `mctl_disable_tenant_skill`,
`mctl_read_platform_skill`, and `mctl_list_tenant_skill_bindings` — exist but are not
referenced anywhere on the documentation site, including the general MCP tools
reference at `docs/mcp/tools-reference.md`.

## User stories

- AS a **tenant owner** I WANT to understand what a "platform skill" is and how
  visibility tiers (public / tenant / admin) work SO THAT I know which skills are
  available to my tenant and which are restricted.
- AS a **tenant owner** I WANT a documented way to list available skills and enable or
  disable a skill for my tenant SO THAT I can adopt new platform capabilities without
  filing a support request.
- AS a **platform admin** I WANT to understand how admin-only skills (like
  "review-watch") differ from public skills (like "archify-diagrams") SO THAT I can
  reason about what a given tenant can and cannot see or use.
- AS a **developer** integrating via MCP I WANT documented parameters and example calls
  for `mctl_list_platform_skills`, `mctl_enable_tenant_skill`,
  `mctl_disable_tenant_skill`, and `mctl_read_platform_skill` SO THAT I can build
  against the skills catalog without reading `mctl-gitops` source.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/platform/skills.md` THE SYSTEM SHALL explain what a
  platform skill is and how it differs from an MCP tool or a platform operation.
- WHEN the page describes visibility tiers THE SYSTEM SHALL define all three tiers
  (public, tenant, admin) and state which tier the two currently-known skills
  ("archify-diagrams", "review-watch") belong to.
- IF a reader wants to list available skills THEN THE SYSTEM SHALL provide a runnable
  `mctl_list_platform_skills` example call and its expected shape.
- IF a reader wants to enable or disable a skill for their tenant THEN THE SYSTEM SHALL
  provide runnable `mctl_enable_tenant_skill` / `mctl_disable_tenant_skill` example
  calls, including required parameters.
- IF a reader wants to read the full definition of a specific skill THEN THE SYSTEM
  SHALL provide a runnable `mctl_read_platform_skill` example call.
- IF a reader wants to see which skills are currently bound to a tenant THEN THE SYSTEM
  SHALL provide a runnable `mctl_list_tenant_skill_bindings` example call.
- WHEN a reader opens `docs/mcp/tools-reference.md` THE SYSTEM SHALL show a cross-link
  to the new `docs/platform/skills.md` page.
- WHILE the exact parameter names / response shapes of these MCP tools are not
  independently confirmed from source in this pass THE SYSTEM SHALL mark those fields
  with `<TODO: confirm with author of <sha>>`.

## Out of scope

- Documenting how to author or publish a new platform skill from the `mctl-gitops` side
  (a contributor/internal-facing workflow, not an end-user-facing capability).
- A full reference of every currently-published skill's individual behavior (only
  "review-watch" and "archify-diagrams" are known as of this scan; a living skills
  index could be a future follow-up).
- Localisation / i18n.
