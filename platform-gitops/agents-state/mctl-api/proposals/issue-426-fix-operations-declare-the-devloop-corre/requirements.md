# Declare the DevLoop correlation parameters so StripUndeclared stops dropping them

## Context

The Temporal `DevLoopWorkflow` in mctl-agents sends correlation parameters with
every ClusterWorkflowTemplate (CWFT) submit it makes through
`POST /api/v1/operations/{name}/execute`: `temporal_workflow_id` and
`temporal_run_id` on the investigate, implement and shepherd steps, plus
`execution_request_id` on investigate, and `work_item_id` / `execution_id` on
implement and shepherd. The CWFTs already declare these names (mctl-gitops#1345
for investigate, #1418 for implement and shepherd), but the submitted Argo
workflows do not carry them. The observed run
`mctl-agents-investigate-98bbc7b3`, started by `dev-loop-mctlhq-mctl-agents-494`
at 07:21Z on 2026-09-30, carries only `agent_version`, `execution_id`,
`issue_url`, `work_item_id` and `agent_image`.

The cause is entirely inside mctl-api. `Registry.StripUndeclared`
(`internal/operations/registry.go:199`) removes every request key the operation
does not declare in `builtinOperations`, and
`handleExecuteOperation` (`internal/api/handlers_write.go:83`) applies it before
anything reaches `Executor.Submit`. The three mctl-agents operations
(`mctl-agents-investigate`, `mctl-agents-implement`, `mctl-agents-shepherd`) do
not declare the correlation names, so they are silently dropped with a
`slog.Warn` and never become Argo workflow parameters. This is the same failure
class as mctl-api#372, where the release pin (`agent_image` / `agent_version`)
was dead for every run until it was declared. The mctl-agents side already
annotates the parameters as "Inert until mctl-api declares them" in
`dev_loop.py`, and this repository records the same expectation in
`devLoopParamsPendingDeclaration`
(`internal/api/handlers_write_devloop_params_test.go:162`).

The impact is loss of correlation, not loss of function. Of 184 usage ledger
rows recorded since 2026-09-29, none carry `temporal_workflow_id` or
`temporal_run_id`, even though mctl-agents#505 has been live since 1.61.0; that
blocks the mctlhq/.github#50 criterion "execution/workflow correlation
preserved across Temporal/Argo boundaries". The investigator never receives
`--temporal-workflow-id` / `--temporal-run-id`, so `_await_human_input` cannot
use the run id to distinguish its own request from a same-id leftover
(mctl-agents#451). Implement and shepherd runs spawned by the shepherd carry an
empty `execution_id` — 56 of 84 implementer rows since 2026-09-29.

## User stories

- AS the Temporal `DevLoopWorkflow` I WANT the correlation parameters I send to
  reach the Argo workflow SO THAT every agent pod knows which Temporal
  workflow, run, work item and execution it belongs to.
- AS a platform operator reading the usage ledger I WANT
  `temporal_workflow_id` and `temporal_run_id` populated on agent spend rows SO
  THAT I can attribute cost to a single DevLoop execution across the
  Temporal/Argo boundary (mctlhq/.github#50).
- AS the issue-investigator agent I WANT `--temporal-run-id` passed through SO
  THAT `_await_human_input` can tell my own human-input request from a
  same-id leftover of a previous run (mctl-agents#451).
- AS the shepherd's implement tick I WANT `work_item_id` and `execution_id`
  forwarded SO THAT the implementer rows it spawns are attributed to the
  execution that caused them instead of carrying an empty `execution_id`.
- AS a maintainer of `internal/operations/registry.go` I WANT a guard test
  against the CWFT parameter sets SO THAT a parameter declared in gitops but
  never declared here cannot silently go inert again.

## Acceptance criteria (EARS)

- WHEN a caller submits `mctl-agents-investigate` with `temporal_workflow_id`,
  `temporal_run_id` and `execution_request_id`, THE SYSTEM SHALL forward all
  three unchanged to `Executor.Submit` as Argo workflow parameters.
- WHEN a caller submits `mctl-agents-implement` or `mctl-agents-shepherd` with
  `temporal_workflow_id`, `temporal_run_id`, `work_item_id` and
  `execution_id`, THE SYSTEM SHALL forward each of those the corresponding CWFT
  declares unchanged to `Executor.Submit`.
- WHILE a caller omits any of these parameters, THE SYSTEM SHALL submit the
  workflow without that key present at all, so the CWFT's own default applies
  (`OmitWhenEmpty`, as with `agent_image` — see `ApplyDefaults`,
  `internal/operations/registry.go:220`).
- WHEN a caller sends one of these parameters as the empty string, THE SYSTEM
  SHALL treat it as omitted and not forward an empty value to Argo.
- IF a value does not match the parameter's declared `Pattern`, THEN THE SYSTEM
  SHALL reject the request with HTTP 400 and a `validationErrors` entry naming
  the parameter, before any workflow is submitted.
- WHILE these parameters are declared, THE SYSTEM SHALL keep treating them as
  opaque: no resolution, minting, defaulting, database lookup or cross-field
  consistency check is performed on them.
- WHILE these parameters are declared, THE SYSTEM SHALL keep `issue_url`
  required on `mctl-agents-investigate` and keep every existing parameter,
  enum, pattern and risk level of the three operations unchanged.
- WHEN a key that no operation declares (for example `config_patch`) is sent
  alongside the new parameters, THE SYSTEM SHALL still drop it and report it in
  the `dropped` list.
- WHEN the test suite runs, THE SYSTEM SHALL fail IF any parameter name in the
  checked-in CWFT parameter inventory for the three templates is neither
  declared by the corresponding operation nor listed in an explicit
  mctl-api-internal exclusion list with a stated reason.
- WHEN the test suite runs, THE SYSTEM SHALL fail IF a parameter still listed
  in `devLoopParamsPendingDeclaration`
  (`internal/api/handlers_write_devloop_params_test.go`) now reaches the
  executor — the existing test that pins "these are dropped today" must be
  updated in the same change, not left red or deleted.

## Out of scope

- Any change to what mctl-api resolves, mints, validates semantically or
  persists. These stay opaque correlation data, exactly like `work_item_id` /
  `execution_id` on investigate today.
- `human_input_responses` on `mctl-agents-investigate`. The CWFT does not
  declare it (mctl-api#372 item 3), so it must remain undeclared here and stay
  in `devLoopParamsPendingDeclaration`; declaring it would forward it to a
  template that rejects it.
- Changes to the ClusterWorkflowTemplates themselves. The gitops half already
  landed (mctl-gitops#1345, #1418); this proposal is the mctl-api half only.
- Writing correlation ids into the usage ledger or the `agent_executions`
  table from mctl-api. The ledger is populated by the agent pods
  (`docs/model-usage-ledger.md`); this change only makes the ids reach those
  pods.
- Changes to the MCP tool surface (`internal/mcp/server.go`). `mctl_trigger_issue`
  and friends are human/LLM entry points that do not carry Temporal identity;
  the DevLoop uses the REST execute path. No MCP tool is added or removed, so
  the tool-count expectation in `internal/mcp/server_test.go` is unaffected.
- A live cross-repository check that fetches the CWFT YAML from mctl-gitops at
  test time. The guard test uses a checked-in inventory instead (see design);
  automating the fetch is a possible follow-up.
- `mctl-agents-incidents`, `mctl-agents-approve` and `mctl-agents-reconcile`.
  The issue names only the three DevLoop steps.

## Open questions

- Does `cwft-mctl-agents-shepherd` actually declare all four of
  `temporal_workflow_id`, `temporal_run_id`, `work_item_id` and
  `execution_id`, or only a subset? The issue says "only the names each CWFT
  actually declares", which implies the sets may differ between implement and
  shepherd. Proceeding interpretation: build the checked-in CWFT inventory by
  reading the three template manifests in mctl-gitops at implementation time
  and declare exactly what each one declares, per operation, rather than
  assuming a uniform set. Declaring a name the CWFT does not declare would make
  Argo reject the submit, so the inventory must be transcribed, not guessed.
- Exact shape of `execution_request_id`. `internal/workitems/execution_requests.go:45`
  fixes the prefix `xr_` but no pattern constant is exported. Proceeding
  interpretation: reuse the conservative `^[A-Za-z0-9_-]{1,64}$` already used
  for `work_item_id` / `execution_id` on investigate, which accepts `xr_<uuid>`
  without pinning mctl-api to the prefix.
- Exact shape of `temporal_workflow_id`. Observed values are
  `dev-loop-mctlhq-mctl-agents-494` and `dev-loop-xr_0000`;
  `docs/model-usage-ledger.md` records it as "free text, unchanged" in the
  ledger. Proceeding interpretation: use the ledger's
  `executionIDPattern`-equivalent `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`
  (`internal/usage/types.go:286`) for both temporal ids — conservative enough
  to block newlines, spaces and shell metacharacters, permissive enough to
  survive a workflow-id naming change on the mctl-agents side.
- Whether the mctl-gitops CWFTs give any of these parameters a non-empty
  default. If one does, `OmitWhenEmpty` is required to avoid overriding it;
  since `OmitWhenEmpty` is also correct when the default is empty, this
  proposal sets it unconditionally and the question does not block.
