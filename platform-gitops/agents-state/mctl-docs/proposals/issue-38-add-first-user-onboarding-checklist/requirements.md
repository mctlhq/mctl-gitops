# Add First-User Onboarding Checklist

## Context

After a tenant is created on MCTL, new users have no single reference that confirms
all platform surfaces are accessible and that their environment is ready to receive
a workload. The existing documentation covers the deployment journey in depth
(`docs/guides/deploy-first-app.md`, eight steps) and a quick-start flow
(`docs/getting-started/index.md`, five steps), but neither serves the purpose of a
concise, shareable post-provisioning checklist that covers access verification across
Portal, ArgoCD, and Argo Workflows before any deployment attempt begins.

The issue requests a short checklist oriented at the "just-provisioned tenant" moment.
Its scope is deliberately wider than deployment alone — it includes access checks for
all three platform UIs, preparation of source artifacts, a first workload deployment,
and an introduction to MCP-based management. The deliverable should be a standalone
page that customer-facing teams can link to in welcome emails or onboarding tickets.

## User stories

- AS a new MCTL user I WANT a single page that lists every step required to go from
  a freshly created tenant to a running workload SO THAT I do not miss a prerequisite
  or discover an access gap after starting the deployment.
- AS a platform operator or customer success manager I WANT a shareable, stable URL
  for the checklist SO THAT I can include it in welcome emails and support tickets
  without pasting raw steps.
- AS a returning user who has completed the checklist I WANT each item to link to the
  relevant deep-dive guide SO THAT I can expand any step without searching the docs.

## Acceptance criteria (EARS)

- WHEN a user navigates to `/guides/first-user-checklist` THE SYSTEM SHALL serve a
  VitePress page that renders without build errors.
- WHEN the page is rendered THE SYSTEM SHALL display all eight checklist items from
  the issue in the order specified (tenant confirmation, Portal access, ArgoCD access,
  Workflow access, artifact preparation, first deploy, log/status review, MCP
  management).
- WHEN the page is rendered THE SYSTEM SHALL present each item as a Markdown task-list
  entry (`- [ ]`) so the page reads as a structured checklist.
- WHEN the sidebar is rendered THE SYSTEM SHALL include a "First-user checklist" entry
  under the Guides section in `docs/.vitepress/config.ts` pointing to
  `/guides/first-user-checklist`.
- WHILE a user reads a checklist item that has a corresponding detail page THE SYSTEM
  SHALL provide an inline hyperlink to that page (e.g. Portal item links to
  `https://app.mctl.ai`; MCP item links to `/mcp/overview`; deploy item links to
  `/guides/deploy-first-app`; logs item links to Argo Workflows URL).
- IF a checklist item covers a topic that is not yet fully documented THE SYSTEM SHALL
  include a note indicating where documentation is expected rather than omitting the
  item.
- WHEN the VitePress build runs (`npm run docs:build`) THE SYSTEM SHALL complete with
  exit code 0 and no broken internal links referencing the new page.

## Out of scope

- Modifying or restructuring the existing `docs/getting-started/index.md` Quick Start
  page — the checklist is a companion, not a replacement.
- Modifying `docs/guides/deploy-first-app.md` — that guide remains the detailed
  deployment reference; the checklist links to it.
- Adding interactive (JavaScript-driven) checkbox persistence — the task-list items
  are static Markdown and are not wired to local storage or a backend.
- Internationalisation or non-English versions of the page.
- Changes to the welcome email template or any system outside the `mctl-docs` repo.

## Open questions

1. Sidebar placement: the issue does not specify where in the Guides sidebar the new
   entry should appear. This proposal places it first in the Guides group (before
   "Deploy your first app") because it precedes deployment chronologically. If the
   team prefers it after "Deploy your first app" or in a separate "Getting Started"
   group, the `config.ts` entry should be adjusted accordingly.
2. ArgoCD URL: the docs reference `workflows.mctl.ai` for Argo Workflows but do not
   consistently name a public ArgoCD URL. The proposal assumes `argocd.mctl.ai` by
   analogy; this should be confirmed before publication.
3. Welcome-email link: the issue says the checklist "can be sent to customers" but
   does not specify whether the page URL should be added to the automated welcome
   email. That change would be outside this repo and is flagged here for follow-up.
