# Design: issue-978-fix-devloop-recover-pre-accepted-proposa

## Current state

**Execution authorization (unchanged by this proposal).**
`orchestrator/proposal_state.py::execution_authorization` returns
`AUTHORIZATION_HUMAN_APPROVAL` only when `approval.approved_by` names someone
AND `approval.approval_ref` matches `aar_[A-Za-z0-9_-]{1,124}`. Otherwise it
returns `UNAUTHORIZED_NO_APPROVAL_GRANT` ("approved with no verifiable approval
grant"). `orchestrator/run_implementer.py` (around line 4512) applies it at the
execution boundary and writes the durable `blocked` marker
(`BLOCKED_EXECUTION_UNAUTHORIZED`, `_mark_blocked`, which keeps
`status: accepted`). It then calls
`orchestrator/approval_evidence.py::verify_execution_grant`, which reads the
grant back from mctl-api and requires: human decider, `mctl-agents-approve`
kind, target `<service>/<slug>`, `artifact_hash == current digest`, and state
`consumed` or `executed`.

**Canonical DevLoop approval.** In
`orchestrator/temporal/workflows/dev_loop.py::DevLoopWorkflow.run`, a
canonical loop always calls `_request_canonical_approval` before the park. That
call creates the `aar_` grant through
`activities/delegated_approval.py::request_devloop_approval`, bound to the
`we_`, `<service>/<slug>` and `read_proposal_content_digest`. The grant is
requested whether or not the proposal is already accepted, so the park already
happens for a pre-accepted proposal. After the signal, the loop runs the
`_ensure_fresh_grant` freshness check (#701) and then `_delegated_approve`, which
runs `submit_delegated_approve`. That call mints an `art_` run token and runs
`POST /api/v1/operations/mctl-agents-approve/execute` with
`X-MCTL-On-Behalf-Of: <aar_>`. mctl-api consumes the grant and submits the
approve CWFT with `approval_ref`. When the CWFT Succeeds, the loop ends its
`we_`, resolves the implementer and submits it. Nothing reads the record back.
`_OVERWRITABLE_PROPOSAL_STATUSES = {"proposed"}` means the investigator does
not rewrite an accepted proposal, so the digest stays the one the standalone
approval recorded.

**The defect: the approve CWFT (mctl-gitops).**
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml`,
`flip-status` step, around lines 349-360: if `CURRENT = accepted`, it compares
the recorded `content_digest` with the expected one. A mismatch is refused as
`approval_content_mismatch`. A match prints "already accepted -- no-op" and
exits 0. `approval_ref` is only appended on the proposed->accepted path
(around lines 449-453). So the consumed grant is never bound, the CWFT reports
Succeeded, and the implementer refuses.

**The no-PR tail.** `_watch_pr` (dev_loop.py around line 6227) polls
`activities/pr_state.py::get_pr_state`. Shepherd ticks are only scheduled when
a PR resolves. With no PR, `polls_without_pr` grows until
`PR_LOOKUP_GRACE_POLLS = 8` (x `MERGE_POLL_INTERVAL = 15 min`). The #516
`proposal-terminal-end` exit fires only for `LOOP_TERMINAL_PROPOSAL_STATUSES`
(`needs-triage`, `review-stuck`, `rejected`, ...). A blocked proposal stays
`accepted`, so that exit never fires. For the whole grace window, and for
older executions up to `MERGE_WATCH_DEADLINE`, the loop answers
`shepherd_in_loop=true`, which makes the global shepherd sweeper skip the slug.
`PRState` carries `proposal_status` but not the `blocked` marker.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/agents-state/.github/proposals/issue-299-design-governance-eliminate-review-workf/.status.yaml`
  shows `status: accepted`, `approval.approved_by: mashkovd`,
  `approval.content_digest: sha256:8b62...`, `digest_binding: reviewed`, **no
  `approval_ref`**, and `blocked.code: execution-unauthorized` with the message
  "execution not authorized: approved with no verifiable approval grant". Its
  remedy says to approve through the DevLoop, which is the path that fails.
  This confirms the root cause above.
- `/workdir/mctl-gitops/platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-approve.yaml`:
  read. The already-accepted branch is a no-op that never writes `approval_ref`.
- `mctl_get_dev_loop(workflow_id=dev-loop-mctlhq-.github-299)`: refused
  ("outside the investigate scope of this agent run"). The live workflow's
  status was not observed, which is recorded under Open questions in
  requirements.md.

## Proposed solution

There are three changes. Authority still comes only from the human-decided
`aar_` grant. The change is that the grant is now bound to the record, and the
loop proves the binding before it releases the implementer.

### 1. Approve CWFT: bind the grant on an already-accepted record (mctl-gitops, paired PR)

In the `flip-status` already-accepted branch, after the existing digest match:

- If `WORKFLOW_APPROVAL_REF` is empty: keep today's no-op (the standalone path
  is unchanged).
- If the record has no `  approval_ref:` line: insert
  `  approval_ref: '<aar_>'` and `  approval_ref_bound_at: '<now>'` into the
  existing `approval:` block. Leave `status`, `approved_by`, `approved_at` and
  `content_digest` untouched, so the original audit trail is preserved. Then
  run the existing post-edit check, commit, and push through the existing
  rebase-retry step. The commit message should read
  `chore(agents): bind approval grant <aar_> to <service>/<slug>`.
- If the record has the same ref: no-op (idempotent retry).
- If it has a different ref: `refuse approval_ref_conflict "..."` through the
  existing typed `refuse` helper, which makes it a typed refusal the DevLoop
  surfaces.

The approver identity is not taken from `approved_by`. The binding is valid
only because mctl-api already validated and consumed the human-decided grant
for this exact content digest before submitting this CWFT, and the
implementer re-verifies that grant independently. The rebase-conflict
fallback (around line 717) must also check that main contains the
`approval_ref` line, not just `status: accepted`, before declaring a
concurrent-approve no-op.

### 2. DevLoop: read back the binding before releasing the implementer (mctl-agents)

- New activity `read_proposal_approval_ref(service, slug) -> ApprovalRefRead`
  in `orchestrator/temporal/activities/proposals.py`. It reuses the GitHub
  contents-read plumbing that `read_proposal_status` uses and returns
  `(readable: bool, approval_ref: str | None)`. Transport and non-404 errors
  raise (retryable), the same contract as `read_proposal_status`. Register it
  on the worker (`orchestrator/temporal/worker.py`) and in
  `tests/temporal_harness.py`.
- In `DevLoopWorkflow.run`, inside the `if self._canonical:` approve branch,
  after the `while True` loop exits with `approve_result.succeeded`, and only
  under a new patch `APPROVAL_REF_BINDING_PATCH = "approval-ref-binding-check"`:
  run the activity. If it is unreadable or the ref is not `self._approval_ref`,
  return
  `self._approval_ended("approval_failed", "approval grant not bound to the proposal record (expected <aar_>, found <ref|none>)", ...)`.
  This happens before `_end_canonical_execution`'s success path and before
  `_resolve("implementer")`. The canonical `we_` ends Failed, as on every
  other approval-failure exit.
- Map the new CWFT refusal `approval_ref_conflict` to `approval_refused` in the
  existing typed-refusal handling. It is not in `STALE_GRANT_REFUSAL_CODES`,
  so no supersede or re-ask is attempted.
- Update the remedy text in `run_implementer.py` (`_UNAUTHORIZED_REMEDY` for
  `UNAUTHORIZED_NO_APPROVAL_GRANT`) so it states that the DevLoop approval
  binds a fresh grant to an already-accepted record.

### 3. DevLoop: end the watch on a blocked, PR-less implementation (mctl-agents)

- Add `blocked_code: str | None = None` to `activities/pr_state.py::PRState`,
  parsed from the same `.status.yaml` read (`blocked.code`). The default
  keeps old serialized results readable.
- In `_watch_pr`'s not-found branch, under a new patch
  `BLOCKED_TERMINAL_PATCH = "blocked-terminal-end"`, evaluated once in the
  `resume is None` arm and carried in `MergeWatchResume.blocked_terminal_end`
  like `proposal_terminal_end`: a non-empty `state.blocked_code` with
  `not saw_open_pr` counts toward the same `terminal_status_polls`
  confirmation (`PROPOSAL_TERMINAL_CONFIRM_POLLS = 2`). It then sets
  `watch_ended = f"implementation blocked ({code})"` and breaks.
  `_finish_after_watch` already turns `watch_ended` into `ended`.
- On every `_watch_pr` exit that ended without an open PR, set
  `self._shepherd_in_loop = False` in the `finally` (guarded by the same
  patch), so the query stops claiming shepherd ownership. The
  lifecycle-ownership release already happens in that `finally`.

### Stale or mismatched grants still fail closed

The following stay unchanged and are covered by tests:
- #701 `_ensure_fresh_grant` / `_supersede_grant_if_stale` before the spend;
- the CWFT's `approval_content_mismatch`;
- mctl-api's own intent check;
- the implementer's `verify_execution_grant` (`GRANT_CONTENT_MISMATCH`,
  `GRANT_NOT_SPENT`, `GRANT_WRONG_TARGET`).

