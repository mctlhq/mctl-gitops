# Design: issue-196-feat-governance-agent-execution-identity

## Current state

**There is no execution identity object.** Identity today is six disjoint
fragments, each owned by a different layer and none of them reaching the layer
that would need it.

1. **Temporal control plane.** `DevLoopWorkflow` is started with
   `IssueRef(issue_url=...)` — a single-field frozen dataclass
   (`orchestrator/temporal/workflows/dev_loop.py:370-372`) — under the id
   `workflow_id_for(issue_url)` = `dev-loop-mctlhq-<repo>-<number>`
   (`orchestrator/temporal/issue_ref.py:30`). No `memo`, no search attributes,
   no interceptors are set anywhere (`orchestrator/temporal/start.py:65-72`);
   `worker.py:394-426` configures `TelemetryConfig` with a Prometheus exporter
   only, so there is no tracing runtime and `trace_id` appears nowhere in the
   repository. The approve signal (`dev_loop.py:787-800`) accepts an approver
   dict/str and stores `self._approver`; if none was supplied the CWFT is sent
   the literal string `"unknown"` (`dev_loop.py:897-905`).
2. **Temporal to Argo boundary.** One funnel,
   `_run_cwft(operation, params: dict[str, str], ...)`
   (`dev_loop.py:483-517`), passes `SubmitAndWaitInput(operation, params)`
   (`orchestrator/temporal/activities/argo.py:61-67`) to `submit_and_wait`,
   which `POST`s `params` as the JSON body of
   `/api/v1/operations/{operation}/execute` (`argo.py:118-122`) under one
   static shared bearer token (`orchestrator/temporal/mctl_client.py:16-31`).
   The complete set of keys ever sent is `issue_url`, `service`, `slug`,
   `approver`, `agent_image`, `agent_version`, `mode`. No labels, no
   annotations, no env injection. mctl-api passes undeclared parameters
   through, which is how `agent_image`/`agent_version` already ride along
   (`orchestrator/temporal/workflows/incidents.py:100-106`).
3. **Durable ledger.** `ExecutionRecord`
   (`orchestrator/temporal/activities/state.py:28-44`) carries
   `temporal_workflow_id, agent, environment, version, image_ref, target_repo,
   argo_workflow_name, phase` and is `POST`ed to `/api/v1/agents/executions`
   (`state.py:47-64`) best-effort from `_record` (`dev_loop.py:524-563`). No
   run id, no attempt, no approver, no target SHA, no content hashes.
4. **Resolver.** `ExecutionPlan` (`orchestrator/resolver.py:226-258`) is by far
   the richest identity-ish record the repo has: definition/profile versions
   and content hashes, release revision, model policy version, prompt and
   skill hashes, tools, permissions, budget, timeout, sandbox backend, CWFT,
   `target_repository_sha`. It exists only in the agent process, only in
   `declarative` resolver mode, and is only ever printed
   (`resolver.py:290`, called at `run_issue_investigator.py:1315`).
5. **Agent runtime.** `orchestrator/run_issue_investigator.py` re-derives what
   it needs: `IssueData` holds four fields and `gh_issue_view`
   (`run_issue_investigator.py:868`) requests
   `number,title,body,state,url` — the issue **author is never fetched**, so
   the human actor is not even available. `write_status_yaml`
   (`:979-1044`) writes a `source:` block plus the hard-coded literal actor
   `"mctl-agents[bot]"`, and `_status_disagreements` (`:539-582`) verifies five
   fields of it after publication. `run_implementer._resolve_attempt_id`
   (`run_implementer.py:741-771`) is the one existing precedent for a
   deterministic per-execution id: `WORKFLOW_UID` if set, else a sha256 over
   `service|slug|owner_epoch|attempt_ordinal|HOSTNAME`.
