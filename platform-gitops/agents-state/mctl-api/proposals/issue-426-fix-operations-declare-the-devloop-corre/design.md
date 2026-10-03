# Design: issue-426-fix-operations-declare-the-devloop-corre

## Current state

### The operation registry is the allowlist for Argo workflow parameters

`internal/operations/registry.go` holds `builtinOperations`, a slice of
`Operation` values. Each carries `Parameters []ParameterDef`
(`registry.go:59-78`), and that list is the *only* thing that decides which
request keys survive to Argo:

- `Registry.StripUndeclared(op, input)` (`registry.go:199-215`) builds a set of
  declared names and returns the filtered map plus a sorted `dropped` slice.
  Its doc comment explains why this exists: `ValidateInput` only walks
  `op.Parameters`, so an *undeclared* key was never validated and was still
  forwarded verbatim, which is how `config_patch` — a raw `yq` expression run
  against `values.yaml` by `tpl-git-commit` — became reachable from an arbitrary
  request body (gitops#997).
- `handleExecuteOperation` (`internal/api/handlers_write.go:83`) calls it right
  after the authentication check and before RBAC, then logs
  `"ignoring undeclared operation parameters"` at warn level. The comment there
  records the deliberate choice to *drop* rather than reject, so a live caller
  sending an extra field is not failed closed.
- `Registry.ApplyDefaults` (`registry.go:220-...`) then fills defaults and
  honours `OmitWhenEmpty`: for such a parameter, a missing or empty value is
  *deleted* from the map so the CWFT's own default applies. The `ParameterDef`
  comment (`registry.go:68-77`) spells out the hazard it guards — a declared
  parameter with `Default ""` would override a non-empty CWFT default with an
  empty string, which for `agent_image` means a pod with no image.
- `Registry.ValidateInput` (`registry.go:148-178`) enforces `Required`, `Enum`
  and `Pattern`; `handlers_write.go:200` turns any error into a 400 with
  `validationErrors`.
- `Executor.Submit` (`internal/operations/executor.go:126-...`) forwards the
  whole surviving map through `buildArgoParams(params)` into
  `spec.arguments.parameters`, and logs only parameters the operation declares.

So an undeclared parameter is not merely unvalidated — it is invisible end to
end: stripped, absent from the submit log's `params`, and absent from the Argo
workflow.

### The three affected operations today

All three are `AdminOnly`, submit into `argo-workflows`
(`executor.go:106-108`), and compose their parameter list as
`append([]ParameterDef{...}, agentPinParams("<agent>")...)`:

- `mctl-agents-investigate` (`registry.go:702-734`): `issue_url` (required, with
  a `^https://github\.com/mctlhq/...$` pattern), `work_item_id` and
  `execution_id` (both optional, `^[A-Za-z0-9_-]{1,64}$`, added for
  mctl-agents#267 with the explicit comment "Declared so StripUndeclared stops
  dropping them on the way to Argo"), plus `agent_image` / `agent_version`.
  Note that `work_item_id` / `execution_id` here are *not* `OmitWhenEmpty`.
- `mctl-agents-implement` (`registry.go:646-667`): `service`, `slug`,
  `max_proposals`, plus the pin pair.
- `mctl-agents-shepherd` (`registry.go:668-701`): `service`, `slug`, `dry_run`,
  plus the pin pair.

`agentPinParams` (`registry.go:98-107`) is the existing precedent for a shared
helper that returns a small block of optional, `OmitWhenEmpty`, pattern-guarded
parameters bound to one operation.

### The tests that already encode this contract

`internal/api/handlers_write_devloop_params_test.go` is the file this issue
turns on. It holds two mirrored tables:

- `devLoopSubmissions` (line 27): every parameter set mctl-agents submits per
  operation, each row annotated with its sender in mctl-agents
  (`dev_loop.py` investigate/implement/`_shepherd_tick`,
  `run_issue_directive_poller.py`, `implement_sweep.py`, `incidents.py`,
  `reconcile.py`). `TestExecuteOperation_DevLoopParamsAreNeverDropped` (line
  125) posts each row as `auth.NewServiceUser()` — the identity the Temporal
  worker uses — asserts 202, and fails naming every key that did not reach
  `exec.submittedParams`.
- `devLoopParamsPendingDeclaration` (line 162): parameters mctl-agents sends
  that the CWFT did *not* declare yet. It currently lists exactly
  `human_input_responses`, `temporal_workflow_id`, `temporal_run_id` and
  `execution_request_id` on investigate.
  `TestExecuteOperation_PendingDevLoopParamsAreStillStripped` (line 181)
  asserts each is dropped, and its comment states the intent: "this fails the
  moment one is declared, so the declaration is a deliberate step that also
  updates the table above."

That is the crucial mechanical consequence: **declaring the parameters makes an
existing green test go red on purpose.** The implementation must move the rows,
not delete the test.

`internal/operations/registry_test.go` holds the unit-level half:
`TestInvestigateAcceptsResumeIdentifiers`,
`TestInvestigateResumeIdentifiersStayOptional`,
`TestInvestigateForwardsResumeIdentifiers`,
`TestInvestigateRejectsMalformedResumeIdentifiers`,
`TestInvestigateForwardsReleasePin`, `TestReleasePinPatterns` and
`TestReleasePinIsOmittedWhenEmpty` (lines 230-523). These are the shape to
copy for the new parameters: pattern acceptance/rejection tables,
`StripUndeclared` round-trips that also assert an undeclared `config_patch` is
still dropped, and `ApplyDefaults` absence checks.

`TestImplementAndShepherdServiceEnumCoversMctlAgentsServices`
(`registry_test.go:38-...`) is the precedent for a cross-repository drift guard.
Its comment is unusually candid about the limits of a hand-kept mirror: it fires
only when one copy *inside this repository* falls behind the others, and
"catching that class needs the real SERVICES list, which is in another
repository and not reachable from a unit test." The guard this issue asks for
lives under the same constraint.

### Documentation

`docs/agent-platform-registry.md` has a "Release pins on `mctl-agents-*`
operations" section (line 343) that already explains `StripUndeclared`, the
per-operation sender table, and points at
`TestExecuteOperation_DevLoopParamsAreNeverDropped` as the list of record with
the rule "gitops first". That section is the natural home for the correlation
parameters.

### Value shapes available in-repo

- `docs/model-usage-ledger.md:143-144` records the ledger's own treatment:
  `temporal_run_id` is "up to 128 characters from `[A-Za-z0-9_.:-]`, starting
  alphanumeric"; `temporal_workflow_id` and `work_item_id` are free text. The
  regex behind the first is `executionIDPattern` in
  `internal/usage/types.go:286`: `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`.
- `internal/workitems/execution_requests.go:45` fixes
  `ExecutionRequestIDPrefix = "xr_"`.
- `internal/agentregistry/store.go:115` stores `temporal_workflow_id` as `TEXT`
  with values like `dev-loop-mctlhq-mctl-telegram-1`
  (`handlers_agent_registry_test.go:381`).

## Proposed solution

Four coordinated changes, all inside mctl-api, no schema and no new
dependency.

### 1. A `devLoopCorrelationParams` helper in `internal/operations/registry.go`

Add a helper alongside `agentPinParams`, returning the correlation block. It
takes the per-operation name set so each operation declares exactly what its
CWFT declares (the open question about shepherd's set is resolved by reading
the manifests, not by a uniform default):

```go
// temporalIDPattern mirrors the usage ledger's own acceptance for these
// values (internal/usage/types.go executionIDPattern,
// docs/model-usage-ledger.md): up to 128 characters from [A-Za-z0-9_.:-],
// starting alphanumeric. Conservative enough to exclude newlines, spaces and
// shell metacharacters on the way into Argo workflow arguments; permissive
// enough to survive a change in how mctl-agents names a workflow id.
const temporalIDPattern = `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`

// correlationIDPattern is the shape already used for work_item_id /
// execution_id on mctl-agents-investigate.
const correlationIDPattern = `^[A-Za-z0-9_-]{1,64}$`

// devLoopCorrelationParams declares the DevLoopWorkflow's correlation
// identifiers ... Opaque to mctl-api: nothing here resolves, mints or
// defaults them (mctlhq/mctl-api#426, mctlhq/.github#50). Every one is
// optional and OmitWhenEmpty, so a caller that sends none — the directive
// poller, implement_sweep.py, a manual operator trigger — is unaffected and
// the CWFT's own default applies.
func devLoopCorrelationParams(names ...string) []ParameterDef { ... }
```

Each returned `ParameterDef` is `Required: false`, `Default: ""`,
`OmitWhenEmpty: true`, with the pattern above by name, and a `Description`
that says what the id is and that omitting it is normal.

Then:

- `mctl-agents-investigate` appends
  `devLoopCorrelationParams("temporal_workflow_id", "temporal_run_id", "execution_request_id")`.
  Its existing `work_item_id` / `execution_id` stay exactly as they are — they
  already work, and changing them is out of scope.
- `mctl-agents-implement` and `mctl-agents-shepherd` append
  `devLoopCorrelationParams("temporal_workflow_id", "temporal_run_id", "work_item_id", "execution_id")`,
  trimmed to the names their own CWFT declares.

Why `OmitWhenEmpty` on all of them, including `work_item_id` / `execution_id`
on implement and shepherd: `ApplyDefaults` would otherwise send
`work_item_id=""` for the many callers that legitimately omit it
(`implement_sweep.py`, a manual `mctl_trigger_implementer`), and an empty
string in `spec.arguments.parameters` overrides whatever the CWFT declared as
its default. That is precisely the hazard documented at `registry.go:68-77`.
The existing investigate `work_item_id` / `execution_id` are *not*
`OmitWhenEmpty`, which is a latent inconsistency; this proposal does not change
them (out of scope, and their CWFT default is empty today), but the design note
records it so a future change is informed.

Why a helper rather than inline literals: three operations, overlapping but
not identical name sets, and the pattern/description text must not drift
between them. `agentPinParams` set this precedent for exactly the same reason.

### 2. Move the rows in `handlers_write_devloop_params_test.go`

- Delete the three correlation entries from `devLoopParamsPendingDeclaration`,
  leaving `human_input_responses` (whose CWFT half has not landed — see
  mctl-api#372 item 3). The table and
  `TestExecuteOperation_PendingDevLoopParamsAreStillStripped` stay, now
  covering one row; that keeps the "gitops first" ratchet alive for the next
  parameter.
- Add rows to `devLoopSubmissions` that mirror what `dev_loop.py` really sends:
  an investigate row with `issue_url` + pin + `work_item_id` + `execution_id` +
  `temporal_workflow_id` + `temporal_run_id` + `execution_request_id`; an
  implement row and a `_shepherd_tick` row each with `service`, `slug`, pin,
  `temporal_workflow_id`, `temporal_run_id`, `work_item_id`, `execution_id`.
  Keep the existing minimal rows (directive poller, `implement_sweep.py`)
  unchanged — they are the regression guard for callers that send nothing.

Because `TestExecuteOperation_DevLoopParamsAreNeverDropped` drives the real
router as `auth.NewServiceUser()` and inspects `exec.submittedParams`, these
rows are the end-to-end proof that the parameters reach Argo, not just that the
registry mentions them.

### 3. The anti-drift guard test

The CWFT manifests live in mctl-gitops and are not reachable from `go test`.
Following the precedent (and the explicit admission) in
`TestImplementAndShepherdServiceEnumCoversMctlAgentsServices`, the guard is a
checked-in inventory with provenance, in a new file
`internal/operations/registry_cwft_params_test.go`:

```go
// cwftDeclaredParams is a transcription of spec.arguments.parameters from the
// three mctl-agents ClusterWorkflowTemplates in mctlhq/mctl-gitops, as of
// mctl-gitops#1345 (investigate) and #1418 (implement, shepherd).
// Transcribe, do not guess: declaring a name the CWFT does not declare makes
// Argo reject the submit.
var cwftDeclaredParams = map[string][]string{
    "mctl-agents-investigate": {...},
    "mctl-agents-implement":   {...},
    "mctl-agents-shepherd":    {...},
}

// cwftParamsNotSettableViaAPI names CWFT parameters that mctl-api
// deliberately does not declare, each with the reason. A parameter is
// exempted here only because mctl-api itself, or the template, owns its
// value — never because declaring it was forgotten.
var cwftParamsNotSettableViaAPI = map[string]map[string]string{...}
```

`TestCWFTParamsAreDeclaredOrExplicitlyInternal` then asserts, per operation,
that every name in `cwftDeclaredParams` is either in `op.Parameters` or has a
non-empty reason in `cwftParamsNotSettableViaAPI`. A second assertion runs the
converse direction — every exemption names a parameter the CWFT actually
declares — so the exclusion list cannot accumulate dead entries that quietly
excuse a future omission. A third asserts each declared correlation parameter
is `OmitWhenEmpty` and carries a non-empty `Pattern`, which is the property
that makes "declared" safe rather than merely present.

The test's doc comment must state plainly what it can and cannot catch, in the
style of `registry_test.go:39-54`: it catches a CWFT parameter transcribed into
the inventory but never declared in the registry, and it does not catch a CWFT
parameter added in gitops that nobody transcribed. Closing that second gap
needs the real manifests at test time; the design records it as a follow-up
(a CI step that clones mctl-gitops and regenerates the inventory, gated on the
mctl-gitops read token already used elsewhere on the platform) rather than
pretending the unit test achieves it.

### 4. Documentation

Extend `docs/agent-platform-registry.md`'s "Release pins on `mctl-agents-*`
operations" section — or add a sibling "DevLoop correlation parameters"
subsection — with: the per-operation table of correlation names and which
mctl-agents sender emits them, the statement that they are opaque to mctl-api,
the `OmitWhenEmpty` rationale, and the "gitops first" ordering rule already
stated there. Also record the guard test and its inventory as the place to edit
when a CWFT parameter is added.

## Alternatives

**A. Stop stripping for `AdminOnly` mctl-agents operations — forward any key
from a trusted service principal.** Smallest diff, and would have prevented
both this bug and mctl-api#372 permanently. Dropped: `StripUndeclared` exists
because forwarding undeclared keys is exactly how `config_patch` became
settable from a request body (gitops#997, quoted at `registry.go:186-191`). An
allowlist that has a trusted-caller bypass is not an allowlist; the service
principal is shared by every Temporal worker activity, and the registry is also
the source of the `/operations` self-description the MCP surface and Backstage
read. Keeping the allowlist total and paying the per-parameter declaration cost
is the property the code was built to hold.

**B. Prefix-based passthrough — allow any key matching `^temporal_` or a fixed
correlation prefix.** Avoids touching the registry when mctl-agents adds a
correlation id. Dropped: it reintroduces unvalidated values into
`spec.arguments.parameters` (no `Pattern`, so newlines and shell
metacharacters get through), it makes the `/operations/{name}` schema response
an incomplete description of what the endpoint accepts, and it silently
forwards a typo'd `temporal_wokflow_id` to a template that will reject the
whole submit — turning a dropped-parameter warning into a failed workflow. The
issue's own framing ("declare ... with a conservative `Pattern`") points the
other way.

**C. Declare the parameters without `OmitWhenEmpty`.** Fewer fields to reason
about, and matches how investigate's existing `work_item_id` / `execution_id`
are declared today. Dropped: `ApplyDefaults` would then send `work_item_id=""`
and `temporal_run_id=""` for every caller that omits them — the directive
poller, `implement_sweep.py`, every manual operator trigger — overriding any
non-empty CWFT default with an empty string. That is the documented `agent_image`
hazard (`registry.go:68-77`) applied to correlation data, and it would put
empty-string correlation dimensions into the ledger, which is worse than absent
ones for the mctlhq/.github#50 criterion: absent is honestly missing, `""` is a
bucket.

**D. Fetch the CWFT manifests from mctl-gitops inside the guard test.** Would
catch the direction the checked-in inventory cannot. Dropped for this proposal:
a unit test that clones another repository is slow, needs a token, and fails
offline — `registry_test.go:47-48` already states the constraint. Recorded as a
follow-up CI job instead, so the honest limitation is documented rather than
papered over.

## Platform impact

**Migrations.** None. No database schema, no Helm value, no CRD, no new env
var. The change is a parameter declaration and tests.

**Backward compatibility.** Additive and safe in both directions:

- Callers that send none of the new parameters are byte-identical to today,
  because every new parameter is optional and `OmitWhenEmpty` — nothing new
  appears in `spec.arguments.parameters`. The existing
  `TestExecuteOperation_UnpinnedCallerSendsNoAgentImage` pattern is extended to
  cover this.
- Callers that already send them (mctl-agents 1.61.0+) go from "silently
  dropped, warn-logged" to "forwarded". The CWFTs already declare the names, so
  Argo accepts them.
- The `/api/v1/operations/mctl-agents-*` schema response grows three to four
  optional parameters. Consumers (Backstage, the MCP `mctl_list_operations`
  tool) render optional parameters already.

**Ordering.** gitops first, always. The CWFT half has landed (mctl-gitops#1345,
#1418), so mctl-api is now the lagging side — which is the safe direction. The
inverse (declaring here before gitops) forwards a parameter to a template that
rejects it and fails the whole submit; that is why
`devLoopParamsPendingDeclaration` exists and why `human_input_responses` must
stay in it.

**Resource impact.** Negligible: three to four extra short strings per Argo
workflow submit, and three to four extra `regexp.MustCompile` calls per
`ValidateInput` invocation for requests that carry them. Note that
`ValidateInput` compiles patterns on every call (`registry.go:172`) rather than
once at init; this change adds to that existing cost but does not create it.
Precompiling is a tempting cleanup and is deliberately not bundled here.

**Risks and mitigations.**

| Risk | Mitigation |
|---|---|
| A declared name that the CWFT does not actually declare → Argo rejects every submit from the DevLoop, breaking the loop entirely | Transcribe `spec.arguments.parameters` from the three manifests; the guard test's inventory is the transcription and is reviewed in the same PR. Verify against one real submit in staging before relying on it. |
| `TestExecuteOperation_PendingDevLoopParamsAreStillStripped` left unchanged → red build | It is in the task list explicitly; the rows move to `devLoopSubmissions` in the same commit. |
| A too-strict `Pattern` rejects a real production value → 400 instead of a dropped parameter, i.e. a *worse* failure than today | Patterns are copied from values this repository already accepts for the same ids (`internal/usage/types.go:286`, and the existing investigate `^[A-Za-z0-9_-]{1,64}$`). Tests assert the observed live shapes (`dev-loop-mctlhq-mctl-agents-494`, a bare UUID run id, `xr_<id>`) are accepted. |
| `execution_request_id` shape drifts from `xr_` | The pattern does not pin the prefix, only the character class and length. |
| Correlation values become a log or injection surface | They are already logged only if declared (`executor.go:136-142`, non-`Secret`, so visible in the submit log — these are opaque ids, not credentials). The `Pattern` excludes whitespace, newlines and shell metacharacters before the value reaches Argo arguments, which is the same defence `TestInvestigateRejectsMalformedResumeIdentifiers` pins for the resume ids. |
| Guard test gives false confidence about cross-repo drift | Its doc comment states the limit explicitly, following `registry_test.go:39-54`; the real cross-repo check is recorded as a follow-up. |

**Verification after deploy.** Trigger one DevLoop run and confirm the submitted
`mctl-agents-investigate-*` workflow's `spec.arguments.parameters` now contains
`temporal_workflow_id`, `temporal_run_id` and `execution_request_id`; then
confirm new usage ledger rows carry `temporal_workflow_id` / `temporal_run_id`
via `GET /api/v1/usage/summary?group_by=temporal_workflow_id`. That closes the
mctlhq/.github#50 criterion with evidence rather than with a passing unit test.
