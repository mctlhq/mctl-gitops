# Tasks: issue-267-feat-work-context-resume-investigator-fr

- [ ] 1. Write `docs/adr/011-work-item-resume-and-context-continuity.md` — the
      amendment ADR to ADR 009: the optional `work_item` block, the
      omit-when-absent content-hash rule, the new field-owner row, the
      epoch-scoped approval rule, and the restated boundary that surface/actor
      provenance grants nothing. — DoD: ADR merged, cross-linked from
      `docs/adr/009-context-snapshot-contract.md`'s follow-up table (rows (a)
      and (b) now name this issue), status `accepted`.
- [ ] 2. Add `orchestrator/work_item.py`: frozen, stdlib-only dataclasses
      `WorkItemRef`, `SurfaceRef`, `ActorRef`, `ResumeIntent`,
      `ExecutionIdentity`, closed vocabularies `SURFACE_KINDS`/`ACTOR_KINDS`,
      `MAX_ID_LENGTH`, `from_dict` with unknown-key rejection, and the
      deterministic `resume_key()` (sha256 over canonical JSON — no `uuid4`, no
      wall clock). — DoD: module imports stdlib only; `uv run ruff check` and
      `uv run mypy` clean; no field name contains
      `allow`/`deny`/`permit`/`grant`/`authorized`.
- [ ] 3. Extend `orchestrator/context_snapshot.py` with `WorkContextRef` and
      `ContextSnapshot.work_item: WorkContextRef | None = None` (depends on 1,
      2) — include `"work_item"` in `_content_payload` only when present;
      extend `validate(parent=...)` to require an equal `work_item` block on a
      child; add `work_item_id`/`execution_id`/`epoch` to `to_log_dict()`. —
      DoD: `tests/fixtures/context/investigator-snapshot.json` still validates
      and still recomputes to `sha256:de22a552...` unchanged.
- [ ] 4. Add `orchestrator/work_context_client.py` — synchronous urllib client
      with no-redirect opener, `resolve()`, `open_execution()`,
      `publish_snapshot()`, `report_refusal()` (depends on 2). Conflicts return
      data (`conflict`), unreachable returns `UNKNOWN`, nothing is invented
      locally. Mirrors `orchestrator/lifecycle/client.py`. — DoD: unit-tested
      against a stub HTTP server; a 409 never raises; an unreachable store
      never yields an execution identity.
- [ ] 5. Add `orchestrator/work_context_rollout.py` (or a `mode()` helper beside
      the client) reading `WORK_ITEM_ROLLOUT_MODE` = `off | shadow | enforce`,
      modelled on `orchestrator/lifecycle/rollout.py` (depends on 4). — DoD:
      `off` is the default; under `off` no work-context call is made at all.
- [ ] 6. Add `orchestrator/temporal/activities/work_items.py` — async httpx
      activities `resolve_work_item`, `open_work_item_execution`,
      `record_surface_transition` (depends on 2), registered in
      `orchestrator/temporal/worker.py` on the control queue. — DoD: activities
      registered; `tests/test_worker_isolation.py` still passes (no
      `claude_agent_sdk` in the worker import graph).
- [ ] 7. Cross-repo prerequisite, lands BEFORE task 9: mctl-gitops
      `cwft-mctl-agents-investigate.yaml` accepts optional `work_item_id` and
      `execution_id` parameters and threads them to
      `run_issue_investigator.py`; mctl-api's operation registry allows them.
      — DoD: an `mctl-agents-investigate` submit carrying the new params
      succeeds, and one omitting them still succeeds.
- [ ] 8. Wire the investigator: add `--work-item`, `--expected-epoch`,
      `--surface`, `--actor`, `--resume-of` to `main()`
      (`run_issue_investigator.py:2075`) and the matching optional parameter to
      `investigate()` (`:1457`) (depends on 2, 4, 5). Open the execution before
      any agent work; abort on conflict; keep the `_OVERWRITABLE_STATUSES`
      refusal and report it to the WorkItem. — DoD: with no new flags, behaviour
      is byte-identical to today; with them, an execution identity is obtained
      before `_clone_repo`.
- [ ] 9. Canonical-state reconstruction in `_build_prompt`
      (`run_issue_investigator.py:1127`) (depends on 8): a delimited "prior work
      on this WorkItem" section built only from the WorkItem record, the
      existing proposal triplet (`resolve_slug` `:842`, `_load_status` `:889`)
      and `gh_issue_view` (`:868`), with `_neutralize_prompt_tags` (`:1098`)
      applied to third-party text. — DoD: no function signature in this module
      accepts a transcript, chat log, or message list; grep proves it.
- [ ] 10. Seal and publish the snapshot (depends on 3, 4, 8): after a successful
      investigation call `context_snapshot.seal()` with `github-issue`,
      `target-repo` (at `_target_repository_sha` `:117`) and, on resume,
      `proposal-dir` sources plus the `work_item` block, then
      `publish_snapshot()`. Failure to publish logs `warn:` and never fails the
      investigation. — DoD: one root snapshot per execution, verified by
      `recompute_content_hash`; publish failure does not change the exit code.
- [ ] 11. Extend `IssueRef` (`dev_loop.py:370`) with defaulted work-item/
      surface/actor/epoch fields and add the `workflow.patched("work-item-resume")`
      marker gating the new `investigate_params` entries (`:812-817`) (depends
      on 6). — DoD: an unpatched history replays with no new command; a new
      execution submits the extra CWFT params.
