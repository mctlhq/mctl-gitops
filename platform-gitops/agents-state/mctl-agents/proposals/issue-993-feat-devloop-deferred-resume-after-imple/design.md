# Design: issue-993-feat-devloop-deferred-resume-after-imple

Amended 2026-11-03 (see requirements.md, "Amendment 2026-11-03"). Part M = lands on `main` via this proposal's
implementer. Part S = commits on PR #992's branch by an operator-directed session under the approved #993 digest. Line numbers are approximate (`~`) and
refer to `main` (a99c888) for Part M and to `origin/pr992` (6b60a7f) for Part S.

## Current state
Read-only clone of `mctlhq/mctl-agents`. `main` does NOT contain PR #992: `IMPLEMENT_EXECUTION_PATCH`
(`"implement-execution-id"`, pr992 `dev_loop.py:475`) and `_hold_canonical_for_implement` (pr992 `:1762`, `:4179`)
exist only on #992's branch. Mechanics of the #991 design (status `implemented`, untouched) are assumed.

Delivery path (`orchestrator/temporal/workflows/dev_loop.py`):
- `ResumeDelivery` (~:1032) carries only `execution_request_id`, `work_item_id`, `surface`, `actor_kind`,
  `actor_id` and `kind`. The request's `intent_id`, `expected_state_version` and `resumed_from_execution_id`, which
  `ExecutionRequest` (`orchestrator/work_context/execution_requests.py` ~:138-207) parses, are dropped by
  `Dispatcher._dispatch` (`orchestrator/temporal/dispatcher.py` ~:434-441).
- `accept_execution_request` (~:2647) and `_validate_execution_request` (~:2696) refuse with `ResumeRefused`
  (permanent; reason must be in `xr.RESUME_REFUSAL_REASONS`) or `ResumeDeferred` (transient, the dispatcher keeps the
  request claimable: `TemporalClientPort.deliver`, dispatcher ~:258-300). Neither looks at `_gates_passed` or the PR.
- `_deliver` (~:2753) binds the fulfilled `we_`, then waits for `self._abandoned or self._is_approved() or
  self._gates_passed or ...` (~:2831) and lands `Succeeded` when `(self._is_approved() or self._gates_passed) and
  not self._abandoned` (~:2833). `_gates_passed` is set before `_implement` (~:4234) and in `_resume_merge_watch`
  (~:4452), so a resume during implement or the merge watch ends `Succeeded` at once: the silent no-op. Codified by
  `tests/test_execution_request_resume.py::test_a_resume_delivered_after_the_implement_step_succeeds_at_once` (~:580).
- Merge watch: `_watch_pr` runs `_shepherd_tick(service, slug)` (~:4949) on tick boundaries; a failed tick is logged,
  not raised. `orchestrator/run_shepherd.py` already has the `--review-feedback` implementer path (~:21, ~:2967-3173).
- Closed-loop path: Update-with-Start of `dev-loop-<owner>-<repo>-<n>`. A resumed investigate on a proposal past
  `proposed` writes a context-only snapshot (`CONTEXT_ONLY_RESUME_PATCH`, ~:447). Rewritable only if status is in
  `_OVERWRITABLE_PROPOSAL_STATUSES = {"proposed"}` (~:458), mirroring `run_issue_investigator._OVERWRITABLE_STATUSES`.
- Orphan reconciliation: `Dispatcher._reconcile_closed_loops` (dispatcher ~:534-604) fails a non-terminal `<loop>#xr_*`
  or `<loop>#run_*` execution whose loop is not RUNNING (or whose RUNNING run does not hold the request, via the
  `holds_execution_request` query, `holds_request` returning None when it cannot say). It runs only from `_dispatch`
  (~:432), i.e. after a request was claimed. While a `we_` is open mctl-api refuses to create a request, so after a
  terminated loop nothing triggers it (switch off). With the #931 switch on a request is queued and the #931 sweeper
  closes the Temporal-owned execution (below).

