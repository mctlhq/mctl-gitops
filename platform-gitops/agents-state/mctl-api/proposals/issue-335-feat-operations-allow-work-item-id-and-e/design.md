# Design: issue-335-feat-operations-allow-work-item-id-and-e

## Current state

**The operation definition.** `internal/operations/registry.go` holds every
platform operation in the package-level `builtinOperations` slice, loaded into
a `map[string]Operation` by `NewRegistry()`. The investigate entry (around
line 633) reads:

```go
Name:             "mctl-agents-investigate",
WorkflowTemplate: "mctl-agents-investigate",
RiskLevel:        RiskLow,
AdminOnly:        true,
ModifiesPaths:    []string{"platform-gitops/agents-state/{service}/proposals/{slug}/"},
Parameters: []ParameterDef{
    {Name: "issue_url", Type: "string", Required: true, ...,
     Pattern: `^https://github\.com/mctlhq/[A-Za-z0-9_.-]+/issues/[0-9]+$`},
},
```

`ParameterDef` (registry.go:59) supports `Name`, `Type`, `Required`,
`Default`, `Description`, `Enum`, `Pattern`, `Secret`. The parameter list is
the only declaration of the operation's input surface — there is no separate
schema file, no OpenAPI object for it (the
`/api/v1/operations/{name}/execute` request body in
`internal/openapi/openapi.yaml:1084` is untyped and its documentation table
does not enumerate the `mctl-agents-*` operations), and no gitops-side
mirror inside this repo.

**The submit path.** `Handlers.HandleExecuteOperation`
(`internal/api/handlers_write.go`) runs, in order:

1. `Registry.Get(opName)`; `HandlerOnly` refusal (investigate is not
   handler-only).
2. JSON decode into `map[string]string`, then the authentication check.
3. `Registry.StripUndeclared(op, input)` — drops every key the operation does
   not declare, logs the dropped names at warn level, and does **not** return
   400. The comment at registry.go:141 and handlers_write.go:67 explains why:
   an undeclared key skipped validation entirely yet was still forwarded to
   Argo, which is how `config_patch` became settable from a request body
   (`gitops#997`). This is exactly the mechanism that discards `work_item_id`
   today.
4. `AdminOnly` gate: admin group membership required, tenant sentinel
   `"platform"`.
5. `Registry.ApplyDefaults` then `Registry.ValidateInput`.
   `ValidateInput` (registry.go:109) iterates `op.Parameters` only: a missing
   required value is an error; an **empty or absent** optional value is
   skipped before the `Enum`/`Pattern` checks, so a pattern on an optional
   parameter never fires for a caller that omits it.
6. `Executor.Submit` → `buildArgoParams(params)` (executor.go:370) turns the
   whole map into `spec.arguments.parameters`, against
   `workflowTemplateRef{name: op.WorkflowTemplate, clusterScope: true}` in the
   namespace `WorkflowNamespace` returns — `argo-workflows` for
   `mctl-agents-investigate` (executor.go:108).

**Callers.** The MCP tool `mctl_trigger_issue`
(`internal/mcp/server.go:2995`) POSTs `extractStringParams(args)` to
`/api/v1/operations/mctl-agents-investigate/execute`, or, with
`use_temporal=true`, calls `/api/v1/agents/dev-loop/start`
(`internal/api/handlers_dev_loop.go`), which carries only `issue_url`.

**Consequence.** A submit carrying the resume identifiers is not "rejected
with a 400" as the issue puts it — it is accepted, and the identifiers are
silently dropped at step 3. The observable result is the same (the CWFT never
sees them) but the failure is quieter, which is an argument for landing the
declaration before `#267` starts relying on it.

## Proposed solution

Add two `ParameterDef` entries to the `mctl-agents-investigate` operation and
nothing else:

```go
Parameters: []ParameterDef{
    {Name: "issue_url", Type: "string", Required: true, /* unchanged */},
    // Resume identifiers from the canonical WorkItem (mctlhq/mctl-agents#267,
    // consumed by the CWFT in mctlhq/mctl-gitops#1279). Optional and
    // un-defaulted on purpose: a fabricated ID would correlate a run to work
    // that does not exist. The pattern is a charset guard, not a format
    // contract -- internal/workitems does not exist yet (see
    // docs/work-context-contract.md), so pinning the wi_/we_ prefixes here
    // would couple this repo to an unlanded ID scheme.
    {Name: "work_item_id", Type: "string", Required: false,
     Description: "Optional. Canonical WorkItem id this run belongs to (e.g. wi_<uuid>). Passed through unchanged; mctl-api does not resolve it.",
     Pattern: `^[A-Za-z0-9_.-]{1,128}$`},
    {Name: "execution_id", Type: "string", Required: false,
     Description: "Optional. Execution the investigator is resuming (e.g. we_<uuid>). Passed through unchanged; mctl-api does not resolve it.",
     Pattern: `^[A-Za-z0-9_.-]{1,128}$`},
},
```

Why this is the whole change:

- **Declaration is the gate.** `StripUndeclared` is keyed off
  `op.Parameters`, so declaring the names is precisely what makes them
  survive to `buildArgoParams`. No handler, executor or MCP edit is needed for
  the acceptance criteria.
