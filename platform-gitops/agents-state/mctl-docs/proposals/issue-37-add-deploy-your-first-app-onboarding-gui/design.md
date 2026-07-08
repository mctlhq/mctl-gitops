# Design: issue-37-add-deploy-your-first-app-onboarding-gui

## Current state

### Content structure

All documentation lives under `docs/` as Markdown files. VitePress builds the site from this directory; the config is in `docs/.vitepress/config.ts`. Navigation is defined in two places in that file: the `nav` array (top bar) and the `sidebar` array (left rail).

The Guides sidebar section currently contains nine entries:

```
{ text: 'Tenants',                   link: '/guides/tenants' },
{ text: 'Services',                  link: '/guides/services' },
{ text: 'Scaffolding (Dockerfile + CI)', link: '/guides/scaffolding' },
{ text: 'GitOps Workflows',          link: '/guides/gitops-workflows' },
{ text: 'Custom Domains',            link: '/guides/domains' },
{ text: 'Databases',                 link: '/guides/databases' },
{ text: 'Preview Environments',      link: '/guides/previews' },
{ text: 'Scaling',                   link: '/guides/scaling' },
{ text: 'Rollbacks',                 link: '/guides/rollbacks' },
```

(`docs/.vitepress/config.ts` lines 60-70)

There is no entry for an end-to-end onboarding guide.

### The closest existing guides

`docs/getting-started/index.md` covers a five-step quick start but deploys a *public* container image (`ghcr.io/mctlhq/hello-world:latest`) via MCP natural language. It does not cover repository preparation, Dockerfile authoring, granting repo access, or the `mctl_deploy_service(action="onboard")` flow needed for a first-party application.

`docs/guides/scaffolding.md` contains the most complete first-party onboarding information: Dockerfile templates for Node.js, Python, Go, and static SPAs; the CI auto-deploy job template; and a "First-time onboard checklist" (lines 278-313). However, it is framed as a reference for CI scaffolding engineers rather than a narrative walkthrough for a new user, and it does not cover tenant confirmation, repository syncing, or accessing the generated service URL.

`docs/guides/gitops-workflows.md` documents `mctl_grant_repo_access` and the sync flow in a single paragraph (lines 84-89) without a step-by-step narrative.

`docs/guides/services.md` documents MCP service operations (deploy, scale, rollback, retire) but does not explain the onboard action or the pre-onboard repository setup.

`docs/guides/domains.md` covers custom domain addition and verification but has no link back to a deployment guide.

### Authoring conventions

Per `CLAUDE.md`:
- Markdown files only in `docs/`; no emoji; English only.
- Mermaid diagrams are supported via a custom fence renderer in `config.ts` (lines 117-133); diagram authoring notes are in `docs/.vitepress/theme/MERMAID_AUTHORING.md`.
- VitePress admonitions (`::: tip`, `::: warning`, `::: danger`) are used in existing guides.

### URL / routing

VitePress is configured with `cleanUrls: true` (`config.ts` line 8), so `docs/guides/deploy-first-app.md` becomes `/guides/deploy-first-app`.

---

## Proposed solution

### Changes

#### 1. New file: `docs/guides/deploy-first-app.md`

A single Markdown file that walks the user through the complete first-party application deployment flow in the order specified in the issue. The page uses H2 headings for each numbered step and includes both a "Via the portal" and a "Via MCP" subsection wherever the platform supports both paths.

Skeleton structure:

```
# Deploy your first app

[Introductory paragraph — what this guide achieves and prerequisites]

## Before you begin
[Prerequisites: GitHub account, tenant exists or will be created, AI client
 connected if using MCP path. Link to /getting-started/ and /mcp/connecting.]

## Step 1: Choose or confirm your tenant
Via the portal / Via MCP

## Step 2: Prepare a repository
[Checklist: repo exists, branch strategy, no secrets in source]

## Step 3: Add a Dockerfile
[Minimal inline example; link to /guides/scaffolding for language templates]

## Step 4: Grant MCTL access to the repository
Via the portal / Via MCP — mctl_grant_repo_access

## Step 5: Sync repositories
Via MCP — mctl_sync_repos

## Step 6: Onboard the service
Via MCP — mctl_deploy_service(action="onboard", ...)

## Step 7: Track the workflow status
Via MCP — mctl_get_workflow_status; link to workflows.mctl.ai

## Step 8: Open the generated service URL
URL pattern https://<team>-<service>.mctl.ai; healthz check

## Optional: Add a custom domain
Link to /guides/domains; brief mctl_add_custom_domain snippet

## Optional: Manage the platform through MCP
Link to /mcp/overview and /mcp/tools-reference; brief next-steps list
```