Facts verified for this amendment (pr992 unless noted):
- Phases the loop writes: `_advance_dispatched_execution` is called only with `Succeeded` or `Failed`; `Error` is
  written only by the #931 sweeper. Under #992 a failed/cancelled/timed-out implement raises out of `_implement`
  (non-retryable `ApplicationError`, marker `implement-outcome`), `run()`'s `except (Exception, CancelledError)` ends
  the `we_` with `_canonical_pending_phase or "Failed"` and `FAST_ACTIVITY_RETRY_POLICY` (~:3489), so the line
  `self._canonical_end_phase = "Succeeded" if implement_result.succeeded else "Failed"` (~:4270-4272) is reachable on
  success only. mctl-api cannot tell Cancel and Timeout from Failed.
- `_resume_merge_watch` (~:4422-4520) rehydrates watch state and calls `_rehydrate_work_context`; `_carry_work_context`
  (~:4324) and `MergeWatchResume` (~:1564) carry NO canonical field. `_canonical_open`, `_canonical_pending_phase`,
  `_canonical_execution`, `_canonical_end_phase` and `_hold_canonical_for_implement` therefore reset to their
  `__init__` values (~:1755-1766) in a continued run, and `_end_canonical_execution` returns at once when
  `_canonical_open` is False (~:3516). A pending end is lost at the first hop; `run`'s exit paths in the continued
  run cannot retry it; the `work_context` query reports `canonical_open=False` after a hop (~:1993).
- `after_flip=not self._hold_canonical_for_implement` (~:4257) is already in #992: False under the hold.
- Docstrings: `_await_canonical_reapproval` (~:2478) still describes the pre-#991 shape (a resume opens a new
  execution after the flip); `_launch_correlation` (~:4623) does not say `execution_id` is deliberately not part of it
  (it goes to implement only, `implement_params["execution_id"]` ~:4236).
- Deployed: `services/admins/mctl-agents-worker/values.yaml:27` image `1.117.0`; `:139` `EXECUTION_REQUEST_DISPATCHER:
  "true"` (commit f1fc08233, 2026-09-24). The comment above it says only the main worker runs the dispatcher; the
  exec and implement workers ignore the flag. Short activities are registered on the main worker
  (`orchestrator/temporal/worker.py` ~:700-790, `short_activities`).
- How the repo does worker flags: workflow code never reads the environment (grep finds no `os.environ` under
  `orchestrator/temporal/workflows/`). Runtime flags are read in activity code, with the command sequence identical in
  every mode (`orchestrator/temporal/activities/lifecycle.py` ~:240-255, `rollout.py`); `dispatcher.enabled()`
  (~:185) reads `EXECUTION_REQUEST_DISPATCHER` with a `_TRUTHY` set. Code versions use `workflow.patched`, memoised per
  id (`tests/test_patch_memoization.py`).
- mctl-api (`origin/main` a11b54d): `GET /api/v1/work-items` (`ListWorkItems`, `handlers_work_items.go:466`) filters
  `state`, `tenant`, `owner`, `limit<=500` and returns the most recently updated first (`store.go:1132`,
  `ORDER BY updated_at DESC, id LIMIT n`); there is NO cursor/offset, no engine filter and the item has no execution
  field. `GET /work-items/{id}` returns the item with `latest_execution`; `GET /work-items/{id}/executions` lists
  one item's executions (`router.go:910-914`, MCP `mctl_list_work_item_executions`). `AttachExecution` never changes
  a finished execution's phase (`store.go:846-851`, 409 `invalid_transition`). The accepted #931 proposal adds
  no capability endpoint/field and no list endpoint; its sweeper (switch on) only examines `engine=temporal`
  executions with an open request behind them and a minimum age, writes `Error`, and leaves Running, ContinuedAsNew
  and unreadable runs alone.
- mctl-agents Temporal reads available: `client.list_workflows(query)` (`activities/visibility.py` ~:118, ~:206;
  `run_issue_directive_poller.py` ~:394), `TemporalPort.loop_state` / `holds_request`, and the workflow query
  `work_context` returning `work_item_id`, `canonical_execution_id`, `canonical_open`, `executions` (~:1975).
  `start.py` memo carries only `requested_by`/`requested_via` (~:95): NO `work_item_id` in the memo, and for a
  non-dispatched loop the item is resolved inside the run (`ensure_issue_execution`), so the start cannot record it.
- Implementer base: `run_implementer._clone_target` clones the default branch (`:1787-1794`), `git checkout -b
  feat/agents-<slug>` (`:4958-4959`), PR `--base main` (`:3784-3794`). No base option.