- **`Required: false` with no `Default`.** `ValidateInput` skips empty values,
  so omitting both parameters is validated exactly as today. Omitting
  `Default` means `ApplyDefaults` fills `""` — an empty Argo argument, not an
  invented ID. This matches the `approver` parameter on
  `mctl-agents-approve`, which deliberately carries no default for the same
  "a manufactured value is worse than an absent one" reason.
- **A loose pattern, not a format contract.** The pattern rejects whitespace,
  quotes, newlines and shell metacharacters — the classes that would be
  unpleasant once a CWFT interpolates the value into a script argument — while
  admitting both `wi_<uuid>`/`we_<uuid>` and engine references such as
  `dev-loop-mctlhq-mctl-api-227`. Because `ValidateInput` short-circuits on
  empty values, adding it costs today's callers nothing.
- **Unchanged everywhere else.** `RiskLow`, `AdminOnly`, `ModifiesPaths`,
  `WorkflowTemplate` and the `argo-workflows` namespace mapping stay as they
  are. The operation's `Description` gains one sentence noting the two
  optional identifiers, because `GET /api/v1/operations` and the MCP
  `mctl_list_operations` surface render it.

The only cross-repo obligation this creates is stated in
`docs/work-context-contract.md` terms: the CWFT in `#1279` must treat an
empty-string `work_item_id`/`execution_id` as absent, because after this
change every investigate submission carries both names, empty when the caller
omitted them.

## Alternatives

1. **Bypass the registry with a dedicated REST handler** (the `HandlerOnly`
   shape used by OpenClaw, which builds params server-side and calls
   `Executor.Submit` directly). Dropped: it duplicates the admin gate, audit
   logging and validation that the generic path already performs, for an
   operation whose only new inputs are two opaque strings. It would also make
   the operation invisible to `/operations/{name}/execute`, breaking the MCP
   tool.
2. **Relax `StripUndeclared` to pass through an allowlisted "correlation"
   prefix** (e.g. anything starting `x_` or `wi_`). Dropped: it reopens the
   hole `gitops#997` closed — the filter's value is that the registry is the
   single enumeration of what can reach Argo — and it makes the accepted
   surface unreadable from the operation definition.
3. **Declare the parameters with a strict `^(wi|we)_[0-9a-f-]{36}$` pattern.**
   Dropped as premature: `internal/workitems` does not exist in this repo,
   `docs/work-context-contract.md` is explicitly a target shape, and a
   mismatch between the minted format and this regex would turn a resume into
   a 400 at the edge — the same class of cross-repo enum drift that
   `TestImplementAndShepherdServiceEnumCoversMctlAgentsServices` was written
   for after the `mctl-design`/`seerrsense` incidents. Tightening later is one
   line; loosening later after a live 400 costs an incident.
4. **Reject undeclared parameters with 400 instead of dropping them**, to make
   the issue's third acceptance bullet literally true. Dropped: the comment at
   handlers_write.go:78 makes the drop deliberate (a 400 would fail closed on
   any live caller sending an extra field), and the bullet is satisfied in
   substance — an undeclared parameter still never reaches Argo.

## Platform impact

- **Migrations:** none. The registry is compiled-in Go data; there is no
  database, no gitops manifest and no ConfigMap backing it.
- **Backward compatibility:** additive and optional. Existing callers
  (`mctl_trigger_issue`, the Temporal dev-loop start path, manual `curl`)
  submit the same bodies and get the same behaviour. `GET /api/v1/operations`
  and `mctl_get_operation` responses gain two entries in the investigate
  parameter list, which is the intended, self-documenting effect.
- **Resource impact:** two extra workflow arguments per submission. Nil.
- **Risk: the CWFT does not declare the parameters yet.** After this merges,
  every investigate submission carries two extra workflow-level arguments
  while `mctl-gitops#1279` is unlanded. Argo merges workflow-level
  `arguments.parameters` with the referenced template's; a name no template
  references is carried and ignored. *Mitigation:* task 5 is one live submit
  of `mctl_trigger_issue` after deploy, confirming the workflow reaches
  `Running`; if it does not, the revert is a one-commit rollback and `#1279`
  lands first instead.
- **Risk: an empty string overriding a CWFT-side default.** If `#1279`
  declares `work_item_id` with a non-empty Argo default, the explicit `""`
  from `ApplyDefaults` wins. *Mitigation:* stated as a contract in this design
  and in `requirements.md`; the CWFT must branch on emptiness, not rely on its
  default.
- **Risk: silent drop if this is reverted after `#267` ships.** Rolling back
  would not fail a resume submit — it would strip the identifiers and run a
  non-resumed investigation, visible only as a warn line
  (`ignoring undeclared operation parameters`). *Mitigation:* noted in the
  rollback section of `tasks.md`; alert on that log line if the rollback is
  ever exercised post-`#267`.
- **Security:** the parameters are inert in mctl-api and never reach a shell
  here; the pattern keeps the forwarded value in a conservative charset. The
  operation stays `AdminOnly`, so the caller set is unchanged. Neither
  parameter is `Secret`, so both appear in the audit entry and the
  `submitting workflow` log line — correct, since correlation IDs are exactly
  what one wants in an audit trail.
