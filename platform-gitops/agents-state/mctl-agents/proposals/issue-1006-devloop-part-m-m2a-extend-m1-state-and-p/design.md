# Design: issue-1006-devloop-part-m-m2a-extend-m1-state-and-p

## Current state

What M1 (#998) already ships, read in the clone at `0a7385d`:

- **Request identity.** `ResumeDelivery` (`orchestrator/temporal/workflows/dev_loop.py`, around line 1053) has
  the defaulted fields `intent_id: int | None = None`, `expected_state_version: int = 0` and
  `resumed_from_execution_id: str = ""`. `Dispatcher._dispatch` (`orchestrator/temporal/dispatcher.py`, around
  line 436) fills all three from `xr.ExecutionRequest`. Covered by
  `tests/test_deferred_resume_m1.py::test_a_pre_m1_resume_delivery_payload_decodes_with_the_identity_defaults`,
  `...round_trip`, and `tests/test_execution_request_resume.py::test_the_dispatcher_hands_the_loop_the_requests_identity`.
  Nothing is missing here; M2a only tightens the tests.
- **Marker.** `DEFERRED_RESUME_PATCH = "deferred-resume-contract"` (around line 432) is evaluated once, at the
  only fresh `_gates_passed = True` site in `run` (around line 4299). The other site, `_resume_merge_watch`
  (around line 4521), restores `resume.deferred_resume_contract` and does not re-evaluate it. Both `_carry_work_context`
  (around line 4353) and `_resume_merge_watch` carry it. `tests/test_patch_memoization.py` has no case for this
  marker (a grep for `deferred`/`DEFERRED` finds nothing). The replay checks live in
  `tests/test_execution_request_replay.py` (`DEFERRED_RESUME_HISTORY = dev_loop_deferred_resume.json`, around line 94).
- **Validator.** `_validate_execution_request` (around line 2740) applies one ordered list after the gates:
  `work_merged` (refused), `legacy-loop`, `implement-running` (deferred), `no_actionable_intent` (refused),
  `recovery-not-ready`, `feedback-not-ready` (deferred). `RESUME_DEFERRAL_REASONS` (around line 499) is the closed
  deferral vocabulary. `_deliver` (around line 2891) fails a delivery `accepted_after_gates` closed with
  `feedback-not-ready`. The matrix test is
  `tests/test_execution_request_resume.py::test_the_validator_fences_a_resume_after_the_gates`.
- **Vocabulary.** `orchestrator/work_context/execution_requests.py` holds `WORK_MERGED`, `NO_ACTIONABLE_INTENT`,
  `LEGACY_RESUME_REFUSAL_REASONS = {"work-merged", "nothing-to-resume"}` and `RESUME_REFUSAL_REASONS`.
  `TemporalClientPort.deliver` normalises unknown refusal and deferral reasons to `unspecified`. The real-port
  legacy decode tests are at the end of `tests/test_deferred_resume_m1.py`.
- **State that is missing.** No `_feedback_done` or `_pending_feedback` exists anywhere (grep). `MergeWatchResume`
  (around line 1583) has no feedback fields.
- **PR reads are not tri-state.** `orchestrator/temporal/activities/pr_state.py::get_pr_state` resolves the PR
  from the proposal's `.status.yaml`. It returns `PRState(found=False)` both for "no `pr:` field" and for a
  404, and its own docstring says GitHub answers unauthorised and missing lookups the same way. A
  transport failure raises. There is no PR-by-branch read and no branch-existence read in the Temporal layer.
  `run_implementer._branch_exists_on_origin` (around line 2546) is a git-CLI helper inside the implementer pod,
  and is not usable from the dispatcher.
- **Dispatcher on a closed loop.** `_dispatch` never asks `loop_state` before `deliver()`, except inside
  `_reconcile_closed_loops`. A resume for a closed loop goes into Update-with-Start, which starts a new run for
  the issue (re-investigation). Task 4b's refusal belongs exactly here, and it is not implemented.
- **Work item client.** `orchestrator/work_context/client.py` `ROUTES` has `execution_request`
  (`/api/v1/work-items/{id}/execution-requests/{request_id}`, one request) plus claim, fulfil and reject. There
  is no route that lists a work item's requests.
- **Observability.** There are queries such as `implement_execution`, `work_context` and
  `holds_execution_request`. There is no `contract_state` query, and `orchestrator/temporal/cli.py` has no
  `contract-drain-check` subcommand.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: image tag `1.117.0`, and
  `EXECUTION_REQUEST_DISPATCHER: "true"` (line 139). The dispatcher is live, so M2a must not change its
  decision path.
- A grep for `DEVLOOP_DEFERRED` / `DEVLOOP_` in `services/*/mctl-agents-worker*/values.yaml` matched nothing,
  so the feedback switch is not set (OFF).
- `agents-state/mctl-agents/proposals/issue-993-.../.status.yaml`: `needs-triage`, failure `no-commits`. It is
  read as provenance and not touched. The #993 `tasks.md` is the source of the task numbers used here.
- I made no mctl MCP calls. The mctl-api execution-request list contract could not be observed from this run.
  It is recorded under Open questions; I do not conclude that it is absent.

## Proposed solution

M2a has five parts. None of them changes a live decision.

### 1. Tests first (task 1, the subset for this slice)

New file `tests/test_deferred_resume_m2a.py`, plus extensions to existing files. Each test is written before
its behaviour and is mutation-checked: revert the line under test, watch the test fail, and record that in the
PR body.

- T1 strengthened: one parametrised test per identity field, where the dispatcher sends a distinct non-default
  value. The mutation is to drop one field in `_dispatch`.
- T2/T3/T4 end-to-end: run the real `DevLoopWorkflow` in the time-skipping environment that
  `test_execution_request_resume.py` already uses. A resume after MERGED is refused `work_merged`, with no
  fulfil and with `intent_id` intact on the row. A redelivery of the same request gives the same answer. A
  `legacy-loop` deferral gives no `Succeeded`.
- T4 replay: replay every fixture in `tests/fixtures/histories/`. Add a `test_patch_memoization.py` case: the
  marker is recorded exactly once on the fresh path and never on the `_resume_merge_watch` path.
- T9b extended: no legacy spelling appears as a minted literal in `dispatcher.py` or in the new
  `closed_loop.py`.
- Red tests for later slices are marked `xfail(strict=True)` with a named owner (see tasks.md, "Red until
  their owning slice").

### 2. Feedback state (task 3)

In `dev_loop.py`:

- `__init__`: `self._feedback_done: set[str] = set()` and `self._pending_feedback: tuple[str, ...] = ()`.
- `MergeWatchResume`: `feedback_done: tuple[str, ...] = ()` and `pending_feedback: tuple[str, ...] = ()`,
  placed beside `deferred_resume_contract`, with a comment that they are carried and never re-derived.
- `_carry_work_context` adds `feedback_done=tuple(sorted(self._feedback_done))` and
  `pending_feedback=self._pending_feedback`. The order of `pending_feedback` is acceptance order, which is
  deterministic because it is a tuple. Sorting the set follows the existing `seen_execution_ids` rule: no hash
  order is allowed into recorded state.
- `_rehydrate_work_context` restores both exactly as carried. It does not filter `pending_feedback` against
  `open_deliveries`. An inconsistency is shown through `contract_state` rather than silently dropped, because
  unknown never means absent.
- No writer is added. Task 6 (the feedback tick) adds the writers and the dedupe guard.

These fields are additive data in the continue-as-new input. They create no new command and no new
`patched()` call, so recorded histories replay the same command sequence.

### 3. Closed-loop contract primitives (tasks 4 and 4b, the safe portions)

New module `orchestrator/temporal/closed_loop.py`, stdlib plus `httpx` as in `pr_state.py`. It contains:

- `PRRead(verdict: Literal["open","merged","closed","absent","unknown"], url: str = "", reason: str = "")`,
  `BranchRead(verdict: Literal["exists","absent","unknown"], reason: str = "")` and
  `GatesRead(verdict: Literal["passed","not-passed","unknown"], reason: str = "")`.
- `read_pr_by_branch(repo, branch)`: `GET /repos/{repo}/pulls?head=mctlhq:{branch}&state=all`. A 200 list
  becomes `absent` when empty, `merged` if any entry has `merged_at`, then `open`, then `closed`. Every other
  status, and any parse error or missing token, becomes `unknown`.
- `read_branch(repo, branch)`: first `GET /repos/{repo}` (a 200 is required), then
  `GET /repos/{repo}/branches/{branch}`. A 200 means `exists`. A 404 means `absent` only after the repository
  read succeeded. Anything else means `unknown`.
- `read_gates(service, slug)`: reads `.status.yaml` in the same way as `get_pr_state`. `accepted`,
  `implementing`, `review-fixing` and `merged` mean `passed`. `proposed` means `not-passed`. Anything else, an
  absent file or a failed read means `unknown`.
- `ClosedLoopReadPort` (a Protocol) with these three async reads, and `GitHubClosedLoopReads` as the real
  implementation.
- `closed_loop_decision(loop_state, intent_id, pr, gates)`, a pure function, first match wins:
  1. `loop_state == running`: `pass` (the loop's own validator decides).
  2. `pr.verdict == merged`: `refuse:work_merged`.
  3. `pr.verdict == unknown`: `defer:closed-loop-unobserved`.
  4. `intent_id is None`: if `gates == passed` then `refuse:no_actionable_intent`; if `gates == unknown`
     then `defer:closed-loop-unobserved`.
  5. Otherwise `pass`. Today's behaviour stays: Update-with-Start, with reinvestigation guarded later by
     task 9.

  Refusal reasons are `xr.WORK_MERGED` and `xr.NO_ACTIONABLE_INTENT`. The legacy spellings are never minted.
- `dispatcher.DEFERRAL_AUDITED` gains `CLOSED_LOOP_UNOBSERVED = "closed-loop-unobserved"`. Nothing emits it
  in M2a.

`Dispatcher` is not changed to call any of this. Wiring (around `_dispatch`, between
`_reconcile_closed_loops` and `deliver()`, behind an injected port that defaults to `None`) is M2c's job. The
full T2b dispatcher test is written now as a strict xfail.

### 4. Read-only observability (task 4)

- `ContractState` frozen dataclass. `@workflow.query def contract_state(self) -> ContractState`, which returns
  `contract=self._deferred_resume_contract`, `gates_passed`, `initialized`, `implement_stage`,
  `implement_outcome`, `last_pr_state` (`"unknown"` when `_last_pr is None`), `open_request_ids` (sorted),
  `pending_feedback` and `feedback_done` (sorted). A query records no history event and needs no patch.
- `cli.py contract-drain-check`: lists the running DevLoop workflows with
  `client.list_workflows('WorkflowType="DevLoopWorkflow" AND ExecutionStatus="Running"')` and queries
  `contract_state` on each, with the same `DELIVERY_TIMEOUT_SECONDS` bound as `holds_request`. It classifies
  each loop as `contract`, `legacy` (gates passed and contract False), `pre-gates` or `UNKNOWN` (query error,
  timeout, or a worker without the handler), and prints one line per loop plus totals. Exit code 0 when all
  loops are classified; 2 when any is `UNKNOWN` or the listing failed. A failed listing prints `UNKNOWN`,
  never `0`.

### 5. Execution-request list read (task 4b dependency): investigate, then implement or stop

1. Confirm the contract from mctl-api's source, read only:
   - the route, which the MCP tool `mctl_list_work_item_execution_requests` implies;
   - the envelope (`schema_version`, list key);
   - pagination and completeness;
   - whether the dispatcher's service principal may call it.
2. If it is confirmed: add `ROUTES["list_execution_requests"]` and
   `WorkItemClient.list_execution_requests(work_item_id) -> xr.RequestsAnswer`, using
   `xr.answer_from_list(status, payload)`. The verdict is `FOUND` only when the envelope matches, every entry
   parses through `ExecutionRequest.from_payload`, and the list is complete (no further page). Otherwise the
   verdict is `UNKNOWN`. It is a GET with no policy-checkpoint operation, like `execution_request`. Unit tests
   use the existing fake API in `tests/test_execution_request_dispatch.py`.
3. If it is not confirmed: add nothing. Write `DEPENDENCY: mctl-api execution-request list (route/envelope/
   completeness/principal) unconfirmed` in the PR body and in `docs/temporal-flow.md`, and keep the test as a
   strict xfail.

No API is invented, and no other repository is edited.

## Alternatives

- **Wire `closed_loop_decision` into `_dispatch` behind a new env switch that defaults to OFF.** Rejected for
  M2a. The dispatcher is live (`EXECUTION_REQUEST_DISPATCHER: "true"`). Even an OFF switch adds a branch to the
  production path and a new flag to govern, and the issue limits this slice to "independently safe portions".
  Wiring together with its switch belongs in M2c, next to the feedback-switch read (task 5).
- **Extend `PRState` / `get_pr_state` to be tri-state instead of adding a new module.** Rejected. `get_pr_state`
  is a recorded activity used by `_watch_pr` across hops, and changing its return semantics risks behaviour
  changes in running merge watches. Its "raise on transport error" contract is also relied on by Temporal
  retries. A separate dispatcher-side read keeps the workflow activity untouched.
- **Store the full `OpenDelivery` in `pending_feedback`.** Rejected. Open deliveries are already carried in
  `open_deliveries`, and duplicating them creates two sources of truth that a hop could make diverge. Ids
  referencing `open_deliveries` are enough, and their consistency is visible through `contract_state`.

## Platform impact

- **Migrations and replay.** No new `workflow.patched` call and no new command. The new `MergeWatchResume`
  fields are defaulted, so pre-M2a records decode to empty. The query is not recorded. Every fixture in
  `tests/fixtures/histories/` must replay green.
- **Backward and forward compatibility.** A worker without M2a that receives a hop payload with the new keys
  depends on Temporal's dataclass converter ignoring unknown keys. M2a adds a test that pins the behaviour. If
  the converter does not ignore them, the PR body must state that a rollback requires no hops recorded by M2a
  workers. Because the fields are always empty in M2a, a rollback loses no information.
- **Runtime.** There are no new activities and the dispatcher hot path is unchanged. The CLI and query are
  operator-invoked. The new GitHub reads are not called in production in M2a.
- **Risks and mitigations.**
  - Accidental activation: the dispatcher construction sites stay unchanged, and a test asserts that
    `Dispatcher` has no reference to `closed_loop`.
  - A false "absent" from a 404: the repository probe is required, and a test covers a 404 on the repository
    returning `unknown`.
  - Red tests breaking CI: strict xfail with a named owner.
  - Silent completion: the PR body carries the "not done in M2a" list.
- **Flags and release.** No flag added or flipped, no release, no deploy. #1003 stays Draft and the release
  hold stays ON. A PR, if one is later authorised, needs independent review, green checks and explicit owner
  merge approval.
