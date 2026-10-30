# Design: approve-content-digest

## Source commits
- mctl-api:6aeed3b — feat(approve): require the reviewed content digest on direct approve (refs mctl-gitops#2012, #1979)

## Current state of documentation
- Existing page: `docs/guides/gitops-workflows.md` (approval section; see proposals `platform-operations-approval-flow` and `devloop-grant-approval`) does not mention a digest.
- `docs/mcp/tools-reference.md` lists `mctl_trigger_approve` without the new required argument.

## Proposed solution
Add a short subsection "Approving with a content digest" to the approval section of `docs/guides/gitops-workflows.md` and update the `mctl_trigger_approve` row/parameters in `docs/mcp/tools-reference.md`. No sidebar change. Coordinate wording with `devloop-grant-approval` so the two approval paths are described side by side.

## Risks
- Exact script invocation flags: from the tool description `--rev <commit> platform-gitops/agents-state/<service>/proposals/<slug>`. Keep verbatim.
