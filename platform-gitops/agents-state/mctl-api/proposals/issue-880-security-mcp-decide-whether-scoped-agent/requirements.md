# Refuse raw WorkItem intent reads to scoped agent run tokens (MCP tool and REST routes)

## Context

`auth.IsReadTool` (`internal/auth/agent_scope.go`) treats every `list_` tool
as a read, and the `investigate` scope uses `IsReadTool` as its tool
predicate. A scoped issue-investigator run token can therefore call
`mctl_list_work_item_intents`. The same scope also admits
`GET ^/api/v1/work-items/([^/]+)(/.*)?$` bound to the run's own work item,
which covers `GET /api/v1/work-items/{id}/intents` and
`GET /api/v1/work-items/{id}/intents/{intent_id}`. Raw intents are
human-authored instructions and are more sensitive than state metadata. The
issue asks the owner to choose between accepting this (option 1) and
excluding it (option 2).

The owner chose option 2 (answer to clarification hir-5ac263d9fe137575):
scoped agent runs are refused raw intents, and both the MCP tool and the REST
`/intents` routes are closed, including for the run's own work item. One
deployed dependency matters here. The mctl-gitops investigate template
(`argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`) sets
`WORK_ITEM_INTENT_SOURCE: "on"` and `MCTL_RUN_TOKEN_MODE: enforce`, so the
investigator pod already reads `GET /api/v1/work-items/{id}/intents` with its
scoped run token to seal intents into its ContextSnapshot. A referenced intent
it cannot resolve fails the run (`intent-unresolved`). That consumer has to be
switched off, or moved to another credential, before this change is deployed.

## User stories

- AS the platform owner I WANT scoped agent run tokens to be unable to read
  raw WorkItem intent text SO THAT human-authored instructions reach only
  human principals and surfaces that can see the item, never an autonomous
  run's model or tools.
- AS a security reviewer I WANT a test that fails if the exclusion is removed
  SO THAT `IsReadTool`'s naming rule cannot widen the investigate scope back
  to intents without notice.
- AS an owner using OAuth (Claude or ChatGPT, mctl-agents#909) I WANT
  `mctl_list_work_item_intents` and the REST intent reads to keep working for
  my own identity SO THAT the manual cross-client proof is not affected.

## Acceptance criteria (EARS)

- WHEN a principal holding a run token with the `investigate` scope calls the
  MCP tool `mctl_list_work_item_intents` (with or without the `mctl_` prefix)
  THE SYSTEM SHALL refuse it with an `agent_scope_denied` tool error and SHALL
  NOT run the tool handler, even when `work_item_id` is the run's own work item.
- WHEN a principal holding a run token with any agent scope sends
  `GET /api/v1/work-items/{id}/intents` or
  `GET /api/v1/work-items/{id}/intents/{intent_id}` (or any other path under
  `/intents`) THE SYSTEM SHALL answer 403 with code `agent_scope_denied` and
  write one `agent_scope.denied` audit row, even when `{id}` is the run's own
  work item.
- WHILE an agent scope lists a route in its exclusion list THE SYSTEM SHALL
  refuse a matching request whatever its allow routes admit, so a broader
  allow route (such as the bound `^/api/v1/work-items/([^/]+)(/.*)?$`) cannot
  re-admit it.
- WHEN a scoped investigate run reads its own work item, executions,
  execution requests, events or snapshots THE SYSTEM SHALL keep admitting
  them as today.
- WHEN a scoped investigate run calls any other read tool admitted today
  (for example `mctl_get_work_item`, `mctl_list_work_item_snapshots`)
  THE SYSTEM SHALL keep admitting it.
- WHEN an unscoped run token, an owner OAuth identity, a human GitHub/Dex
  identity or a surface relaying for its linked human reads intents THE SYSTEM
  SHALL behave exactly as before this change.
- WHEN a direct service principal shadows the `investigate` scope (header
  `X-Mctl-Agent-Scope-Shadow`) and reads intents or calls
  `mctl_list_work_item_intents` THE SYSTEM SHALL count the decision as `deny`
  in `mctl_agent_scope_decisions_total` and SHALL NOT refuse the request.
- IF the exclusion entry for `mctl_list_work_item_intents` or for the
  `/intents` route is removed THEN THE SYSTEM's unit tests SHALL fail.
- WHILE the exclusion is in place THE SYSTEM SHALL keep
  `mctl_list_work_item_intents` at `enabled: false` in
  `docs/portal-allowlist.json`.
- THE SYSTEM's documentation (`docs/work-context-contract.md`) SHALL state that
  scoped agent run tokens are refused raw intent reads on both MCP and REST,
  for their own work item too.

## Out of scope

- Changing `IsReadTool` or the `readVerbs` naming rule itself; the exclusion
  is scope-specific.
- Changing which non-agent principals may read intents, or enabling the tool
  on the shared portal.
- Closing ContextSnapshot reads (`GET /work-items/{id}/snapshots[...]`,
  `GET /work-items/{id}/executions/{execution_id}/snapshot`,
  `mctl_list_work_item_snapshots`). Sealed snapshot bytes can embed intent
  text, but the owner's decision named only the intent tool and routes (see
  Open questions).
- The mctl-gitops change that turns off `WORK_ITEM_INTENT_SOURCE` for the
  investigate template, and any mctl-agents change giving context assembly a
  different credential. These live in other repositories. This proposal
  records the first as a hard deploy prerequisite (tasks.md task 1).

## Open questions

- Deploy ordering conflict with a live consumer. The investigate template
  reads intents with the scoped run token (`WORK_ITEM_INTENT_SOURCE: "on"`,
  `MCTL_RUN_TOKEN_MODE: enforce`). After this change those reads get 403.
  That would put `intent-unresolved` failures on runs whose execution request
  names an `intent_id`. Proposed interpretation: set `WORK_ITEM_INTENT_SOURCE`
  to `"off"` in mctl-gitops first. The template documents `"off"` as the
  byte-neutral default. With `ISSUE_INVESTIGATOR_CONTEXT_MODE: "shadow"` the
  prompt does not change, so only the sealed snapshot loses intents. If the
  owner instead wants intents in snapshots, mctl-agents needs a credential the
  model cannot reach. A clarification draft asks which way to go.
- Snapshots may already contain intent text. Snapshots sealed while
  `WORK_ITEM_INTENT_SOURCE` was `"on"` embed intents. A later run on the same
  work item can still read them through the bound snapshot routes. Whether
  snapshot reads should also be closed, or only new snapshots kept free of
  intents, is not settled.
- `mctl_get_service_config admins/mctl-api` returned "service not found", so
  this run did not observe the deployed mctl-api version or tenant. The
  investigate template's comments reference mctl-api 4.58.0 (intents route)
  and 4.117.0 (run-token enforce).
