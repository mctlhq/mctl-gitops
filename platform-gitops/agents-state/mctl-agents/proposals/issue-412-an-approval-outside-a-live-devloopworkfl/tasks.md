# Tasks: issue-412-an-approval-outside-a-live-devloopworkfl

- [ ] 1. Widen `ProposalStateRef` in
  `orchestrator/temporal/activities/gitops_state.py`: `_parse_status_yaml`
  also returns `updated_at`, `attempt_expires_at` and the raw mapping needed
  for the approval check; new dataclass fields are defaulted — DoD: existing
  callers (`detect_orphans`, `reconcile_lifecycle_ownership`) compile and pass
  unchanged, and a result payload without the new fields still deserializes.
- [ ] 2. Promote `orphans._expected_workflow_id` to a public
  `expected_dev_loop_id(slug, repo, service)` in the same module, keeping the
  private name as an alias (depends on nothing) — DoD: `detect_orphans`
  behaviour is byte-identical and `tests/test_temporal_activities.py` passes.
- [ ] 3. Add `orchestrator/temporal/activities/stranded.py` with
  `StrandedProposal`, `StrandedScanResult` and the
  `find_stranded_accepted(active_workflow_ids, grace_minutes)` activity,
  applying the five skip filters from `design.md` §1 and reusing
  `proposal_state.human_approval_satisfied` / `unrunnable_reason` (depends on
  1, 2) — DoD: every skip carries a reason string; no predicate is duplicated
  from `proposal_state.py` or `run_implementer.py`.
- [ ] 4. Add `orchestrator/temporal/workflows/implement_sweep.py` with
  `SweptImplementWorkflow` (one `submit_and_wait` of
  `IMPLEMENTATION_OPERATION` on `IMPLEMENTATION_TASK_QUEUE`, scoped
  `{service, slug}`) and `ImplementSweepWorkflow` (visibility query ->
  `find_stranded_accepted` -> bounded `start_child_workflow` with
  `id=implement-sweep-{service}-{slug}`, `USE_EXISTING`, `ABANDON`)
  (depends on 3) — DoD: a failed visibility query returns a
  `skipped_reason` and starts zero children; `ImplementSweepResult` carries
  candidate/submitted/skipped counts.
- [ ] 5. Log one `STRANDED service=... slug=... reason=...` line per candidate,
  including candidates dropped by the per-tick cap, mirroring `detect_orphans`'
  `ORPHAN` lines (depends on 4) — DoD: a tick that submits nothing is still
  distinguishable in logs from a tick that found nothing.
- [ ] 6. Register both workflows and `find_stranded_accepted` in
  `worker.worker_plans` (control queue / `short_activities`) (depends on 4) —
  DoD: `tests/test_worker_roles.py` and `tests/test_worker_isolation.py` pass;
  the execution and implementation roles register no new workflows.
- [ ] 7. Add `IMPLEMENT_SWEEP_SCHEDULE_ID`/`_WORKFLOW_ID` and register the
  schedule in `worker.setup_schedules` at `every=15 min, offset=12 min`,
  `overlap=SKIP`, unpaused, with a comment stating why the offset is 12 and
  why it does not ship paused (depends on 6) — DoD:
  `tests/test_worker_schedules.py` passes, including
  `test_no_two_schedules_fire_on_the_same_minute` and
  `test_no_schedule_lands_on_an_argo_cron_minute`.
- [ ] 8. Make the grace period and per-tick cap configurable via
  `IMPLEMENT_SWEEP_GRACE_MINUTES` (default 20) and
  `IMPLEMENT_SWEEP_MAX_SUBMITS` (default 5), parsed the way
  `constants._int_env` parses `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` — a
  malformed value is a refusal, not a silent default (depends on 4) — DoD:
  documented in `.env.example`; a non-positive value raises at startup.
- [ ] 9. Update the docs the tests treat as code: `docs/temporal-flow.md` §4
  and §"Границы", `docs/diagrams/temporal-flow-schedules.mmd`,
  `docs/agent-inventory.yaml` (implementer `triggeredBy` gains the sweep;
  correct the `cronworkflow-mctl-agents-implement` note to say it is
  superseded, not merely suspended), and `README.md`'s Tier 2 section
  (depends on 7) — DoD: prose and diagram name the same four schedules.
