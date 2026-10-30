# Design: issue-799-feat-directives-mctl-investigate-starts

## Current state

- `orchestrator/directives.py` contains the pure recognition rule.
  `VERBS = frozenset({"reinvestigate"})`; `MENTION_TOKENS` match only at line
  start; `parse_comment` returns `Directive(verb=None)` for an unknown verb;
  `PRIVILEGED_ASSOCIATIONS = {OWNER, MEMBER, COLLABORATOR}`. Ack and fail
  markers (`ack_trailer`, `fail_trailer`) are honoured only when authored by
  `BOT_LOGINS = {"mctl-agents[bot]"}`.
- `orchestrator/run_issue_directive_poller.py` `scan()` gets its input only
  from `list_proposal_refs()`. It drops `TERMINAL_STATUSES`, maps each slug's
  `issue-<N>-` prefix to an issue URL (`issue_url_for`) and reads that issue's
  comments with `read_issue_comments` (REST
  `repos/{repo}/issues/{n}/comments`, `--paginate --jq '.[]'`, `node_id` as the
  comment id). An issue without a proposal is never read, which is cause 1 in
  the issue. `_handle_directive` runs the decision table: unauthorized,
  unrecognised, no-proposal (`_reply_no_proposal` points only to the label),
  ambiguous, not-overwritable, or dispatch. Dispatch requires a live DevLoop
  (`directive_execution.resolve_loop_execution`) and submits the
  `mctl-agents-investigate` operation to mctl-api (`submit_investigate`). The
  module docstring states the comment path "never starts, signals or updates"
  a DevLoop. Failure accounting is `_record_dispatch_failure`
  (`MAX_DISPATCH_ATTEMPTS = 3`, fail trailer, give-up ack). The per-tick cap is
  `DEFAULT_MAX_DIRECTIVES = 3`, applied round-robin per issue.
- `orchestrator/temporal/activities/issue_poll.py` defines
  `directive_scan_activity`, which runs as the second activity of
  `IssuePollWorkflow` (`orchestrator/temporal/workflows/issue_poll.py`, gated by
  `workflow.patched("directive-scan")`, 5-minute `start_to_close`).
- `orchestrator/temporal/start.py` defines `start_dev_loop_workflow(issue_url, client)`:
  id `workflow_id_for(issue_url)` (`dev-loop-mctlhq-<repo>-<n>`),
  `ALLOW_DUPLICATE_FAILED_ONLY` plus `USE_EXISTING`. A COMPLETED prior run
  raises `WorkflowAlreadyStartedError`. `restart_if_restartable` is the
  operator-only restart after an abandon. The intake poller
  (`orchestrator/run_issue_poller.py` `poll()`) calls `start_dev_loop_workflow`
  for `SERVICES` repos only and does not call `restart_if_restartable`.
- `orchestrator/temporal/workflows/dev_loop.py` defines `IssueRef` (frozen
  dataclass: `issue_url`, `work_item_id`, `resume`, `execution_request_id`,
  all defaulted). Investigate runs via `_run_cwft("mctl-agents-investigate", ...)`
  at line ~3580, with a continuation submit at ~3735. Queries exist for
  `work_context`, `abandon_state`, `human_input_state` and others. No query
  says whether an investigation is in flight, and no search attributes are
  upserted.
- `orchestrator/temporal/activities/visibility.py` lists running loops with
  `ACTIVE_DEV_LOOPS_QUERY = "WorkflowType = 'DevLoopWorkflow' AND ExecutionStatus = 'Running'"`.
- `config/settings.py` `SERVICES` lists 17 repos (mctl-web through mctl-alice).
- The "one investigate at a time" rule: the only enforcement found is the
  `mctl-gitops-main-writes` mutex on the write step of
  `cwft-mctl-agents-investigate.yaml`. Nothing serialises whole
  investigations.
