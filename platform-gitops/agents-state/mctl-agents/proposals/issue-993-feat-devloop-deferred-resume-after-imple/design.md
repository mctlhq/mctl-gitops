# Design: issue-993-feat-devloop-deferred-resume-after-imple

## Current state
All paths are in the read-only clone of `mctlhq/mctl-agents` at `main` (a99c888). The clone does NOT contain
PR #992: `IMPLEMENT_EXECUTION_PATCH` and `_hold_canonical_for_implement` are absent. This design therefore
builds on the #991 proposal's design (`agents-state/mctl-agents/proposals/issue-991-feat-devloop-pass-execution-id-to-the-im/design.md`,
status `implemented`, PR #992 open) and assumes that design's mechanics: the hold is decided at the flip site,
and the end of the hold comes after `_implement`.

Delivery path (`orchestrator/temporal/workflows/dev_loop.py`):
- `ResumeDelivery` (~:1032) carries only `execution_request_id`, `work_item_id`, `surface`, `actor_kind`,
  `actor_id` and `kind` (defaulted `resume`). The request's `intent_id`, `expected_state_version` and
  `resumed_from_execution_id`, which `ExecutionRequest` (`orchestrator/work_context/execution_requests.py`
  ~:138-207) does parse, are dropped by `Dispatcher._dispatch` (`orchestrator/temporal/dispatcher.py` ~:434-441).
- `accept_execution_request` (~:2647) and its validator `_validate_execution_request` (~:2696) refuse with
  `ResumeRefused` (permanent; the dispatcher rejects `resume_refused:<reason>`, and the reason must be in
  `xr.RESUME_REFUSAL_REASONS`) or `ResumeDeferred` (transient). Neither validator looks at
  `_gates_passed` or the PR state.
- `_deliver` (~:2753) binds the fulfilled `we_`, then waits for
  `self._abandoned or self._is_approved() or self._gates_passed or ...` (~:2831). It lands `Succeeded` when
  `decided = (self._is_approved() or self._gates_passed) and not self._abandoned` (~:2833). After the implement
  step, `_gates_passed` is already True (set at ~:4234 before `_implement`, and at ~:4452 in
  `_resume_merge_watch`), so the delivery ends `Succeeded` at once and no work is done. That is the silent no-op
  the issue describes. `tests/test_execution_request_resume.py::test_a_resume_delivered_after_the_implement_step_succeeds_at_once`
  (~:580) asserts exactly this.
- `_land_delivery` (~:2838) advances the `we_` with retries and keeps a pending phase across hops.
  `_end_delivery` (~:2899) records a `ResumeRejection` when there is a refusal string. `OpenDelivery` (~:1053)
  is carried across continue-as-new.
- Merge watch: `_watch_pr` (~:6227) runs `_shepherd_tick(service, slug)` (~:4949) on tick boundaries. With
  `concurrent_ticks` it runs one tick task at a time (~:6571-6593). `_shepherd_tick` submits
  `mctl-agents-shepherd` with `service`, `slug`, the agent image and `_launch_correlation()` (~:4586). A failed
  tick is logged, not raised. `orchestrator/run_shepherd.py` already has the `--review-feedback` implementer
  path (~:21, ~:2967-3173).
- Closed-loop path: a delivery to a closed loop is an Update-with-Start
  (`TemporalClientPort.deliver`, dispatcher ~:258-300) of `dev-loop-<owner>-<repo>-<n>`. A resumed investigate
  on a proposal past `proposed` writes a context-only snapshot and ends (`CONTEXT_ONLY_RESUME_PATCH`, ~:447).
  The proposal is rewritable only if its status is in `_OVERWRITABLE_PROPOSAL_STATUSES = {"proposed"}`
  (~:458), which mirrors `run_issue_investigator._OVERWRITABLE_STATUSES` (~:299, used at ~:3528 and the
  post-agent re-check ~:4199).
