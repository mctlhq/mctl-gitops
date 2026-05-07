# Proposed content: mcp-agent-runs-cron-source

> **Apply to:** `mctl-docs/docs/mcp/tools-reference.md` (UPDATE)
> **Source:** mctl-api@41b6d4d, mctl-api@b73a825
> **version-status: unverified** — commits dated 2026-05-07, not yet confirmed in a
> mctl-gitops prod image bump. Remove the `::: warning` admonition below once confirmed.

---

Find the existing `mctl_list_recent_agent_runs` entry in `docs/mcp/tools-reference.md`
and apply the following diff.

### BEFORE (current state — operator-only description)

```markdown
### `mctl_list_recent_agent_runs`

Returns the most recent agent runs recorded in the audit log.

**Parameters:** none

**Returns:** Array of run objects with fields:
- `id` — run identifier
- `status` — run status (`running`, `completed`, `failed`)
- `timestamp` — start time (RFC3339)
- `summary` — short description of what was run
```

### AFTER (updated — merged cron+operator view with `source` field)

```markdown
### `mctl_list_recent_agent_runs`

Returns a merged list of up to 10 recent agent runs, combining **cron-scheduled runs**
(Argo CronWorkflow-spawned: `mctl-agents-daily`, `mctl-agents-shepherd`,
`mctl-agents-implement`) with **operator-triggered runs** (REST `POST /api/v1/runs`).
The list is sorted by start time descending (most recent first).

Use the `source` field on each item to distinguish how a run was triggered.

::: warning version-status: unverified
This merged view was introduced in mctl-api commits `41b6d4d` and `b73a825` (2026-05-07).
Remove this note once the production image bump is confirmed in mctl-gitops.
:::

**Parameters:** none

**Returns:** Array of up to 10 run objects:

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique run identifier |
| `source` | `"operator"` \| `"cron"` | How the run was triggered |
| `status` | string | Run phase: `running`, `completed`, `failed`, `error` |
| `timestamp` | string (RFC3339, UTC) | Start time of the run |
| `summary` | string | Short description of what was run |

**Example response:**

```json
[
  {
    "id": "mctl-agents-daily-2026-05-07t06-00-00",
    "source": "cron",
    "status": "completed",
    "timestamp": "2026-05-07T06:00:12Z",
    "summary": "mctl-agents-daily cron run — 3 proposals processed"
  },
  {
    "id": "mctl-agents-daily-2026-05-06t06-00-00",
    "source": "cron",
    "status": "completed",
    "timestamp": "2026-05-06T06:00:09Z",
    "summary": "mctl-agents-daily cron run — 1 proposal processed"
  },
  {
    "id": "op-7f3a92c1",
    "source": "operator",
    "status": "completed",
    "timestamp": "2026-05-05T14:23:41Z",
    "summary": "Manual trigger: implement mcp-shepherd-tool"
  }
]
```

> **Note:** If the Argo cluster API is unavailable, the tool degrades gracefully
> and returns the operator-only audit view with a warning in the response metadata.
```

---

> The example field values above (`id`, `summary`) use plausible formats derived from
> the commit description. Confirm exact field names and `id` format with the author of
> `41b6d4d` before merging. Add `<TODO: confirm id format with author of 41b6d4d>` if
> uncertain.
