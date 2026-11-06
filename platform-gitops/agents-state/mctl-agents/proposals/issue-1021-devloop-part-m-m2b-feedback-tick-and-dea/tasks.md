# Tasks: issue-1021-devloop-part-m-m2b-feedback-tick-and-dea

Slice M2b-1 of #993 (umbrella digest
`sha256:1e461962bc774bc5ed7f129c6a78378720a79beb97e601d2ca26985d3109742b`, provenance only). Commit order is
evidence: every `test:` commit lands before the `feat:`/`fix:` commit that turns it green, and the PR description lists
the pairs. Umbrella tasks 5-7 are not in this slice; they belong to M2b-2.

## Implementation

- [ ] 1. Gap harness: a helper in `tests/test_merge_watch_final_read.py` (or `tests/temporal_harness.py`) that runs a
  real `DevLoopWorkflow` in `WorkflowEnvironment.start_time_skipping()`, stops the worker, flips the fake `get_pr_state`
  to the scripted post-gap answer, `env.sleep`s past `MERGE_WATCH_DEADLINE`, then starts a fresh worker on the same task
  queue and awaits the result; records every activity call and every lifecycle op in order - DoD: helper committed with
  the first tests, which fail on current `main` for the right reason (result `pr.state == "OPEN"`, no post-deadline
  read), not on an import error. If the time-skipping harness cannot express a gap across a worker restart, stop and
  report; do not substitute a test that only calls methods directly.
- [ ] 2. Tests first (commit): T-1..T-23 below, red on `main` except the pins that describe behaviour already true
  there: T-16, T-23, the pre-change parts of T-11, and the unchanged exits in T-15. The PR lists which tests are pins -
  DoD: one or more `test:` commits, CI log of the red run linked in the PR.
- [ ] 3. `MERGE_WATCH_RECONCILE_PATCH`, `MergeWatchResume.terminal_reconcile`: evaluated only in `_watch_pr`'s
  fresh-start arm, written into the hop record, read from the record in the resume arm (depends on 2) - DoD: T-10 and
  T-11 marker counts pass; `tests/test_patch_memoization.py` green.
- [ ] 4. `_terminal_claim` and `_apply_found_state` extracted from the in-loop found branch, and the watch's poll locals
  moved to the per-run `watch` record (pure refactor, same commands) - DoD: every existing `_watch_pr` and replay test
  green with no fixture change.
- [ ] 5. `record_merge_watch_reconcile` and its dataclasses in `activities/issue_state.py`, registered in `worker.py`
  and in the test activity registry fake (depends on 2) - DoD: T-7 passes; `post_issue_comment` unchanged.
- [ ] 5a. `confirm_no_pr` and `NoPrProof` in `activities/pr_state.py`, registered the same way (depends on 2) - DoD: T-17
  passes; `get_pr_state` unchanged.
- [ ] 6. `_settle_watch_work`, `_final_pr_read`, `_decide_watch_end`, `_record_reconcile`, wired at the `while ...
  else:` deadline exit, the grace-polls exit and the non-transient read exit; `_gate_ran_head` and its resume field;
  `_no_pr_proven`; `_wait_unless_abandoned`; the bounded backoff and `_reconcile_heartbeat`; `_retain_claim`; the
  cancellation re-raises; the raise after `finally` (depends on 3, 4, 5, 5a) - DoD: T-1..T-6, T-8, T-9, T-18..T-22 pass.
- [ ] 7. Typed result: `_WatchOutcome` and `DevLoopResult` fields, `outcome`, `ended` precedence, `pr=None`, log lines,
  docstrings; `_reconcile_required` in `_deliver` and `MERGE_WATCH_RECONCILE_REFUSAL`; `cli.py` (depends on 6) - DoD:
  T-4, T-12, T-13, T-15 assert every field; old `DevLoopResult` payloads decode.
- [ ] 8. Replay fixtures: `dev_loop_final_read.json` (deadline, no hop), `dev_loop_final_read_hop.json` (hop then gap),
  `dev_loop_reconcile_required.json` (record then release), `dev_loop_no_pr_confirmed.json` (grace polls, proven absence)
  via `tools/record_workflow_history.py` scenarios added to
  `tests/replay_scenarios.py`, and registered in `_STANDALONE_FIXTURES` (`tests/test_workflow_replay.py:576`) because
  scenarios otherwise map to `.prepatch`/`.patched` pairs; no existing fixture re-recorded (depends on 7) - DoD: T-11
  green; `test_every_recorded_fixture_belongs_to_a_scenario` green.
