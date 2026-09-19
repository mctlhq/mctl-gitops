# Tasks: issue-417-fix-devloop-a-directive-comment-on-an-is

- [ ] 1. Add `orchestrator/directives.py`: `DIRECTIVE_MENTION`, `RECOGNISED_VERBS`,
      `ACK_MARKER`, `Directive`, `parse_directive`, `is_authorized`,
      `answered_comment_ids`. Pure functions, stdlib only, no `gh` and no temporalio
      import — DoD: module imports cleanly under
      `tests/test_worker_isolation.py`'s constraints; `ruff` and `mypy` clean; the
      mention is recognised only at the start of the first non-blank line;
      `re-investigate`/`Reinvestigate` normalise to `reinvestigate`.
- [ ] 2. Extend `run_issue_investigator.gh_issue_view` to request
      `authorAssociation` and populate a new defaulted
      `IssueData.comment_records: tuple[IssueComment, ...] = ()` (depends on 1) —
      DoD: the existing 4-tuple `IssueData.comments` is byte-identical, so
      `context_assembly.collect_issue_comments` and
      `tests/test_context_assembly.py` need no edit.
- [ ] 3. Add `issue_ref.workflow_id_for_directive(issue_url, comment_id)` returning
      `dev-loop-{owner}-{repo}-{number}-d{sha256(comment_id)[:8]}`, and an optional
      `workflow_id=` keyword on `start.start_dev_loop_workflow` (depends on 2) —
      DoD: `workflow_id_for` is unchanged and still the default; the module stays
      temporalio-free; id-reuse and conflict policies are untouched.
- [ ] 4. Add `orchestrator/run_directive_poller.py` with `poll_directives(...)`,
      `DirectivePollResult`, `DEFAULT_MAX_DIRECTIVES = 3`, a
      `DIRECTIVE_TRIGGER_ENABLED` kill switch, and a `main()` with
      `--dry-run`/`--max-directives` mirroring `run_issue_poller.main` (depends on
      3) — DoD: candidate discovery via
      `gh search issues --owner mctlhq --state open --match comments -- "@MCTL"`;
      one `gh_issue_view` per candidate; every classification branch posts exactly
      one reply carrying the ack marker; no code path touches a label; per-issue
      failures are counted and never fatal; `--dry-run` writes nothing and posts
      nothing.
- [ ] 5. Implement the proposal precondition read: fetch
      `agents-state/<service>/proposals/<slug>/.status.yaml` from `mctlhq/mctl-gitops`
      through the contents-API helper behind
      `temporal/activities/proposals.find_proposal_slug` (depends on 4) — DoD:
      returns one of "missing", "ambiguous", "unreadable", or a status string;
      "ambiguous" and "unreadable" each get their own reply; statuses outside
      `run_issue_investigator._OVERWRITABLE_STATUSES` are refused by name.
- [ ] 6. Add the "a prior directive run for this issue is still RUNNING" refusal
      using `temporal/activities/visibility.list_active_dev_loop_ids` (depends on 4)
      — DoD: a live `dev-loop-...-d*` id for the same issue produces a reply naming
      it and zero new starts; a visibility-query failure skips the check and
      dispatches, so an unknown active set never blocks all work.
- [ ] 7. Add `poll_directives_activity` to
      `temporal/activities/issue_poll.py`, register it in `worker.py`'s
      `short_activities`, and call it from `IssuePollWorkflow.run` behind
      `workflow.patched("directive-poll")` (depends on 4) — DoD:
      `IssuePollWorkflowInput` gains `max_directives: int = 3` and the result gains
      defaulted `directives_started`/`directives_answered`/`directives_failed`, so
      the bare `IssuePollWorkflowInput()` the schedule passes still works and
      historical payloads still deserialize; `tests/test_workflow_replay.py` passes.
- [ ] 8. Thread requester provenance: optional `requested_by` /
      `directive_comment_url` / `directive_comment_id` on `dev_loop.IssueRef`, into
      `investigate_params` (dev_loop.py:893), onto `run_issue_investigator.main()`
      as CLI flags, and into `write_status_yaml` as an additive top-level `request:`
      block (depends on 3) — DoD: with no directive, the emitted `.status.yaml` is
      byte-identical to today's; `_status_disagreements` behaviour is unchanged.
- [ ] 9. Add the reconcile backstop: `UnactionedDirective` plus a defaulted
      `unactioned_directives: list[...] = []` on `ReconcileDiscoveryResult`,
      computed read-only for `source.type == github_issue` proposals whose status is
      overwritable, capped by `RECONCILE_DIRECTIVE_SCAN_LIMIT = 25` with the
      remainder logged (depends on 1) — DoD: nothing is written, `_apply` is still
      gated on `projections` alone, and each finding logs one
      `warn: unactioned-directive service=… slug=… comment=…` line.