- ADRs: latest is `025-independent-review-receipts.md`; this adds `026`.
- Not checked: the shepherd CWFT (outside the visible gitops paths), the live mctl-api switch state, and Temporal
  namespace retention.

## Proposed solution

### Part M

#### M1. Carry the full request identity
Defaulted `ResumeDelivery` fields `intent_id: int = 0` (0 = none), `expected_state_version: int = 0`,
`resumed_from_execution_id: str = ""`, filled by `Dispatcher._dispatch`. `execution_request_id` stays the Update id
and dedupe key.

#### M2. Contract marker and carried state
`DEFERRED_RESUME_PATCH = "deferred-resume-contract"`, recorded once where `_gates_passed = True` is set (both sites)
into `self._deferred_contract`, carried in `MergeWatchResume` as a defaulted field. A continued run evaluates the
marker afresh, so a pre-marker loop upgrades at its next hop. New state, all defaulted in `MergeWatchResume`:
`_implement_running`, `_pr_merged`, `_feedback_done: frozenset[str]`, `_pending_feedback`. Validators record no
command; they read flags only.

#### M3. Validator decisions (refuse before a `we_` is minted)
In `_validate_execution_request`, after the existing checks:
- `self._gates_passed and not self._deferred_contract` -> `ResumeDeferred("legacy-loop")` (the fence). Update validators
  are not run on replay, so an already accepted update is unaffected (T-test asserts a replayed history stays green).
  A rolling update can still be validated by an old pod; step 2 of the rollout order closes that window.
- under the contract: `_implement_running` -> `ResumeDeferred("implement-running")` (defence in depth);
  `_pr_merged` -> `ResumeRefused("work_merged")`; `kind == resume and intent_id == 0` -> `ResumeRefused("no_actionable_intent")`.
Add `work_merged`, `no_actionable_intent`, `implement-running`, `legacy-loop` to the vocabularies
(`xr.RESUME_REFUSAL_REASONS`, and the deferred reasons) so the dispatcher forwards them.
A new read-only workflow query `contract_state` -> `(gates_passed, deferred_contract)` and CLI
`orchestrator/temporal/cli.py contract-drain-check` list RUNNING DevLoop runs (visibility query
`ACTIVE_DEV_LOOPS_QUERY`) where `gates_passed and not deferred_contract`. A query on an old pod that lacks it counts
as listed (unknown). Queries replay old histories on the new code, so old loops answer too.

#### M4. `_deliver` after gates: one feedback tick, typed outcome
For contract loops with `_gates_passed`:
1. `rid in _feedback_done` -> nothing more (redelivery after a hop).
2. Read the switches with the activity `read_rollout_switches` (below). Not on -> land `Failed` with `feedback-disabled`.
3. `_feedback_authority_valid()`: the `aar_` the flip spent, the approved content digest recorded at the flip, and the
   approver authority still match the live proposal (reuses `GRANT_FRESHNESS_PATCH` reads). Failure -> `Failed`,
   `reapproval-required`.
4. Else set `_pending_feedback = FeedbackRequest(rid, intent_id, actor, surface)`; wait for the watch to run it (or
   `_exiting` / `_hopping` / `_abandoned`).
5. `_watch_pr` checks `_pending_feedback` each poll and runs one tick under the single-tick rule, outside the cadence
   budget, via `_shepherd_tick(service, slug, feedback=...)` adding `intent_id`, `execution_request_id`,
   `feedback_actor` and reading `feedback_outcome`. The request id is added to `_feedback_done` BEFORE awaiting the
   tick: a crash after that fails closed, never twice.
6. `run_shepherd --feedback-intent` fetches the intent text (`list_intents`), classifies scope against the approved
   `requirements.md`/`design.md` (`in-scope` / `scope-expansion`), runs `--review-feedback` for in-scope under the same
   lifecycle claim, `--match-head-commit` fencing, review and CI gates, and emits `processed` / `scope-expansion` /
   `failed` / `unobservable`.
7. `processed` -> `Succeeded`; anything else -> `Failed` plus `ResumeRejection` (`scope-expansion`, `feedback-failed`,
   `feedback-unobservable`). A tick that fails as an activity is `feedback-failed`.
