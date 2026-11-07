# Resume-based worker-restart gap harness for the merge-watch deadline (M2b-1a', #1029)

## Context

Issue #1026 tried to show, on `WorkflowEnvironment.start_time_skipping()`,
that a worker outage spanning the 14-day merge-watch deadline makes
`DevLoopWorkflow._watch_pr` end without a final `get_pr_state` read (the code
path behind #1021). That attempt returned a negative result. The Java test
server locks time skipping while a workflow task is scheduled and no worker
has started it. So with no worker polling, virtual time stops at the first
timer that fires during the gap, and a 14-day deadline cannot be crossed.

This proposal is the owner-chosen second route (option 4). It starts a real
`DevLoopWorkflow` from a `MergeWatchResume` record whose absolute `deadline`
lies between "now" and the next 15-minute poll timer (`MERGE_POLL_INTERVAL`).
A worker stop and start can then straddle the deadline while no timer fires,
so virtual time advances freely. The first post-gap workflow task starts past
the deadline. The deliverable is test-only: one new test module, with no
production change. It reproduces the deadline-in-gap code path only. It does
not reproduce a 14-day outage.

## User stories

- AS the DevLoop owner I WANT a deterministic Temporal-history proof that a
  worker gap crossing the merge-watch deadline ends the watch without reading
  the PR state again SO THAT the #1021 fix (a later slice) has a failing pin
  to turn green.
- AS a reviewer I WANT a positive control and mutation proofs SO THAT I can
  trust that the pin is not vacuous.
- AS the DevLoop owner I WANT the resume record and every resume flag
  verified and mapped against an ordinary production merge watch SO THAT I
  know exactly how far the harness differs from production.

## Acceptance criteria (EARS)

- WHEN the harness runs scenario A THE SYSTEM SHALL start a real
  `DevLoopWorkflow.run` on a time-skipping environment with
  `IssueRef(resume=MergeWatchResume(...))`, using fakes only at the activity
  boundary, and with no direct call to `_watch_pr` or any other workflow
  method.
- WHEN scenario A is built THE SYSTEM SHALL set `resume.deadline` to an
  absolute instant strictly between the start time and the start time plus
  `MERGE_POLL_INTERVAL` (for example start + 10 min).
- WHEN worker 1 has completed the workflow task that recorded the first
  `get_pr_state` result (`OPEN`) and started the poll timer THE SYSTEM SHALL
  stop worker 1, switch the `get_pr_state` fake to `MERGED`, advance virtual
  time past the deadline but before the poll timer, and only then start
  worker 2 on the same task queue.
- WHEN scenario A completes THE SYSTEM SHALL assert that `get_pr_state` was
  scheduled exactly once in the history, that the fake never returned
  `MERGED`, and that the result's `pr.state` is `OPEN`.
- WHEN scenario B (the control) runs with the deadline after the poll timer
  (for example start + 20 min) and the same gap THE SYSTEM SHALL assert that
  worker 2 reads `MERGED` and the result's `pr.state` is `MERGED`.
- THE SYSTEM SHALL prove from the fetched Temporal history, for both
  scenarios:
  - every `WorkflowTaskStarted` event before the gap carries worker 1's
    identity, every one after it carries worker 2's identity, and the two
    identities differ;
  - no `WorkflowTaskScheduled`, `WorkflowTaskStarted` or
    `ActivityTaskScheduled` for `get_pr_state` lies between the gap's start
    and end timestamps;
  - the workflow id and run id are the same before and after the gap, and no
    `WorkflowExecutionContinuedAsNew` event exists;
  - the `deadline` in the first event's input equals the value the test set.
- WHEN scenario A completes THE SYSTEM SHALL assert that the event time of the
  first post-gap `WorkflowTaskStarted` is at or after the deadline.
- THE SYSTEM SHALL verify the `MergeWatchResume` record separately. The check
  decodes the record from the `WorkflowExecutionStarted` input and compares
  every field the test sets to the value set: the absolute `deadline`,
  `fast_cadence`, `shepherd_in_loop`, `concurrent_ticks`, `track_ownership`,
  `proposal_terminal_end`, `deferred_resume_contract`, `saw_open_pr`,
  `poll_index`, `merge_gate_settled_head`, the ownership fields, and the
  carried stage results.
- THE SYSTEM SHALL include, in the test module docstring and in the PR body,
  a mapping of the `_watch_pr` statements this run executes against an
  ordinary production merge watch, stating every difference.
- WHILE the harness exists THE SYSTEM SHALL contain no change under
  `orchestrator/`, `agents/` or `config/`.
- IF the gap cannot be reproduced 20 of 20 times, or the test needs a
  production change, a direct method call, or a substitute for Temporal
  workflow execution, or the resume record cannot reach the same merge-watch
  path as production, THEN THE SYSTEM SHALL report a negative result on
  #1029 and open no PR that presents as success.
- WHEN the implementer PR is opened THE SYSTEM SHALL verify that GitHub
  reports it as blocked by the code-owner hold (#1020) and SHALL NOT merge,
  bypass, release, deploy or change a flag.

## Out of scope

- Any workflow fix for #1021 (for example a final read at the deadline
  exit), patch marker, new activity, typed outcome or fixture migration.
- Hop or continue-as-new variants of the gap.
- M2b-1b to M2b-1d.
- Any claim that the harness is equivalent to a 14-day worker outage.
- B4, the release hold, #1003, gitops#2394 and mctl-api#934. They stay
  untouched.

## Open questions

- Sticky task queue after worker 1 stops. With the default sticky cache, the
  server may first offer the post-gap task to worker 1's sticky queue and
  wait for its schedule-to-start timeout. Under the time-skipping server that
  could interfere with the gap. Proposed answer: run both workers with
  `max_cached_workflows=0`, so every task goes to the normal queue and worker
  2 replays from history. This is recorded as a difference from production.
  If the default sticky configuration also reproduces 20 of 20, the
  implementer may keep it and say so.
- The merge gate (`MERGE_GATE_PATCH`) starts a child approval workflow for an
  `OPEN` PR with a `head_sha`. Its timers would fire during the gap. Proposed
  answer: carry `merge_gate_settled_head` equal to the fake head SHA, which is
  a state a real hop record can carry, so `_gate_may_start` is false. This is
  recorded as a difference.
- Whether "the rest" of the resume flags in item 6 includes the stage results
  (`investigate`, `implement`, `approve`) and the work-context fields. Assumed
  yes. Every field the test sets is verified.
