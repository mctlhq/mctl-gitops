# Tasks: issue-417-fix-devloop-a-directive-comment-on-an-is

- [ ] 1. Add `orchestrator/directives.py`: `MENTION_TOKENS`, `VERBS` (only
  `reinvestigate`), `BOT_LOGINS`, `PRIVILEGED_ASSOCIATIONS`, the frozen
  `Directive` dataclass (`comment_id`, `author`, `created_at`, `verb`,
  `authorized`), and `parse_comment()` / `parse_comments()`. No imports beyond
  the stdlib — no `gh`, no temporalio, no filesystem. — DoD: a mention with a
  known verb returns `verb="reinvestigate"`; a mention with an unknown verb
  returns `verb=None` (not `None`); a comment with no mention returns `None`; a
  bot-authored comment returns `None`; a login failing
  `^[A-Za-z0-9-]{1,39}$` is refused. `uv run ruff check orchestrator` and
  `uv run mypy` clean.

- [ ] 2. Add the ack-marker helpers to `orchestrator/directives.py` (depends on
  1): `ack_trailer(comment_id) -> str` rendering
  `<!-- mctl-directive-ack: <id> -->`, and `acked_comment_ids(comments) -> set[str]`
  parsing trailers out of existing bot comments. — DoD: `acked_comment_ids` is
  the exact inverse of `ack_trailer` for any id; a comment body that merely
  quotes the trailer inside a fenced code block is still parsed as an ack (the
  conservative direction — a false "already acked" costs a missed retry, a
  false "not acked" costs a duplicate SDK run).

- [ ] 3. Add `orchestrator/run_issue_directive_poller.py` with
  `DirectiveScanResult`, `issue_url_for(service, slug)`, `read_issue_comments()`
  and `async def scan(dry_run=False, max_directives=DEFAULT_MAX_DIRECTIVES)`
  (depends on 1, 2). Enumerate candidates from
  `gitops_state.list_proposal_refs()` filtered to non-terminal statuses, derive
  the issue URL from `service` + the slug's `issue-<N>-` prefix, and fetch
  comments with one `gh issue view --json number,url,state,comments` per
  candidate through `run_issue_investigator._run`. — DoD: `scan()` returns
  counts of dispatched / replied / deferred / failed; a `gh` failure on one
  issue is logged and the scan continues; `--dry-run` neither submits nor posts.

- [ ] 4. Implement the decision table in `scan()` (depends on 3). For each
  unacked directive, in order: unauthorized author -> refusal reply; unrecognised
  verb -> "not a recognised instruction" reply listing supported verbs; no
  `issue-<N>-*` directory -> reply pointing at `agents:intake`; more than one
  matching directory -> reply naming them; status outside
  `run_issue_investigator._OVERWRITABLE_STATUSES` -> reply naming the status;
  otherwise dispatch. — DoD: every branch posts exactly one reply carrying the
  ack trailer, and only the last branch submits anything. No branch is silent.

- [ ] 5. Implement dispatch in `scan()` (depends on 4): submit the mctl-api
  operation `mctl-agents-investigate` with `issue_url`, `slug` and
  `requested_by`, reusing the auth from `orchestrator/temporal/mctl_client.py`
  (`MCTL_API_BASE_URL`, `auth_headers`). Post the ack reply naming the returned
  Argo workflow name, the `service`/`slug`, and the commenter — **only after** a
  successful submit. — DoD: on submit failure no ack trailer is written, the
  reply says the dispatch failed, and the directive counts as a per-issue failure
  without failing the tick; the next tick retries the same comment id.

- [ ] 6. Add the per-tick cap and CLI (depends on 5): `DEFAULT_MAX_DIRECTIVES = 3`,
  `--max-directives`, `--dry-run`, `main()` mirroring
  `run_issue_poller.main()` (summary block, `sys.exit(0)` on per-issue failures).
  — DoD: a tick with more actionable directives than the cap dispatches exactly
  the cap, leaves the rest unacked, and logs the number deferred.

- [ ] 7. Record the requester in the proposal (depends on 5). Thread
  `requested_by` and the requesting comment URL through
  `run_issue_investigator.investigate()` into `write_status_yaml`'s payload as a
  `request: {by, comment, received_at}` block beside the existing `source`
  block. — DoD: a re-investigation carrying the parameters writes the block; one
  without them writes an unchanged payload; `proposal_state.update_status_file`
  preserves the block across every later transition.

- [ ] 8. Wire the scan into the existing tick (depends on 6). Add
  `directive_scan_activity` to `orchestrator/temporal/activities/issue_poll.py`
  and a second `execute_activity` in
  `orchestrator/temporal/workflows/issue_poll.py`, gated on
  `workflow.patched("directive-scan")`. Register the activity in
  `orchestrator/temporal/worker.py` on the control queue. — DoD: no new Temporal
  schedule; the existing `issue-poll-mctl-agents-schedule` (15m / offset 7m /
  SKIP) drives both passes; replay of a pre-change history takes the unpatched
  branch.

- [ ] 9. Carry `updated_at` through the gitops read (depends on nothing else).
  Extend `ProposalStateRef` and `gitops_state._read_blob` to extract
  `updated_at` from the `.status.yaml` already being parsed, defaulted to `""`.
  — DoD: existing callers compile unchanged; `list_proposal_refs()` returns the
  timestamp; a `.status.yaml` missing the field yields `""` rather than raising.

