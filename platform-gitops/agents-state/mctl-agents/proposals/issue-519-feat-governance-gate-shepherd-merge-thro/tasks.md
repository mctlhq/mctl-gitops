# Tasks: issue-519-feat-governance-gate-shepherd-merge-thro

- [ ] 1. Carry over #484's approval-evidence plumbing (no ticket, no store).
      Add `Decision.approver` / `Decision.decided_at` and
      `ApprovalOutcome.decided_by` in `orchestrator/policy_checkpoint.py`,
      return them from `_redeem`, emit them in `decision_record` and forward
      them from `emit`; fill `decided_by` from `ApprovalRecord.decided_by` in
      `orchestrator/action_approvals.py` (`_outcome`, `redeem`'s expired and
      granted branches); add the three kwargs to
      `tracing.record_policy_decision`. — DoD: a granted decision's
      `POLICY_DECISION` line and its `mctl.policy.decision` span event carry
      `approval_ref`, `approver`, `decided_at`; a decision that never reached a
      human carries all three empty; no raw arguments or payloads are logged.

- [ ] 2. Add the env-selected merge policy variant (depends on 1) —
      `MERGE_APPROVAL_ENV = "MCTL_POLICY_MERGE_APPROVAL"`,
      `MERGE_APPROVAL_POLICY` (the `github-pr-merge` rule replaced by
      `Rule("github-pr-merge-approval", GITHUB_PR_MERGE, "merge",
      REQUIRE_APPROVAL)`, version `mctl-agents/policy/v1-merge-approval`) and
      `configured_policy()` in `orchestrator/policy_checkpoint.py`. — DoD:
      unset/empty/`none` returns `BUILTIN_POLICY` unchanged; `require` returns
      the variant; any other value yields a policy whose merge rule is `DENY`;
      `BUILTIN_POLICY` itself is not mutated.

- [ ] 3. Split the shepherd's merge (depends on 2) — extract
      `run_shepherd.merge_pr_unchecked(pr)` (the `NEVER_MERGE_SERVICES`
      refusal, `refresh_github_token()`, `gh pr merge --merge --delete-branch
      --match-head-commit <SHA>`, the snapshot re-read) and keep `merge_pr(pr)`
      as the checkpoint wrapper, now passing `policy=configured_policy()`. —
      DoD: with the gate off, `merge_pr` behaves exactly as before (existing
      `tests/test_run_shepherd.py` and
      `tests/test_github_mutations_policy.py` pass untouched); the `gh` command
      is constructed in exactly one place.

- [ ] 4. Delegate the merge for gated services (depends on 3) — add
      `SHEPHERD_MERGE_APPROVAL_SERVICES` via `_service_set_from_env`, add
      `_merge_gate_delegated(service)`, feed it into the `fix_only` argument of
      `decide()` in the tick, return `devloop-workflow` from
      `_merge_owner_for` for a gated non-`NEVER_MERGE` service, and guard
      `merge_pr` so a gated service prints `MERGE_GATED pr=<repo>#<n>
      head=<sha>` and returns `(False, None)` **before** the checkpoint. —
      DoD: for a gated service a tick that would have merged yields
      `defer-merge`, invokes no `gh pr merge`, creates no approval request even
      with `MCTL_POLICY_APPROVALS=mctl-api` in the pod env, writes no approval
      field to `.status.yaml`, and leaves `status` and
      `SHEPHERD_INPUT_STATUSES` membership unchanged.

- [ ] 5. Add the gated merge activity (depends on 2, 3) — new
      `orchestrator/temporal/activities/pr_merge.py` with
      `merge_pull_request_gated(GatedActionInput) -> GatedActionResult`:
      gate-off and `NEVER_MERGE_SERVICES` short-circuits first; then
      `run_shepherd._fetch_pr_snapshot`, `run_shepherd.read_codex_review`,
      `ci_checks.read_required_checks` in `asyncio.to_thread`; preconditions
      (unreadable, merged, closed, draft, head moved) and
      `run_shepherd.decide(...) == "merge"`; then `run_gated(...,
      pc.GITHUB_PR_MERGE, "merge", pr_ref, {"method", "delete_branch",
      "match_head_commit": pr.head_sha}, side_effect=merge_pr_unchecked,
      policy=configured_policy())`; surface `approver`/`decided_at` on
      `GatedActionResult`. — DoD: with the gate off it performs zero network
      calls; every precondition path returns without creating, redeeming or
      consuming a receipt; a permitted decision performs exactly one
      `gh pr merge`; a raising side effect is reported as `effect_error`.

- [ ] 6. Register the activity (depends on 5) — add
      `merge_pull_request_gated` to `orchestrator/temporal/worker.py`'s
      activity list beside `read_action_approval`. — DoD: the worker starts and
      `tests/test_temporal_activities.py`-style registration assertions cover
      the new name.

- [ ] 7. Wire `DevLoopWorkflow` as the first caller (depends on 5, 6) — in
      `_watch_pr`, behind `workflow.patched("gated-merge")`: mint one execution
      identity via `mint_execution_context` on the first attempt, keep it in
      workflow state, add `merge_gate_execution_id` / `merge_gate_trace_id` to
      `MergeWatchResume` and rehydrate them in `_resume_merge_watch`, refuse a
      `continue_as_new` hop while a merge-approval wait is in flight in
      `_merge_watch_hop_suggested`, call `run_gated_action(
      "merge_pull_request_gated", ...)` while the polled PR is open with
      `max_wait_seconds` bounded by the remaining merge-watch budget, and
      handle every outcome per design.md's table (no automatic
      `next_attempt()`). — DoD: one stable `execution_id` is used for the
      request and every revalidation, including across a hop; a history without
      the marker replays unchanged; `ran` logs `MERGE_APPROVED` with
      `approval_ref`/approver/`decided_at`.

