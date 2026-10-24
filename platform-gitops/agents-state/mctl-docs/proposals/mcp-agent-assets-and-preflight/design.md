# Design: mcp-agent-assets-and-preflight

## Source commits
- mctl-api:ba48fc4 — feat(agents): issue-748 read-only agent asset index and preflight
- mctl-api:72086aa, 9e1eaa1 — review fixes for the same issue

## Current state of documentation
- `docs/mcp/tools-reference.md` has no entry for either tool. Proposal `mcp-agents-tools` predates them.

## Proposed solution
Add an "Agent platform (admin)" subsection to `docs/mcp/tools-reference.md` with the two tools. Place it next to existing agent registry tools if present. No sidebar change.

## Risks
- Response shape beyond what tool descriptions state is not verified; the content avoids field-level claims. <TODO: confirm with author the reverse-reference field names if wanted>