- [ ] 9. Mutation proof. Each applied, confirmed red, reverted, output pasted into the PR:
  (a) remove the final read at the deadline exit;
  (b) remove it at the grace-polls exit;
  (c) remove it at the read-error exit;
  (d) treat a failed read as OPEN;
  (e) recompute the deadline on a hop;
  (f) call `workflow.patched` for the marker in `_resume_merge_watch`;
  (g) relinquish the claim before the final read;
  (h) relinquish the claim before the record;
  (i) release when the record is unconfirmed;
  (j) complete instead of fail when the record is unconfirmed;
  (k) treat a failed comment page as "no marker";
  (l) accept the marker from any comment author;
  (m) land an open delivery `Succeeded` on reconcile-required;
  (n) end a grace-polls or read-error exit on a found OPEN instead of resuming the loop;
  (o) treat a status-file 404 as proven absence;
  (p) treat a recorded PR answering 404 as proven absence;
  (q) treat a failed later `pulls` page as an empty list;
  (r) skip `confirm_no_pr` and always end a grace-polls exit as a normal no-PR completion;
  (s) skip `confirm_no_pr` and always end it as reconcile-required;
  (t) use a fixed retry interval, and separately no upper bound on it;
  (u) stop the `acquire` heartbeat during the record wait;
  (v) add a final read to the abandon exit;
  (w) run the deadline exit's final read before settling the tick and gate;
  (x) treat a found OPEN as final while an attempt is unobserved;
  (y) swallow a cancelled `ActivityError` in `_record_reconcile`, and separately in `_final_pr_read`;
  (z) clear `_retain_claim` before the decision, so that a cancellation releases the claim;
  (aa) heartbeat with `progress`, and separately drop the `_owned_entity_id` guard;
  (ab) remove the abandon guard at the grace-polls site, and separately at the read-error site;
  (ac) skip `_apply_found_state` on a final-read state;
  (ad) answer `issue-gone` on a 404;
  (ae) set `_reconcile_required` only after the record;
  (af) accept the marker from any bot;
  (ag) accept a status file with no `status:` line or a non-base64 encoding, and separately an indented or quoted `pr`;
  (ah) confirm absence while the branch exists
  - DoD: thirty-nine red runs recorded (the items with "separately" count twice).
- [ ] 10. PR description: link #993, #1021, the umbrella digest as provenance only, the approved digest of this
  proposal, the test->fix commit pairs, the mutation and replay evidence, and M2b-2 as not started; state that the PR
  is blocked for owner approval by #1020, needs independent review and green checks, and is not merged with an admin
  bypass; state that release is blocked by #1022 - DoD: PR open; nothing released or deployed.

## Tests

Watch behaviour (new file `tests/test_merge_watch_final_read.py` unless noted):

- [ ] T-1. Deadline gap, final read MERGED: the PR merges with no worker, time passes the deadline, the worker returns
  -> exactly one post-deadline `get_pr_state`; `pr.state == "MERGED"`, `watch_end == "final-read"`; deploy observation
  and `security_record_landed` each scheduled exactly once; lifecycle op `terminal`, never `release`.
- [ ] T-2. Deadline gap, final read OPEN -> the result carries the FRESH OPEN (distinct `head_sha` from the last pre-gap
  read), `watch_end == "final-read"`, `release` after the read, no deploy observation, no comment.
- [ ] T-3. Deadline gap, final read CLOSED -> `pr.state == "CLOSED"`, `terminal` write, no deploy observation.
- [ ] T-4. Deadline gap, final read unreadable (every attempt raises transient, then non-transient, then `found=False`
  variants) -> exactly `FINAL_READ_ATTEMPTS` scheduled `get_pr_state` activities, counted from history events because
  the retry policy multiplies calls at the fake; `watch_end == "reconcile-required"`,
  `outcome == "merge_watch_reconcile_required"`, `pr is None`, `last_observed_pr.state == "OPEN"`, `reconcile_record`
  set, `ended` non-empty, no deploy observation; workflow status Completed; never OPEN, CLOSED or success.
