# Design: issue-904-fix-work-context-accept-mcp-resume-surfa

## Current state

### Surface vocabularies (two deliberate copies)

- `orchestrator/work_context/contract.py:44` defines
  `SURFACE_KINDS = frozenset({"github", "telegram", "web", "cli", "api"})`. This is the
  tolerant mctl-api mirror. `answer_from` (around lines 368-393) classifies an item whose
  `origin.kind` or execution `surface.kind` falls outside it as `WORK_ITEM_UNKNOWN`.
- `orchestrator/context_snapshot.py:100` defines `WORK_CONTEXT_SURFACE_KINDS`, the same
  set, for the strict sealed-document schema. `validate()` (around lines 1061-1069)
  refuses an `origin_surface` or `current_surface` outside it. The module comment
  (lines 84-99) says the duplication is deliberate: there is no import edge.
- `tests/test_context_snapshot.py:1043-1055` pins
  `cs.WORK_CONTEXT_SURFACE_KINDS == SURFACE_KINDS`.
- `orchestrator/execution_evidence.py:95-104` documents a third
  mirrored-vocabulary pattern, asserted by `tests/test_execution_evidence.py` T11. Any
  surface set mirrored there must move in step.
- `tests/test_work_context_contract.py:268-272`
  (`test_out_of_vocabulary_origin_surface_is_unknown`) uses `"mcp"` as its negative
  example.

### Where an MCP resume is refused today

- `orchestrator/temporal/dispatcher.py:419-426` builds
  `ResumeDelivery(surface=request.surface, actor_kind=RESUME_ACTOR_KIND, actor_id=request.requested_by, ...)`.
  The surface label comes from mctl-api (`mcp` for the MCP tool). The actor id is the
  authenticated requester. No client or model identity is carried.
- `DevLoopWorkflow._resume_provenance` (`orchestrator/temporal/workflows/dev_loop.py`,
  around line 2041) returns `surface-or-actor-unrecognised` when
  `surface.kind not in SURFACE_KINDS`. Both the `resume` signal (around line 2616) and
  the `accept_execution_request` validator use it. `mcp` is therefore refused before any
  `we_` is minted, and the request is rejected.
- `orchestrator/work_context/execution_requests.py:71-85` lists
  `surface-or-actor-unrecognised` as a documented rejection reason.
- The investigator CLI check `_validate_work_context_args`
  (`orchestrator/run_issue_investigator.py:4503-4515`) refuses `--surface mcp`.

### Transition semantics

- `_take_resume_provenance` (dev_loop.py, around line 2069) compares
  `SurfaceRef(kind)` and `ActorRef(kind, actor_id)` with the current values. A change
  clears `_approved`, `_approval_ref` and `_requested_ref`, bumps `_approval_attempt` and
  sets `_grant_refresh`. With no baseline, any declared value counts as a transition
  (fail closed). Equality covers only surface kind, actor kind and actor id, so a model
  or client change under the same principal is already not a transition. The tests must
  pin this. Nobody should add a client field to `SurfaceRef` or `ActorRef`.
- In the investigator, `_work_context_ref` (`run_issue_investigator.py:2990-3068`)
  computes `surface_transition` from the newest prior execution with a known surface,
  falling back to `item.origin.kind`. If the `--surface` flag is absent, it seals
  `current_surface=""` and `surface_transition=False`. That is "unknown reported as
  false", which the issue forbids.
- `WorkContextRef.surface_transition` (`context_snapshot.py:602`) is `bool = False`.
  `to_dict` always emits it, and `from_dict` defaults a missing key to `False`.

### Forwarding gap (#573)

- dev_loop.py lines 3565-3602 build `investigate_params` with `work_item_id`,
  `execution_id` and `execution_request_id`. They do not include surface, actor kind or
  actor id. So an investigator launched for a dispatched resume never receives
  `--surface/--actor-kind/--actor-id`, and seals an empty current surface.

### Redacted intents

- `orchestrator/context_assembly.py:1058-1086` (`_intent_candidate`) renders a
  `text_redacted` intent body as the literal `[text removed by retention]`. The pinned
  resume intent (`AssemblyInput.resume_intent`, line 277) is placed first and is
  exempt from the budget (lines 489-506), so the placeholder becomes the primary
  instruction.
- `IntentUnresolved` (context_assembly.py, around line 1888) already fails a run as
  `failed / intent-unresolved` when the intent cannot be read. It seals nothing, and it
  does not park the loop.
