# Design: mcp-shepherd-tool

## Source commits

- `mctl-api:f29adbd` — feat(mcp): add mctl_trigger_shepherd tool
- `mctl-api:e1fbe3f` — fix(mcp): include mctl-agents in single-service and implementer enums
- `mctl-gitops:6c0ba41` — feat(workflows): un-suspend mctl-agents-shepherd CronWorkflow
  (confirms shepherd is in production in mctl-api 4.17.0)

## Current state of documentation

- **Existing page:** `docs/mcp/tools-reference.md` — "MCP Tools Reference"
  - Does not contain the "mctl-agents pipeline controls" section (that section is proposed
    but not yet implemented by `proposals/mcp-agents-tools/`).
  - Has no entry for `mctl_trigger_shepherd`.

- **Dependency — existing unimplemented proposal:** `proposals/mcp-agents-tools/`
  - Proposes a "mctl-agents pipeline controls" section covering **five** tools.
  - The `proposed-content.md` in that proposal lists 7 `service` enum values for
    `mctl_trigger_single_service` (missing `mctl-agents` as the 8th) and uses the phrase
    "five tools" throughout.
  - The `tasks.md` test T3 explicitly says "7 repos: mctl-web, mctl-openclaw, mctl-docs,
    mctl-api, mctl-portal, mctl-agent, mctl-gitops" — this is now stale (8 repos).

## Proposed solution

### Option A (chosen): amend `mcp-agents-tools` + add shepherd entry

1. **Update `proposals/mcp-agents-tools/proposed-content.md`** (editorial, no new file):
   - Change "five tools" → "six tools" in the intro paragraph.
   - Add `mctl_trigger_shepherd` row to the tool summary table.
   - Add `mctl-agents` to the `service` enum row for `mctl_trigger_single_service` and
     `mctl_trigger_implementer`.
   - Append a `### mctl_trigger_shepherd` detail block (content from `proposed-content.md`
     in this proposal).

2. **Update `proposals/mcp-agents-tools/tasks.md`** test T3:
   - Change "7 repos" → "8 repos" and add `mctl-agents` to the list.
   - Add a new T5: confirm mctl-api ≥ 4.17.0 in production for the shepherd entry.

3. **Apply the combined content to `docs/mcp/tools-reference.md`** as part of the
   `mcp-agents-tools` implementation (this proposal's `proposed-content.md` supplies
   the shepherd detail block ready to paste in).

The implementer does **not** need to create a new page or change `.vitepress/config`.

### Option B: standalone shepherd page `docs/mcp/shepherd.md`

Dropped — the shepherd tool is one of six tightly related pipeline-control tools.
Splitting it out would fragment what users naturally want to read together.

### Option C: separate `mcp-agents-tools-v2` proposal that rewrites the entire section

Dropped — unnecessary overhead. The delta is small (one new tool block + enum tweak);
an in-place amendment of the existing proposed-content is the right scope.

## Impact

- **Sidebar / nav config:** no change required.
- **Mermaid diagrams:** not required for the tool reference. A future "How the agents
  pipeline works" how-to guide could add a Tier 1 → Tier 2 → Tier 3 flow diagram.
- **Documentation versioning:** applies to mctl-api 4.17.0 (`f29adbd`). The shepherd
  CronWorkflow is already un-suspended in production.
- **Dependency on `mcp-agents-tools`:** this proposal should be implemented together
  with (or immediately after) `mcp-agents-tools`. If `mcp-agents-tools` is already
  applied, the implementer only needs to insert the shepherd block and fix the enum rows.