- [ ] T-5. Grace-polls exit, each of: final read MERGED (`terminal`, deploy observed); CLOSED; OPEN (the loop resumes,
  `polls_without_pr` is 0, a later MERGED is reported normally); absence proven (`pr is None`,
  `watch_end == "no-pr-confirmed"`, `ended` and `outcome` empty, no comment); unknown with `last` None, with an
  unresolved reference, and with a stale OPEN (reconcile-required in all three, `last_observed_pr` as given, and
  `confirm_no_pr` not even called in the last two).
- [ ] T-6. Non-transient read exit, each of: final read MERGED; CLOSED; OPEN (the loop resumes, and the deadline still
  bounds it); unreadable (reconcile-required).
- [ ] T-7. Record activity (`tests/test_issue_state.py` or new): marker absent -> posts once and returns `recorded`;
  marker on a `mctl-agents[bot]` comment with `author_association` `CONTRIBUTOR`, and on an owner, member or collaborator
  comment -> `already-recorded`, no post; marker on a comment from a third party, and from another bot -> ignored, posts;
  marker on page 2 -> found; page 2 returns 500, a malformed body or a transport error -> raises and posts nothing; no
  token, 401, 403, 404, 429, 5xx -> raises; 410 -> `issue-gone`; 201 with no URL -> raises; a post that succeeded but
  timed out -> the retry finds the marker, one comment in total.
- [ ] T-8. Ordering: in the recorded op order, settle < final read on a deadline exit, final read < settle < proof or
  record on the other two, and final read < record < relinquishing write on all three; the record is absent on every
  path that did not reach reconcile-required.
- [ ] T-9. Fail closed: the record activity fails for all of `RECONCILE_RECORD_WAIT`, and separately answers
  `issue-gone`, and separately answers 404 for all of the wait -> no `release` and no `terminal` write; workflow status
  Failed with type `MergeWatchReconcileUnrecorded`; `MERGE_WATCH_RECONCILE_UNRECORDED` logged; an abandon signal during
  the wait does not end it early. A 404 streak that later succeeds, and any record that lands after a failure streak ->
  the release follows it, and the workflow ends Completed. An unparsable `self._issue_url` is unreachable through a real
  run, so a method-level unit test of `_record_reconcile` pins that it returns `""`.
- [ ] T-10. Hop: T-1..T-4 repeated where the watch hopped before the gap (continued run starts after the deadline) and
  where the gap begins after a hop; same outcomes; `MergeWatchResume.deadline` and `terminal_reconcile` carried
  unchanged; marker text in the record identical across a hop.
- [ ] T-11. Marker and replay (`tests/test_patch_memoization.py`, `tests/test_workflow_replay.py`):
  `merge-watch-terminal-reconcile` recorded exactly once on a fresh run and zero times on a resumed run; a resume record
  with `terminal_reconcile=False` does no final read at any exit and ends with today's result; every existing pre-change
  fixture replays unchanged and contains no such marker; the four new fixtures replay green.
- [ ] T-12. Deliveries, on both the Completed and the Failed end state: a delivery still polling its bind that binds
  during the record wait -> `Failed merge-watch-reconcile-required`; one that never binds -> `request-not-fulfilled`;
  neither `Succeeded`; a delivery held at the first attempt appears in the record. `_reconcile_required` is set before
  the first record activity is scheduled. A delivery with a `pending_phase` keeps it, an `accepted_after_gates` one keeps
  `feedback-not-ready`, and a deferred request is not in the record. Final-read MERGED with an open delivery -> today's
  behaviour.
- [ ] T-13. Readers: `cli.py` prints reconcile-required with the record and not `not watched`; a `DevLoopResult` payload
  from before this change decodes with the defaults.
- [ ] T-14. Duplicates: an activity task redelivered (the fake fails the first delivery after recording) at the final
  read and at the record yields one landed terminal or release write, one comment, one deploy observation, one security
  record; replay of the recorded history produces no extra command. A `terminal` write that fails and is retried by
  `finally`, as today, is allowed and lands once.
- [ ] T-15. Abandon and unchanged exits: abandon during the watch does no final read, no `confirm_no_pr` and no record,
  adds no timer, writes `release`, and reports `watch_end == "abandoned-unverified"` with `ended` as today; `cli.py`
  states the `pr` is not verified current; an existing abandon fixture replays unchanged. Abandon already set at the
  grace-polls site and at the read-error site -> the same result with no final read. Abandon during a final-read backoff
  or the R1a window -> wakes at once, no further attempt, no record. Abandon during a read that returns MERGED -> the
  MERGED is reported. Abandon after the decision point -> the record is still written and `ended` names the exit. The
  #516 terminal-status break does no final read and no record. A MERGED read inside the loop is byte-identical in
  commands.
