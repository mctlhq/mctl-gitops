# Design: issue-996-feat-devloop-m1-deferred-resume-identity

## Current state
All paths are in the `mctlhq/mctl-agents` clone at `a99c888`.

- `orchestrator/temporal/dispatcher.py` `Dispatcher._dispatch` (around line 413) builds `ResumeDelivery(execution_request_id, work_item_id, surface, actor_kind=RESUME_ACTOR_KIND, actor_id=request.requested_by, kind)`. It sends that through `TemporalClientPort.deliver`: Update-with-Start of `accept_execution_request`, with update id = request id. It calls `_fulfil` (which mints the `we_`) only after the Update answered `accepted`. `deliver` maps `ResumeRefused` to `DELIVERY_REFUSED`, normalising the reason against `xr.RESUME_REFUSAL_REASONS`. It maps `ResumeDeferred` to `DELIVERY_DEFERRED` and passes the free-text reason through to `_defer`, which only audits it.
- `orchestrator/work_context/execution_requests.py` `ExecutionRequest` already parses `intent_id: int | None`, `expected_state_version: int = 0` and `resumed_from_execution_id: str = ""`. The dispatcher drops all three before they reach the loop. `RESUME_REFUSAL_REASONS` is the closed vocabulary after `resume_refused:`.
- `orchestrator/temporal/workflows/dev_loop.py`:
  - `ResumeDelivery` (line ~1032) is a frozen dataclass with defaulted fields (`kind` defaults to `resume` for pre-#461 payloads).
  - `OpenDelivery` is carried across continue-as-new.
  - `accept_execution_request` / `_validate_execution_request` (lines ~2647-2747) apply the `resume` signal's rules. Reasons today: `malformed-delivery`, `loop-active`, `loop-not-ready`, `loop-ending`, `work-item-mismatch`, `resume-already-pending`, and the provenance refusals.
  - `_deliver` (line ~2753) is gated by `EXECUTION_REQUEST_RESUME_PATCH`. After binding, it waits for `_abandoned or _is_approved() or _gates_passed or ...` and lands `Succeeded` when `_is_approved() or _gates_passed`. So a delivery onto a loop whose gates already passed lands `Succeeded` immediately and does no work. `tests/test_execution_request_resume.py::test_a_resume_delivered_after_the_implement_step_succeeds_at_once` pins exactly that.
  - `_gates_passed = True` is set in `run` just before `_implement` (line ~4234) and in `_resume_merge_watch` (line ~4452).
  - `_implement_state: ImplementExecutionState` has `stage` "" or "implementer" and `outcome` None until the step ends. It is carried in `MergeWatchResume.implement_state`.
  - `_watch_pr` keeps the last `PRState` (`orchestrator/temporal/activities/pr_state.py`, with `state` OPEN/MERGED/CLOSED and `merged`) in a local `last`, and carries it as `MergeWatchResume.last_pr`.
  - Patch ids are module constants, for example `EXECUTION_REQUEST_RESUME_PATCH`, `CONTEXT_ONLY_RESUME_PATCH` and `PROPOSAL_TERMINAL_PATCH`. `tests/test_patch_memoization.py` documents that an unpatched branch is sticky for the life of an execution, and that decisions are carried across hops instead of being re-evaluated (`MergeWatchResume.proposal_terminal_end`).
- Tests and fixtures:
  - `tests/test_execution_request_resume.py` contains the validator parametrisation `test_the_validator_answers_with_the_resume_rules` and the `_validator(**state)` helper.
  - `tests/test_execution_request_replay.py` replays `tests/fixtures/histories/dev_loop_{dispatched,resumed,issue_keyed,delegated,issue_started_delegated}.json`.
  - `tests/test_execution_request_dispatch.py` covers the dispatcher.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: the worker runs image `ghcr.io/mctlhq/mctl-agents` at tag `1.117.0`, bumped by hand.
- Grep of `$MCTL_GITOPS_ROOT/services` for `DEVLOOP_DEFERRED_FEEDBACK`, `DEVLOOP_IMPLEMENT_HOLD` and `EXECUTION_ORPHAN_SWEEP`: no matches. None of these flags is configured on any deployed service values file, which is consistent with "OFF". The clone has no code reading them either.
- I did not call the mctl MCP tools. The gitops values were sufficient, and M1 changes no deployed configuration. I did not observe live Temporal histories, so whether any in-flight loop is currently past its gates is unknown (see Open questions in requirements.md).

## Proposed solution
The solution is option (b) of the issue: an explicit, fail-closed typed `ResumeDeferred(feedback-not-ready)` until an approved M2 is installed. Everything is decided by state the workflow already holds, plus one marker.

### 1. Request identity
- `ResumeDelivery` gets three new fields: `intent_id: int | None = None`, `expected_state_version: int = 0`, `resumed_from_execution_id: str = ""`. They go after `kind`, and all are defaulted, so old Update payloads (in histories and in `OpenDelivery` carried through `MergeWatchResume`) decode unchanged.
- `Dispatcher._dispatch` passes `request.intent_id`, `request.expected_state_version` and `request.resumed_from_execution_id`. Actor, surface, request id (= update id, the idempotency key) and kind are unchanged.

### 2. Replay-safe contract marker
- Add `DEFERRED_RESUME_PATCH = "deferred-resume-contract"`, with a comment block in the style of its neighbours.
- `__init__` gets `self._deferred_resume_contract = False`.
- In `run`, immediately before `self._gates_passed = True`: `self._deferred_resume_contract = workflow.patched(DEFERRED_RESUME_PATCH)`. The patch is evaluated in the workflow body, never in the validator, because a validator must not issue commands.
  - A history that passed this point before M1 replays the call without a marker and gets False. It stays a `legacy-loop` for its whole life (patch memoization).
  - A loop still waiting for approval when M1 deploys reaches the point live and records the marker.
  - The marker is the only command added. No activity, timer or signal is introduced.
- `MergeWatchResume.deferred_resume_contract: bool = False` is set by `_carry_work_context` and restored in `_resume_merge_watch` without re-evaluating the patch. A pre-M1 hop record therefore decodes as legacy.
- Add `self._last_pr: PRState | None`. It is assigned wherever `_watch_pr` updates its local `last`, and restored from `resume.last_pr`. This is a pure state assignment and adds no command.

### 3. Validator fence and typed outcomes
A new block in `_validate_execution_request` sits after the existing `resume-already-pending` and provenance checks, so existing reasons keep their precedence. It applies only to `kind == resume` deliveries that are not this run's own start request, and only `if self._gates_passed:`.

```
if not self._deferred_resume_contract:            -> ResumeDeferred  "legacy-loop"
st = self._implement_state
if st.stage == "implementer" and st.outcome is None: -> ResumeDeferred  "implement-running"
pr = self._last_pr
if pr is not None and pr.merged:                  -> ResumeRefused   "work-merged"
if (st.outcome not in (None, "success")) or (pr is not None and pr.state == "CLOSED")
   or delivery.intent_id is None:                 -> ResumeRefused   "nothing-to-resume"
otherwise (intent, PR open or not yet observed):  -> ResumeDeferred  "feedback-not-ready"
```

- A rejected Update writes no history event, and the Python SDK does not run validators on replay. The fence is therefore replay-neutral, and the dispatcher never reaches `_fulfil`, so no `we_` is minted.
- Name the constants: `RESUME_DEFERRAL_REASONS` (in `dev_loop.py`, re-exported to the dispatcher) = `{loop-not-ready, loop-ending, legacy-loop, implement-running, feedback-not-ready}`. Add `work-merged` and `nothing-to-resume` to `xr.RESUME_REFUSAL_REASONS`.
- `TemporalClientPort.deliver` normalises a deferral reason outside `RESUME_DEFERRAL_REASONS` to `unspecified`, mirroring the refusal path. `_defer` audits `resume_deferred:<reason>`.
- Idempotence is unchanged. A refused or deferred update id is not in Temporal's registry, so a re-send is validated again. Once accepted, `_accepted_request_ids` makes repeats a no-op. There is never a second delivery.

### 4. Interim state transitions (no feedback slice)
| Loop state at delivery | Before M1 | M1 |
|---|---|---|
| gates not passed | accept; `Succeeded` on approval | unchanged |
| gates passed, legacy history | accept; `Succeeded` at once | `ResumeDeferred(legacy-loop)`, no `we_` |
| gates passed, implement running | accept; `Succeeded` at once | `ResumeDeferred(implement-running)` |
| gates passed, PR merged | accept; `Succeeded` at once | `ResumeRefused(work-merged)` |
| gates passed, implement failed / PR closed / no intent | accept; `Succeeded` at once | `ResumeRefused(nothing-to-resume)` |
| gates passed, intent, PR open or unknown | accept; `Succeeded` at once | `ResumeDeferred(feedback-not-ready)` |

Defence in depth: `OpenDelivery` gets `accepted_after_gates: bool = False`, set in `accept_execution_request` from `self._gates_passed and self._deferred_resume_contract`. In `_deliver`, after the bind, a delivery with that flag lands `Failed` with refusal `feedback-not-ready` instead of entering the `Succeeded` wait. This uses the existing `_land_delivery` path, so there is no new command type. It is reachable only under the marker. With the validator in place it should be unreachable, and a unit test proves it fails closed if reached anyway.

M2 will later replace the `feedback-not-ready` arm behind its own new patch id. M1 never consults any env flag.

## Alternatives
- **Option (a): do not record the contract at all, and only fence delivery.** This was dropped. Without a marker, M2 cannot distinguish loops that passed their gates under the M1 fence from legacy ones, and the issue asks for the marker in M1.
- **Refuse (`ResumeRefused(feedback-not-ready)`) instead of deferring.** This was dropped because it permanently destroys a valid human request that M2 could serve. Deferral keeps it claimed and fail-closed. The open-request cost is recorded as an open question.
- **Evaluate `workflow.patched` inside the validator.** This was rejected: validators must not issue commands, and a patch call there would be non-deterministic relative to history.
- **Keep accepting and fail the execution in `_deliver`.** This was rejected as the primary mechanism because it mints a `we_` for work that will not happen. It is kept only as the defence-in-depth arm.

## Platform impact
- **Migrations:** none. All new dataclass fields are defaulted, so old Update payloads, `OpenDelivery` and `MergeWatchResume` records decode unchanged.
- **Temporal replay:**
  - The only new command is the `DEFERRED_RESUME_PATCH` marker, at a point every pre-M1 gates-passed history replays as False.
  - Validator changes do not affect replay.
  - All fixtures in `tests/fixtures/histories/` must replay unchanged. A new fixture, recorded with the marker, is added.
- **Behaviour change for in-flight loops:** gates-passed loops now defer (`legacy-loop`) instead of landing a false `Succeeded`. Deferred requests occupy the item's single open-request slot until they are resolved. They are visible as `resume_deferred:<reason>` in the dispatcher audit.
- **Compatibility with mctl-api:** the new refusal reasons are emitted only after the dispatcher's closed vocabulary includes them. An older mctl-api reading the reason as opaque text is unaffected. Nothing is enabled in mctl-api, and #934 stays Draft.
- **Resource impact:** negligible (one marker per loop, one dataclass reference).
- **Risk:** the dispatcher re-claims deferred requests on each lease expiry, which is extra polling load. The lease already bounds this. Risk: the existing test that asserts `Succeeded`-at-once is rewritten. The PR must say so explicitly for the merge decision.
- **Release:** no release, deploy or flag change. The PR is left for an explicit human merge decision.