- Orphan reconciliation: `Dispatcher._reconcile_closed_loops` (dispatcher ~:534-604) fails a non-terminal
  `<loop>#xr_*` or `<loop>#run_*` execution whose loop is not RUNNING, or whose running run does not hold
  the request. It is called only from `_dispatch` (~:432), i.e. only after a request has been claimed.
  `_end_if_orphaned` (~:470) covers the fulfil race only. While a `we_` is open, mctl-api refuses to create a
  request, so after a terminated loop nothing ever triggers the reconciliation.
- Dispatcher enablement: `dispatcher.enabled()` reads `EXECUTION_REQUEST_DISPATCHER` (~:90, ~:185), default off;
  it is started from `orchestrator/temporal/worker.py` (~:885).
- Docstrings: `_await_canonical_reapproval` (~:2462) and `_launch_correlation` (~:4586) describe the
  pre-#991 shape. #992 makes them inaccurate: the canonical `we_` is now held through implement, and
  `execution_id` is sent to implement only, not through `_launch_correlation`.
- Tests: `tests/test_execution_request_resume.py`, `tests/test_execution_request_dispatch.py`,
  `tests/test_execution_request_replay.py`, the replay harness in `tests/test_workflow_replay.py` /
  `tests/replay_scenarios.py` with histories in `tests/fixtures/histories/`, and `tests/test_patch_memoization.py`.
- ADRs: `docs/adr/011-work-item-resume-contract.md` and `011-execution-identity-contract.md` are the contracts
  this extends; the latest ADR number is 025.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: image tag `1.117.0` (~:27);
  `EXECUTION_REQUEST_DISPATCHER: "true"` (~:139). This confirms the issue: the dispatcher is on in production.
- The `mctl-agents-worker-exec` and `mctl-agents-worker-implement` services exist under `services/admins/`.
  A grep for `IMPLEMENT_EXECUTION` / `EXECUTION_REQUEST` found nothing in them.
- `.../proposals/issue-991-.../.status.yaml`: status `implemented`, PR #992, `github.state: open`.
- Not checked: the shepherd CWFT (`argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`). That
  directory is outside the gitops paths available to this run, so I could not observe whether it declares
  `intent_id` / `execution_request_id` params or an output. The mctl-api #931 source and its capability surface
  were not readable. No mctl MCP tool calls were made (the gitops checkout covered the worker config). All three
  gaps are recorded under Open questions.

## Proposed solution

### 1. Carry the full request identity (dispatcher + `ResumeDelivery`)
Add defaulted fields to `ResumeDelivery`: `intent_id: int = 0` (0 = none), `expected_state_version: int = 0`,
`resumed_from_execution_id: str = ""`. `Dispatcher._dispatch` fills them from `ExecutionRequest`. A
recorded payload without these fields decodes to the defaults. `execution_request_id` is already the Update id and
the idempotency identity (one surface idempotency key maps to one request in mctl-api). It is kept as the dedupe key.

### 2. New contract marker
`DEFERRED_RESUME_PATCH = "deferred-resume-contract"`, declared beside `EXECUTION_REQUEST_RESUME_PATCH` with the
usual migration-by-attrition comment. It is recorded once, where the loop sets `_gates_passed = True` (both
sites, ~:4234 and ~:4452), into `self._deferred_contract: bool`, and carried in `MergeWatchResume` as a
defaulted field. Validators must not record commands, so they read only this flag. A history recorded without
the marker never sets it and keeps today's command sequence, including the at-once `Succeeded`.

New loop state, carried across continue-as-new through defaulted `MergeWatchResume` fields:
`_implement_running: bool`, `_pr_merged: bool` (set when `_watch_pr` observes MERGED),
`_feedback_done: frozenset[str]` (request ids whose tick has run), and `_pending_feedback: FeedbackRequest | None`.

### 3. Validator decisions (refuse before a `we_` is minted)
In `_validate_execution_request`, after the existing checks and only if `self._deferred_contract`:
- `_implement_running` -> `ResumeDeferred("implement-running")`. With #931 the claim guard should prevent this
  case. It is kept as defence in depth.
- `_pr_merged` -> `ResumeRefused("work-merged")`.
- `kind == resume and intent_id == 0` -> `ResumeRefused("nothing-to-resume")`.
Add `work-merged`, `nothing-to-resume`, `implement-running` to `xr.RESUME_REFUSAL_REASONS`, so the dispatcher
forwards them and does not collapse them to `unspecified`.