- [ ] 12. Add the `resume` signal and the `work_item` query to `DevLoopWorkflow`
      (depends on 11), in the defensive never-raise style of `approve`
      (`:787-800`); extend `approve`'s dict form with optional `actor_kind`,
      `actor_id`, `surface_kind`, `surface_id`, `epoch` and enforce
      `approved_epoch == current epoch` on the resume path. — DoD: a malformed
      signal payload is ignored rather than raising; an epoch-N approval does
      not satisfy an epoch-N+1 gate.
- [ ] 13. Add `resume_workflow_id_for(issue_url, epoch)` to
      `orchestrator/temporal/issue_ref.py` and `start_dev_loop_resume()` to
      `orchestrator/temporal/start.py` (depends on 2, 12), keeping
      `workflow_id_for` byte-identical for epoch 0 and the existing
      `ALLOW_DUPLICATE_FAILED_ONLY` + `USE_EXISTING` policies. — DoD: epoch 0
      produces exactly today's id; epoch N > 0 produces `...-r{N}`;
      `mctl_get_dev_loop` still resolves the first execution.
- [ ] 14. Update `README.md`/`LLMS.md` and `docs/agent-inventory.yaml` with the
      resume flow and the new investigator flags (depends on 8, 13). — DoD:
      `uv run pytest tests/test_agent_inventory.py` passes; the documented flags
      match `main()`.

## Tests

- [ ] T1. `tests/test_work_item.py` — closed vocabularies rejected outside the
      allow-list; unknown keys rejected; id length bounded; `resume_key` is
      stable across processes and identical for identical intents; recursive
      field-name assertion that no `allow`/`deny`/`permit`/`grant`/`authorized`
      token appears; subprocess import-direction assertion that the module
      loads stdlib only (the style of `tests/test_worker_isolation.py`).
- [ ] T2. `tests/test_context_snapshot.py` additions — the existing golden
      fixture still recomputes to its recorded `content_hash` after the schema
      change (hash stability of omit-when-absent); a new fixture
      `tests/fixtures/context/investigator-resume-snapshot.json` seals with a
      `work_item` block and round-trips through `from_dict`; a child whose
      `work_item` differs from its parent's fails `validate(parent=...)`;
      `to_log_dict()` emits the three new identifiers and still no
      locator/selector.
- [ ] T3. `tests/test_work_context_client.py` — 409 returns a `conflict` answer
      without raising; connection error returns `UNKNOWN` and no execution
      identity; same idempotency key returns the same execution identity twice;
      a redirect is surfaced as an error rather than followed.
- [ ] T4. `tests/test_run_issue_investigator.py` additions — legacy invocation
      (no work-item flags) is unchanged; resume path builds the prompt from the
      proposal triplet and issue only, with no transcript input; a proposal
      outside `_OVERWRITABLE_STATUSES` is refused and the refusal is reported;
      exactly one snapshot is sealed and published per execution; a publish
      failure logs `warn:` and leaves the exit code 0.
- [ ] T5. `tests/test_dev_loop_workflow.py` additions — the `resume` signal
      records the surface transition and starts no second execution while the
      workflow is parked at `wait_condition`; an epoch-N approval does not
      release an epoch-N+1 gate; the `work_item` query returns both execution
      ids after a resume; a malformed resume payload is ignored.
- [ ] T6. Concurrency — two resumes with the same `resume_key` yield one
      Temporal start (`USE_EXISTING`) and one execution identity; a resume with
      a stale `expected_epoch` raises a non-retryable `ApplicationError` and
      starts nothing.
- [ ] T7. `tests/test_workflow_replay.py` + a new pre-patch history fixture in
      `tests/fixtures/histories/` — a history recorded before
      `work-item-resume` replays with no nondeterminism error; `tests/
      test_patch_memoization.py` still passes with the new marker.
- [ ] T8. `tests/test_worker_isolation.py` — the new activities module keeps the
      worker's import graph free of `claude_agent_sdk`.
- [ ] T9. Correlation end-to-end (fake store): execution A and execution B on
      different surfaces produce two snapshots whose `work_item.work_item_id`
      matches, whose `execution_id`s differ, and where B's
      `prior_execution_ids`/`prior_snapshot_ids` contain A's — and A's stored
      record is byte-identical before and after B runs.

## Rollback

1. **First lever, no deploy:** set `WORK_ITEM_ROLLOUT_MODE=off`. The
   investigator stops calling the work-context surface, snapshot publishing
   stops, and every invocation falls back to today's issue-keyed path. Resume
   starts stop being issued because nothing mints an epoch.
2. **Second lever:** roll the investigator agent version back through the
   registry (`mctl_rollback_agent issue-investigator production`), which
   re-pins the previous image for new executions. In-flight executions keep
   the version they pinned at start (`dev_loop.py:806-808`), by design.
3. **Do NOT delete the `work-item-resume` patch marker from deployed code.**
   Removing a marker while a pre-patch or post-patch execution can still be
   running is a nondeterminism wedge for every in-flight 14-day loop. Removal is
   by attrition only: leave the marker, let executions age out past
   `MERGE_WATCH_DEADLINE` (14 days, `dev_loop.py:144`), then
   `workflow.deprecate_patch`, then delete in a later release.
4. **Data:** nothing to undo in this repo. Sealed snapshots and execution rows
   are immutable and additive; leaving them in place costs storage only, and
   `retention: execution-record` already bounds them. Resume epochs already
   minted stay valid and simply stop being consumed.
5. **Cross-repo:** the CWFT parameters from task 7 are optional, so reverting
   mctl-agents alone leaves them unused rather than broken; no mctl-gitops
   revert is required to stop the feature.
