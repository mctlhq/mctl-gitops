# Document the platform operations catalog and the two approval paths for agent proposals

## Context

Between 2026-08-29 and 2026-09-02, `mctl-api` shipped two new first-class **platform
operations** — `mctl-agents-approve` (commit `1c6a746`) and `mctl-agents-reconcile`
(commit `20db091`) — plus a durable, Temporal-signal-backed approve path for DevLoop
workflow runs exposed as the `mctl_approve_dev_loop` MCP tool (commit `3dee7e9`). All
three are confirmed live in production (mctl-api 4.37.0): `mctl-agents-approve` and
`mctl-agents-reconcile` already appear in `mctl_list_operations` output today.

`mctl-agents-approve` lets an admin flip a proposal's `.status.yaml` from
`proposed` to `accepted` as a tracked platform operation instead of a manual GitOps
edit. `mctl-agents-reconcile` reconciles GitHub PR state (merged / closed / needs-triage)
onto a proposal's `.status.yaml` without invoking a model. `mctl_approve_dev_loop` is a
different, durable mechanism: it sends a Temporal signal to a running DevLoopWorkflow
execution rather than touching a GitOps file directly. The tool description for
`mctl_approve_dev_loop` explicitly warns callers not to confuse this durable-signal path
with the direct `.status.yaml` mutation performed by the `mctl-agents-approve` operation —
a strong, author-flagged signal that this distinction needs a human-readable explainer,
not just an in-code warning. Today, docs.mctl.ai has no page describing the "platform
operations" concept (`mctl_list_operations` / `mctl_get_operation`) at all; only
individual MCP tools are covered, in `docs/mcp/tools-reference.md`.

## User stories

- AS a **platform admin** I WANT a reference page listing every platform operation
  (not just individual MCP tools) SO THAT I can discover what admin-level actions exist
  without reading `mctl-api` source.
- AS a **platform admin** I WANT to understand the difference between the durable
  DevLoop Temporal-signal approve path and the direct GitOps-file `.status.yaml`
  mutation path SO THAT I approve an agent proposal the correct way for the situation
  I am in and do not corrupt workflow state.
- AS a **developer** reading `docs/guides/gitops-workflows.md` I WANT a section that
  explains how agent proposals get approved SO THAT I understand what happens after
  `mctl-agents` opens a proposal PR.
- AS a **platform admin** I WANT `docs/mcp/tools-reference.md` to point me to the
  operations catalog page SO THAT I don't have to guess which document covers
  "operations" versus "MCP tools."

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/reference/operations.md` THE SYSTEM SHALL show what a
  "platform operation" is, how it differs from an individual MCP tool, and how to list
  and inspect operations via `mctl_list_operations` and `mctl_get_operation`.
- WHEN the operations catalog page describes `mctl-agents-approve` THE SYSTEM SHALL
  state that it mutates a proposal's `.status.yaml` from `proposed` to `accepted`
  directly in the GitOps repository.
- WHEN the operations catalog page describes `mctl-agents-reconcile` THE SYSTEM SHALL
  state that it reconciles GitHub PR state (merged / closed / needs-triage) onto a
  proposal's `.status.yaml` without invoking a model.
- WHEN a reader opens `docs/guides/gitops-workflows.md` THE SYSTEM SHALL show a
  dedicated "Approving agent proposals" subsection comparing the durable DevLoop
  `mctl_approve_dev_loop` Temporal-signal path against the `mctl-agents-approve`
  gitops-file operation, including when to use each.
- IF a reader wants to call `mctl_list_operations`, `mctl_get_operation`, or
  `mctl_approve_dev_loop` THEN THE SYSTEM SHALL provide a runnable example call and its
  expected shape.
- WHEN a reader opens `docs/mcp/tools-reference.md` THE SYSTEM SHALL show a cross-link
  to the new `docs/reference/operations.md` page from the section listing admin-level
  tools.
- WHILE the exact field shape of `mctl_list_operations` / `mctl_get_operation` responses
  and the exact `mctl_approve_dev_loop` parameter list are not independently confirmed
  from source in this pass THE SYSTEM SHALL mark those specific fields with
  `<TODO: confirm with author of <sha>>` rather than inventing them.

## Out of scope

- Documenting the internal Temporal workflow/activity implementation of DevLoopWorkflow
  (belongs in `mctl-agents`' own internal docs, not docs.mctl.ai).
- The in-flight `mctl_trigger_reconcile` / `mctl_trigger_approve` MCP tool wrappers
  (commit `04fec23`) — not yet released past mctl-api 4.37.0; explicitly out of scope
  per the "do not document in-flight code" rule. Revisit once shipped.
- A step-by-step tutorial for writing or reviewing a proposal PR (separate how-to guide,
  not part of this proposal).
- Localisation / i18n.