6. **Tool/MCP surface.** `mctl_mcp_config` (`orchestrator/options.py:15-54`)
   builds `{"type": "http", "url": MCTL_MCP_URL, "headers": {"Authorization":
   "Bearer <MCTL_TOKEN>"}}`. Every agent's options pass the whole parent
   environment to the child (`env={**os.environ, ...}`, options.py:296, 317,
   371, 407, 458, 499). `orchestrator/mcp_guard.py` is a connectivity verifier
   only (`wait_for_mctl_connected`, `ensure_mctl_connected`) — it does not
   intercept tool calls. The only interception point that exists is
   `_audit_pre_tool_use` / `_command_audit_hooks` (`options.py:224-276`), a
   `PreToolUse` hook matched on `Bash` that prints and returns `{}`.

Two contracts already anticipate this work and constrain its shape.
**ADR 009** (`docs/adr/009-context-snapshot-contract.md`) defines
`ContextSnapshot` and an `ExecutionCorrelation` block
(`orchestrator/context_snapshot.py:407-475`) whose eleven fields are exactly
the join keys "both sides already have" — but §4 is explicit that this is a
*copy supplied by the caller*, not an assertion, and §5 forbids any
authorization-shaped field in that module. **ADR 007** separates
`AgentDefinition` (identity) from `ExecutionProfile` (constraints) and states
that `tools` is not authorization. **ADR 010** already names actors without
naming permissions: `Executor{type, id}`
(`orchestrator/lifecycle/contract.py:670`) with the closed vocabulary
`shepherd | pr-steward | devloop-workflow | reconciler | implementer`, and
`ExecutionClaimRequest` (`orchestrator/temporal/activities/lifecycle.py:330-353`)
carries `executor_type`/`executor_id`/`attempt`/`claim_id`.

## Proposed solution

Add one canonical document, minted by the control plane, propagated with the
work, and resolved server-side wherever it matters: **`ExecutionContext`,
`identity.mctl.ai/v1alpha1`**, specified in a new ADR
(`docs/adr/011-execution-identity-contract.md`) and implemented in a new
stdlib-only module `orchestrator/execution_identity.py` that deliberately
mirrors `orchestrator/context_snapshot.py` line for line in style: module
constants `API_VERSION`/`KIND`/`SUPPORTED_API_VERSIONS`, closed `frozenset`
vocabularies, frozen dataclasses with `to_dict`/`from_dict`,
`_require_str`/`_require_int`/`_reject_unknown_keys` validators, one
`ExecutionIdentityError(ValueError)`, a keyword-only `seal()` and a
`to_log_dict()`.

### 1. The schema

```
ExecutionContext                 # identity.mctl.ai/v1alpha1
  api_version, kind
  context_id      "ex-" + content_hash[7:23]      (derived, never random)
  content_hash    "sha256:..." over all fields except content_hash,
                  context_id, issued_at
  issued_at       RFC3339 Z
  trace_id        32 lowercase hex (W3C trace-context), stable per DevLoop
  parent_context_id: str | null                   (step chaining)
  workflow_type   investigate|approve|implement|review-fix|incident|reconcile
  step_sequence   int                             (strictly increasing)
  actor: Actor        {type, id, verification}
  executor: Executor  {type, id, agent, version, image_ref, binding}
  scope: Scope        {tenant, repository, target_repository_sha,
                       environment, service, slug}
  trigger: Trigger    {type, ref}
  correlation: Correlation {temporal_workflow_id, temporal_run_id,
                       argo_workflow_name, attempt}
  assertions: Assertions {asserted_by, asserted_fields, declared_fields}
```

Closed vocabularies: `actor.type` in `github_user | operator | cron |
temporal-schedule | system`; `actor.verification` in `control-plane-verified |
signal-asserted | unverified`; `trigger.type` in `github_issue |
github_issue_comment | pull_request | incident | schedule | manual`;
`executor.type` reuses ADR-010's `Executor` values verbatim so the two
contracts never diverge; `environment` in `production | shadow`
(`dev_loop.py:80`, `resolver.py:110`).

`Executor.version`/`image_ref` are copied from `ResolvedRelease`
(`orchestrator/temporal/activities/registry.py:45-55`) and are `""` when
nothing resolved — the same honesty rule `_record` already applies
(`dev_loop.py:533`). `scope.target_repository_sha` is `""` until the CWFT
exposes it (the gap `state.py:35-41` documents); the investigator already
computes it (`run_issue_investigator.py:117`) and can seal a child context
with it.

