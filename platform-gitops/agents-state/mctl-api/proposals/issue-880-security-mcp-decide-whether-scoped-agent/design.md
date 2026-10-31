# Design: issue-880-security-mcp-decide-whether-scoped-agent

## Current state

Agent run scopes live in `internal/auth/agent_scope.go`:

- `AgentScope` has `Routes []AgentScopeRoute` (allow-only) and
  `Tool func(name string) bool`. `Allows(req)` walks `Routes` and returns true
  on the first match. There is no deny list.
- `IsReadTool(name)` returns true for any tool whose bare name starts with
  `get_`, `list_`, `read_`, `search_` or `describe_`, or that equals
  `whoami`, `incident_summary` or `resolve_agent`.
  `TestReadToolsAreRecordedReadOnly` (`internal/mcp/agent_scope_test.go`)
  holds this rule to the tools' read-only annotations.
- The `investigate` scope (`AgentScopeInvestigate`, agent
  `issue-investigator`) has `Tool: IsReadTool`, so it admits
  `mctl_list_work_item_intents`, which `internal/mcp/workitems.go` registers
  and which maps to `GET /api/v1/work-items/{id}/intents`. Its routes include
  `AgentScopeRoute{Method: GET, BindWorkItem: true, Pattern: ^/api/v1/work-items/([^/]+)(/.*)?$}`.
  That route admits the run's own `/intents` and `/intents/{intent_id}`
  (handlers `ListWorkItemIntents` / `GetWorkItemIntent`,
  `internal/api/handlers_work_item_intents.go`, routes at
  `internal/api/router.go:881-882`).
- The `support` scope's tool predicate is an explicit allowlist
  (`supportTools`). It has no work-item route, so it already refuses intents
  on both layers.
- Enforcement points:
  - REST: `Handlers.agentScopeGate` (`internal/api/agent_scope_gate.go`) calls
    `scope.Allows(...)`. On a refusal it answers 403 `agent_scope_denied` and
    writes an `agent_scope.denied` audit row. In shadow mode it calls
    `scope.AllowsRoute` and only counts the decision.
  - MCP: `Server.agentScopeMiddleware` (`internal/mcp/agent_scope.go`) calls
    `scope.AllowsToolCall`, which calls `AllowsTool`, which calls `Tool`. The
    shadow branch calls `scope.AllowsTool`.
  - An admitted MCP tool's loopback REST call comes back through the REST
    gate with the same token, so the two layers are independent checks.
- Docs: `docs/work-context-contract.md` says intents are readable "by whoever
  can see the item" and lists `mctl_list_work_item_intents` as disabled on
  the shared portal. `docs/portal-allowlist.json` has it at
  `"enabled": false`.
- Tests that pin today's behaviour: `TestInvestigateScope_Routes`
  (`internal/auth/agent_scope_test.go`),
  `TestAgentScopeGate_ScopedRunReachesOnlyItsScope`, which expects 6
  `agent_scope.denied` rows (`internal/api/agent_scope_gate_test.go`), and
  `TestAgentScopeMiddleware_ScopedRunCallsOnlyItsTools`
  (`internal/mcp/agent_scope_test.go`).

Deployed state checked:

- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`:
  - `MCTL_RUN_TOKEN_MODE: enforce`. The pod's MCP connection and its own
    work-item REST calls use the scoped run token, and the container has no
    `MCTL_TOKEN`.
  - `WORK_ITEM_INTENT_SOURCE: "on"`. The investigator reads
    `GET /api/v1/work-items/{id}/intents` and seals intents into the
    ContextSnapshot. A referenced intent it cannot resolve fails the run
    (`intent-unresolved`). The comment documents `"off"` as the byte-neutral
    default and the rollback.
  - `ISSUE_INVESTIGATOR_CONTEXT_MODE: "shadow"`. The prompt is byte-identical,
    so intents reach only the sealed snapshot, not the model's prompt.
  - The template says only this template reads intents; the Temporal workers
    do no context assembly.
- `mctl_get_service_config(team=admins, service=mctl-api)` (called by the
  earlier run of this proposal, not repeated here): error "service not
  found". The deployed mctl-api version and tenant were not observed.
  This is recorded under Open questions in requirements.md, not treated as
  absent.
- `$MCTL_GITOPS_ROOT/services/*/mctl-api`: no such directory exists in this
  checkout, so mctl-api's own values were not observed here.

## Proposed solution

Implement option 2 as the owner decided: an explicit, per-scope exclusion on
both layers, checked before the allow lists.

1. `internal/auth/agent_scope.go`:
   - Add a field to `AgentScope`:
     `Deny []AgentScopeRoute // checked before Routes; a match refuses whatever Routes admit. An empty Method matches every method.`
   - In `Allows`, before the `Routes` loop (and after the BoundTenant query
     checks), return false when any `Deny` entry's method matches (or is
     empty) and its `Pattern` matches `req.Path`. Deny entries ignore
     `BindWorkItem` and the other bindings: they refuse the path for every
     work item, the run's own included.
   - Add a named, documented set:
     ```go
     // agentDeniedTools are MCP tools (bare names) no agent scope may call,
     // even though IsReadTool classifies them as reads: raw WorkItem intents
     // are human-authored instructions (mctl-api#880, owner decision).
     var agentDeniedTools = map[string]bool{"list_work_item_intents": true}
     // agentDeniedRoutes mirror agentDeniedTools on REST.
     var agentDeniedRoutes = []AgentScopeRoute{
         {Pattern: regexp.MustCompile(`^/api/v1/work-items/[^/]+/intents(/.*)?$`)},
     }
     ```
   - Make `AllowsTool` return false when
     `agentDeniedTools[strings.TrimPrefix(name, "mctl_")]` before it consults
     `Tool`. Doing this centrally rather than in the investigate `Tool`
     closure means every current and future scope inherits it. The `support`
     allowlist already excludes the tool, so this is defence in depth there.
   - Set `Deny: agentDeniedRoutes` on both `investigate` and `support`. For
     `support` it is redundant today but keeps the rule scope-independent.
     Optionally apply it in `Allows` for every scope instead of per-scope;
     the implementer may choose either, as long as both scopes are covered
     and a test proves it.
   - RE2 has no negative lookahead, so carving `/intents` out of the bound
     regex is not practical. A separate deny list is the clean form.
2. No change to `internal/api/agent_scope_gate.go` or
   `internal/mcp/agent_scope.go` is required. Both already call
   `Allows`/`AllowsRoute`/`AllowsToolCall`/`AllowsTool`, so enforce and shadow
   pick up the exclusion. Refusals keep the existing 403 / tool error with
   `agent_scope_denied`, the audit row and the metric.
3. Docs:
   - `docs/work-context-contract.md`, `WorkItemIntent` bullet and the MCP
     surface section: add "Scoped agent run tokens (any `AgentScope`) are
     refused raw intent reads on MCP (`mctl_list_work_item_intents`) and REST
     (`GET /work-items/{id}/intents[/...]`), their own work item included:
     403 / tool error `agent_scope_denied` (mctl-api#880)."
   - `docs/portal-allowlist.json`: keep `"enabled": false` and extend the
     `reason` to cite mctl-api#880. Do this only if no test pins the reason
     text; otherwise leave the file unchanged.
4. Deploy prerequisite (outside this repo, owner decision
   hir-6053c71d87283c69): the mctl-gitops investigate template must set
   `WORK_ITEM_INTENT_SOURCE: "off"` before an mctl-api release carrying this
   change reaches the cluster. Otherwise runs whose execution request
   references an `intent_id` would fail with `intent-unresolved`. The
   template documents `"off"` as the byte-neutral default, and with
   `ISSUE_INVESTIGATOR_CONTEXT_MODE: "shadow"` the prompt is unchanged, so
   the only effect is that newly sealed ContextSnapshots carry no intents.
   The owner accepted that loss. The PR description must state this ordering
   and link the gitops change.
5. `docs/work-context-contract.md` also records the consequence: with scoped
   run tokens refused intents, the investigator's intent source must stay
   `off`, and its snapshots do not include intents.

Path-matching notes: the gate matches on `r.URL.Path` (decoded). chi routes
on `RawPath` when one is set, so an encoded variant such as `/%69ntents` does
not reach the intents handler. Trailing-slash and sub-path variants are
covered by `(/.*)?`. HEAD is already refused because no allow route admits
it, and the deny entry with an empty Method also covers it.

## Alternatives

- Option 1, accept and document. Rejected by the owner. It would also leave
  the model and its tools reading human-authored instructions with a token
  minted for autonomous use.
- Narrow only the investigate `Tool` closure
  (`IsReadTool(n) && n != "list_work_item_intents"`) and rewrite the bound
  REST regex as an enumerated allowlist of sub-paths (`executions`,
  `snapshots`, `events`, ...). Dropped: it scatters the rule in one scope.
  The enumerated regex would silently close future sub-routes the scope
  needs, or need regex surgery each time. A future scope built on
  `IsReadTool` would reopen the hole.
- Rename the tool so `IsReadTool` stops classifying it as a read. Dropped: it
  breaks the policy-checkpoint naming rule mirrored from mctl-agents and the
  annotation test, and it is an API break for owner OAuth clients.
- Keep intents in snapshots by giving mctl-agents context assembly a
  credential the model cannot reach (a non-scoped service token used only by
  the orchestrator). Dropped by the owner (hir-6053c71d87283c69): it
  reintroduces a static credential into the investigate pod, which
  `MCTL_RUN_TOKEN_MODE: enforce` removed, and it needs an mctl-agents change.
- Gate intents by principal type inside `ListWorkItemIntents` /
  `GetWorkItemIntent`. Dropped: it splits scope policy between the gate and
  the handlers, the shadow observe stage would not see it, and the scope file
  stops being the single place that answers "what can a run reach".

## Platform impact

- Migrations: none. No schema or config change in mctl-api.
- Backward compatibility: non-agent principals and unscoped run tokens are
  unchanged. Scoped investigate runs lose intent reads by design. The known
  consumer is the investigator's context assembly
  (`WORK_ITEM_INTENT_SOURCE: "on"`). Risk: `intent-unresolved` run failures
  if mctl-api ships first. Mitigation: the gitops flip to `"off"` must land
  first (tasks.md task 1). The prompt is unaffected because context mode is
  `shadow`; new snapshots lose intents, which the owner accepted. A later
  flip back to `"on"` while the exclusion is deployed would cause
  `intent-unresolved` failures, so the template comment should cite
  mctl-api#880.
- Observability: refusals show as `verdict="deny"` in
  `mctl_agent_scope_decisions_total{scope="investigate"}` and as
  `agent_scope.denied` audit rows. After the release, a non-zero rate on
  `/intents` means a consumer was missed.
- Resource impact: one extra short slice scan per scoped request. Negligible.
- Residual risk: snapshots sealed while intents were on still embed intent
  text and stay readable by later runs on the same work item through the
  bound snapshot routes until the retention sweeper (#353) deletes them on
  the intent-text schedule. Recorded as an open question, not addressed
  here.
- Rollback: revert the commit. No data is touched.