- [ ] T-16. Scope pin: `tests/test_execution_request_resume.py:586` stays green unedited, so the validator still defers
  `feedback-not-ready`; an unpatched `accepted_after_gates` delivery still lands `feedback-not-ready`; no
  `DEVLOOP_DEFERRED_FEEDBACK` read exists in the diff.
- [ ] T-17. `confirm_no_pr` (activity unit test): a status file with a `status:` line and no `pr` key, `200 []` on every
  page and a 404 on the branch -> confirmed. Each of these -> not confirmed or raises, and never confirmed: status file
  404, 500, undecodable, empty, a non-base64 `encoding`, or no `status:` line; a `pr:` line of any shape, including blank,
  indented and quoted; a non-empty listing, including one whose items do not match the branch; page 2 answering 500 or a
  malformed body; a branch answering 200 or 500; a transport error; no token.
- [ ] T-18. Record retry timing: failures produce sleeps of 5, 10, 20, 30, 30 minutes and never above 30; the last sleep
  is clipped so the total stays within 24 hours; an `acquire` heartbeat lands when the wait starts, no two land more than
  2 hours apart, no `progress` write is issued, and the claim row is still owned at the end of it. A heartbeat answering
  unknown or failing does not stop the retries and does not drop the claim. A heartbeat answering owned by another owner
  drops the claim, the retries continue, and no relinquishing write follows. With no claim, and with
  `track_ownership=False`, no heartbeat is written and no `#0` entity appears.
- [ ] T-19. Own merge attempts: on a deadline exit, a tick or gate in flight is settled before the first final read. With
  a gate in flight whose merge lands during the window, the second read reports MERGED with `terminal`. With one still
  OPEN after `GATED_ACTIVITY_TIMEOUT` -> reconcile-required, `last_observed_pr` the fresh OPEN, not a `final-read` OPEN.
  With a gate that reported `ran` at the returned head and a read of OPEN -> the same. With no attempt in flight -> no
  window timer and a `final-read` OPEN. On a grace-polls and a read-error exit, a found OPEN leaves the tick and gate
  running; no found state settles them before the proof or record; an unobserved attempt adds the window and a second
  read, and an OPEN then resumes the loop. No double settle in `finally`. `gate_ran_head` survives a hop.
- [ ] T-20. Cancellation: a cancel during a final-read backoff, the R1a window, `confirm_no_pr`, a record retry sleep and a
  running record activity -> no `release`, no `terminal`, `MERGE_WATCH_RECONCILE_UNRECORDED` logged, status Cancelled,
  and deliveries ended by `run`'s `except`. A cancelled activity is not counted as a failed attempt. A cancel during an
  ordinary loop poll -> today's `release`, status Cancelled, not a `read-error` exit and no final read.
- [ ] T-21. Bookkeeping: a final-read OPEN sets `self._last_pr` and `saw_open_pr`, resets `polls_without_pr` and
  `terminal_status_polls`, and takes the claim through `_track_ownership`. After such a resume, a loop-terminal proposal
  status does not reach the #516 break. A MERGED first resolved by the final read takes the claim and then writes
  `terminal`, in that order.
- [ ] T-22. Result edges: reconcile-required with an abandon arriving after the decision point -> `ended` names the exit,
  not `abandoned:`. Reconcile-required with no claim, and with `track_ownership=False` -> the record is written, the
  workflow ends Completed, and no lifecycle write is issued. A grace-polls exit whose found OPEN resumes past the deadline
  -> the loop condition goes false, and the deadline exit decides with one further read set.
- [ ] T-23. Restart pins (R15): `start.py`'s intake and dispatcher reuse policies stay as stated; a dispatcher start after
  a Completed reconcile-required run is accepted and its watch re-reads the PR rather than inheriting the old result; an
  intake start after that Completed run is refused as already handled.

## Rollback

Nothing is released or deployed by this proposal (release hold ON), so before any release the rollback is a plain
revert of the PR. If a later release carries it and must be rolled back while loops that recorded
`merge-watch-terminal-reconcile` are in flight, do not delete the patched branches: either keep them and stop new
adoption with `workflow.deprecate_patch` in a follow-up deploy, or let those loops drain first (visibility listing).
The record activity must stay registered until no such loop remains. Comments already posted stay on their issues as
records; they are not deleted.
