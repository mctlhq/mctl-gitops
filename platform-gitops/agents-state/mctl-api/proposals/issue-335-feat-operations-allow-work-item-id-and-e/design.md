# Design: issue-335-feat-operations-allow-work-item-id-and-e

## Current state

**Where the operation lives.** `mctl-agents-investigate` is one entry in the
`builtinOperations` slice in `internal/operations/registry.go` (lines 633-652).
Its current shape:

```go
Name:             "mctl-agents-investigate",
DisplayName:      "Run mctl-agents issue-investigator",
WorkflowTemplate: "mctl-agents-investigate",
RiskLevel:        RiskLow,
AdminOnly:        true,
ModifiesPaths:    []string{"platform-gitops/agents-state/{service}/proposals/{slug}/"},
Parameters: []ParameterDef{
    {Name: "issue_url", Type: "string", Required: true, ..., Pattern: `^https://github\.com/mctlhq/[A-Za-z0-9_.-]+/issues/[0-9]+$`},
},
```

`ParameterDef` (`registry.go:59-68`) carries `Name`, `Type`, `Required`,
`Default`, `Description`, `Enum`, `Pattern`, `Secret`. Nothing else in the
struct is needed here.

**How a submit flows.** `POST /api/v1/operations/{name}/execute` is handled by
`internal/api/handlers_write.go`:

1. `Registry.Get(opName)` (line 40), then the `HandlerOnly` refusal (line 50) —
   investigate is not `HandlerOnly`, so it passes.
2. JSON body decoded into `map[string]string` (line 56).
3. Authentication (line 61).
4. `Registry.StripUndeclared(op, input)` (line 83). This is the decisive step
   for this issue: `StripUndeclared` (`registry.go:160-176`) builds a set from
   `op.Parameters` and **drops** every key not in it, logging the dropped names
   at warn level. It does not error. So today a submit carrying `work_item_id`
   and `execution_id` is accepted and the two values are silently discarded
   before Argo ever sees them — a quiet loss, not a 400. The function's own
   comment records why it exists (gitops#997, `config_patch` reachable from an
   arbitrary request body).
5. `AdminOnly` gate (line 94) — investigate requires admin membership and gets
   the sentinel team `"platform"`.
6. `Registry.ApplyDefaults` (line 199) fills every declared-but-absent
   parameter with its `Default` (empty string when none is declared), then
   `Registry.ValidateInput` (line 200) walks `op.Parameters` only: required
   check, `Enum` membership, `Pattern` match. A parameter that is absent or
   empty after the required check is skipped (`registry.go:117-119`), so an
   optional parameter with a `Pattern` is validated only when non-empty.
7. `Executor.Submit` (`internal/operations/executor.go`) builds the
   `argoproj.io/v1alpha1` Workflow with `workflowTemplateRef` and
   `buildArgoParams(params)` (line 370), which turns the whole map into
   `{name, value}` pairs — so whatever survives step 4 and 6 is forwarded
   verbatim. `WorkflowNamespace` (`executor.go:89`) already routes
   `mctl-agents-investigate` to `argo-workflows`.

**Other surfaces touching the same operation.**
`internal/mcp/server.go:2995-3043` (`mctl_trigger_issue`) posts
`extractStringParams(req.GetArguments())` to
`/api/v1/operations/mctl-agents-investigate/execute`, or, with
`use_temporal=true`, posts `{"issue_url": ...}` to
`/api/v1/agents/dev-loop/start` (`internal/api/handlers_dev_loop.go:60`,
`internal/temporalclient/client.go:102`). `internal/openapi/openapi.yaml`
documents the dev-loop start body (lines 1814-1869) but the generic
`/operations/{name}/execute` body is schema-free, so no OpenAPI change is
forced by adding registry parameters.

**The identifier contract already in the repo.** `docs/work-context-contract.md`
is the design of record for the `WorkItem` model: ids are `<prefix><uuid>` with
`wi_` for `WorkItem`, `we_` for `WorkItemExecution`, `cs_` for
`ContextSnapshot` (lines 63-72), and the snapshot route is keyed
`/api/v1/work-items/{id}/executions/{execution_id}/snapshots` (line 301). The
doc explicitly states (line 366) that `internal/workitems` does not exist yet.
So these ids are, at this moment, opaque strings minted elsewhere.

## Proposed solution

Add two optional `ParameterDef` entries to the `mctl-agents-investigate`
operation in `internal/operations/registry.go`, and nothing else:

```go
Parameters: []ParameterDef{
    {Name: "issue_url", Type: "string", Required: true, ...unchanged...},
    // Resume identifiers (mctlhq/mctl-agents#267). Optional and opaque to
    // mctl-api: nothing here resolves them, mints them, or defaults them.
    // Declared so StripUndeclared stops dropping them on the way to Argo;
    // the CWFT half is mctlhq/mctl-gitops#1279.
    {Name: "work_item_id", Type: "string", Required: false,
        Description: "Optional. Canonical WorkItem id to resume from (docs/work-context-contract.md, e.g. wi_<uuid>). Omit for a cold issue-driven run.",
        Pattern: `^[A-Za-z0-9_-]{1,64}$`},
    {Name: "execution_id", Type: "string", Required: false,
        Description: "Optional. WorkItemExecution id this run is attributed to (e.g. we_<uuid>). Omit for a cold issue-driven run.",
        Pattern: `^[A-Za-z0-9_-]{1,64}$`},
},
```

Why this shape, point by point:

- **No `Default:`.** An omitted `Default` is the zero value `""`, which is what
  `ApplyDefaults` then writes for a caller that omitted the parameter. That is
  the existing convention for every optional parameter in the registry
  (`mctl-agents-shepherd`'s `slug`, `preview-deploy`'s `git_ref`), and it
  satisfies "no invented default" literally: mctl-api never synthesizes an id.
- **`Required: false`.** Stated explicitly rather than omitted, matching the
  shepherd entries at `registry.go:628-630`, so the intent is readable at the
  call site and not inferred from a missing field.
- **A shape-only `Pattern`, not a prefix-and-UUID one.** These values are
  forwarded verbatim into Argo workflow parameters and interpolated by the CWFT
  as `{{workflow.parameters.work_item_id}}`, typically into a shell command —
  the same exposure that made `issue_url` and `slug` pattern-validated in this
  registry. A bounded `[A-Za-z0-9_-]` class removes quoting, whitespace,
  `$`, backtick and newline injection while accepting any id scheme
  mctl-agents settles on, including the documented `wi_`/`we_` prefixes.
  Pinning the exact prefix here would recreate this issue's own failure mode
  (a valid submit rejected at the registry) the next time the id scheme moves,
  in a repo that cannot see the minting code. `ValidateInput` skips empty
  values, so the pattern costs omitting callers nothing.
- **Nothing changes outside `Parameters`.** Risk level, `AdminOnly`,
  `WorkflowTemplate`, `ModifiesPaths` and the `WorkflowNamespace` switch
  (`executor.go:108`) stay as they are. The operation is no more dangerous for
  carrying two correlation ids.
- **`StripUndeclared` keeps its guarantee.** The declared set grows by exactly
  two names; every other key is still dropped by the same code path, so the
  third acceptance criterion holds without touching the filter.
- **Discoverability comes for free.** `Registry.List` / `Get` serialize
  `Parameters` as JSON, so `GET /api/v1/operations` starts advertising the two
  optional parameters the moment the entries exist.

Tests go in `internal/operations/registry_test.go`, following the pattern of
`TestReconcileDefaultsToWriting`: assert the declared struct fields *and* the
behaviour a caller actually hits (`ValidateInput` / `ApplyDefaults`), because
that test file's own comments record that asserting only the struct field has
missed live failures before.

## Alternatives

1. **Reject undeclared parameters instead of declaring these two.** The
   `StripUndeclared` comment (`registry.go:78-82`) leaves the door open to
   turning the silent drop into a 400. That would make today's behaviour
   *louder* but not *correct* — mctl-agents#267 still could not pass the
   identifiers. Orthogonal hardening, dropped from this proposal; worth its own
   issue, and note it would have surfaced this bug immediately.
2. **Accept the ids only on the Temporal path** (`/api/v1/agents/dev-loop/start`
   → `DevLoopStartRequest` → `temporalclient.DevLoopInput`), letting
   DevLoopWorkflow pass them to the CWFT. Dropped: the acceptance criteria name
   the `/operations/mctl-agents-investigate/execute` endpoint, the direct-Argo
   path is still the default (`use_temporal` defaults to false,
   `server.go:3021`), and this would leave the direct path unable to resume.
   Can be added later without conflicting with this change.
3. **Validate the ids strictly (`^wi_[0-9a-f-]{36}$` / `^we_...`) or resolve
   them against a store.** Strict patterns couple an mctl-api release to an id
   scheme owned by another repo and defined in a doc whose own implementation
   (`internal/workitems`) is not written yet; resolution is impossible for the
   same reason — there is no store to resolve against. Both were dropped in
   favour of shape-only validation, with the option to tighten once
   `internal/workitems` lands.
4. **Declare the parameters with no `Pattern` at all** (pure pass-through, the
   most literal reading of "passed through unchanged"). Dropped: every other
   free-form string parameter that reaches a gitops/Argo script in this
   registry carries a pattern, and an unvalidated value interpolated into a
   workflow template is the shape of gitops#997. The chosen class still passes
   any real id through unchanged.

## Platform impact

- **Migrations:** none. No schema, no store, no persisted state.
- **Backward compatibility:** additive. `issue_url` stays required with its
  pattern; existing callers (`mctl_trigger_issue`, the `mctl-agents-issue-poll`
  cron, any direct REST submit) send neither new parameter and are unaffected
  through `StripUndeclared` → `ApplyDefaults` → `ValidateInput`, which skips
  empty optional values.
- **Behaviour change worth naming:** after this lands, every investigate submit
  through the generic path carries `work_item_id=""` and `execution_id=""` as
  Argo workflow parameters, because `ApplyDefaults` fills declared-but-absent
  keys. This already happens for other operations' optional parameters
  (shepherd's `service`/`slug`), so it is consistent — but it means the
  `mctl-agents-investigate` CWFT starts receiving two arguments it does not yet
  declare. **Risk:** if the Argo controller rejects workflow-level arguments
  the referenced ClusterWorkflowTemplate does not declare, every investigate run
  would fail at submit. **Mitigation:** verify this against a real submit before
  merge (task T4), and coordinate ordering with `mctlhq/mctl-gitops#1279` — the
  zero-risk sequence is to merge the CWFT parameter declarations first, even
  though the issue states this half can land independently. If verification
  shows Argo does reject them, the fallback is to strip empty-valued optional
  parameters for this operation before `Submit` rather than to revert the
  declaration.
- **Security:** the operation stays `AdminOnly`, so only admins can set these
  values; the pattern bounds them to 64 characters of a safe class before they
  reach an Argo parameter. `StripUndeclared`'s invariant is unchanged for every
  other key. No new secret material — neither parameter is marked `Secret`, and
  both are correlation ids, so they appear in the audit entry and the
  "submitting workflow" log line (`executor.go:145`), which is the intent.
- **Resources:** none. Two struct literals and two test functions; no new
  dependency, no new route, no MCP tool (so the MCP tool-count assertion in
  `internal/mcp/server_test.go` is untouched).
- **Risk of drift:** the `Description` strings reference
  `docs/work-context-contract.md` so a future reader can find the id scheme.
  If mctl-agents#267 renames either parameter, this registry entry and
  gitops#1279 must move together; the tests below pin the exact names so a
  rename cannot land silently on this side.