### 4. `_deliver` after gates: one feedback tick, typed outcome
In `_deliver`, replace the `_gates_passed` short-circuit for contract loops. When `self._deferred_contract` and
`self._gates_passed`:
1. If `rid in self._feedback_done`, do nothing more (redelivery after a hop).
2. Check the grant binding with `_feedback_authority_valid()`: the `aar_` the flip spent, the approved content
   digest recorded at the flip, and the approver authority must still match the live proposal. This reuses the
   grant-freshness reads behind `GRANT_FRESHNESS_PATCH`. If the check fails, land `Failed` with refusal
   `reapproval-required`. This covers changes to content and authority, not only actor or surface changes.
3. Otherwise set `self._pending_feedback = FeedbackRequest(rid, intent_id, actor, surface)` and wait for the
   watch to run it (or for `_exiting` / `_hopping` / `_abandoned`).
4. `_watch_pr` checks `_pending_feedback` at each poll, in addition to the cadence, and runs one tick under the
   existing single-tick rule. This tick does not consume the cadence budget. It calls
   `_shepherd_tick(service, slug, feedback=...)`, which adds `intent_id`, `execution_request_id` and
   `feedback_actor` to the CWFT params and reads a structured `feedback_outcome` from the result. Before
   awaiting the tick, the request id is added to `_feedback_done`. A crash after that point fails closed, never
   twice. Temporal replay is deterministic, so replay adds no second tick.
5. `run_shepherd` gets a `--feedback-intent` mode. It fetches the intent text through the work-context client
   (`list_intents`), and runs a scope classification against the approved `requirements.md` / `design.md`:
   `in-scope` or `scope-expansion`. For `in-scope` it runs the existing `--review-feedback` implementer, under
   the same lifecycle claim, `--match-head-commit` fencing, independent review and CI gates. It emits one of
   `processed` (a commit was pushed, or the feedback was shown to be addressed already, with evidence),
   `scope-expansion`, `failed` or `unobservable`.
6. `processed` -> land `Succeeded`. Anything else -> land `Failed` with the refusal `scope-expansion`,
   `feedback-failed` or `feedback-unobservable`, recorded as a `ResumeRejection`. A tick that fails as an
   activity is `feedback-failed`.
7. If the watch ends before the tick runs (PR merged or closed, or the deadline passes), land `Failed` with
   `work-merged` or `feedback-not-run`.

### 5. Implement Failed / Cancelled / TimedOut -> closed-loop path
A loop whose implement did not succeed skips the merge watch and ends. The canonical `we_` ends `Failed`.
The queued request is then claimed and Update-with-Start starts a new run. Widen the guard in both mirrors
(`run_issue_investigator._OVERWRITABLE_STATUSES` usage at ~:3528 / ~:4199, and the loop's
`_OVERWRITABLE_PROPOSAL_STATUSES`) by adding a predicate, not by changing the set. A dispatched `resume` that
pins an available intent may rewrite a proposal whose status is `accepted` or `needs-triage`, if both hold:
`.status.yaml` has no `pr`, and GitHub shows no open or merged canonical `feat/agents-<slug>` PR. The rewrite
writes `proposed` with the pinned intent recorded. The loop then parks on the normal canonical approval, so
nothing implements without a fresh human grant. The loop-side decision is guarded by the same
`DEFERRED_RESUME_PATCH` at the context-only branch. Old histories keep ending context-only.

