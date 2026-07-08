# Deploy your first app — onboarding guide

## Context

A first-time MCTL user can create a tenant today and connect an AI client via MCP, but the docs do not yet provide a single, ordered walkthrough for taking their own GitHub-hosted application from source code to a running, publicly accessible service. The relevant information is scattered across `docs/getting-started/index.md`, `docs/guides/scaffolding.md`, `docs/guides/services.md`, `docs/guides/gitops-workflows.md`, and `docs/guides/domains.md`. A new user must read and correlate several pages to understand the full flow, which increases time-to-first-deploy and the likelihood of abandonment.

This proposal adds a dedicated end-to-end guide at `/guides/deploy-first-app` (`docs/guides/deploy-first-app.md`) that consolidates those scattered steps into a single, sequential narrative. The guide covers both the portal-based path (using `app.mctl.ai`) and the MCP-based path (using an AI client), and closes with optional steps for custom domains and ongoing MCP management.

## User stories

- AS a new MCTL user I WANT a single page that walks me through every step to deploy my own application SO THAT I can reach a working service URL without reading multiple separate guides.
- AS a developer who prefers AI tooling I WANT the guide to include the MCP-based variant of each step SO THAT I can complete the deployment entirely from my AI client without switching to the portal.
- AS a developer who prefers a graphical interface I WANT the guide to include the portal-based variant of each step SO THAT I can complete the deployment without configuring an MCP client.
- AS a returning user who needs to add a custom domain I WANT the guide to include an optional domain step with a clear reference to `docs/guides/domains.md` SO THAT I can follow up without searching.

## Acceptance criteria (EARS)

- WHEN a user navigates to `/guides/deploy-first-app` THE SYSTEM SHALL render the guide with a title of "Deploy your first app" and a visible, ordered list of steps matching the ten-step structure in the issue.
- WHEN the guide renders THE SYSTEM SHALL present each of the following steps in order: (1) choose or confirm your tenant, (2) prepare a repository, (3) add a Dockerfile, (4) grant MCTL access to the repository, (5) sync repositories, (6) onboard the service, (7) track the workflow status, (8) open the generated service URL, (9) optional — add a custom domain, (10) optional — manage the platform through MCP.
- WHEN a step has both a portal path and an MCP path THE SYSTEM SHALL present both variants within that step, clearly labelled "Via the portal" and "Via MCP".
- WHEN the guide references a Dockerfile THE SYSTEM SHALL either inline the minimal template or link to `docs/guides/scaffolding.md` for language-specific templates.
- WHEN the guide is added to the site THE SYSTEM SHALL include an entry for "Deploy your first app" at the top of the Guides section in `docs/.vitepress/config.ts`, linking to `/guides/deploy-first-app`.
- WHILE the user follows the onboard step THE SYSTEM SHALL document the `mctl_deploy_service` tool with `action="onboard"` parameters (`team_name`, `component_name`, `dockerfile_repo`, `git_tag`, `port`, `service_template`) as defined in `docs/guides/scaffolding.md`.
- WHEN the guide documents the "Grant access" step THE SYSTEM SHALL reference the `mctl_grant_repo_access` tool and instruct the user to install the GitHub App via the returned URL, matching the pattern in `docs/guides/scaffolding.md` lines 285-287.
- WHEN the guide documents the "Sync repositories" step THE SYSTEM SHALL reference the `mctl_sync_repos` tool with the `team` parameter.
- WHEN the guide documents the "Track workflow status" step THE SYSTEM SHALL reference `mctl_get_workflow_status` and note that the Argo Workflow UI is available at `workflows.mctl.ai`, consistent with `docs/guides/gitops-workflows.md`.
- WHEN the guide documents the "Open the generated service URL" step THE SYSTEM SHALL state the URL pattern `https://<team>-<service>.mctl.ai` and recommend verifying with `curl https://<team>-<service>.mctl.ai/healthz`.
- IF the user does not yet have a tenant THE SYSTEM SHALL direct them to the portal at `mctl.ai` or to `mctl_create_tenant` before proceeding with the remaining steps.
- IF the repository is already accessible to MCTL THE SYSTEM SHALL note that the "Grant access" step can be skipped and the user may proceed directly to syncing.

## Out of scope

- Changes to any guide other than the new `docs/guides/deploy-first-app.md` and the sidebar config.
- Documentation for database provisioning, preview environments, scaling, or rollbacks (those are covered by existing guides and may be referenced but not expanded here).
- A portal UI walkthrough with screenshots (the portal UI is not currently documented at this level in the repo; adding screenshots would require production portal access and is a separate effort).
- Changes to `docs/getting-started/index.md` (that page targets a public-image quick-start; the new guide targets first-party application onboarding — the two are complementary, not duplicates).
- CI workflow scaffolding details beyond what is needed to trigger the onboard step (the full CI template lives in `docs/guides/scaffolding.md`).

## Open questions

1. **Portal steps for grant-access and sync**: The current docs do not describe portal equivalents for `mctl_grant_repo_access` or `mctl_sync_repos`. If those operations are portal-accessible, the exact UI path (menu item, button label) is unknown and should be confirmed with the product team before the guide is published. The implementer should stub these as "Via the portal: navigate to [Settings > Repositories] (exact path TBC)" and file a follow-up.
2. **Scope of "portal-based deployment"**: The issue says the guide should mention portal-based deployment, but `docs/guides/services.md` only documents MCP and API paths. The portal service-deploy flow (if it exists at `app.mctl.ai`) is undocumented in the repo. The implementer should confirm with the product team what portal steps exist for steps 4-6 and mark any unconfirmed portal steps with a tip block directing users to MCP as the authoritative path.
3. **Step 1 — "Choose or confirm your tenant"**: It is unclear whether the tenant-selection step should describe using the portal tenant picker, calling `mctl_list_tenants`/`mctl_get_tenant`, or both. The most reasonable interpretation is to offer both and link to `docs/guides/tenants.md` for deeper management.
4. **Sidebar placement**: The issue specifies the URL `/guides/deploy-first-app` but does not specify where in the sidebar it should appear. This proposal places it first in the Guides section (before "Tenants") so it reads as the primary entry point. If the team prefers it under "Getting Started", the sidebar entry location should be adjusted.