- README "Directive comments" (README.md ~125-150) documents only
  `reinvestigate` and says the comment path never starts a DevLoop.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: the
  Temporal worker that runs `directive_scan_activity` is at image tag `1.100.0`,
  with `TEMPORAL_ADDRESS=temporal-frontend.temporal.svc.cluster.local:7233`,
  `TEMPORAL_NAMESPACE=mctl-agents`, and `GITHUB_TOKEN_FILE` mounted.
  `MCTL_DIRECTIVE_SCAN_ENABLED` is not set, so the scan is enabled by default.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`:
  the only `synchronization` is `mutex: mctl-gitops-main-writes` on the write
  step. There is no whole-template semaphore.
- mctl MCP tools were not called. Runtime facts (Temporal visibility, mctl-api
  `dev-loop/start` internals) were not observed, and the related gaps are
  recorded under Open questions in requirements.md.

## Proposed solution

### 1. Verb (`orchestrator/directives.py`)
`VERBS = frozenset({"investigate", "reinvestigate"})`. Matching is unchanged.
The split-first-word rule already distinguishes `investigate` from
`reinvestigate`. Update the comment above `VERBS`.

### 2. Fresh-issue discovery (`run_issue_directive_poller.py`)
New function `list_repo_comments(repo: str, since: str) -> list[RepoComment]`:
`gh api --paginate --jq '.[]' "repos/mctlhq/{repo}/issues/comments?since=<iso>&sort=updated&direction=asc&per_page=100"`.
It parses each line into the existing `RawComment` fields plus the issue number
taken from `html_url` (`/issues/<n>#`). Comments whose `html_url` contains
`/pull/` are dropped. Any `CalledProcessError`, JSON error or line missing
`html_url`/`node_id` raises `RepoCommentScanError`. Partial output is never
returned. `since = now - MCTL_DIRECTIVE_LOOKBACK_HOURS` (default 72).

`scan()` gets a second discovery pass, run after the proposal-driven pass has
filled `seen_issue_urls`:
- For each `repo in SERVICES`, call `list_repo_comments`. On
  `RepoCommentScanError`, log a WARN, increment `failed` and skip the repo. No
  directive from it is acted on this tick, and none is acked.
- `parse_comments` runs on the listing. Only issues with at least one parsed
  directive (any verb, including `None`) and whose URL is not already in
  `seen_issue_urls` move on.
- For those issues, call `read_issue_comments(issue_url)`, the same
  authoritative full read used today, then apply `acked_comment_ids` and
  `failed_attempt_counts` and add unacked directives to `pending_by_issue`
  with `ref=None`. A failure here is per-issue, as today.
- The proposal-driven pass and its `ref` stay as they are. Pending entries
  become `(ref | None, issue_url, directive, fail_count)`, and the round-robin
  cap applies to both sources.

### 3. Decision table (`_handle_directive`)
Pass `service` and `number` explicitly, because `ref` may be None. After the
unauthorized and unrecognised checks:
- `verb == "reinvestigate"`: existing path. `matches` is derived from
  `all_refs`. With `ref=None` and no matches, it replies `_reply_no_proposal`,
  whose text now also suggests `@MCTL investigate`.
- `verb == "investigate"`:
  1. `matches` (service and issue number over unfiltered `all_refs`) not empty:
     reply `_reply_investigate_has_proposal(author, id, matches)` naming each
     `service/slug (status)` and pointing to `@MCTL reinvestigate`. Ack.
  2. `describe()` on `workflow_id_for(issue_url)`. RUNNING: reply
     `_reply_investigate_loop_running(author, id, wf_id)` pointing to
     `reinvestigate`, ack. `RPCError` NOT_FOUND, FAILED, TERMINATED, CANCELED or
     TIMED_OUT: go on to step 3. COMPLETED: reply
     `_reply_investigate_already_handled` (ack), which names the operator
     restart (`mctl_trigger_issue`, `use_temporal=true`). Any other describe
     error: `_record_dispatch_failure` (unacked, fail-trailer budget).
  3. Concurrency gate. Each tick has one `_InvestigateGate` object. If this
     tick already started one investigate, refuse. Otherwise call
     `investigation_in_flight(client)`, which lists
     `ACTIVE_DEV_LOOPS_QUERY` and runs the new `investigate_in_flight` query on
     each run, stopping at the first True. A True answer gets
     `_reply_investigate_busy(author, id, wf_id_of_busy)`: "another
     investigation (`<id>`) is running, only one runs at a time; comment
     `@MCTL investigate` again once it finishes". The reply is acked. Any
     listing or query error is unknown and goes to `_record_dispatch_failure`.
     It is never read as "none in flight".
  4. Dry-run prints what would happen and returns.
  5. Policy checkpoint (`policy_checkpoint.MCTL_OPERATION_EXECUTE` style,
     `execute:dev-loop-start`, as for `submit_investigate`), then
     `start_dev_loop_workflow(issue_url, client, requested_by=author)`.
     `WorkflowAlreadyStartedError` gets the already-handled reply. Any other
     exception goes to `_record_dispatch_failure`. On success the gate is
     marked and `_reply_investigate_started(author, id, handle.id,
     handle.result_run_id)` is posted with `_post_reply_with_retries` and the
     ack. The ack is posted only after the start returned. If the ack write
     fails, the code logs loudly and re-raises, as on the existing dispatched
     path. A retry next tick is safe because `USE_EXISTING` attaches to the
     running loop, and step 2 then answers "running".

