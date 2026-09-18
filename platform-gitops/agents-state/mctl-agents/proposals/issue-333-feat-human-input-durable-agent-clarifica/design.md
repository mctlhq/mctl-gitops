# Design: issue-333-feat-human-input-durable-agent-clarifica

## Current state

**The only durable human checkpoint is authorization.** `DevLoopWorkflow`
(`orchestrator/temporal/workflows/dev_loop.py`) runs
investigate -> `wait_condition(lambda: self._approved)` -> approve flip ->
implement -> watch. `approve()` is a `@workflow.signal` (`dev_loop.py:787`)
carrying an optional approver string; `orchestrator/temporal/cli.py:approve`
and `POST /api/v1/agents/dev-loop/{workflow_id}/approve` are its senders. The
workflow exposes exactly two queries today — `shepherd_in_loop()` and
`lifecycle_claim()` (`dev_loop.py:753`, `:766`) — and mctl-api's
`mctl_get_dev_loop` reads `shepherd_in_loop` over HTTP. There is no state a
caller can read that says "this run is blocked on a question", and
`wait_condition` on `_approved` has no timeout, so a parked loop waits
forever.

**Agent steps are one-shot Argo runs.** Every model call is submitted through
`_run_cwft` -> `submit_and_wait` (`orchestrator/temporal/activities/argo.py`),
which POSTs to `/operations/{op}/execute` and polls, returning
`WorkflowResult(workflow_name, phase, started_at, finished_at)` with
`succeeded` as a `phase == "Succeeded"` property. The Temporal worker
deliberately holds no gitops checkout — "every gitops write must go through
Argo" (module docstring, `dev_loop.py:16-19`). `SDK_STEP_TIMEOUT` is two
hours and the CWFT has its own `activeDeadlineSeconds`, so a synchronous wait
for a human is impossible by construction as well as by policy.

