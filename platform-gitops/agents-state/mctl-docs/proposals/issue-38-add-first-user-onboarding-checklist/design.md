# Design: issue-38-add-first-user-onboarding-checklist

## Current state

The `mctl-docs` repository is a VitePress 1.6+ site (confirmed in `package.json`)
whose content lives under `docs/`. The site is built with `npm run docs:build` and
served by nginx in a Docker multi-stage image.

Navigation and sidebar are declared in `docs/.vitepress/config.ts` (the sole config
file; there is no per-directory config). The sidebar is a plain JavaScript array of
groups starting at line 41. The **Guides** group is defined at lines 59-73 and
currently contains ten items:

```
Deploy your first app   → /guides/deploy-first-app
Tenants                 → /guides/tenants
Services                → /guides/services
Scaffolding             → /guides/scaffolding
GitOps Workflows        → /guides/gitops-workflows
Custom Domains          → /guides/domains
Databases               → /guides/databases
Preview Environments    → /guides/previews
Scaling                 → /guides/scaling
Rollbacks               → /guides/rollbacks
```

There is no existing `/guides/first-user-checklist` route. The closest content to
what the issue requests lives in:

- `docs/getting-started/index.md` — five-step Quick Start covering sign-in, MCP
  connection, first deploy, and "What's next?" table; written as instructional prose,
  not a checklist.
- `docs/guides/deploy-first-app.md` — eight-step detailed deployment guide covering
  tenant selection, repository preparation, Dockerfile authoring, GitHub App
  installation, repo sync, onboarding, workflow tracking, and URL verification;
  similarly prose-oriented.

Neither page has a scannable task-list format, and neither surfaces the access
verification steps (Portal, ArgoCD, Argo Workflows) as discrete pre-deployment
checkpoints.

The VitePress theme applies a custom CSS layer from
`docs/.vitepress/theme/custom.css` and a Vue layout from
`docs/.vitepress/theme/Layout.vue`; no changes to those files are needed for a plain
Markdown checklist page. VitePress renders GitHub Flavored Markdown task lists
(`- [ ]` / `- [x]`) natively.

## Proposed solution

Create one new Markdown file and make one targeted edit to the VitePress config.

### New file: `docs/guides/first-user-checklist.md`

The page consists of:

1. A brief introduction paragraph (2-3 sentences) explaining the page's purpose and
   its relationship to the detailed guides.
2. Eight task-list items corresponding exactly to the items in the issue, each with:
   - A short heading or bold label.
   - One or two sentences of context.
   - Inline links to the canonical detail page or URL where one exists.

Checklist items and their link targets derived from the existing docs:

| # | Item | Link target |
|---|------|-------------|
| 1 | Confirm tenant/workspace | `/guides/tenants` |
| 2 | Check Portal access | `https://app.mctl.ai` |
| 3 | Check ArgoCD access | `https://argocd.mctl.ai` (see Open question 2) |
| 4 | Check Workflow access | `https://workflows.mctl.ai` (referenced in `deploy-first-app.md` line 217) |
| 5 | Prepare a Git repository or Docker image | `/guides/deploy-first-app#step-2-prepare-a-repository` and `/guides/scaffolding` |
| 6 | Deploy the first workload | `/guides/deploy-first-app` |
| 7 | Review logs and status | `/mcp/tools-reference` and `https://workflows.mctl.ai` |
| 8 | Learn to manage via MCP | `/mcp/overview` and `/mcp/connecting` |

The page does not include interactive JavaScript. Static task-list syntax is correct
because the checklist is primarily a reference document to be worked through once, not
a persisted to-do board.

### Config change: `docs/.vitepress/config.ts`

Add one entry to the Guides sidebar array. The new entry is inserted **before**
"Deploy your first app" at line 62 so that the chronological sequence in the sidebar
reflects the pre-deployment nature of the checklist:

```ts
{ text: 'First-user checklist', link: '/guides/first-user-checklist' },
```

No other config changes are required. `cleanUrls: true` (line 7) means the file at
`docs/guides/first-user-checklist.md` is served at `/guides/first-user-checklist`
without a trailing `.html`.

### Why this location

A dedicated `/guides/first-user-checklist` page is preferred over embedding the
checklist in an existing page for three reasons:

1. **Stable, shareable URL** — customer success teams can include a direct link in
   welcome emails. A section anchor on an existing page is fragile; an anchor on a
   page whose primary topic is something else is harder to communicate.
2. **Separation of concerns** — `deploy-first-app.md` is a deep-dive with CLI
   snippets and parameter tables. Prepending an access-verification checklist there
   would make the page dual-purpose and harder to scan.
3. **Sidebar discoverability** — a named sidebar entry labelled "First-user
   checklist" communicates intent immediately to readers browsing the nav.

## Alternatives

### Alternative A: Add a checklist section to `docs/getting-started/index.md`

The Quick Start page (`/getting-started/`) is the first nav item and already mentions
tenant creation. A new "Onboarding checklist" section could be added at the top.

Dropped because: the Quick Start is already a five-step instructional guide. Mixing
a checklist format with step-by-step prose in the same page creates structural
ambiguity. The page would grow in a way that is harder to maintain, and it would not
have its own stable URL distinct from the broader Quick Start content.

### Alternative B: Add a checklist preamble to `docs/guides/deploy-first-app.md`

A "Before you begin — access checklist" section could be inserted before "Step 1" in
the deploy guide.

Dropped because: the deploy guide covers deployment of source code, not access
verification across ArgoCD and Argo Workflows. Items 2-4 of the checklist (Portal,
ArgoCD, Workflow access) have no natural home in a deployment walkthrough. The deploy
guide would become longer and unfocused. Additionally, the guide already has a
"Before you begin" block (lines 12-17) whose purpose is different (prerequisites for
the deployment itself, not general access checks).

### Alternative C: Create a new top-level section (e.g., `/onboarding/checklist`)

A separate nav group "Onboarding" could be introduced alongside "Getting Started" and
"Guides".

Dropped because: it requires a nav bar change in addition to a sidebar change, adds a
new top-level concept to the information architecture, and is disproportionate for a
single page. The Guides section already accommodates operational reference pages
(`rollbacks.md`, `scaling.md`) and is the right home for a how-to checklist.

## Platform impact

- **Build**: one new `.md` file, one sidebar entry. No new dependencies. The VitePress
  build step remains unchanged; build time impact is negligible.
- **Navigation**: the Guides sidebar gains one entry. All existing URLs are
  unaffected; `cleanUrls: true` means no redirect rules are needed for the new page.
- **Docker image**: the build artifact gains one additional HTML file. Size impact is
  under 10 KB.
- **Backward compatibility**: fully additive. No existing pages are modified beyond
  the single `config.ts` sidebar insertion.
- **Risks**: none identified beyond the ArgoCD URL ambiguity noted in Open question 2.
  If the URL is wrong, a single-line correction fixes it without structural changes.
- **Rollback**: remove the `docs/guides/first-user-checklist.md` file and revert the
  `config.ts` sidebar entry. One commit reverts the entire change.