The concurrency outcome is **refused with a retry hint**, not queued. A queue
would need a third marker type to keep the "queued" reply from repeating every
tick while the comment stays unacked, and a starvation policy. Refusal reuses
the ack model as it is and answers every comment exactly once.

### 4. Requester and in-flight state (`dev_loop.py`, `start.py`)
- `IssueRef.requested_by: str | None = None`. It is defaulted, so old histories
  still deserialize, the same way as the other optional fields.
- `start_dev_loop_workflow(issue_url, client=None, *, requested_by=None)` sets
  `IssueRef(issue_url, requested_by=requested_by)` and, when given,
  `memo={"requested_by": requested_by, "requested_via": "directive"}`. Existing
  callers are unaffected.
- `DevLoopWorkflow._investigate_in_flight: bool`, set True immediately before
  both `_run_cwft("mctl-agents-investigate", ...)` awaits and reset in a
  `finally`. A new `@workflow.query def investigate_in_flight(self) -> bool`
  exposes it. Assigning instance state and adding a query handler do not add
  commands, so no `workflow.patched` marker is needed and replays are
  deterministic. Running loops answer the query once workers run the new
  image. A loop parked at approval answers False, which is correct because its
  investigate is done.

### 5. Module docstring, replies, README
Update the docstring sentence "never starts ... one": the comment path now may
start a DevLoop, only for `investigate` on a fresh issue. Update the README
"Directive comments" section: both verbs, fresh-issue discovery through the
repo-wide comments endpoint within the lookback window, the one-at-a-time
refusal, and the replies for an existing proposal or loop.

## Alternatives

- **Call mctl-api `POST /api/v1/agents/dev-loop/start`** instead of Temporal
  directly. This gives exact parity with `mctl_trigger_issue`, including the
  abandon restart. It was dropped because the worker authenticates to mctl-api
  as a service identity, so the endpoint would record the service and not the
  commenter as requester. It would also restart abandoned loops, which the
  intake poller deliberately avoids. The label path already starts loops
  directly, so the directive path follows it.
- **Discovery via `gh search issues --match comments`.** The issue rules this
  out, and the existing docstring explains why: search is index-lagged, so a
  delay would bring back the silence being fixed.
- **Queue busy requests** (leave the comment unacked and post a single "queued"
  reply with a new marker). This gives better UX but adds a third marker
  family, an ordering/starvation policy, and a reply whose promise depends on
  the lookback window. It was rejected in favour of the simpler refusal and
  recorded as possible future work.
- **In-flight detection via Argo** (list running `mctl-agents-investigate`
  workflows through mctl-api). This would also catch operator-submitted
  investigates. It was dropped because no list-by-template call exists in this
  repo's mctl client, and the Temporal query keeps the signal next to the loop
  that owns it.

## Platform impact

- **API cost:** 17 extra paginated REST listings per 15-minute tick, plus one
  full issue read per fresh issue that has a mention. This is well within
  installation rate limits. The visibility listing and queries run only when an
  `investigate` actually reaches the gate.
- **Backward compatibility:** `IssueRef.requested_by` and
  `start_dev_loop_workflow(requested_by=...)` are defaulted. The new query is
  additive. The `reinvestigate` and label paths are unchanged except for the
  wording of `_reply_no_proposal`.
- **Activity timeout:** `directive_scan_activity` has a 5-minute limit. The new
  listings are bounded by the lookback window. If needed, raise
  `ACTIVITY_TIMEOUT` for that activity only.
- **Risks:**
  - A forged ack. Mitigated: unchanged, only `BOT_LOGINS` markers count.
  - A mass-comment burst. Mitigated by the existing `DEFAULT_MAX_DIRECTIVES`
    cap and by the one-investigate-start-per-tick rule.
  - A missed comment after an outage longer than the lookback window. Mitigated
    by a configurable window and a WARN when a repo listing fails. Recorded in
    Open questions.
  - The in-flight gate fails closed. A persistent query failure ends in a
    give-up reply after 3 attempts, not silence.
- **Kill switch:** `MCTL_DIRECTIVE_SCAN_ENABLED=false` already disables both
  passes. A new `MCTL_DIRECTIVE_FRESH_ISSUES_ENABLED=false` disables only the
  repo-wide pass, so the scan returns to proposal-driven discovery.