### 6. Orphaned-execution sweep (no claim needed)
Move the per-execution decision in `_reconcile_closed_loops` into a pure helper `_orphan_verdict(execution, loop)`
that both callers share. Add `Dispatcher.sweep_orphans_once()`, run by `run_dispatcher` every
`EXECUTION_ORPHAN_SWEEP_SECONDS` (default 300) in the same task. It does not depend on claims:
- Source A (preferred, if #931 provides it): mctl-api lists the work items that have a non-terminal `temporal`
  execution with a queued request. The sweep applies `_orphan_verdict` and the same Failed attach.
- Source B (fallback, mctl-agents-only): Temporal visibility,
  `WorkflowType='DevLoopWorkflow' AND ExecutionStatus!='Running' AND CloseTime > now-48h`. For each closed run it
  resolves the work item from the start memo, which gains a `work_item_id` entry for new starts in
  `orchestrator/temporal/start.py` and the dispatch start op. Then it GETs the item and applies the verdict.
  Every read error skips. Nothing is treated as gone because a read failed.
The sweep ends only executions whose engine ref is this dispatcher's own (`#xr_` or `#run_`) and whose owner is
CLOSED/ABSENT or does not hold them, exactly as today.

### 7. Rollout gate
Add an activity `probe_execution_queue_capability`, which reads a mctl-api capability flag with the worker
identity through the policy checkpoint. Add a marker `IMPLEMENT_HOLD_CAPABILITY_PATCH`, consulted immediately
before #992's `workflow.patched(IMPLEMENT_EXECUTION_PATCH)` at the flip site. Under the marker the loop runs the
probe (its answer is recorded in history) and holds the `we_` only if the probe says on. A probe that gets no
answer counts as off. That is today's behaviour, which drops no request. This must land in #992 before #992
leaves draft, because the probe precedes #992's marker in the command order. Add a read-only CLI subcommand
(`orchestrator/temporal/cli.py`: `capability execution-queue`) for the release owner to run before the
`mctl-agents-worker*` image bump. Order: #931 switch on -> CLI reports on -> #992 + this change released -> image bump.

### 8. Documents
ADR `docs/adr/026-deferred-resume-contract.md`: the request-to-outcome table (implement running -> deferred;
PR open -> feedback tick; merged -> `work-merged`; implement not succeeded -> closed loop with rewind and fresh
approval; no intent -> `nothing-to-resume`), the authority rule, and orphan recovery. Amend the #991
requirements/design/tasks to reference it (owner decision 5 stays there). Fix the `_await_canonical_reapproval`
and `_launch_correlation` docstrings. A new approval digest is needed for the amended #991 spec.

## Alternatives
- Re-approve every deferred resume (route it all through the closed-loop path, including PR-open cases).
  Dropped: the owner chose shepherd feedback for an open PR. Rewinding would also discard a live PR's review state.
- Validate in `_deliver` only, after the bind. Dropped: a refusal after the fulfil mints a `we_` and loses the
  request row's intent. The validator refuses before minting, which keeps the intent (owner decision 2).
- Put orphan recovery in a separate cron workflow. Dropped for now: the dispatcher already owns the
  write path, the policy checkpoint identity and the verdict logic. A second actor would duplicate the fencing.
  This can move once the owner decides placement.
- Gate the hold on a worker env var. Dropped: workflow code cannot read env deterministically, and an env var
  does not prove mctl-api's state. An activity answer is recorded in history and is evidence.

## Platform impact
- Replay compatibility: every new behaviour is behind `DEFERRED_RESUME_PATCH` or
  `IMPLEMENT_HOLD_CAPABILITY_PATCH`, and every new dataclass field is defaulted. New replay fixtures are recorded
  before and after `implement-execution-id` and the new markers.
- Gitops: the shepherd CWFT needs `intent_id`, `execution_request_id` and `feedback_actor` params plus a
  `feedback_outcome` output (a sibling mctl-gitops PR). Until it merges, the tick's outcome is
  `feedback-unobservable`, which fails closed.
- mctl-api dependency: the capability flag, the queue (#931) and optionally the open-execution list. Without
  them the hold stays off and the sweep uses source B.
- Cost: one extra shepherd run per accepted feedback request (about $1-5). The sweep makes one visibility query
  plus N item reads every 5 minutes.
- Risk: the scope classification is model-judged. Mitigation: only `in-scope` proceeds, every other result fails
  closed, and the independent review gate still guards the merge.
- Risk: the rewind could revoke an approval in flight. Mitigation: it applies only with no PR and the
  post-agent re-read at ~:4199 kept, and it needs a fresh grant.