`assertions` is the trust model made machine-readable: `asserted_by` is
always `"control-plane"` for a minted context, `asserted_fields` lists the
dotted paths the control plane vouches for, and `declared_fields` lists paths
a workload filled in (e.g. `scope.target_repository_sha` sealed inside the
agent container). A consumer that needs a trustworthy field checks membership
rather than trusting the document wholesale.

### 2. Minting and propagation

- **Mint (Temporal).** A new activity module
  `orchestrator/temporal/activities/identity.py` exposes
  `mint_execution_context(MintRequest) -> MintedContext`, which seals the
  document locally and `POST`s it to mctl-api
  (`/api/v1/agents/executions/context`) next to the existing execution
  ledger, using the same `httpx` + `auth_headers()` pattern as `state.py`.
  `DevLoopWorkflow` mints a root context on first step and one child per step
  (investigate / approve / implement / review-fix), sharing one `trace_id`
  derived deterministically from `temporal_workflow_id` + run id so replay is
  stable (Temporal workflows may not call `random`/`uuid` directly — the id is
  computed inside the activity and returned, exactly like
  `resolve_agent_release`).
- **Cross the boundary.** `_run_cwft` adds two keys to the existing
  `params: dict[str, str]`: `execution_context_id` and `trace_id`. No new
  transport, no signature change, and the pass-through behaviour that already
  carries `agent_image` keeps working until mctl-gitops declares the
  parameters on the CWFTs.
- **Reach the agent.** The CWFT writes the fetched context JSON to a file and
  exports `MCTL_EXECUTION_CONTEXT_FILE` (a file, not an inline env value, so
  the document never lands in an Argo parameter dump or a `printenv` in agent
  logs). `orchestrator/execution_identity.load_from_environment()` returns the
  sealed context, or — when the variable is absent and
  `MCTL_REQUIRE_EXECUTION_CONTEXT` is unset — a locally minted context with
  `actor.verification = "unverified"` and `assertions.asserted_by = "local"`,
  so local runs and `--dry-run` keep working.
- **Reach tools.** `mctl_mcp_config` adds `X-Mctl-Execution-Context` and
  `X-Mctl-Trace-Id` to the `headers` dict it already builds
  (`options.py:47-51`). Every `mcp__mctl__*` call then carries the identity
  with zero agent cooperation, which is what "without requiring each agent to
  reconstruct identity" means in practice. For non-MCP tools, the existing
  `PreToolUse` hook (`options.py:259`) gains the context id in its `AUDIT`
  line so Bash invocations are attributable in the same log stream.
- **Land in the records.** `ExecutionRecord` gains `execution_context_id` and
  `trace_id`; `write_status_yaml`'s payload
  (`run_issue_investigator.py:987-1000`) gains a read-only `execution:` block
  with `context_id`, `trace_id`, `agent`, `version`; `_status_disagreements`
  (`:576-582`) is extended to verify the block survived publication.
  `ContextSnapshot.ExecutionCorrelation` is produced by
  `ExecutionContext.to_execution_correlation()` rather than hand-built twice.

### 3. Trust boundary

The rule is one sentence: **the copy a workload holds is evidence, not
authority.** mctl-api stores the minted document; a call presenting
`X-Mctl-Execution-Context` is attributed by *looking up that id server-side*,
and any identity claim in a request body or prompt is ignored. The workload
can read its context, log it, and put it in a trace; it cannot change what
anyone else believes about it, because nothing else reads its copy.
`content_hash` makes local tampering detectable (a modified file no longer
reseals to its `context_id`), and `executor.binding` records the
`argo_workflow_name` the id was issued to, so a stolen id from a sibling run
is rejectable as soon as mctl-api can observe the caller's workflow. That last
check is the honest weak point today: every caller shares one admin
`MCTL_TOKEN`, so the binding is currently tamper-evident rather than
tamper-proof. The ADR states this plainly instead of implying a guarantee the
deployment cannot make, and per-run credentials are recorded as follow-up work.