- [ ] 10. Docs (depends on 4, 8, 9) — DoD: new `docs/directives.md` with the
      grammar, the authorization rule and every refusal message verbatim;
      `docs/agent-inventory.yaml` `issue-investigator.triggeredBy` gains the
      directive poller; `docs/diagrams/archify/facts.yaml`, `docs/temporal-flow.md`
      and `README.md` gain the second trigger edge;
      `tests/test_agent_inventory.py` and `tests/test_diagram_facts.py` pass.

## Tests

New file `tests/test_directives.py` (pure grammar) and
`tests/test_run_directive_poller.py`, following the existing idiom in
`tests/test_run_issue_poller.py`: monkeypatch the module's own `_run` to return
`subprocess.CompletedProcess`, stub `start_dev_loop_workflow`, drive with
`asyncio.run`.

- [ ] T1. `parse_directive`: recognises `@MCTL reinvestigate`, `@mctl Reinvestigate
      please`, `@MCTL re-investigate`; returns `verb=None` for `@MCTL frobnicate`;
      returns `None` when the mention is mid-body or absent.
- [ ] T2. Unrecognised verb: one reply naming `RECOGNISED_VERBS`, zero calls to
      `start_dev_loop_workflow`.
- [ ] T3. Idempotency across cycles: the same directive comment present on two
      consecutive `poll_directives` calls, where the second cycle's comment list
      includes the first cycle's ack reply, yields exactly one start and one reply.
- [ ] T4. Two distinct directive comments on the same issue yield two requests with
      two distinct workflow ids (asserting the `-d<hash>` suffixes differ), and the
      second is refused with a reply naming the live run when T6's visibility stub
      reports the first as RUNNING.
- [ ] T5. No label side-effects: across every branch, assert no invoked `gh` argv
      contains `issue edit`, `--add-label`, or `--remove-label`.
- [ ] T6. Authorization: `authorAssociation` of `NONE`/`CONTRIBUTOR` and an author
      login ending in `[bot]` each produce zero starts; the bot case also produces
      zero replies.
- [ ] T7. Precondition refusals, one test each: proposal at `implementing`
      (refused by name), no proposal directory, two `issue-<N>-*` directories,
      repo not in `config.settings.SERVICES`, unreadable `.status.yaml`. Each
      asserts exactly one reply and zero starts.
- [ ] T8. Happy path: reply body contains the concrete workflow id, the service and
      the slug, and the ack marker for that comment id — modelled on
      `tests/test_run_issue_investigator.py:594` (`--body` argv extraction, assert no
      placeholder text survives).
- [ ] T9. `WorkflowAlreadyStartedError` from the start call is treated as "already
      handled": zero new starts, the reply is still posted, the cycle is not a
      failure.
- [ ] T10. A reply that raises `CalledProcessError` after a successful start counts
      as a failure, and the following cycle posts the reply without starting again.
- [ ] T11. Cap and kill switch: more authorized directives than `max_directives`
      dispatches exactly the cap and logs the remainder;
      `DIRECTIVE_TRIGGER_ENABLED=false` performs no `gh` calls at all.
- [ ] T12. Reconcile: a proposal at `proposed` whose issue has a directive newer
      than `updated_at` and no ack marker appears in `unactioned_directives`; one
      already carrying an ack marker does not; the activity writes nothing.
- [ ] T13. `write_status_yaml` with no directive arguments produces a payload equal
      to today's; with them, the `request:` block is additive and
      `_status_disagreements` returns the same result as without it.
- [ ] T14. `workflow_id_for_directive` is stable for a given comment id, differs
      across comment ids, keeps the `dev-loop-mctlhq-<repo>-<n>-` prefix, and stays
      within Temporal's workflow-id length limit.
- [ ] T15. Regression guard: `tests/test_run_issue_poller.py` passes unmodified —
      any required edit means the `agents:intake` path was disturbed.

## Rollback

Disable without a deploy: set `DIRECTIVE_TRIGGER_ENABLED=false` (or
`max_directives=0`) on the control worker. `poll_directives` returns immediately,
the label path and the reconcile projections are unaffected, and the only visible
change is that directives go unanswered again — the state this proposal started
from, not a worse one.

Revert: the change is additive (one new module, one new activity call behind
`workflow.patched("directive-poll")`, defaulted fields everywhere), so
`git revert` of the feature commit is safe. Temporal replay of an
`IssuePollWorkflow` execution recorded with the patch is handled by the patch
marker; if the revert is permanent, follow it with `workflow.deprecate_patch`
before removing the marker, as the repo already does for `atomic-approve`.

Durable state to unwind: none by design. No labels were touched. `request:` blocks
already written to `.status.yaml` are inert to every reader
(`_status_disagreements` ignores unknown top-level keys) and can be left in place.
Ack markers are HTML comments inside bot replies and render as nothing. Any live
directive DevLoopWorkflow can be terminated by its `-d<hash>` id via
`python -m orchestrator.temporal.cli`; its proposal is left at `proposed`, which is
exactly the state a re-investigation is allowed to overwrite.
