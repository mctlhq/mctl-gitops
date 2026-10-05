# Design: issue-127-test-e2e-execution-evidence-producer-pro

## Current state
- `docs/mcp/tools-reference.md` (431 lines) is the MCP tools reference. The section
  `## mctl-agents pipeline controls` (line ~196) contains per-tool subsections; the shepherd one is
  `### mctl_trigger_shepherd` (line ~341). It describes the four-step scan/fix/merge/reject flow,
  the merge-approval gate, the `30 */2 * * *` UTC cron, then `**Parameters:**`, `**Cost / duration:**`,
  `**Concurrency:**`, `**Returns:**` and an example block, closed by a `---` separator before
  `### mctl_trigger_issue`.
- No page in `docs/` mentions execution-evidence envelopes; "evidence" appears only in incident
  docs and in `docs/human-input/` (`evidence:` locator prefix for `context_refs`).
- `docs/public/llms-full.txt` is a tracked, generated concatenation of all docs, produced by
  `scripts/generate-llms-full.ts` via `bun run generate:llms`, which `bun run build` runs before
  `vitepress build docs` (`package.json`). It currently contains the shepherd text around line 3319.

## Proposed solution
Insert one paragraph (one sentence) into the `### mctl_trigger_shepherd` section of
`docs/mcp/tools-reference.md`, directly after the paragraph ending "advance the queue now\" cases."
and before `**Parameters:** none`:

> Each governed agent run, including every shepherd run, records a sealed execution-evidence
> envelope in mctl-api.

Then run `bun run generate:llms` to refresh `docs/public/llms-full.txt`. No config, sidebar, or
theme changes (`.vitepress/config.ts` untouched) since no page is added.

Placement rationale: the paragraph sits with the other behavioral notes (approval gate, cron),
ahead of the structured Parameters/Cost/Returns block, matching the section's existing layout.

## Alternatives
- Add a sentence to the `## mctl-agents pipeline controls` intro instead: covers all agent tools,
  but the issue explicitly asks for the shepherd section. Dropped.
- Add a new `**Evidence:**` field alongside `**Concurrency:**`/`**Returns:**`: more structured, but
  it would invite adding the field to every tool and exceeds the requested one sentence. Dropped.
- A dedicated execution-evidence page: appropriate for a real feature launch, but out of scope
  for a test fixture. Dropped.

## Platform impact
- Migrations: none. Backward compatibility: purely additive docs text.
- Resources: negligible; static site rebuild only.
- Risk: documenting a feature (mctl-agents#199) that may not be generally available, misleading
  readers. Mitigation: the issue states the proposal will be rejected, so nothing ships; if ever
  implemented, gate it on #199 being live.
- Risk: `llms-full.txt` drift if not regenerated. Mitigation: task 2 regenerates it.