## Alternatives

- **Accept `approved_by` + `content_digest` as authority for legacy records.**
  Rejected by the issue and by the design of `execution_authorization`: a
  file claim is not a decision.
- **Have the DevLoop rewrite the record back to `proposed` and run a normal
  flip.** Rejected. It needs a new write path that demotes an accepted record
  outside the CWFT, it races the implement sweep, and
  `update_status_file`'s `UnrunnableProposalError` guard and the
  idempotent-approve contract both assume one-way flips. Binding the ref in
  place is smaller and keeps the original approval trail.
- **Write `approval_ref` from the worker (an mctl-agents activity committing
  to gitops).** Rejected. Today the only writer of `approval_ref` is the CWFT
  that mctl-api submits after consuming the grant. A worker-side writer would
  be a second, weaker authority path (anything holding the worker's gitops
  token could bind any ref).
- **Only end the loop on the blocked marker (part 3) without fixing the
  binding.** Rejected as insufficient: the loop would fail visibly, but the
  migration would still be impossible.

## Platform impact

- **Cross-repo**: part 1 is an mctl-gitops change and must merge (and the
  ClusterWorkflowTemplate must sync) before the mctl-agents part 2 is
  deployed. Otherwise every canonical loop over a legacy-accepted proposal
  ends with `approval_failed: approval grant not bound` instead of a silent
  block. That is still strictly better than today, so the merge order is a
  preference, not a hard requirement.