**The investigator cannot ask.** `orchestrator/run_issue_investigator.py`
clones the target repo read-only, builds one prompt (`_build_prompt`, the
manifest's only `promptSources` entry), and runs the SDK with
`build_issue_investigator_options` /
`build_issue_investigator_options_from_plan`
(`orchestrator/options.py:387`, `:422`). The prompt explicitly instructs the
agent to "capture the ambiguity in `## Open questions`, never stop to ask".
Untrusted issue text is wrapped in `<issue_title>`/`<issue_body>` blocks and
run through `_neutralize_prompt_tags` (`run_issue_investigator.py:1098`),
which strips forged and unclosed delimiters. `investigate()`'s `finally`
discards the staging directory on any error path rather than publish work
whose provenance it cannot vouch for. Exit codes are ad hoc (`SystemExit`,
`sys.exit(1)`); `run_implementer.py` already reserves `45` for "batch was
only blocked proposals".

**Capability eligibility already has a home.** ADR 007 makes
`ExecutionProfile.tools` the client-side allow-list;
`orchestrator/resolver.py`'s `ExecutionPlan` (`resolver.py:226-256`) pins
`tools`, `permissions`, `policy_ref`, `budget_usd`, `timeout_seconds` and the
four version/content hashes per run. `build_issue_investigator_options_from_plan`
treats `plan.tools` as authoritative and refuses to hand back a tool the
profile withheld even when the environment would allow it
(`options.py:441-457`). `issue-investigator` is the one agent migrated to
`agents.mctl.ai/v1alpha2` (`agents/_manifests/issue-investigator/agent.yaml`),
resolving its profile from the mctl-gitops catalog; the resolver runs only
under `ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative`, default `legacy`
(`docs/resolver-pilot-status.md`).

**The provenance contract exists and is inert.** ADR 009 defines
`ContextSnapshot` and `orchestrator/context_snapshot.py` implements it:
stdlib-only, `seal()` as the sole constructor,
`content_hash = "sha256:" + sha256(canonical JSON)` over every field except
`content_hash`/`snapshot_id`/`created_at`, `snapshot_id = "cs-" +
content_hash[7:23]`, `from_dict` rejecting unknown keys, `_require_sha256`,
`ExecutionCorrelation`, `StepRef{parent_snapshot_id, step, sequence}`,
`EvidenceRef{evidence_id, kind}`, `to_log_dict()`, and a test asserting no
`allow`/`deny`/`permit`/`grant`/`authorized` field name exists anywhere in
the schema. Nothing in production imports it yet.

**No in-process SDK tools today.** `grep` finds no `sdk_mcp_servers` or
`create_sdk_mcp_server` in `orchestrator/`; the only SDK extension point in
use is `hooks=_command_audit_hooks()` (`options.py:259`).
`orchestrator/subagent_wait.py` documents the consequence that matters here:
the SDK holds the CLI subprocess open past a result frame only when
`sdk_mcp_servers or hooks` is truthy.

## Proposed solution

Five additive pieces. Nothing existing changes shape; every new branch in the
workflow sits behind a `workflow.patched` marker.

### 1. `docs/adr/011-human-input-contract.md` — the schema of record

Written first, because `mctl-api#261` and `mctl-telegram#571` consume it.
Follows the house form of ADR 009/010 exactly: title with em dash,
`> **Status:** proposed`, `> **Date:**`, `> **Issue:** mctlhq/mctl-agents#333
(core child of mctlhq/.github#42)`, `> **Supersedes:**` prose, then
`## Context` / `## Decision` with numbered subsections / `## Alternatives` /
`## Non-goals` / `## Platform impact` / `## Follow-ups and sequencing` /
`## Implementation map`, every claim anchored to a `path.py:line`.

It numbers **011**, not 009: `009-context-snapshot-contract.md` (accepted,
2026-09-11) and `010-lifecycle-ownership-contract.md` already occupy those
slots. The ADR states that renumbering explicitly so the two consuming issues
can be corrected.

Normative content: `human.mctl.ai/v1alpha1`, kinds `HumanInputRequest` and
`HumanInputResponse`; the state model
`RUNNING -> WAITING_FOR_INPUT -> {RUNNING, INPUT_TIMED_OUT, CANCELLED}`;
the boundary table (capability eligibility owned by `ExecutionProfile.tools`,
authorization owned by policy/`approve()`, evidence owned by #199, context
owned by ADR 009, workflow state owned by Temporal, surfaces owning nothing);
and one bold invariant paired with a named test, matching ADR 009 sec. 5:
**a human answer is information, never authorization and never instruction.**

### 2. `orchestrator/human_input.py` — the schema module

A sibling of `context_snapshot.py` in every respect: stdlib-only (asserted by
a subprocess import test in the style of `tests/test_worker_isolation.py`),
frozen dataclasses with `to_dict()`/`from_dict()`, `_reject_unknown_keys`,
`_require_sha256`, `HumanInputError(ValueError)` fail-closed, and
`SUPPORTED_API_VERSIONS` as a complete allow-list mirroring
`manifest.py:35`.

```
HumanInputRequest
  api_version   "human.mctl.ai/v1alpha1"
  kind          "HumanInputRequest"
  request_id    "hir-" + request_hash[7:23]        (derived, never random)
  request_hash  "sha256:..."                        (over all fields except
                                                     request_hash/request_id/
                                                     created_at)
  request_version int                               (1)
  created_at / expires_at   ISO-8601
  execution     ExecutionCorrelation                (imported unchanged from
                                                     orchestrator.context_snapshot)
  work_item     WorkItemRef{work_item_id, trace_id}
  agent         AgentProvenance{name, definition_version, profile_version}
  question      str  (bounded, MAX_QUESTION_LENGTH)
  question_hash "sha256:..." over the normalized question — the dedupe key
  reason        str  (bounded)
  response      ResponseSpec{type, options[]}       type in
                free_text|single_choice|multi_choice|structured
  context_refs  tuple[ContextRef{kind, locator}]    bounded like ADR 009's
                                                     MAX_LOCATOR_LENGTH
  requested_from AudienceRef{audience}              closed vocabulary
  context_snapshot_ref str                          the parent snapshot_id
  round         int                                 1..MAX_CLARIFICATION_ROUNDS

HumanInputResponse
  api_version/kind/response_id (= "hia-" + response_hash[7:23])
  request_id, request_hash      must match the outstanding request exactly
  respondent    RespondentRef{actor_type, actor_id}  identity reference only
  surface       str                                  telegram|portal|api|github
  value         str | tuple[str] | Mapping           validated against
                                                     ResponseSpec
  received_at   ISO-8601
  response_hash "sha256:..."
```

`seal_request()` / `seal_response()` are the only constructors that fill the
hash and id, exactly as `context_snapshot.seal()` is. `validate_response(
request, response)` is the single place that enforces id match, hash match,
expiry, type/option conformance and length bounds — one function, so mctl-api
and the workflow cannot drift into two answers. `to_log_dict()` emits
`request_id`, `request_hash`, `question_hash`, `round`, lengths and codes;
never `question`, `reason` or `value`.

The schema declares no field named or containing `allow`, `deny`, `permit`,
`grant`, `approve` or `authorized`, and the recursive field-name test from
`tests/test_context_snapshot.py` is reused verbatim against it. That is the
executable form of "clarification is not approval".

### 3. `human.request_input` — the capability, and the yield

Exposed as an in-process SDK MCP server (`create_sdk_mcp_server`, server name
`human`, tool `request_input`), built in a new
`orchestrator/human_input_capability.py` and wired only in
`build_issue_investigator_options_from_plan` — i.e. only under the
declarative resolver, only when `"human.request_input" in plan.tools`. The
builder maps the logical profile name to the SDK's actual
`mcp__human__request_input` tool string, the same conjunction
`_mctl_tool_globs()` already applies to `mcp__mctl__*`. The legacy builder is
untouched, so the default `legacy` path cannot acquire the capability by
accident.

The tool handler is deterministic Python, not a model decision. It:

1. refuses if a request is already outstanding for this step, if
   `round > MAX_CLARIFICATION_ROUNDS`, or if `question_hash` matches one
   already recorded for this workflow (the "do not re-ask" rule);
2. seals a `HumanInputRequest` from the `ExecutionPlan` and the parent
   `ContextSnapshot`;
3. POSTs it to mctl-api with the `MCTL_TOKEN` the pod already carries
   (idempotent on `request_id` — a retried Argo attempt re-POSTs the same
   derived id and gets the same row back, which is why the id is derived
   rather than random);
4. writes it to `$HUMAN_INPUT_DIR/request.json` for the driver;
5. returns only `{request_id, request_hash, status: "needs_input"}` plus the
   instruction to stop working.

`investigate()` then checks for that file after the stream settles
(`drain_until_settled`, `orchestrator/subagent_wait.py`), discards the
staging triplet the way every other non-publish path does (the
`InvestigatorOrphanedSubagent` branch's precedent: a partial proposal is
worse than a re-run), and exits with `EXIT_NEEDS_INPUT = 50`. That is a
deliberate departure: this driver reports through `InvestigateResult`, not
exit codes (`run_issue_investigator.py:1966-1969`), and gains exactly one
code plus one `InvestigateResult.needs_input: str = ""` field, because the
CWFT has to distinguish "asked a question" from "failed". 50, not 46 —
`run_implementer.py` already reserves 42-49 (`EXIT_ORPHANED_SUBAGENT = 46`,
`EXIT_BLOCKED_ONLY = 45`), and reusing one of those would collide the moment
a caller reads both taxonomies. No `.status.yaml` field is added: the
publish path re-reads and rejects any unexpected `status`/`source`/`control`
value (`_status_disagreements`), and a needs-input step publishes nothing at
all. The CWFT maps 50 to a distinguishable Argo phase; `submit_and_wait` gains a
defaulted `outcome: str = ""` field on `WorkflowResult`, which is
replay-safe (existing histories deserialize a dataclass with a new default)
and lets `DevLoopWorkflow` read `needs_input` without parsing logs. **The pod
exits here.** Nothing is held open.

### 4. `WAITING_FOR_INPUT` in `DevLoopWorkflow`

Additive state, all behind `workflow.patched("human-input")`:

- `@workflow.signal human_input(payload)` — parses defensively and never
  raises, exactly as `approve()` does; sets `self._human_response` only when
  `request_id` and `request_hash` match the outstanding request, so a stale
  or forged signal is a no-op rather than a resume. It never touches
  `self._approved`.
- `@workflow.query waiting_for() -> str` — closed vocabulary `"" |
  "approval" | "input"`. This is the first-class distinction the issue
  requires, and it reaches mctl-api the same way `shepherd_in_loop` already
  does.
- `@workflow.query human_input_state() -> HumanInputState` with
  `request_id`, `request_hash`, `question_summary` (bounded), `expires_at`,
  `round`, `resume_count`, `outcome` — the safe read model for surfaces.
- After each agent step whose `outcome == "needs_input"`, the workflow runs
  `fetch_human_input_request` (a thin mctl-api read activity beside
  `record_execution`, bounded by `FAST_ACTIVITY_TIMEOUT` /
  `FAST_ACTIVITY_RETRY_POLICY`), emits `human_input.requested` and
  `.wait_started`, then:

```python
answered = await workflow.wait_condition(
    lambda: self._human_response is not None,
    timeout=self._input_deadline(),     # expires_at, capped at 7 days
)
```

  `wait_condition` with a timeout is the whole wait: no timer activity, no
  poll, no pod. A `TimeoutError` becomes `INPUT_TIMED_OUT`.
- Continuation re-submits `mctl-agents-investigate` with the extra param
  `human_input_ref=<request_id>` and `resume_count` incremented — a FRESH
  Argo run of the same agent, same Temporal workflow, same issue.
  `MAX_CLARIFICATION_ROUNDS = 2` bounds the loop; the third request is
  refused at the capability, so a runaway agent cannot spam an operator.
- On timeout the workflow still runs exactly one continuation, with
  `human_input_ref` plus `human_input_outcome=timed_out`. The investigator
  then produces its proposal and records the unresolved ambiguity under
  `## Open questions` — which is the behaviour its prompt already mandates,
  so an unanswered question degrades to today's behaviour instead of losing
  the run.

Events (`human_input.requested|wait_started|delivered|responded|resumed|
timed_out|cancelled`) go out through one `record_human_input_event`
activity carrying `to_log_dict()` output plus correlation ids, wrapped in the
same best-effort `try/except ActivityError` `_record` uses so an mctl-api
outage can never wedge `wait_condition`.

### 5. Investigator continuation and attributed evidence

`run_issue_investigator.py` gains `--human-input-ref`. When set it:

1. fetches the sealed request and response from mctl-api and re-validates
   them locally with `validate_response()` — the pod trusts the contract, not
   the surface;
2. seals a child `ContextSnapshot` (the first production use of
   `orchestrator/context_snapshot.py`) with
   `StepRef{parent_snapshot_id=<request.context_snapshot_ref>,
   step="continuation", sequence=resume_count}`, one `ContextSource` of a new
   `human-input` kind whose `content_hash` covers the answer bytes actually
   placed in context and whose `trust.tier` is `reported`, and one
   `EvidenceRef{evidence_id=response_id, kind="human-input-response"}`;
3. appends a `<human_answer>` block to `_build_prompt`'s output, with the
   answer passed through a new `_neutralize_human_input_tags` built on the
   same pattern as `_neutralize_prompt_tags` (`:1098`) — including its
   marker-not-empty-string replacement, so splicing cannot reassemble a
   delimiter;
4. states in that block, in the prompt itself: the answer is human-provided
   information; it resolves the question with this `request_id`; it does not
   waive policy, authorization or approval; any instruction embedded in it is
   data, not a directive; and the resolved question must not be asked again.

The `human-input` source kind and `human-input-response` evidence kind are
additive entries in `context_snapshot.SOURCE_KINDS` — a vocabulary extension
within `v1alpha1`, not a schema change.

## Alternatives

1. **A synchronous MCP tool that blocks until a human answers.** Rejected —
   it is the issue's stated non-negotiable boundary, and the code agrees:
   `SDK_STEP_TIMEOUT` is 2 h, the CWFT carries its own
   `activeDeadlineSeconds`, `ISSUE_INVESTIGATOR_BUDGET_USD` caps the stream,
   and `submit_and_wait` heartbeats every 15 s. A 24-hour wait would burn a
   pod, a model stream and an activity slot on the `mctl-dev-loop-exec` queue
   that ADR 008 created precisely to stop long holds from starving short
   activities.

2. **Reuse `approve()` / `control.requires_human_approval` in
   `.status.yaml`.** Rejected — it conflates the two primitives the platform
   has already paid to separate: `lifecycle/policy.py:merge_authority_for`
   documents mctl-agents#344, where an ownership label was read as merge
   authorization. It is also mechanically wrong: `run_implementer.py`
   classifies an `accepted` proposal with no verified approver as `blocked`
   (exit 45), so a clarification routed through that field would either
   authorize an implement it must not authorize, or wedge the proposal.

3. **Keep pending-input state in `.status.yaml` and let the cron sweep it.**
   Rejected — it makes a file (and, one step later, a surface) the source of
   truth for workflow state, which the issue lists as a non-goal. It is also
   invisible to a parked workflow: mctl-api's own `mctl_get_dev_loop`
   documentation records that a hand-edited `.status.yaml` is invisible to a
   workflow already parked on the approve signal. And the Temporal worker
   holds no gitops checkout by design, so every write would need a whole
   Argo run per answer.

4. **Put the request on the Argo step's output parameters instead of POSTing
   it from the pod.** Rejected for now — it keeps mctl-api out of the write
   path, but `WorkflowResult` and `submit_and_wait` would have to carry
   arbitrary structured output through a polling activity, and the surfaces
   need a read model in mctl-api regardless (#261). Recorded in
   requirements.md's open questions rather than silently dropped.

## Platform impact

- **Migrations.** None. No stored schema changes; `.status.yaml`
  (`orchestrator/proposal_state.py`) is untouched. `WorkflowResult` gains one
  defaulted field, which older payloads deserialize unchanged.

- **Backward compatibility.** Every new workflow branch sits behind
  `workflow.patched("human-input")`. Per `tests/test_patch_memoization.py`
  and the `exec-queue` precedent (`dev_loop.py:499`), `patched()` memoizes per
  execution, so in-flight loops replay their recorded command sequence for
  the rest of their lives and only new executions get the state. The
  investigator's `--human-input-ref` is optional; without it the driver is
  byte-identical to today. The capability is absent from the default
  `legacy` resolver path entirely.

- **Cross-repo coupling.** Three sibling changes are required and are not in
  this repository: mctl-api #261 (create/respond/get/list/cancel plus
  `WAITING_FOR_INPUT` in the execution read model and a `waiting_for`
  passthrough beside the existing `shepherd_in_loop` query), mctl-telegram
  #571 (the surface), and mctl-gitops (the investigate CWFT's
  `human_input_ref`/`human_input_outcome` parameters and the exit-46 phase
  mapping). Note that `orchestrator/validate_manifest.py`'s
  `_check_tool_policy_and_budget_match_options_py` compares
  `set(options.allowed_tools)` against the manifest's resolved `tool_allow`,
  and for `issue-investigator` that list comes from the mctl-gitops catalog
  profile `issue-investigator-default` — so adding the capability to the
  builder without the matching `spec.tools` entry in that profile turns
  manifest validation red. The gitops profile bump must land first.