The "Via MCP" sections use fenced natural-language prompts (consistent with the style in `docs/guides/services.md` and `docs/guides/scaffolding.md`) and, where the issue specifies a tool name directly, also show the tool call signature.

The "Before you begin" section avoids duplication by linking to `docs/getting-started/index.md` for MCP connection setup and to `docs/mcp/connecting.md` for token details, rather than re-explaining those flows.

#### 2. Sidebar entry in `docs/.vitepress/config.ts`

Add one entry at the top of the Guides section (before the existing "Tenants" entry):

```typescript
{ text: 'Deploy your first app', link: '/guides/deploy-first-app' },
```

This makes the new guide the first item a user encounters when browsing the Guides section, consistent with the intent of the issue.

No changes are required to the top `nav` bar; the "Guides" nav item already points to `/guides/tenants` (the first guide) and will continue to work. A follow-up could update that nav link to `/guides/deploy-first-app`, but that is out of scope for this issue.

### Rationale

- A single new file minimises the blast radius. No existing guides are modified, so there is no risk of breaking links or changing established content.
- Placing it at the top of the Guides sidebar gives it maximum discoverability without touching the top nav, which would require more design judgement than the issue specifies.
- The dual-path (portal / MCP) structure inside each step directly satisfies the issue requirement that "the guide should mention both options" without duplicating the entire guide as two parallel documents.
- Linking out to existing guides (`/guides/scaffolding`, `/guides/domains`, `/mcp/connecting`) for depth avoids content drift: if those guides are updated, the new guide stays accurate by reference.

---

## Alternatives

### Alternative 1: Expand `docs/getting-started/index.md` in place

The quick-start page already covers a subset of these steps. Its "Step 4: Deploy your first service" section could be extended to cover the full first-party onboarding flow.

Rejected because: (a) the quick-start uses a public image and is intentionally short; mixing in a ten-step Dockerfile-and-CI walkthrough would destroy its "under 10 minutes" promise; (b) the issue explicitly requests a new page at `/guides/deploy-first-app`, not an expansion of the existing page; (c) extending the quick-start would require restructuring its headings, risking broken deep-links from external sources.

### Alternative 2: Create a multi-page mini-guide under `docs/guides/deploy-first-app/`

Each of the ten steps becomes its own Markdown file under a sub-directory (`deploy-first-app/index.md`, `deploy-first-app/step-1-tenant.md`, etc.) with a dedicated sidebar sub-group.

Rejected because: the ten steps are each short enough to fit comfortably on one page; VitePress pages with anchored H2 headings offer equivalent navigation via the in-page TOC; creating a sub-directory adds sidebar configuration complexity for no user benefit; the existing guides (e.g. `docs/guides/scaffolding.md` at 313 lines) demonstrate that single-file long-form guides are the established pattern in this repo.

### Alternative 3: Annotate and cross-link existing guides rather than creating a new page

Add "next step" callout blocks to the end of each relevant guide (tenants → scaffolding → services → domains) so a user can navigate the existing pages in sequence.

Rejected because: it requires editing five existing files and does not produce a single shareable URL that can be used in onboarding emails, support responses, or marketing material; users following a cross-page trail are more likely to get lost than users following a single numbered guide; the issue explicitly requests a dedicated guide.

---

## Platform impact

### Migrations

None. VitePress generates a static site. Adding a new Markdown file and a sidebar entry does not change existing URLs or require a database migration.

### Backward compatibility

No existing URLs change. The new sidebar entry is additive. The existing "Tenants" entry moves down one position in the rendered sidebar but its URL is unchanged.

### Resource impact

One additional ~5-8 KB Markdown file. No measurable impact on build time or generated bundle size.

### Risks and mitigations

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Portal steps for grant-access and sync are not publicly accessible (portal may not expose these flows) | Medium | Use `::: tip` admonition directing portal users to complete those steps via MCP; file a follow-up to add portal instructions once UI paths are confirmed |
| Tool names or parameters diverge from what is documented in `docs/guides/scaffolding.md` | Low | Cross-reference the scaffolding guide's "First-time onboard checklist" (lines 278-313) as the authoritative source; the new guide links to it rather than duplicating parameters |
| The generated service URL pattern (`<team>-<service>.mctl.ai`) changes | Low | The pattern is stated in `docs/getting-started/index.md` line 104 and is the established convention; document it as-is and flag for review if the platform changes |