- [ ] 10. Regenerate `docs/diagrams/archify/facts.yaml` with
  `python tools/diagram_facts.py --update` (depends on 9) — DoD:
  `tests/test_diagram_facts.py` reports no drift; `facts["schedules"]` and
  `facts["workflows"]` list the new entries.
- [ ] 11. File the cross-repo follow-ups and link them from the PR body
  (depends on 4): mctl-api — `mctl_trigger_approve` consults
  `mctl_get_dev_loop` and returns a warning when no live loop exists (the
  issue's fix 1); mctl-gitops — keep `cronworkflow-mctl-agents-implement`
  suspended and record why in the file — DoD: both issues exist and are
  referenced in `design.md`'s Alternatives section by number.

## Tests

- [ ] T1. `find_stranded_accepted` selects an `accepted` proposal with no PR,
  no attempt and no matching active workflow id; asserts the reason string.
- [ ] T2. Each skip filter, one test apiece: PR present; unexpired `attempt`;
  `requires_human_approval` with no approver (`approval-missing`); `blocked`
  marker; `updated_at` inside the grace window; expected DevLoop id in the
  active set. Each asserts both "not stranded" and the recorded reason.
- [ ] T3. An `incident-*` slug (no `issue-<N>-` prefix, so
  `expected_dev_loop_id` is `None`) IS swept — the incident responder's
  auto-accepted proposals are exactly the permanently-stranded case.
- [ ] T4. `ImplementSweepWorkflow` starts zero children and returns a
  `skipped_reason` when `list_active_dev_loop_ids` fails after retries
  (fail-closed), using the existing `tests/temporal_harness.py`.
- [ ] T5. The workflow submits `IMPLEMENTATION_OPERATION` with BOTH `service`
  and `slug`, on `IMPLEMENTATION_TASK_QUEUE` — an unscoped submit would let one
  sweep implement another proposal (the hazard `dev_loop.py` documents for
  #203).
- [ ] T6. With more candidates than `IMPLEMENT_SWEEP_MAX_SUBMITS`, exactly the
  cap is started, the remainder is logged, and the counts appear in the result.
- [ ] T7. Starting the sweep twice for the same `(service, slug)` while the
  first child runs yields one execution (`USE_EXISTING`), asserted against the
  harness's client.
- [ ] T8. Schedule tests: the new schedule is registered, unpaused, with
  `overlap=SKIP`; the existing collision and Argo-minute tests are extended to
  cover it (they enumerate `client.created`, so they pick it up automatically —
  assert that they do).
- [ ] T9. A `ProposalStateRef` payload serialized without the fields added in
  task 1 still deserializes (the defaulted-field rule `PRSnapshot.head_sha`
  follows).
- [ ] T10. Replay: add an `implement_sweep` scenario to
  `tests/replay_scenarios.py` with a recorded history so future edits to the
  workflow are checked for nondeterminism the way `dev_loop` and `reconcile`
  already are.

## Rollback

Three levels, cheapest first.

1. **Pause the schedule** —
   `temporal schedule pause --schedule-id implement-sweep-mctl-agents-schedule
   --reason "..."`. `_ensure_schedule` converges only spec and overlap policy
   and never touches `state` (pinned by
   `test_preserves_paused_state_and_note`), so the pause survives worker
   restarts and redeploys. Already-started children are `ABANDON`ed and finish
   on their own; each is one ordinary implementer run.
2. **Throttle instead of stopping** — set `IMPLEMENT_SWEEP_MAX_SUBMITS=1`, or
   drop `IMPLEMENTATION_MAX_CONCURRENT_ACTIVITIES` on the implementation
   worker, both values edits in `mctl-gitops`. No code change, no redeploy of
   this repo.
3. **Revert the PR.** Nothing else depends on the new module; the widened
   `ProposalStateRef` fields are additive and defaulted, so reverting cannot
   break a result recorded while they existed. Delete the now-unused schedule
   with `temporal schedule delete --schedule-id
   implement-sweep-mctl-agents-schedule`, otherwise it stays registered and
   fires at a workflow type no worker serves.

Recovery state after any rollback is exactly today's: `accepted` proposals wait
for a hand-run `mctl_trigger_implementer`. Nothing the sweep did is a one-way
door — every action it takes is a normal, scoped, claim-protected implementer
run.
