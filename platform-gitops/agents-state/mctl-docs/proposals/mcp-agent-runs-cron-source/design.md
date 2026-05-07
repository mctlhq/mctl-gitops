# Design: mcp-agent-runs-cron-source

## Source commits
- `mctl-api:41b6d4d` — feat(agent-runs): include cron-driven workflows in mctl_list_recent_agent_runs
- `mctl-api:b73a825` — fix(agent-runs): normalize operator timestamp to RFC3339 string

## Current state of documentation
- **Existing page:** `docs/mcp/tools-reference.md`
- The page documents the MCP tool `mctl_list_recent_agent_runs` but describes it as
  returning only operator-initiated runs from the audit log. The response example (if
  one exists) shows items without a `source` field. The merged cron+operator view,
  the `source` discriminator, and the RFC3339 sort semantics are all absent.
- No new page is needed — this is a targeted update to one tool's entry.

## Proposed solution

**Target file:** `docs/mcp/tools-reference.md`

Update the `mctl_list_recent_agent_runs` entry to:

1. **Description paragraph** — replace / augment the current description:
   > Returns a merged list of up to 10 recent agent runs, combining cron-scheduled
   > runs (Argo CronWorkflow-spawned) with operator-initiated runs, sorted by start
   > time descending. Use the `source` field on each item to distinguish how a run
   > was triggered.

2. **Response fields table** — add or extend:
   | Field | Type | Description |
   |---|---|---|
   | `source` | `"operator"` \| `"cron"` | How the run was triggered |
   | `status` | string | Argo phase mapped to audit-log vocabulary |
   | `timestamp` | string (RFC3339) | Start time of the run, UTC |
   | ... | ... | existing fields unchanged |

3. **Example response block** — show a JSON snippet with two items, one of each
   source type. Include realistic field values derived from the commit description.

4. **Version note** — add an admonition or inline note:
   > **version-status: unverified** — see commits `41b6d4d`, `b73a825` (mctl-api,
   > 2026-05-07). Remove this note once the production image bump is confirmed in
   > mctl-gitops.

## Alternatives

1. **New standalone page** `docs/mcp/agent-runs.md` — rejected: the tool is one
   of many in the reference; fragmenting into per-tool pages adds nav complexity
   without proportionate value at the current scale.

2. **Inline comment only** (no example) — rejected: the `source` field and the
   merged-list behavior are non-obvious; a concrete JSON example is the fastest
   way for readers to understand and validate against their own calls.

## Impact
- **VitePress sidebar / nav config:** no change — existing `tools-reference.md` page
  is already in the nav.
- **Diagrams (mermaid):** not needed — the change is a JSON schema update best shown
  as a code block.
- **Documentation versioning:** applies to the current production line (mctl-api
  4.17.x). Remove the version-status note once the image bump is confirmed.
