# MCP Tools Reference: mctl_trigger_shepherd (Tier 3 PR Shepherd)

## Context

On 2026-05-01, `mctl-api` shipped a **sixth admin-only MCP tool** — `mctl_trigger_shepherd`
(commit `f29adbd`, mctl-api 4.17.0). It completes the mctl-agents autonomous pipeline by
adding a Tier 3 "shepherd" step that drives already-open implementer PRs through codex
review fix loops and merges them once they pass.

The tool is live in production: mctl-gitops commit `6c0ba41` (2026-05-01) un-suspended
the `mctl-agents-shepherd` CronWorkflow, meaning automated shepherd runs are already
occurring in the `argo-workflows` namespace.

The existing `proposals/mcp-agents-tools/` (unimplemented) documents five tools and
proposes a new "mctl-agents pipeline controls" section in `docs/mcp/tools-reference.md`.
That section is incomplete without `mctl_trigger_shepherd`. Additionally, commit `e1fbe3f`
(same date) extended the `service` parameter enum for `mctl_trigger_single_service` and
`mctl_trigger_implementer` to include `mctl-agents` as an 8th valid value; the
`mcp-agents-tools` proposed-content still lists only 7 services.

This proposal documents the shepherd tool and patches both omissions.

## User stories

- AS a **platform admin** I WANT to find `mctl_trigger_shepherd` documented alongside
  the other five mctl-agents MCP tools SO THAT I understand the full Tier 1 → Tier 2 →
  Tier 3 pipeline I can trigger via MCP.
- AS a **platform admin** I WANT to understand the `dry_run` parameter of the shepherd
  tool SO THAT I can preview its decisions before anything is merged.
- AS a **platform admin** I WANT to know the cost profile and duration of shepherd runs
  SO THAT I do not accidentally trigger expensive automated merges without understanding
  the stakes.
- AS a **platform admin** I WANT to know that `mctl-agents` itself can be passed as a
  `service` value to `mctl_trigger_single_service` and `mctl_trigger_implementer`
  SO THAT I can self-improve the agents pipeline via MCP.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/mcp/tools-reference.md` THE SYSTEM SHALL show
  `mctl_trigger_shepherd` in the "mctl-agents pipeline controls" section alongside the
  other five tools.
- WHEN the section describes `mctl_trigger_shepherd` THE SYSTEM SHALL include: tool
  name, purpose (Tier 3 shepherd — drives review fix loops and merges), parameters
  (`service`, `slug`, `dry_run`) with types and defaults, cost (~$1–5 per proposal),
  duration (~1–10 min), and return value (`workflow_name`).
- IF a reader wants to preview shepherd decisions without merging THEN THE SYSTEM SHALL
  explain the `dry_run="true"` parameter and what it outputs.
- WHEN the section describes `mctl_trigger_shepherd` THE SYSTEM SHALL note that the
  tool is annotated destructive (merging PRs is irreversible) and admin-only.
- WHEN the section describes `mctl_trigger_single_service` and `mctl_trigger_implementer`
  THE SYSTEM SHALL list `mctl-agents` as one of the valid `service` enum values (8 total,
  not 7).
- WHILE version-status is not independently verified THE SYSTEM SHALL tag the shepherd
  entry with source commit SHA `f29adbd` and note the mctl-api 4.17.0 version.

## Out of scope

- Internal documentation of the shepherd state machine (`decide()`, `.status.yaml`
  transitions `implementing → review-fixing → merged`) — that belongs in the mctl-agents
  repo's own CLAUDE.md / README.
- Documentation of the Argo ClusterWorkflowTemplate (`mctl-agents-shepherd`) itself.
- Non-admin access (the tool is gated to the `admins` group; no tenant-level equivalent exists).
- Localisation / i18n.