8. Watch ends before the tick (PR merged / closed / deadline) -> `Failed` with `work_merged` or `feedback-not-run`.
The classification is model-judged; only `in-scope` proceeds and everything else fails closed.

#### M5. `read_rollout_switches` activity (shared switch mechanism)
New short activity on the main worker, `orchestrator/temporal/activities/rollout_switches.py`, returning
`RolloutSwitches(deferred_feedback: bool = False, implement_hold: bool = False)` (Part S adds the second field, a
defaulted dataclass field, so a recorded result still decodes). It reads `DEVLOOP_DEFERRED_FEEDBACK` and
`DEVLOOP_IMPLEMENT_HOLD` in the activity (legal outside the sandbox, as `lifecycle.py` does) and returns true only for an
explicit on (`true`, `1`, `on`, `yes`, as `dispatcher._TRUTHY`); empty, unknown or malformed is off with a warning.
It never raises; the workflow also treats an `ActivityError` as off. The call is scheduled unconditionally at its site
under a marker, so the command sequence is identical whichever way the environment is set; only the payload differs,
and the payload is replayed from history. Env vars are frozen at pod start: a flip needs a pod roll of the main worker
only. Alternative considered, a recorded workflow input (a field on `IssueRef` set by the starter): rejected, because
there are several starters (intake poller, dispatcher, directive scan) and a long-lived loop could not be switched.

#### M6. Closed-loop path after a failed implement, rewind with proof
A loop whose implement did not succeed skips the merge watch and ends; the canonical `we_` ends `Failed` (exception
path). The queued request is then claimed and Update-with-Start starts a new run. Widen the guard in both mirrors by a
predicate, not by changing the set: a dispatched `resume` that pins an available intent may rewrite a proposal in
`accepted`/`needs-triage` only when the guarded-reinvestigation checks (a) to (e) of the requirements all hold: the
prior execution is terminal (a timeout alone is not proof of termination); no live implement Workflow and no live
attempt lease; no active lifecycle-ownership claim; no `pr` and no open PR; no merged PR, no pushed
`feat/agents-<slug>` branch and no pending end-advance. Each read is an error or unknown on failure; any unknown
writes `needs-triage` carrying a typed evidence record (check name and `proven`/`refuted`/`unknown`), no `proposed`,
no implementer. The pinned intent (`intent_id`, actor, surface, `request_id`, idempotency) is bound to the new
investigation and the new run parks for a fresh content-bound approval. The rewrite writes only `status: proposed` with the pinned intent
through the existing path; it never edits or re-binds an earlier approval, and the new run parks on the canonical
approval for a fresh grant at the then-current digest. Guarded by `DEFERRED_RESUME_PATCH` at the context-only branch;
old histories keep ending context-only.

#### M7. Orphan sweep (no claim needed), `temporal` only
Move the per-execution decision of `_reconcile_closed_loops` into a pure helper `_orphan_verdict(execution, loop_state,
holds)` shared by both callers. `Dispatcher.sweep_orphans_once()` runs from `run_dispatcher` every
`EXECUTION_ORPHAN_SWEEP_SECONDS` (default 0 = off until task C0 passes; 300 afterwards).

Sources (all confirmed in code, see Current state):
1. Candidate runs: `list_workflows("WorkflowType = 'DevLoopWorkflow' AND ExecutionStatus != 'Running' AND
   ExecutionStatus != 'ContinuedAsNew'")` plus a `CloseTime` bound. A run that continued as new is not closed.
2. Per candidate run: the `work_context` query (`work_item_id`, `canonical_execution_id`, `canonical_open`,
   `executions`). It is read from the closed run's replayed history, so it needs a worker that replays the run.
   A query that fails (not replayable, timeout) is `unobserved`: counted and skipped, never "nothing open".