- [ ] 10. Report stale directives from reconcile (depends on 1, 2, 9). Add
  `StaleDirective` and `stale_directives` to `ReconcileDiscoveryResult` in
  `orchestrator/temporal/activities/discovery.py`, and
  `stale_directives: list[StaleDirective] | None = None` to
  `ReconcileWorkflowResult`, populated behind
  `workflow.patched("directive-staleness")` and logged. Report-only — no
  dispatch, no write. — DoD: a proposal whose issue has a directive-shaped
  comment newer than its `updated_at` and no matching ack appears in the tick
  result; one with an ack does not; the field defaults so older recorded results
  still deserialize.

- [ ] 11. Document the gesture (depends on 4). Add the comment trigger to
  `spec.triggers` in `agents/_manifests/issue-investigator/agent.yaml`, to the
  matching entry in `docs/agent-inventory.yaml`, and a short "Directive comments"
  section to `README.md` giving the exact syntax, the supported verb, and the
  authorization rule. — DoD: `uv run pytest tests/test_agent_inventory.py
  tests/test_manifest.py` passes (both are machine-checked against the code).

## Tests

- [ ] T1. `tests/test_directives.py` — table-driven over `parse_comment`:
  recognised verb, unrecognised verb after a mention, no mention, bot author,
  mixed case, mention mid-line vs. line-initial, a body whose *quoted* text
  contains a mention, and a login failing the login pattern.

- [ ] T2. `tests/test_directives.py` — `ack_trailer` / `acked_comment_ids`
  round-trip, including an id containing `-` and `_` (GraphQL node ids do), and
  a comment carrying two trailers.

- [ ] T3. **The acceptance test.** `tests/test_run_issue_directive_poller.py` —
  the same directive posted twice as two distinct comment ids produces exactly
  two submits and two replies; running `scan()` three more times over the
  resulting comment list (now containing both acks) produces zero further
  submits; and **no `gh issue edit` call is ever made** — assert the recorded
  `_run` command lists contain no `--add-label` / `--remove-label`. This is the
  issue's stated acceptance criterion, and the label assertion is the part that
  proves the two paths stay independent.

- [ ] T4. `tests/test_run_issue_directive_poller.py` — one test per
  non-dispatch branch of task 4 (unauthorized, unrecognised verb, no proposal
  dir, ambiguous dirs, non-overwritable status), each asserting exactly one
  reply posted, the reply body naming the specific reason, and zero submits.

- [ ] T5. `tests/test_run_issue_directive_poller.py` — submit failure leaves no
  ack trailer, posts a dispatch-failed reply, counts one failure, and a second
  `scan()` over the same comments retries the same comment id exactly once.

- [ ] T6. `tests/test_run_issue_directive_poller.py` — `--dry-run` posts nothing
  and submits nothing but reports what it would do; `--max-directives` caps
  dispatches and reports the deferred count; a `gh` failure on one candidate
  does not stop the others.

- [ ] T7. `tests/test_run_issue_investigator.py` — `write_status_yaml` writes
  the `request` block when the parameters are present and an unchanged payload
  when they are not; `update_status_file` preserves it across a later transition.

- [ ] T8. `tests/test_temporal_activities.py` — `directive_scan_activity`
  returns the scan counts; `list_proposal_refs()` surfaces `updated_at`; a
  `.status.yaml` without the field yields `""`.

- [ ] T9. `tests/test_reconcile_workflow.py` — a proposal with a newer
  directive-shaped comment and no ack is reported as stale; one with an ack is
  not; the sweep performs no submits and no writes in either case.

- [ ] T10. `tests/test_workflow_replay.py` — replay a pre-change
  `IssuePollWorkflow` history and a pre-change `ReconcileWorkflow` history
  against the patched code; both must take the unpatched branch and replay clean.
  Add the new-path histories to `tests/fixtures/histories/` once recorded.

- [ ] T11. Full gate before the PR: `uv run pytest`,
  `uv run ruff check orchestrator config tests tools`, `uv run mypy` — all three,
  as `.github/workflows/pr-validation.yml` runs them. Commit with a
  release-please-releasable type (`fix(devloop): ...`), per the `commit-lint`
  job.

## Rollback

The change is additive and each layer reverts independently.

1. **Fastest kill, no deploy.** Set `MCTL_DIRECTIVE_SCAN_ENABLED=false` on the
   Temporal worker (task 3 reads it, defaulting to on). The scan short-circuits
   and the tick reverts to label-only dispatch. Nothing else in the system knows
   the scan existed.
2. **Revert the wiring only.** Revert task 8's commit. `IssuePollWorkflow` stops
   calling the scan; the `directive-scan` marker takes the unpatched branch on
   replay, so in-flight executions are unaffected.
3. **Revert reconcile reporting.** Revert task 10. `stale_directives` is
   report-only and defaulted, so removing it cannot break a reader.
4. **Full revert.** Revert tasks 1-11. The only artifacts left behind are
   acknowledgement comments on issues (inert text, no reader once the parser is
   gone) and `request` blocks in some `.status.yaml` files — which
   `update_status_file` preserves harmlessly and no code requires.

No gitops schema is migrated and no `.status.yaml` transition is changed, so a
revert at any point leaves every proposal in a state the pre-change code already
handles. What a revert restores is the original defect: a directive comment
starts nothing and reports nothing.