Identity is never authorization. The same executable guard ADR 009 uses is
copied: a recursive field-name test fails the build if `allow`, `deny`,
`permit`, `grant`, `authorized` or `role` ever appears in the serialized
schema, and a subprocess import-direction test proves
`orchestrator/execution_identity.py` imports stdlib only (the
`tests/test_worker_isolation.py` pattern), so it stays importable by the
Temporal worker, the agent container, and any future policy process alike.

## Alternatives

1. **Extend `ContextSnapshot.ExecutionCorrelation` instead of adding a new
   kind.** Tempting — eleven of the fields already exist there. Dropped
   because ADR 009 §5 is normative that the snapshot records context
   provenance and nothing a policy path may consume, and its `execution`
   block is explicitly a caller-supplied copy. Folding an asserted identity
   into it would make one document simultaneously untrusted input and trusted
   assertion. The chosen direction keeps the dependency one-way:
   `ExecutionContext` projects into `ExecutionCorrelation`, never the reverse.
2. **A signed token (JWS/HMAC) carried entirely by the workload.** No
   server-side store, and any consumer with the key can verify. Dropped:
   it needs key distribution and rotation to every consumer, the workload
   holds the full signed claim set (so replay across steps becomes the new
   problem), and the token would sit in an Argo parameter — the one place
   this repo already knows leaks into workflow specs and logs. The handle plus
   server-side lookup gives the same attribution with nothing forgeable in
   the blast radius.
3. **Plain env vars (`MCTL_AGENT`, `MCTL_ACTOR`, ...) with no document.**
   Cheapest, and roughly what `agent_version` does today. Dropped: the agent
   process receives the entire parent environment and can rewrite it before
   spawning anything, there is no version, no vocabulary and no hash, and
   three consumers would each re-derive a slightly different notion of
   "environment" — the exact drift this issue exists to stop.
4. **Temporal search attributes / memo as the carrier.** Good for control
   plane queries, useless past the Argo boundary (the agent container has no
   Temporal client by design, ADR-008 and `tests/test_worker_isolation.py`)
   and it cannot reach an MCP call at all. Kept as an optional later addition
   for operator queries, not as the propagation mechanism.

## Platform impact

- **Migrations.** Additive only. New module, new ADR, two new CWFT params, two
  new `ExecutionRecord` fields, one new `.status.yaml` block. No existing field
  changes meaning; no existing row is invalidated.
- **Backward compatibility.** Every consumer treats a missing context as
  "unverified", never as an error, outside the cluster. Workflow changes that
  alter command order in `DevLoopWorkflow` must be gated by
  `workflow.patched("execution-identity")` and covered by the replay fixtures
  (`tests/fixtures/histories/dev_loop_full.*.json`,
  `tests/test_workflow_replay.py`) — this repo has already been bitten by
  patch memoization (`tests/test_patch_memoization.py`), so the marker is
  evaluated once in a single funnel, not inside a branch.
- **Cross-repo.** mctl-api must accept and store the context and extend the
  executions row; mctl-gitops must declare `execution_context_id`/`trace_id`
  on the four `mctl-agents-*` CWFTs and write the context file into the agent
  container. Until both land, the mctl-agents side degrades to
  mint-and-record-only, which is still a strict improvement to the audit
  trail.
- **Resource impact.** One extra sub-second activity per DevLoop step, two
  extra HTTP headers per MCP call, a few hundred bytes per stored row.
  Negligible against a two-hour `SDK_STEP_TIMEOUT`.
- **Risks and mitigations.** (a) *A minting failure blocks real work* —
  mitigated by making the mint activity non-fatal in the same way `_record`
  is (`dev_loop.py:524-563`): a failed mint downgrades the step to an
  unverified locally-sealed context and logs loudly, it never fails the loop.
  (b) *Identity mistaken for authorization* — mitigated by the ADR sentence,
  the field-name test, and the import-direction test. (c) *Secret leakage
  through the context* — mitigated by file-based transport, `to_log_dict()`
  being the only emission path, and no free-text field except `trigger.ref`
  and `actor.id`, both bounded and structurally validated. (d) *Replay
  divergence* — mitigated by deriving `trace_id` inside an activity and
  pinning behaviour with the existing replay harness
  (`tests/temporal_harness.py`, `tests/replay_scenarios.py`).
