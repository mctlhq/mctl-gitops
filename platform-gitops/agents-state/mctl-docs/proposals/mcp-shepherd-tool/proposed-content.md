# Proposed content: mcp-shepherd-tool

> **Apply to:** `mctl-docs/docs/mcp/tools-reference.md` (UPDATE)
> **Source:** mctl-api@f29adbd, mctl-api@e1fbe3f
> **version-status:** verified — mctl-api 4.17.0 in production 2026-05-01 (mctl-gitops `00dc844`)

---

This proposal supplies **two sets of changes** to `docs/mcp/tools-reference.md`.
Apply them after (or together with) `proposals/mcp-agents-tools/proposed-content.md`.

---

## Change 1 — Add `mctl_trigger_shepherd` to the tool summary table

**Location:** inside the `## mctl-agents pipeline controls` section, in the
`### Tool summary` table.

**Before:**

```markdown
| Tool | Purpose | Returns |
|---|---|---|
| `mctl_trigger_agents_run` | Full pipeline — all service-agents + mentor digest | `workflow_name` |
| `mctl_trigger_mentor_only` | Mentor weekly digest only | `workflow_name` |
| `mctl_trigger_single_service` | One service-agent cycle | `workflow_name` |
| `mctl_list_recent_agent_runs` | List ≤10 recent pipeline runs from audit log | JSON array |
| `mctl_trigger_implementer` | Tier 2: open PRs for accepted proposals | `workflow_name` |
```

**After:**

```markdown
| Tool | Purpose | Returns |
|---|---|---|
| `mctl_trigger_agents_run` | Full pipeline — all service-agents + mentor digest | `workflow_name` |
| `mctl_trigger_mentor_only` | Mentor weekly digest only | `workflow_name` |
| `mctl_trigger_single_service` | One service-agent cycle | `workflow_name` |
| `mctl_list_recent_agent_runs` | List ≤10 recent pipeline runs from audit log | JSON array |
| `mctl_trigger_implementer` | Tier 2: open PRs for accepted proposals | `workflow_name` |
| `mctl_trigger_shepherd` | Tier 3: drive implementer PRs through review to merge | `workflow_name` |
```

---

## Change 2 — Update `service` enum for `mctl_trigger_single_service` and `mctl_trigger_implementer`

**Location:** `### mctl_trigger_single_service` parameter table, `service` row.

**Before:**

```markdown
| `service` | string (enum) | yes | One of: `mctl-web`, `mctl-openclaw`, `mctl-docs`, `mctl-api`, `mctl-portal`, `mctl-agent`, `mctl-gitops` |
```

**After:**

```markdown
| `service` | string (enum) | yes | One of: `mctl-web`, `mctl-openclaw`, `mctl-docs`, `mctl-api`, `mctl-portal`, `mctl-agent`, `mctl-gitops`, `mctl-agents` |
```

Apply the same change to the `service` row in `### mctl_trigger_implementer`:

**Before:**

```markdown
| `service` | string (enum) | no | Filter to one service. Leave empty to process all services. Same enum as `mctl_trigger_single_service`. |
```

**After:**

```markdown
| `service` | string (enum) | no | Filter to one service. Leave empty to process all services. Same enum as `mctl_trigger_single_service` (8 values, including `mctl-agents`). |
```

---

## Change 3 — Insert `### mctl_trigger_shepherd` detail block

**Location:** Insert after `### mctl_trigger_implementer` and before
`### Status polling`.

**Insert (new content — paste verbatim):**

```markdown
---

### `mctl_trigger_shepherd`

> ⚠️ **Destructive.** The shepherd may merge pull requests. Merging is irreversible.
> Review `dry_run` output before triggering a live run.

Triggers the Tier 3 PR shepherd. The shepherd inspects `.status.yaml` entries with
`status` in `{implementing, review-fixing}`, fetches each linked PR's codex review
state, and decides one of three actions:

- **Implement feedback** — calls the implementer with `--review-feedback`, pushing
  a follow-up commit to the PR branch (transitions to `review-fixing`).
- **Merge** — merges the PR once codex review passes and CI is green (transitions
  to `merged`).
- **Wait** — no action if the PR is still pending review or CI.

An automated shepherd CronWorkflow runs daily in the `argo-workflows` namespace.
This tool triggers an on-demand run.

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `service` | string (enum) | no | Filter to one service. One of: `mctl-web`, `mctl-openclaw`, `mctl-docs`, `mctl-api`, `mctl-portal`, `mctl-agent`, `mctl-gitops`, `mctl-agents`. Leave empty to consider all services. |
| `slug` | string | no | Filter to one proposal slug (across services unless `service` is also set). |
| `dry_run` | `"true"` \| `"false"` | no | Evaluate `decide()` for every matched proposal and print the decision **without** calling the implementer or merging anything. Default `"false"`. |

**Cost / duration:** ~$1–5 per proposal; ~1–10 minutes per proposal.

**Returns:** `workflow_name` — use with `mctl_get_workflow_status` or
`mctl_list_recent_agent_runs` to track progress.

**Example — preview shepherd decisions for mctl-docs without acting:**

```
mctl_trigger_shepherd(service="mctl-docs", dry_run="true")
# → { "workflow_name": "mctl-agents-shepherd-xyz42" }
# Check output: mctl_get_workflow_status(workflow_name="mctl-agents-shepherd-xyz42")
```

**Example — shepherd one specific proposal to merge:**

```
mctl_trigger_shepherd(service="mctl-docs", slug="mcp-agents-tools")
# → { "workflow_name": "mctl-agents-shepherd-abc77" }
```

_Available as of mctl-api 4.17.0 (commit `f29adbd`). CronWorkflow
`mctl-agents-shepherd` is live in `argo-workflows` namespace as of 2026-05-01._
```

---

## Change 4 — Update intro paragraph count

**Location:** Opening paragraph of `## mctl-agents pipeline controls`.

**Before:**

```markdown
The five tools below let platform admins drive this pipeline on demand from any MCP-capable
client (e.g. Claude Desktop, Claude Code).
```

**After:**

```markdown
The six tools below let platform admins drive this pipeline on demand from any MCP-capable
client (e.g. Claude Desktop, Claude Code).
```

---