- **Replay safety**: every new command (the read-back activity and the
  blocked-terminal exit) sits behind a new `workflow.patched` marker.
  `tests/test_patch_memoization.py` and `tests/test_workflow_replay.py` must
  stay green. In-flight executions keep their recorded behaviour by
  attrition.
- **Backward compatibility**: `PRState.blocked_code` and
  `MergeWatchResume.blocked_terminal_end` are defaulted fields. The CWFT
  behaviour is unchanged when `approval_ref` is empty (standalone approve).
- **Resource impact**: one extra GitHub contents read per canonical approve,
  and a shorter watch for blocked loops.
- **Risks**: (a) The CWFT's YAML editing uses `sed`/`printf` against an
  `approval:` block. Inserting a line into an existing block must keep it
  valid YAML. Mitigation: the existing post-edit check plus a new Python
  YAML-parse check, and an mctl-gitops test in
  `tests/test_cwft_mctl_agents_approve_digest_binding.py`. (b) A legacy
  record with a stale `blocked` marker: the implementer re-evaluates
  authorization each run, so a bound ref passes. Verify in T6.
- **Existing stuck loop** (`dev-loop-mctlhq-.github-299`): it cannot replay
  into the new branch. After deploy, abandon it (`mctl_abandon_dev_loop`) and
  restart it. A loop abandoned before implement restarts on the same
  workflow id.