- ADR 013 (`docs/adr/013-human-input-contract.md`): the investigator seals
  `human-input/request.json`. The DevLoop reads it with `find_human_input_request`
  (`_await_human_input`, dev_loop.py around line 2943) and parks in `WAITING_FOR_INPUT`.
  Logs never carry question, reason or value.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`:
  the declared parameters are `issue_url`, `agent_image`, `agent_version`,
  `work_item_id`, `execution_id`, `temporal_workflow_id`, `temporal_run_id`,
  `execution_request_id`, `human_input_responses`, `work_item_owner_principal_id` and
  `traceparent`. There is no `surface`, `actor_kind` or `actor_id` parameter. This
  confirms the forwarding gap is also present in the deployed template.
- The mctl MCP tools were not called. This proposal concerns orchestrator code and an
  Argo template, not a tenant service. The live worker image version and the
  `WORK_ITEM_INTENT_SOURCE` rollout flag value were not observed (see Open questions in
  requirements.md).

## Proposed solution

### Slice A: vocabulary (can start now, no api#868 prerequisite)

1. Add `"mcp"` to `SURFACE_KINDS` (contract.py) and to `WORK_CONTEXT_SURFACE_KINDS`
   (context_snapshot.py). Update both comments: `mcp` is mctl-api's label for the MCP
   tool surface and carries no client identity. Mirror the change in any
   execution_evidence copy that T11 asserts.
2. Keep the parity test. Change `test_out_of_vocabulary_origin_surface_is_unknown` to a
   truly unknown value (for example `"carrier-pigeon"`) and add a positive test that
   `origin_surface="mcp"` is `WORK_ITEM_FOUND`.
3. With no further code change, `_resume_provenance`, the Update validator and the CLI
   accept `mcp`, because they all read `SURFACE_KINDS`.

### Slice B: provenance forwarding (absorbs the mctl-agents side of #573)

1. This proposal implements the mctl-agents side of #573 itself; #573 has no branch
   or code to integrate against. Add `surface`, `actor_kind` and `actor_id` to
   `investigate_params` (dev_loop.py, around lines 3565-3602) for a dispatched or
   resumed execution, from `self._current_surface` and `self._current_actor`, using
   the omit-when-empty rule of the other params. Add the end-to-end regression: a
   Telegram-origin item resumed over `mcp` seals `current_surface="mcp"` and
   `surface_transition=true`, and the mutation run (T6) shows it fails with the
   forwarding removed. The PR references #573 (`Refs`, not a closing keyword: #573
   closes only when the forwarding works live, see the rollout order).
1a. The forwarding crosses three repositories, and only the first is in this
   proposal's implementation scope:
   - mctl-agents (this proposal): the DevLoop puts the three keys into
     `investigate_params`; the investigator already accepts
     `--surface/--actor-kind/--actor-id`.
   - mctl-gitops (follow-up PR, not the implementer's): declare `surface`,
     `actor_kind` and `actor_id` in
     `argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml` with default
     `""`, and map each to its flag only when non-empty.
   - mctl-api (follow-up PR, not the implementer's): mctl-api strips investigate
     parameters it does not declare (mctl-api#372; `internal/operations/registry.go`,
     `devLoopCorrelationParams`). Declare the three keys with validation patterns:
     `surface` limited to the vocabulary, `actor_kind` to the actor kinds, `actor_id`
     to the principal formats `requested_by` can take.
   Until both follow-ups ship, the new keys are dropped by mctl-api and the forwarding
   is inert. That is safe: with Task 4 the investigator then seals an unknown (absent)
   `surface_transition`, never `false`.
2. Unknown is never false. Change `WorkContextRef.surface_transition` to
   `bool | None`. `to_dict` omits the key when it is None, following the
   `intent_high_water` pattern, so existing documents serialise to the same bytes.
   `from_dict` reads an absent key as None. `_work_context_ref` returns None when the
   current surface or the baseline is unknown. It returns True or False only when both
   sides are known. `ExecutionRef.surface_transition` in contract.py stays a bool,
   because it is a DevLoop-side fact that is always measured there.
3. No identity invention. `actor_id` is only ever `requested_by`, or the CLI value
   forwarded from it. No model, client, session or account field is added to
   `SurfaceRef`, `ActorRef` or `WorkContextRef`. Tests pin that same-principal `mcp` to
   `mcp` is not a transition. They also pin that approval stays bound to
   content (`_request_canonical_approval` re-checks the slug, and the content-digest gate
   applies) rather than to the client.

### Slice C: redacted pinned intent parks for input

1. In `context_assembly._resolve_work_item_intents` / assembly: when the pinned
   `resume_intent` is `text_redacted`, or its text is unavailable, raise a new typed
   `ResumeIntentUnavailable(work_item_id, execution_request_id, intent_id)`. Do not build
   a candidate from the placeholder. Unpinned redacted intents keep today's explicit
   `text_redacted` marker as context, never as the primary instruction.
2. In `run_issue_investigator.py`: catch it and seal an ADR 013 `HumanInputRequest`
   through the existing `_seal_draft` path, with an orchestrator-authored generic
   question and reason. The reason is a fixed string naming only the IDs, along the
   lines of "intent <id> on <wi_> is unavailable; add replacement text as a new intent
   and rebind". The response type is `structured`, whose only accepted field is a
   replacement `intent_id`. Publish the outcome `human-input-requested`. The model is not
   run.
3. The DevLoop needs no new state. The existing `_await_human_input` parks in
   `WAITING_FOR_INPUT`. On the answer, the continuation forwards the new `intent_id`.
   The investigator re-reads it from mctl-api (authorized intent storage). It checks that
   the intent belongs to the same work item and principal, then pins it in place of the
   redacted one. The text never appears in `request.json`, in `answered.json` or in the
   response `value`. If the replacement is also redacted, it parks again, within
   `MAX_CLARIFICATION_ROUNDS`.
4. The check runs when the investigator reads the intent, not when the request is
   enqueued, so redaction after enqueue is covered. Request-side refusal is api#871.

### Ownership

There are no changes to lifecycle claims. A resume over `mcp` goes through the same
`accept_execution_request` path, under the same single DevLoop owner and fencing epoch
(ADR 010). Tests assert that the epoch and owner are unchanged across an `mcp` resume.

### Rollout order (documented, not executed here)

1. Ship investigator and worker images that contain Slice A, Slice B and Slice C. The
   new `investigate_params` keys are inert at this point (stripped by mctl-api).
2. mctl-gitops PR: the investigate CWFT declares `surface`, `actor_kind`, `actor_id`
   (default `""`) and maps them to the flags.
3. mctl-api PR: the operations registry declares the same three keys with validation
   patterns. Only after this release does a live resume seal real provenance; the
   live T5 proof (and closing #573) happens here.
4. Only then enable new MCP execution admission in mctl-api. A mixed-version test shows
   that an old image receiving `--surface mcp` exits non-zero at
   `_validate_work_context_args`, and that an old DevLoop refuses with
   `surface-or-actor-unrecognised`. Both fail closed, and neither seals a wrong
   provenance.

## Alternatives

- **Map `mcp` to `api` at the dispatcher.** This was rejected. It erases a real
  surface transition (Telegram to MCP would still be visible, but MCP to API would not)
  and lies in sealed provenance.
- **Record client or model identity (for example `mcp/claude`, `mcp/codex`) as
  separate surfaces.** This was rejected by the issue. It invents identity that mctl-api
  does not authenticate, and it would wrongly re-arm approval, or suggest reviewer
  independence, on a model switch.
- **Run the redacted intent with the placeholder and let the model ask.** This was
  rejected. The placeholder becomes the pinned primary instruction, the model may act
  on surrounding context, and the question would be model-authored instead of a fixed,
  ID-only request.
- **Refuse to seal when provenance is unknown, instead of sealing null.** This is
  acceptable under the issue. It was not chosen as the default because CLI-launched
  investigations legitimately run without `--surface`. Omitting the field keeps them
  working and never reports a false negative.

## Platform impact

- **Migrations:** none. `surface_transition` becomes optional in the sealed schema in an
  additive way, within `context.mctl.ai/v1alpha1`. Existing documents always carry the
  key, so their bytes and hashes are unchanged. mctl-api does not read
  `surface_transition` (verified on main 2026-10-31: no non-test reference), so no
  mctl-api consumer change is needed; the readers are all in mctl-agents and are covered
  by Task 4.
- **Slice C reachability:** the redacted-intent park is reachable in production only
  while `WORK_ITEM_INTENT_SOURCE` is on. It is currently off (mctl-gitops#2320), so
  Slice C is proven by T8-T10 against fixtures only. Do not claim a live proof for it
  in this PR.
- **Backward compatibility:** legacy surfaces are unchanged. Temporal determinism is not
  affected, because the vocabulary is read in a validator and signal handler. A history
  that refused `mcp` earlier stays refused, and replay sees the same recorded
  rejection. Even so, the change should be checked under `workflow.patched` review
  (Task 2).
- **Resource impact:** negligible. Slice C adds one mctl-api read on rebind.
- **Risks:**
  - Admission is enabled before the images roll out. Mitigation: the documented order,
    plus fail-closed mixed-version tests.
  - The approval appears to "carry over" across a client switch. Mitigation: approval is
    content-bound and attempt-bound. Tests cover both unchanged and changed content.
  - Replacement text leaks into public gitops. Mitigation: the response schema accepts
    only an `intent_id`, and a test greps `request.json` and `answered.json` for the
    text.
