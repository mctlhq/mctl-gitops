# Proposed content: mcp-agents-tools

> **Apply to:** `mctl-docs/docs/mcp/tools-reference.md` (UPDATE)
> **Source:** mctl-api@016b3c8, mctl-api@f41590e

---

Insert the following section at the end of `docs/mcp/tools-reference.md`, after the last
existing tool category and before any footer/see-also block.

---

## mctl-agents pipeline controls

> **Admin-only.** All tools in this section require membership in the `admins` group.
> Calls from non-admin users return `403 Forbidden`.
>
> _Version note: available as of mctl-api 4.15.0 (commit `016b3c8`) and 4.16.0 (`f41590e`).
> version-status: unverified — confirm against production before relying on this page._

The mctl platform runs a daily autonomous R&D pipeline (`mctl-agents`) that scans sibling
repos for changes, identifies documentation gaps, and writes spec proposals — one cycle per
service (researcher → analyst → spec-writer). A Tier 2 implementer can also convert accepted
proposals into pull requests automatically.

The five tools below let platform admins drive this pipeline on demand from any MCP-capable
client (e.g. Claude Desktop, Claude Code).

### Tool summary

| Tool | Purpose | Returns |
|---|---|---|
| `mctl_trigger_agents_run` | Full pipeline — all service-agents + mentor digest | `workflow_name` |
| `mctl_trigger_mentor_only` | Mentor weekly digest only | `workflow_name` |
| `mctl_trigger_single_service` | One service-agent cycle | `workflow_name` |
| `mctl_list_recent_agent_runs` | List ≤10 recent pipeline runs from audit log | JSON array |
| `mctl_trigger_implementer` | Tier 2: open PRs for accepted proposals | `workflow_name` |

---

### `mctl_trigger_agents_run`

Triggers a full mctl-agents run: every service-agent (researcher → analyst → spec-writer
in parallel) followed by the mentor weekly digest. Equivalent to the daily 06:00 UTC cron,
but on demand.

**Parameters:** none

**Cost / duration:** ~$10 against Claude subscription quota; ~15 minutes.

**Result:** A `chore(agents)` commit lands in `mctl-gitops` main under
`platform-gitops/agents-state/` with new inbox files, proposals, and updated `.status.yaml`
entries.

**Returns:** `workflow_name` string — use with `mctl_get_workflow_status` to track progress.

```
mctl_trigger_agents_run()
# → { "workflow_name": "mctl-agents-daily-abc12" }
```

---

### `mctl_trigger_mentor_only`

Runs only the mentor sub-agent, which reads all service inbox files from the past week and
produces a cross-service digest. Lighter than the full run.

**Parameters:** none

**Cost / duration:** ~$2, ~5 minutes.

**Returns:** `workflow_name`

---

### `mctl_trigger_single_service`

Runs the researcher → analyst → spec-writer cycle for a single service only.
Useful for spot-checking one repo after a significant release.

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `service` | string (enum) | yes | One of: `mctl-web`, `mctl-openclaw`, `mctl-docs`, `mctl-api`, `mctl-portal`, `mctl-agent`, `mctl-gitops` |

**Cost / duration:** ~$2–5, ~5–10 minutes.

**Returns:** `workflow_name`

**Example:**

```
mctl_trigger_single_service(service="mctl-docs")
# → { "workflow_name": "mctl-agents-single-xyz99" }
```

---

### `mctl_list_recent_agent_runs`

Returns up to 10 recent mctl-agents pipeline runs from the audit log, enriched with the
run mode and target service so you don't need to parse the workflow name.

**Parameters:** none

**Returns:** JSON object `{ "items": [...], "count": N }` where each item has:

| Field | Description |
|---|---|
| `workflowName` | Argo workflow name (use for status polling) |
| `operation` | Operation name (`mctl-agents-run`, `mctl-agents-implement`, …) |
| `mode` | Run mode (`full`, `mentor-only`, `single-service`) |
| `service` | Target service (empty for full/mentor runs) |
| `status` | Last known status (`running`, `succeeded`, `failed`) |
| `user` | Admin user ID who triggered the run |
| `timestamp` | ISO8601 start time |
| `riskLevel` | `high` for all mctl-agents triggers |
| `message` | Short status message |

---

### `mctl_trigger_implementer`

Triggers Tier 2 implementer agents. The implementer scans
`platform-gitops/agents-state/<service>/proposals/<slug>/.status.yaml` for entries with
`status: accepted`. For each accepted proposal it:

1. Clones the matching `mctlhq/<service>` repo.
2. Runs the per-service implementer sub-agent to make the change.
3. Pushes a `feat/agents-<slug>` branch and opens a PR.
4. Updates `.status.yaml` to `status: implemented` with the PR URL.

**Parameters:**

| Name | Type | Required | Description |
|---|---|---|---|
| `service` | string (enum) | no | Filter to one service. Leave empty to process all services. Same enum as `mctl_trigger_single_service`. |
| `slug` | string | no | Filter to one proposal slug (across services unless `service` is also set). |
| `force` | `"true"` \| `"false"` | no | Retry proposals stuck in `in-progress` (e.g. from a crashed run). Default `"false"`. |

**Cost / duration:** ~$3 per proposal; 1–10 minutes per proposal.

**Returns:** `workflow_name`

**Example — implement one specific proposal:**

```
mctl_trigger_implementer(service="mctl-docs", slug="mcp-agents-tools")
# → { "workflow_name": "mctl-agents-implement-abc34" }
```

---

### Status polling

All trigger tools return a `workflow_name`. Poll for progress with:

```
mctl_get_workflow_status(workflow_name="mctl-agents-daily-abc12")
```

Or check the last few runs at any time:

```
mctl_list_recent_agent_runs()
```

Results also appear as `chore(agents)` commits in the `mctl-gitops` repository under
`platform-gitops/agents-state/`.

---
