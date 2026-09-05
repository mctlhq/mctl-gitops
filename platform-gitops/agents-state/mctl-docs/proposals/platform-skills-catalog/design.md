# Design: platform-skills-catalog

## Source commits

- `mctl-gitops:fc35b55` — feat(platform-skills): publish review-watch (part 1)
- `mctl-gitops:cae7549` — feat(platform-skills): publish review-watch (part 2)
- `mctl-gitops:6d0c3d0` — feat(platform-skills): publish review-watch (part 3)

## Current state of documentation

- **Page is missing** — no `docs/platform/skills.md` (or any equivalent) exists.
- `docs/mcp/tools-reference.md` has no entries for `mctl_list_platform_skills`,
  `mctl_enable_tenant_skill`, `mctl_disable_tenant_skill`, `mctl_read_platform_skill`,
  or `mctl_list_tenant_skill_bindings`.
- `docs/platform/components.md` and `docs/platform/overview.md` describe platform
  components and concepts (ArgoCD, Backstage, mctl-agent, Temporal) but do not mention
  "platform skills" as a concept at all.
- This is a structural gap, not a stale-content gap: the entire concept is new to the
  documentation, not just the specific "review-watch" skill from these three commits.

## Proposed solution

**Action:** Create a new page `docs/platform/skills.md`.

**Content outline:**

1. **Introduction** — what a platform skill is: a reusable, published capability in the
   platform skills catalog, distinct from an MCP tool (a skill is content/config the
   platform surfaces or executes on a tenant's behalf, per the visibility tier it was
   published at) and from a platform operation (see
   `docs/reference/operations.md`, proposed separately in `platform-operations-approval-flow`).

2. **Visibility tiers** — define the three tiers:
   - **public** — visible and available to every tenant by default (example:
     "archify-diagrams", published this week).
   - **tenant** — visible to a tenant only once explicitly enabled for that tenant.
     <TODO: confirm with author of fc35b55 — exact semantics of "tenant" tier vs.
     "public": is "tenant" opt-in per-tenant, or restricted to specific named tenants?>
   - **admin** — visible only to platform admins, not exposed to tenant owners at all
     (example: "review-watch", admin-only per the 2026-09-05 inbox scan).

3. **Discovering skills** — `mctl_list_platform_skills` example call and response
   shape; note that the response is expected to be filtered by the caller's visibility
   (a tenant owner would not see admin-tier skills in the list).

4. **Reading a skill's definition** — `mctl_read_platform_skill` example call.

5. **Enabling / disabling a skill for a tenant** — `mctl_enable_tenant_skill` and
   `mctl_disable_tenant_skill` example calls, with required parameters (tenant
   identifier, skill name at minimum — exact shape
   `<TODO: confirm with author of fc35b55/cae7549/6d0c3d0>`).

6. **Listing a tenant's current skill bindings** — `mctl_list_tenant_skill_bindings`
   example call.

7. **Known skills table** — the two skills confirmed live as of this scan:
   "review-watch" (admin), "archify-diagrams" (public). Framed as a living list that
   will grow, not an exhaustive catalog.

**Also update:**

- `docs/mcp/tools-reference.md` — add a cross-link (short callout, not a full section
  duplication) pointing to the new `docs/platform/skills.md` page from wherever
  tenant-facing / admin-facing tool categories are listed.
- `.vitepress/config.{js,ts}` — add `skills` entry under the `platform/` sidebar group.

## Alternatives

1. **Add a "Platform Skills" subsection to `docs/mcp/tools-reference.md`** instead of a
   standalone page. Dropped: the skills catalog is a first-class platform concept with
   its own lifecycle (publish → tier → enable/disable per tenant) that is broader than
   "here are some MCP tools" — comparable in scope to how Temporal warranted its own
   `docs/platform/temporal.md` page rather than a subsection of
   `docs/platform/components.md` (see the `platform-temporal` proposal precedent).
   A standalone page under `docs/platform/` also gives room to grow the "known skills"
   table as more skills are published, without repeatedly restructuring the tools
   reference page.

2. **Put the new page under `docs/reference/skills.md`** instead of
   `docs/platform/skills.md`. Dropped: `docs/reference/` in this site currently holds
   FAQ/glossary/troubleshooting-style lookup content, while `docs/platform/` holds
   platform-concept pages (architecture, components, openclaw). Platform skills are a
   platform concept a reader needs to understand conceptually (tiers, enable/disable
   lifecycle), which fits `docs/platform/` better.

## Impact

- **Sidebar / nav config:** yes — add `skills` entry under the `platform/` sidebar
  group in `.vitepress/config.{js,ts}`.
- **Diagrams (mermaid):** a simple diagram showing the three visibility tiers and how a
  skill moves from "published to catalog" to "enabled for tenant" is warranted.
- **Documentation versioning:** applies to the current `mctl-gitops` state (skills
  "review-watch" and "archify-diagrams" confirmed live via `mctl_list_platform_skills`
  as of the 2026-09-05 inbox scan). No version-gating language needed for the concept
  itself; the "known skills" table should note it reflects catalog state as of this
  writing and may go stale as more skills are published.
