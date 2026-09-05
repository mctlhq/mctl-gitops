# Design: platform-operations-approval-flow

## Source commits

- `mctl-api:1c6a746` — feat(operations): add mctl-agents-approve operation
- `mctl-api:20db091` — feat(operations): add the mctl-agents-reconcile operation
- `mctl-api:3dee7e9` — feat(agents): expose durable DevLoop approve endpoint (issue-228)

## Current state of documentation

- **Existing page:** `docs/mcp/tools-reference.md` — "MCP Tools Reference"
  - Documents individual MCP tools grouped by category. Has no concept of a separate
    "platform operations" catalog (`mctl_list_operations` / `mctl_get_operation`), and no
    entry for `mctl_approve_dev_loop`.
- **Existing page:** `docs/guides/gitops-workflows.md` — "GitOps Workflows"
  - Describes the push-to-main → auto-deploy contract and repository structure. Has no
    section on how an `mctl-agents` proposal gets approved after a PR is opened — that
    whole lifecycle (proposed → accepted → implemented, or the durable DevLoop signal
    path) is currently undocumented anywhere on docs.mctl.ai.
- **Page is missing:** no `docs/reference/operations.md` exists. The "platform
  operations" surface (as distinct from individual MCP tools) is not documented at all,
  even though it is confirmed live in production (`mctl_list_operations` returns
  `mctl-agents-approve` and `mctl-agents-reconcile` today, per the 2026-09-05 inbox scan).

## Proposed solution

1. **Create `docs/reference/operations.md`** — a new reference page documenting:
   - What a "platform operation" is and how it differs from an individual MCP tool
     (an operation is a named, audited admin-level action; MCP tools are the callable
     interface, and some tools trigger operations while others are direct actions).
   - How to discover operations: `mctl_list_operations` (list all) and
     `mctl_get_operation` (inspect one by name).
   - A table of currently known operations relevant to the agent-proposal lifecycle:
     `mctl-agents-approve`, `mctl-agents-reconcile` (plus a forward-reference to
     `mctl-agents-run` / `mctl-agents-implement`, already touched on in
     `docs/mcp/tools-reference.md` per the `mcp-agents-tools` proposal).
   - Per-operation detail: what each does, its effect on `.status.yaml`, and an example
     `mctl_get_operation` call.

2. **Add an "Approving agent proposals" subsection to `docs/guides/gitops-workflows.md`**
   — placed after the existing proposal/PR lifecycle content, contrasting:
   - The **durable DevLoop path** (`mctl_approve_dev_loop`): sends a Temporal signal to
     a running `DevLoopWorkflow` execution. Durable — survives worker restarts — and
     scoped to workflows that are still alive.
   - The **direct GitOps-file path** (`mctl-agents-approve` operation): mutates
     `.status.yaml` from `proposed` to `accepted` directly in the `mctl-gitops`
     repository. Works regardless of whether a DevLoop workflow execution is still
     running, but does not signal any in-flight workflow.
   - A short decision guide: use the durable signal path while the DevLoop workflow is
     still live (check with the new `describe` endpoint from the
     `dev-loop-describe-endpoint` proposal); fall back to the direct `.status.yaml`
     mutation once the workflow has completed or if you need to approve without a live
     execution.

3. **Add a cross-link from `docs/mcp/tools-reference.md`** in the admin-tools area,
   pointing to `docs/reference/operations.md` for the full operations catalog, and a
   one-line pointer to the new "Approving agent proposals" subsection.

`.vitepress/config` sidebar/nav needs one addition: `operations` under the existing
`reference/` group (the group already exists, containing `faq`, `glossary`,
`troubleshooting`).

## Alternatives

1. **Fold the operations catalog into `docs/mcp/tools-reference.md` as a subsection**
   instead of a standalone `docs/reference/operations.md` page. Dropped: operations and
   MCP tools are related but distinct concepts (not every operation has a 1:1 MCP tool
   wrapper, and the catalog is expected to grow independently of the tool list per the
   in-flight `mctl_trigger_reconcile`/`mctl_trigger_approve` wrappers noted in the
   2026-09-05 inbox). A standalone reference page scales better and matches the existing
   `docs/reference/` pattern (faq, glossary, troubleshooting are all standalone).

2. **Put the durable-vs-direct approval explainer only in `docs/reference/operations.md`**
   rather than also in `docs/guides/gitops-workflows.md`. Dropped: a reader following the
   GitOps proposal lifecycle in the guides section would not think to look in
   `docs/reference/` for "how do I approve this PR," and the author-flagged confusion
   risk (the `mctl_approve_dev_loop` tool docstring explicitly warns against mixing up
   the two paths) justifies covering it in both places, cross-linked.

## Impact

- **Sidebar / nav config:** yes — add `operations` entry under the `reference/` sidebar
  group in `.vitepress/config.{js,ts}`.
- **Diagrams (mermaid):** a small flowchart is warranted for the "Approving agent
  proposals" subsection (decision: durable signal vs. direct file mutation).
- **Documentation versioning:** applies to mctl-api 4.37.0 and later. All three source
  commits are confirmed shipped (verified via `mctl_list_operations` showing
  `mctl-agents-approve` / `mctl-agents-reconcile` live, and via the
  `bump admins/mctl-api to 4.37.0` commit `3441a91` in mctl-gitops, per the 2026-09-05
  inbox). No version-gating language needed in the page body.
