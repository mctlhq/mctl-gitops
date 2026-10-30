# Tasks: issue-799-feat-directives-mctl-investigate-starts

- [ ] 1. Add `investigate` to `orchestrator/directives.py` `VERBS` and update the comment above it — DoD: `parse_comment` returns `verb="investigate"` for `@MCTL investigate`, still returns `"reinvestigate"` for `@MCTL reinvestigate`, and returns None for mid-line or quoted mentions.
- [ ] 2. Add `IssueRef.requested_by: str | None = None` in `orchestrator/temporal/workflows/dev_loop.py`, and add keyword `requested_by` to `orchestrator/temporal/start.py` `start_dev_loop_workflow` (passed into `IssueRef` and the start `memo`) — DoD: existing callers (`run_issue_poller.poll`, `temporal/cli.py`) are unchanged, and an old-history replay test still passes.
- [ ] 3. Add `DevLoopWorkflow._investigate_in_flight`, set around both `_run_cwft("mctl-agents-investigate", ...)` awaits with try/finally, and a `@workflow.query investigate_in_flight` — DoD: the query returns True during the investigate step and False before and after it, and the replay tests for existing histories pass.
- [ ] 4. (depends on 3) Add `investigation_in_flight(client)` to `run_issue_directive_poller.py`: list `ACTIVE_DEV_LOOPS_QUERY` and query each run, returning the busy workflow id or None. Any error raises `InFlightUnknown` — DoD: a unit test covers True, False and error.
- [ ] 5. Add `list_repo_comments(repo, since)` (repo-wide `issues/comments`, `since`, `sort=updated`, `--paginate --jq '.[]'`, skip PR comments, raise `RepoCommentScanError` on any page or parse failure) and `MCTL_DIRECTIVE_LOOKBACK_HOURS` (default 72) — DoD: the function never returns a partial list.
- [ ] 6. (depends on 5) Extend `scan()` with the fresh-issue pass over `config.settings.SERVICES`: skip issues already in `seen_issue_urls`, run `read_issue_comments` for issues with a mention, add unacked directives with `ref=None` to the same round-robin cap, and honour `MCTL_DIRECTIVE_FRESH_ISSUES_ENABLED` — DoD: a repo listing failure increments `failed` and acks nothing.
- [ ] 7. (depends on 2, 4, 6) Extend `_handle_directive` with the `investigate` branch: existing-proposal reply, describe (running / completed / restartable / error), per-tick and platform-wide gate with a busy refusal, policy checkpoint, `start_dev_loop_workflow(..., requested_by=author)`, and ack only after a successful start. Make `ref` optional for `reinvestigate` and reword `_reply_no_proposal` to mention `@MCTL investigate` — DoD: every branch returns a named outcome, and `scan()` counts `investigate-started` as dispatched.
- [ ] 8. Update the module docstring of `run_issue_directive_poller.py` and `directive_scan_activity`, the README "Directive comments" section (both verbs, lookback, one-at-a-time refusal, replies), and the `main()` description — DoD: no text claims the comment path never starts a DevLoop.

## Tests

All in `tests/test_run_issue_directive_poller.py` / `tests/test_directives.py` / `tests/test_dev_loop_workflow.py`, using the existing `_run`/`list_proposal_refs`/`_post_reply` monkeypatch fakes plus a fake for `start_dev_loop_workflow`, `describe` and the in-flight check. Each must fail with the fix reverted.

- [ ] T1. Fresh issue (no ref, describe NOT_FOUND, nothing in flight) with an authorized `@MCTL investigate` gives exactly one `start_dev_loop_workflow` call with `requested_by=<login>`, then one reply that has the ack trailer. The reply is posted after the start.
- [ ] T2. Unauthorized author (`author_association=NONE`) gets the unauthorized reply with the ack, and no start.
- [ ] T3. A second tick on the same comments (ack now present) gives no second start. A second distinct `investigate` comment after the start finds the loop RUNNING and gets the "running, use reinvestigate" reply, with no start.
- [ ] T4. An investigation already in flight (fake check returns a busy id) gets the busy/refused reply with the ack, and no start. Two fresh issues in one tick give one start, and the second issue gets the busy reply.
- [ ] T5. A failed page from the repo comments listing (`gh` non-zero on page 2, and separately malformed JSON) counts as a scan failure for that repo, with no reply, no ack and no start. The next tick with a healthy listing dispatches the directive.
- [ ] T6. An issue with an existing proposal ref (including a terminal one) gets the reply naming `service/slug (status)` and `@MCTL reinvestigate`, with no start.
- [ ] T7. The in-flight check raises (visibility error) and gives no start, no ack, and a fail trailer; after `MAX_DISPATCH_ATTEMPTS` it gives the give-up ack.
- [ ] T8. Describe COMPLETED, or `WorkflowAlreadyStartedError` from the start, gives the already-handled reply with no start. Describe FAILED goes ahead and starts.
- [ ] T9. PR comments from the repo-wide listing are ignored. An issue reached by both discovery passes has its comments read once and gets one reply.
- [ ] T10. `@MCTL reinvestigate` on a fresh issue gets the no-proposal reply that mentions `investigate`. The existing reinvestigate tests and the label-path acceptance test pass unchanged.
- [ ] T11. `test_directives.py`: `investigate` is in `VERBS`, the unrecognised reply lists both verbs, and `reinvestigate` is not parsed as `investigate`.
- [ ] T12. `test_dev_loop_workflow.py`: the `investigate_in_flight` query is True while the investigate CWFT activity is pending and False after it, and an `IssueRef` without `requested_by` deserializes.

## Rollback

1. Fastest, no deploy: set `MCTL_DIRECTIVE_FRESH_ISSUES_ENABLED=false` on `mctl-agents-worker` (`services/admins/mctl-agents-worker/values.yaml`) to turn off the repo-wide pass only. Set `MCTL_DIRECTIVE_SCAN_ENABLED=false` to turn off the whole directive scan.
2. Full: revert the PR and roll the worker image back to the previous tag (`1.100.0` at the time of writing). The `IssueRef.requested_by` field and the query are additive, so loops started while the change was live should replay on the old code, provided the Temporal data converter ignores the unknown `requested_by` key. Confirm this with a replay test of one such history before rolling back. If the converter does not ignore it, keep the field and revert only the poller changes. Ack markers already posted remain valid for the restored `reinvestigate` path.