- **Resource impact.** Negative for compute: a clarification that today
  either never happens or costs a failed run now costs one extra Argo step
  per answered round, capped at 2. Temporal history grows by roughly a dozen
  events per round; `wait_condition` with a timeout adds a single timer, far
  below the budget `MERGE_WATCH_DEADLINE`'s ~1344 polls already justify.
  mctl-api gains a small table and five endpoints.

- **Risks and mitigations.**
  - *Operator spam / infinite asking.* Mitigated by the three-way bound:
    one outstanding request per execution, `MAX_CLARIFICATION_ROUNDS = 2`,
    and `question_hash` dedupe that survives a retry because `request_id` is
    derived from content rather than random.
  - *A stale or forged signal resuming the wrong run.* Mitigated by
    requiring both `request_id` and `request_hash` to match, in a signal
    handler that returns silently on mismatch and never raises.
  - *Prompt injection via the answer.* Mitigated by
    `_neutralize_human_input_tags`, by the explicit unprivileged-data framing
    in the continuation block, and by the fact that the answer arrives as a
    bounded `value` field rather than free-form transcript.
  - *Privilege creep.* Mitigated by making `plan.tools` the sole gate and by
    reusing ADR 009's recursive no-authorization-field-name test against the
    new schema.
  - *A leaked question exposing repository internals.* Mitigated by bounding
    `question`/`reason` and by `context_refs` being `{kind, locator}` pointers
    with no payload field declared — the same "no payload, ever, anywhere"
    property ADR 009 sec. 7 relies on.
  - *An unanswered question silently killing a run.* Mitigated by the
    `INPUT_TIMED_OUT` continuation, which degrades to today's
    `## Open questions` behaviour instead of failing.

- **Security.** A `HumanInputResponse` sets no approval state anywhere: it
  cannot reach `self._approved`, cannot flip `.status.yaml`, and cannot
  satisfy `control.requires_human_approval`. Any consequential mutation
  downstream still goes through `approve()` and the implementer's own
  approval gate.