3. Per candidate that reports an open `we_` or unfinished delivery: `WorkItemClient.get(work_item_id)` for the
   authoritative executions (`latest_execution` and the item's executions), then `_orphan_verdict` with `loop_state`
   re-read immediately before the write, then the same attach-or-advance the loop uses
   (`attach_execution(..., EngineRun(temporal, ref), "Failed")`) through the policy checkpoint.
`GET /work-items?state=open` is NOT a source: no cursor, newest-updated 500 only, no execution data. It may only
be used as a cross-check, never to decide absence.

Division of labour with the #931 sweeper: #931 (switch on) closes Temporal executions that have a queued request
behind them and are at least the minimum age old, as `Error`. This sweep closes the DevLoop-owned executions found
from the Temporal side, as `Failed`, with or without a request. Both use "owning run closed or absent, unreadable
means leave" and mctl-api never changes a finished phase, so whichever writes first wins and the other gets 409
`invalid_transition`, which is classified as converged. Neither depends on the other, so the sweep does not wait for
or duplicate #931. With the switch on a waiting request exists as a queued row, which #931 handles: this sweep is
for the no-request case (hygiene, switch-off periods, items that no request is waiting on).

Starvation (the hazard found reviewing mctl-api#932: sweeping the oldest N forever starves later rows): two lanes.
- Fresh lane: closes since the last completed cycle start minus an overlap (visibility `CloseTime >` mark), newest
  first, bounded by `SWEEP_FRESH_MAX` (default 50).
- Backlog lane: a descending keyset cursor on `CloseTime` (`CloseTime <= cursor`, resume at the oldest examined row),
  `SWEEP_BATCH` rows per cycle (default 50, hard cap 200), walking back to the namespace retention floor, then wrapping
  to now. Rows examined and found converged are remembered in a bounded in-process set; unresolvable rows are skipped
  and counted, they do not hold the cursor. Overlap at equal `CloseTime` is harmless: the write is idempotent.
- Bounded cost per cycle: at most `batch + fresh` queries (replays) and one item GET per open candidate.
- Audit: `orphan_sweep` events carry examined / unobserved / ended / converged counts and the wrap age.
Engine coverage: `temporal` only. argo and a2a executions are never touched and are tracked separately. Only
executions whose engine ref is this dispatcher's own (`#xr_`, `#run_`) are ended.
Typed blocker: task C0 is a spike that terminates a real DevLoop in the Temporal test environment and queries
`work_context` on the closed run, also against a recorded pre-hop history. If it cannot be shown, the sweep ships off
and the proposal STOPS at the blocker `ORPHAN_SOURCE_BLOCKED`: the minimal API follow-up would be a read of items
with an open `temporal` execution with a keyset cursor, proposed and approved on its own. Nothing here depends on it.

#### M8. Documents
ADR `docs/adr/026-deferred-resume-contract.md`: the request-to-outcome table (implement running -> deferred; PR open
-> feedback tick; merged -> `work_merged`; implement not succeeded -> closed loop with proof-gated rewind and fresh
approval; no intent -> `no_actionable_intent`; legacy loop -> `legacy-loop`), the authority rule, the two switches, the
sweep and its division of labour with #931.

### Part S (on PR #992's branch)

#### S1. Hold switch at the flip site
After `workflow.patched(IMPLEMENT_EXECUTION_PATCH)` (pr992 ~:4179) add the marker `IMPLEMENT_HOLD_SWITCH_PATCH =
"implement-hold-switch"`. If not patched: `hold = True` (what a history recorded under #992 did, so the fixture
`dev_loop_implement_execution.patched.json` replays). If patched: `hold = (await read_rollout_switches()).implement_hold`,
off on `ActivityError`. `self._hold_canonical_for_implement = hold` then drives every existing use unchanged: the end at
the flip when False (~:4180), `execution_id` in `implement_params` (~:4227), `after_flip` (~:4257), the end after
implement (~:4270). With the switch off the loop equals `main`: the `we_` ends at the flip, no `execution_id`. That
leaves the #991 observe-proof unresolved until the switch is on, by design.

#### S2. Merge-watch retry (`IMPLEMENT_END_RETRY_PATCH = "implement-end-retry"`)
Declared beside `IMPLEMENT_EXECUTION_PATCH`, evaluated once right after the post-implement end, only when the hold is on,
stored as `self._retry_pending_end`. In `_watch_pr`, at the top of each poll iteration (after the hop check, before
`get_pr_state`):
```
if self._retry_pending_end and self._canonical_open and self._canonical_pending_phase:
    await self._end_canonical_execution(self._canonical_pending_phase, retry_policy=FAST_ACTIVITY_RETRY_POLICY)
```
One attempt per poll, none once landed, so no extra command in the common case; the fast policy keeps a store outage
from stalling merge detection. Hops: in the hop branch, before the `MergeWatchResume` is built, one more attempt; then
`_carry_work_context` folds `canonical_execution_id`, `canonical_open`, `canonical_pending_phase`,
`canonical_end_phase` and `retry_pending_end` into the record (new defaulted `MergeWatchResume` fields; one place, both
hop sites), and `_resume_merge_watch` rehydrates them before its first await. A record without the fields decodes to
today's behaviour. It also makes the `work_context` query accurate after a hop, which M7 relies on.
Evidence that a pending end cannot strand a queued resume for 14 days: with the retry the `we_` closes at the first
poll at which the store answers (the cadence), tested with a clock-skipped watch of many polls and across a hop (T-S3,
T-S4); without it the test fails (mutation).

#### S3. Docstrings and other
Fix `_await_canonical_reapproval` (the hold means no resume opens a new execution; `after_flip=True` is legacy-only) and
`_launch_correlation` (`execution_id` is deliberately not part of it); `_end_canonical_execution` docstring; add the
`implement_hold` field to `RolloutSwitches`; record fixtures: pre-switch (existing `.patched.json`), post-switch with
hold on, post-switch with hold off, and one with a retried advance and one across a hop.

## Part S authority (verified)
The shepherd and `run_implementer --review-feedback` cannot carry Part S:
- The shepherd discovers proposals in `{implemented, review-fixing}` by slug (`run_shepherd.py:1-8`) and the follow-up
  runs `run_implementer --service <svc> --slug <slug> --review-feedback <bundle>` (`run_shepherd.py:3208-3215`), i.e.
  under the `issue-991-*` slug and its approval, not #993's.
- The bundle is a findings bundle (`{"p1","p2","summaries":[{file,line,severity,body}]}`, `run_implementer.py:18-24`) of
  codex findings and CI blockers, not an arbitrary task. The prompt it builds is the proposal spec of THAT slug
  (`_build_prompt(review_feedback=...)` ~:1917-1960). The #993 spec is never in it.
- The content-digest approval check runs on the new-branch path only (`run_implementer.py:~4568`
  `approval_digest_verdict`); the review-feedback mode explicitly leaves status as is (`:30-36`).
- The new-branch path (what a #993 implementer run does) creates `feat/agents-<slug of #993>` from the default branch
  (`:4958-4959`), never #992's branch.
- `decide()` returns `wait` for a draft PR (`run_shepherd.py:2666`), so while #992 stays draft the shepherd takes no
  action on it. This is what makes a single-writer rule enforceable by a draft state plus a check for an in-flight tick.
Conclusion: no automated mechanism exists. Part S is an operator-directed session (human, or an explicitly started
Claude session) pushing to #992's branch under the approved #993 digest, with the single-writer rule of requirements.md.
The commit trailers name the #993 digest and S-task ids, so the authority is auditable from git. The PR's own
claude-review still reviews each push. An automated path would need a base option for the
implementer plus a task-scoped bundle; the owner decided against it (2026-11-03).

## Delivery
One ordering, stated identically in requirements.md ("Delivery and rollout order") and tasks.md (S0):
1. Part M lands on `main` and is RELEASED first. It needs none of #992's code, and it rewrites the `main` test that
   exists there only after its own behaviour and mutation tests exist.
2. Then an operator-directed session MERGES `main` INTO the existing draft #992 branch. There is no rebase and no
   force-push. It reruns the whole suite and every replay fixture, old and new, green.
3. Only then does it push the Part S commits (without force). #992 stays a draft through Part M and the Part S
   integration. Part S is never merged or released before the integration gates; readiness of #992 is a later,
   explicit owner gate.
Consequence for the 21 failing #992 resume tests: they fail on #992 as it stands because the hold is unconditional
(stated by the issue; not re-run in this authoring pass). With the hold switch off the loop is `main`'s loop, so each
test's existing expectation should stay valid. Plan, per owner decision 6 of the 2026-11-03 disposition (never fit an
expectation to a lost request):
  1. After the `main` merge, add the fake `read_rollout_switches` to the test activity registry, default off; run the 21
     unchanged and record which still fail and why.
  2. Parametrise them over `implement_hold in {off, on}`. The off leg keeps today's expectation, untouched.
  3. Write the on leg last, after the Part M behaviour and the mutation-discriminating tests TS* exist; each on-leg
     test asserts a delivered or typed-refused request, never a lost one.
  Any of the 21 that still fails with the switch off is a real contract difference and is handled like an on-leg test.
Decided: the implementer gets no base option; a separate proposal would be needed for one (see "Part S authority").

## Desync matrix and observability
Dimensions: mctl-api queue switch (API), worker image (OLD = without Part M, M = Part M, M+S), `DEVLOOP_DEFERRED_FEEDBACK`
(FB), `DEVLOOP_IMPLEMENT_HOLD` (HOLD), dispatcher (D: on / paused / old image). "Observe" lists only confirmed reads:
the worker log lines below via `mctl_get_service_logs`, `mctl_get_service_pods`/`status` for image tags,
`mctl_list_work_item_execution_requests` (= `GET /work-items/{id}/execution-requests`, per item, has `created_at`),
`mctl_list_work_item_executions`, and the new `rollout-status`. mctl-api has NO global list of requests
(`router.go:920-921`, per item only).

| # | State | What happens to a request | Observe | Typed outcome / requirement |
|---|-------|---------------------------|---------|------------------------------|
| 1 | API off, any worker, HOLD off | create during open `we_` -> 409, nothing stored (today) | requester sees 409 | unchanged |
| 2 | API off, HOLD on (misconfig) | `we_` held through implement; every create 409 for minutes | 409 to requesters; `ROLLOUT_STATE hold=on`; `rollout-status` shows held `we_` age | gate: functional check must precede HOLD; window check "no unexpected 409" |
| 3 | API on, OLD worker, D on | queued only in investigate-to-approval; after delivery a post-gates old loop ends `Succeeded` with no work (FALSE SUCCESS) | not observable on the old image | PREVENTED by order: Part M released first; step 5 requires `ROLLOUT_STATE` of the new image on every pod and an empty drain check |
| 4 | API on, rolling update (mixed OLD/M pods) | a validator on an old pod can still no-op a request | `mctl_get_service_pods` image tags differ; start lines differ | pause D during the roll (required, decided 2026-11-03); gate "all pods new" before step 3 |
| 5 | API on, M, loop without marker (post-gates) | `ResumeDeferred legacy-loop`, request stays claimable | rate-limited `defer reason=legacy-loop`; `rollout-status` lists the loop | typed deferral; never Succeeded; loop upgrades at next hop or ends |
| 6 | API on, M, FB off, PR open | accepted, `we_` minted, ends `Failed` | `ResumeRejection feedback-disabled` in `work_context`; execution phase Failed; `rollout-status` counts | typed; never Succeeded |
| 7 | API on, M, FB on, CWFT output missing | tick runs, outcome unreadable | `Failed feedback-unobservable` | typed; never Succeeded |
| 8 | API on, M, FB on, PR merged | refused before minting | dispatcher `reject resume_refused:work_merged`; request row keeps the intent | typed refusal |
| 9 | API on, M+S, HOLD on, FB off | queued during implement, delivered after `we_` closes, ends `Failed feedback-disabled` | as 6, plus held `we_` age in `rollout-status` | typed |
| 10 | API on, M+S, HOLD on, D PAUSED | request stays `pending`/`claimed`, nothing processes it | `ROLLOUT_STATE` line missing >5 min; `rollout-status` shows open requests of held items with age; claim/defer lines absent | window gate: age bound; for items no running loop names: UNKNOWN (never zero), mctlhq/mctl-api#933 |
| 11 | API on, HOLD on, post-implement end-advance keeps failing | `we_` stays open; request not claimable | `rollout-status` held `we_` age; retried each poll (Part S); audit of failed advances | retry per poll; age bound in the window gate |
| 12 | API switched OFF after requests were queued | rows stay `pending`; claim guard off so they are claimable | defer lines `implement-running` for contract loops | validator defers while implement runs; never Succeeded |
| 13 | API on, M+S, HOLD off | `we_` ends at the flip; queued requests only in the early window | `ROLLOUT_STATE hold=off` | equals today's |
Mismatch states with a possible silent mishandling: 3, 4 (prevented by order and the pod gate, not detectable after
the fact), 10 for items outside any running loop (unobservable with the current API: reported UNKNOWN; the aggregate read is mctlhq/mctl-api#933, tracked separately, not a dependency). Every other state
yields a typed ResumeRefused, a typed ResumeDeferred, or `Failed` plus a recorded `ResumeRejection`, and is visible.

Implementation notes (confirmed mechanisms only): the dispatcher already prints structured audit lines with the prefix
`EXECUTION_REQUEST_DISPATCH` (`dispatcher.py:103,211-215`: events claim, claim_failed, deliver, defer, reconcile,
deliver_stale); the worker logs one line at dispatcher start (`worker.py:~935`). `ROLLOUT_STATE` and the age fields extend
those. The agents-side `ExecutionRequest` parser (`work_context/execution_requests.py`) does not read `created_at`
today, although mctl-api returns it (`execution_requests.go:217`): add it as a defaulted field. No metrics are added:
the worker exports Prometheus metrics for Temporal only (`worker.py:645`), and a new metric family is out of scope.

## Alternatives
- Re-approve every deferred resume (route all through the closed-loop path, including PR-open). Dropped: the owner chose
  shepherd feedback for an open PR; rewinding would discard a live PR's review state.
- Validate in `_deliver` only. Dropped: a refusal after fulfil mints a `we_` and loses the request row's intent.
- A mctl-api capability field (`queue_while_active`) read by a worker probe. Better as a machine proof, but it needs an
  amendment of the accepted #931 (new digest, release) and a probe that must still fail closed. Decided against
  (2026-11-03): #931 is not extended now. The default-off switch, the operator gate and the real durable 201 `pending`
  check stand, and a read that gives no answer fails closed.
- Trial request from the worker. Dropped: a write with side effects on a real item.
- Orphan recovery via a list endpoint of open executions. Dropped: it does not exist in mctl-api and #931 is not to be
  amended speculatively; the only list (`GET /work-items`) has no cursor, so it would starve.
- A separate cron workflow for the sweep. Dropped for now: the dispatcher already owns the write path and the verdict logic.
- Gate the hold on a workflow input or a patch marker only. Dropped: a marker is true for every new execution; an input
  cannot be flipped for a running fleet.

## Platform impact
- Replay: Part M is behind `DEFERRED_RESUME_PATCH` (+ the switch activity's marker); Part S behind
  `IMPLEMENT_HOLD_SWITCH_PATCH` and `IMPLEMENT_END_RETRY_PATCH`. Every dataclass field is defaulted. New fixtures are
  recorded before and after each marker.
- Gitops: the shepherd CWFT needs the additive params and the `feedback_outcome` output (sibling PR); until live, a tick
  reports `feedback-unobservable` (fails closed). Two env lines on the main worker (`DEVLOOP_DEFERRED_FEEDBACK`,
  `DEVLOOP_IMPLEMENT_HOLD`), absent = off. `EXECUTION_ORPHAN_SWEEP_SECONDS` default 0.
- mctl-api: no change. The queue switch (#931) is operated by gitops, verified by the functional check.
- Cost: one shepherd run per accepted feedback request (about $1-5); the sweep makes at most 100 replays plus
  a few GETs per cycle, only when enabled.
- Risks: scope classification is model-judged (fails closed); the rewind could revoke an approval in flight (applies only
  with the proof checklist, needs a fresh grant); a held `we_` with the mctl-api switch off widens the 409 window to the
  whole implement run (prevented by the human gate, visible as 409, never silent); a query on a closed run may not replay
  after a code change (counted unobserved).

## Rollback
Every behaviour is behind markers and switches. Order when backing out: first the hold (`DEVLOOP_IMPLEMENT_HOLD` off,
pod roll of the main worker; new loops end the `we_` at the flip; loops already holding finish normally), then
`DEVLOOP_DEFERRED_FEEDBACK` off (feedback requests then end `feedback-disabled`), and only then the mctl-api queue
switch; switching the queue off first re-opens the refusal window while the worker still holds the `we_`. Image rollback
is safe only for loops that never recorded the new markers; histories that recorded `deferred-resume-contract`,
`implement-hold-switch` or `implement-end-retry` fail non-determinism on an older image, so let them drain or abandon
them (`mctl_abandon_dev_loop`); the sweep and the exit path end their `we_`. The sweep is disabled on its own with
`EXECUTION_ORPHAN_SWEEP_SECONDS=0`. The shepherd CWFT params are additive and stay.
