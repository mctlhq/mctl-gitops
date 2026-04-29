# Design: openclaw-docker-skip-onboarding

## Source commits

- `mctl-openclaw:490e6d6` — feat(docker): add OPENCLAW_SKIP_ONBOARDING env to skip
  onboarding during Docker setup (#55518)

## Current state of documentation

- **Existing page:** `docs/platform/openclaw.md` — "OpenClaw Integration"
  - Does not contain a deployment / setup environment variable reference.
  - A platform admin must navigate to `docs.openclaw.ai/install/docker` to find
    `OPENCLAW_SKIP_ONBOARDING`. That page lists ~20 env vars; finding the right one
    is not obvious.
  - **Gap:** `docs.mctl.ai` is missing the variable entirely.

## Proposed solution

Add a **"Deployment configuration"** subsection to `docs/platform/openclaw.md` containing
a concise env-var table scoped to the variables most relevant to mctl's automated deployment
model. Start with `OPENCLAW_SKIP_ONBOARDING`; the table can grow as more deployment-relevant
vars ship.

The table format mirrors the one in openclaw's upstream Docker docs for familiarity.

Cross-link to OpenClaw's full Docker guide (`docs.openclaw.ai/install/docker`) for the
complete variable list.

No changes to `.vitepress/config` are needed.

## Alternatives

1. **Inline note only (no table)** — a one-sentence callout instead of a table; dropped
   because a table scales naturally as more ops-relevant env vars ship.

2. **Separate `docs/guides/openclaw-docker.md` page** — a dedicated Docker setup guide
   for mctl; dropped because mctl provisions OpenClaw via ArgoCD (gitops), not raw
   `docker run` commands. A full Docker setup guide would duplicate openclaw's own docs.
   A single table cell in `openclaw.md` is sufficient.

## Impact

- **Sidebar / nav config:** no change (content added inside existing page).
- **Mermaid diagrams:** none needed for this proposal.
- **Documentation versioning:** applies to mctl-openclaw as of commit `490e6d6`.
  Version unverified (no mcp__mctl__* check possible).