- [ ] 8. Documentation (depends on 4, 7) — update ADR-014 §7 and its open
      decision 3 to name the merge gate as the first `run_gated_action`
      adopter; add `docs/adr/017-shepherd-merge-approval.md` (including why
      #484's `ApprovalTicket` is unrepairable); add
      `docs/runbooks/shepherd-merge-approval.md` (enablement, approving/denying
      through mctl-api's action-approval routes, the log lines, the two
      documented consequences); note the new env var and `merge_owner:
      devloop-workflow` in `README.md`'s shepherd section. — DoD: docs describe
      only the built behaviour; no `ApprovalTicket` vocabulary survives
      anywhere in the repo.

- [ ] 9. Close out PR #484 (depends on 8) — close it unmerged with a comment
      pointing at this issue and at the parts that were carried over (task 1
      and the runbook text). — DoD: #484 is closed, not merged;
      `orchestrator/approval_ticket.py` exists nowhere on `main`.

## Tests

- [ ] T1. `tests/test_policy_checkpoint*`: `configured_policy()` for unset /
      `none` / `require` / a bogus value; the variant's rule id and version;
      `BUILTIN_POLICY` unmutated; a `github-pr-merge` request under the variant
      with `NO_APPROVALS` is refused `approval_required` and never permitted.
- [ ] T2. Evidence: a granted decision records `approver` and `decided_at` in
      `decision_record` and passes them to `tracing.record_policy_decision`
      (extend `tests/test_tracing_agents.py`); a pending/denied decision records
      `approval_ref` with an empty approver.
- [ ] T3. `tests/test_run_shepherd.py`: with the gate off, `merge_pr` is
      byte-identical in behaviour (command, refusal paths, return values).
- [ ] T4. New `tests/test_run_shepherd_merge_gate.py`: for a gated service the
      tick yields `defer-merge` with `merge_owner: devloop-workflow`, prints
      `MERGE_GATED`, runs no `gh pr merge`, and — with a stub approval store
      that records every call — creates **no** approval request; `.status.yaml`
      gains no approval field and keeps its `status`.
- [ ] T5. New `tests/test_pr_merge_activity.py` (`ActivityEnvironment`): gate
      off → no network call; `NEVER_MERGE_SERVICES` → forbidden, no request;
      already merged / closed / draft / head moved → precondition unmet, no
      request; `decide()` returning `wait` or `address-review` → precondition
      unmet; `decide()` returning `merge` → a request is created and the
      decision is `approval_pending`.
- [ ] T6. Single use, on the same fake mctl-api used by
      `tests/test_action_approval_wait.py`: approve → exactly one
      `gh pr merge`; an activity retry after the consume → `approval_consumed`
      and no second merge; a simulated worker crash between consume and effect
      → the retry ends `consumed`; a second waiter on the same receipt →
      `already_waiting`.
- [ ] T7. Fail-closed: deny → `denied` and no merge; expire → `expired`;
      nobody answers → `timed_out`; the head SHA changes while the human waits
      → `mismatch` with nothing consumed (the head is in the args, so this is
      asserted on the intent hash, not just the outcome); mctl-api unreachable
      → `undecided`, retried inside the wait, never approved.
- [ ] T8. `tests/test_dev_loop_workflow.py` + a replay scenario in
      `tests/replay_scenarios.py`: a history recorded before the
      `gated-merge` marker replays unchanged (no new commands); a new history
      enters the gate; the same `execution_id` is used before and after a
      merge-watch `continue_as_new` hop; no hop is taken while the wait is in
      flight; `denied` does not trigger a second request.
- [ ] T9. Lint/type gates the repo already runs (`ruff`, `pytest`) stay green;
      `tests/test_patch_memoization.py` still pins the marker semantics.

## Rollback

Three independent levers, smallest first:

1. **Config only (no deploy).** Unset `SHEPHERD_MERGE_APPROVAL_SERVICES` in the
   shepherd CWFT and `MCTL_POLICY_MERGE_APPROVAL` on the worker and the CWFT in
   mctl-gitops. `configured_policy()` returns `BUILTIN_POLICY`, the merge rule
   is `ALLOW` again, the shepherd's next tick merges in-pod as before, and the
   gated activity short-circuits to `blocked` on its first check. In-flight
   receipts are simply never redeemed and expire. This is the primary rollback
   and needs no code change.
2. **Stop asking.** If the gate misbehaves while the policy must stay tight,
   leave `MCTL_POLICY_MERGE_APPROVAL=require` and unset
   `MCTL_POLICY_APPROVALS` on the worker: every merge is then refused
   `approval_required` (fail closed, no merges for gated services) while
   humans merge by hand.
3. **Revert the code.** Reverting the PR is safe at any point: the only
   persisted artefacts are mctl-api approval rows (which expire on their own
   TTL) and two additive `MergeWatchResume` fields that older code ignores. No
   migration, no `.status.yaml` shape change, nothing to clean up. Loops that
   already recorded the `gated-merge` marker keep replaying it; a revert must
   therefore keep the activity registered (or accept that those loops fail
   their next gate attempt and fall through to `blocked`), so prefer lever 1
   for anything urgent.
