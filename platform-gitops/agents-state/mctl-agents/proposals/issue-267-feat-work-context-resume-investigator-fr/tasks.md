# Tasks: issue-267-feat-work-context-resume-investigator-fr

All tasks are completable inside one PR against `mctlhq/mctl-agents`. No task
touches a sibling repository, requires a post-merge production action, or needs
an interactive human step. `uv run pytest tests/`, `uv run ruff check
orchestrator config tests` and `uv run mypy` must pass (CONTRIBUTING.md).

- [ ] 1. Add `orchestrator/work_context/contract.py` — stdlib-only frozen
      dataclasses `SurfaceRef`, `ActorRef`, `WorkItemRef`, `ExecutionRef`,
      `WorkItem`, `WorkItemAnswer`, `CanonicalState`; closed vocabularies
      `SURFACE_KINDS`, `ACTOR_KINDS`, `WORK_ITEM_STATES`; verdicts
      `WORK_ITEM_FOUND | WORK_ITEM_ABSENT | WORK_ITEM_CONFLICT |
      WORK_ITEM_UNKNOWN`; tolerant `from_payload` staticmethods that ignore
      unknown keys and return `None` on a malformed payload, mirroring
      `orchestrator/lifecycle/contract.py:129-137`.
      — DoD: module imports with stdlib only; every dataclass is
      `frozen=True` with every field defaulted; an unrecognised vocabulary
      value classifies as `WORK_ITEM_UNKNOWN` rather than defaulting
      permissively; mypy clean.
- [ ] 2. Add `execution_id_for(work_item_id, sequence, attempt) -> str` to
      `contract.py` (depends on 1) — sha256 over
      `"{work_item_id}|{sequence}|{attempt}"`, the shape of
      `lifecycle/contract.py:1013-1024`. No UUID fallback.
      — DoD: identical inputs yield an identical id; differing inputs differ;
      a docstring states why a random fallback is forbidden (ADR-010 §8).
- [ ] 3. Add `reconstruct_canonical_state(item, proposal_dir, prior_digests)
      -> CanonicalState` to `contract.py` (depends on 1) — pure, deriving
      state from the `WorkItem`'s structured fields, the gitops
      `.status.yaml` + `requirements/design/tasks.md` triplet, and
      `to_log_dict()`-shaped prior digests only.
      — DoD: the signature exposes no parameter able to carry a conversation
      transcript; `CanonicalState` has no free-text message field; a docstring
      records the constraint the way `ContextSource`'s does
      (`context_snapshot.py:277-281`).
- [ ] 4. Add `orchestrator/work_context/client.py` (depends on 1) —
      `WorkItemClient` over synchronous `urllib`, `MCTL_API_BASE_URL` /
      `MCTL_TOKEN`, https-only, `_no_redirect_opener`, module-level route
      table (`GET /api/v1/work-items/{id}`,
      `POST|GET /api/v1/work-items/{id}/executions`), and
      `WorkItemUnavailable(RuntimeError)` raised only by the transport.
      — DoD: every public method returns a `WorkItemAnswer`, never raises; a
      non-https base and a missing token both surface as
      `WORK_ITEM_UNKNOWN`; structurally mirrors
      `orchestrator/lifecycle/client.py:86-301`.
- [ ] 5. Add `orchestrator/work_context/rollout.py` (depends on 4) —
      `WORK_CONTEXT_ROLLOUT_MODE` ladder `off|observe|enforce|only` with
      `mode()`, `at_least()`, `records_writes()`, `computes_new_answer()`,
      `new_answer_may_veto()`, `new_answer_decides()`, `blocks_on_unknown()`;
      `WORK_CONTEXT_REQUIRED` read only through `blocks_on_unknown()`.
      — DoD: default is `off`; an unrecognised value prints a `warn:`-style
      line and answers `off` without raising; module docstring carries the
      three-switch table in the style of `lifecycle/rollout.py:12-21`.
- [ ] 6. Add `orchestrator/work_context/__init__.py` (depends on 1-5) —
      re-export block with `# noqa: F401`, matching
      `orchestrator/lifecycle/__init__.py`.
      — DoD: ruff clean; the package imports no third-party module.
- [ ] 7. Add `WorkContextRef` to `orchestrator/context_snapshot.py`
      (depends on 1) — frozen dataclass with `work_item_id`,
      `work_item_revision`, `execution_id`, `execution_sequence`,
      `prior_execution_ids`, `resumed_from_snapshot_id`, `origin_surface`,
      `current_surface`, `actor_kind`, `actor_id`, `surface_transition`;
      strict `from_dict` that rejects unknown keys.
      — DoD: follows the module's existing `to_dict`/`from_dict`/
      `_require_*` idiom; no field is read by any authorization path.
- [ ] 8. Wire `work_context` into `ContextSnapshot` (depends on 7) — add to
      `_SNAPSHOT_KEYS` (`:631`), `to_dict`, `from_dict`, `_content_payload`
      (`:860-882`), `seal()` (`:885`), `recompute_content_hash` (`:935`),
      `validate()` (closed-vocabulary checks plus the rule that a child step
      snapshot's `work_context` must equal its parent's, next to `:804-805`),
      and `to_log_dict()` (`:807-827`, ids only — never `actor_id`).
      — DoD: sealing with two different `execution_id`s yields different
      `snapshot_id`s; `from_dict` accepts a document with no `work_context`
      key; `to_log_dict()` provably omits `actor_id`.
- [ ] 9. Re-cut `tests/fixtures/context/investigator-snapshot.json` (depends
      on 8) — regenerate the golden document and its asserted hash under the
      extended payload shape.
      — DoD: `recompute_content_hash(from_dict(fixture)) ==
      fixture["content_hash"]`; the commit message states the pre-GA hash
      break and that no persisted snapshot exists
      (`context_snapshot.py:19-21`).
- [ ] 10. Add investigator flags to `orchestrator/run_issue_investigator.py`
      (depends on 1-6) — `--work-item-id`, `--execution-id`,
      `--resume-from-execution-id`, `--surface`, `--actor-kind`,
      `--actor-id` in `main()` (`:2075-2094`); drop `required=True` from
      `--issue-url` and enforce it by an explicit post-parse check; add a
      `_work_context_from_args(args)` validator.
      — DoD: `--resume-from-execution-id` without `--work-item-id` exits
      non-zero naming the flag; an out-of-vocabulary `--surface`/`--actor-kind`
      exits non-zero; `--issue-url` omitted without `--work-item-id` + mode
      `only` exits non-zero.
- [ ] 11. Thread the work context into `investigate()` (depends on 10) — new
      **keyword-only** parameters defaulting to `None`; at mode `observe`+
      resolve the `WorkItem`, call `reconstruct_canonical_state`, and log the
      derived `WorkContextRef`; at `enforce` allow the reconstructed state to
      veto (terminal work item) but never to license; import
      `orchestrator.work_context` lazily inside the function bodies.
      — DoD: `investigate(url, tmp_path)` still works positionally; no
      module-scope import added (`run_issue_investigator.py:68-73`);
      `tests/test_worker_isolation.py` still passes.
- [ ] 12. Add the `resume` signal and `work_context` query to
      `orchestrator/temporal/workflows/dev_loop.py` (depends on 1-6) —
      defensive parsing that never raises (the `approve` shape at
      `:787-800`); new state `_work_item_id`, `_executions`,
      `_seen_execution_ids`, `_resume_pending`, `_resume_rejections`,
      `_current_surface`, `_current_actor`; add a defaulted
      `work_item_id: str | None = None` to `IssueRef` (`:370-372`); add
      `ResumeRejection` and `WorkContextState` result dataclasses.
      — DoD: the handler raises on no input; the query returns the work item
      id, current execution id/sequence, every `ExecutionRef`, last
      surface/actor and every rejection.
- [ ] 13. Implement resume semantics (depends on 12) — duplicate
      `execution_id` is a no-op; a differing id while `_resume_pending` is
      rejected with `reason="resume-already-pending"`; a mismatched
      `work_item_id` is rejected with `reason="work-item-mismatch"`; an
      accepted resume that changes surface or actor sets `_approved = False`,
      clears `_approver`, and records `surface_transition=True`.
      — DoD: no historical `ExecutionRef` is mutated on any path; the existing
      `wait_condition(lambda: self._approved)` (`:827`) re-arms after a
      surface transition.
- [ ] 14. Gate every new workflow command behind
      `workflow.patched("work-context-resume")` (depends on 13) — including
      the `work_context_params(...)` merge into `investigate_params`
      (`:812-815`), which is additionally gated on
      `work_context.rollout.at_least(ENFORCE)` so nothing new is submitted at
      the default `off` mode.
      — DoD: with the patch unset, the command stream is byte-identical to
      today's; the marker is documented alongside the cost note at
      `dev_loop.py:2286-2295`.
- [ ] 15. Add `docs/adr/011-work-item-resume-contract.md` (depends on 8, 13) —
      the 007/009 template (Context → Decision with numbered subsections →
      Alternatives → Non-goals → Platform impact → Implementation map), stating
      that `work_context` extends ADR 009 sec. 1's field/owner table, that it
      is correlation not chaining (so ADR 009 `:203-205` and `:796-805` stay
      intact), and that it is never an authorization input (ADR 009 sec. 5).
      — DoD: the file follows the repo's blockquote metadata block
      (`Status`/`Date`/`Issue`/`Supersedes`) and cross-links #267, #264, #198.
- [ ] 16. Update `docs/agent-inventory.yaml` and
      `agents/_manifests/issue-investigator/agent.yaml` if the new flags change
      the declared trigger/driver surface (depends on 10).
      — DoD: `uv run pytest tests/test_agent_inventory.py
      tests/test_manifest.py` passes; if nothing in the declared contract
      changed, record that explicitly in the PR description rather than
      editing the files.

## Tests

- [ ] T1. `tests/test_work_context_contract.py` — round-trip of every
      dataclass; a payload with an unknown key parses; a payload missing a
      required key returns `None`; an out-of-vocabulary `surface.kind` /
      `actor.kind` / `state` classifies as `WORK_ITEM_UNKNOWN`.
- [ ] T2. `tests/test_work_context_contract.py` — `execution_id_for` is
      deterministic across calls and distinct for distinct inputs.
- [ ] T3. `tests/test_work_context_contract.py` —
      `reconstruct_canonical_state` rebuilds service/slug/prior status/prior
      execution ids from a `WorkItem` plus a `tmp_path` proposal dir alone;
      a companion test asserts the function signature and `CanonicalState`
      field set contain no transcript-shaped parameter or field.
- [ ] T4. `tests/test_work_context_client.py` — monkeypatched urllib, in the
      style of `tests/test_lifecycle_client.py`: 200 → `WORK_ITEM_FOUND`,
      404 → `WORK_ITEM_ABSENT`, 409 → `WORK_ITEM_CONFLICT`, transport error /
      non-https base / missing `MCTL_TOKEN` → `WORK_ITEM_UNKNOWN`; a 3xx is
      surfaced, never followed.
- [ ] T5. `tests/test_work_context_rollout.py` — default `off`; each of the
      four modes; an unrecognised value warns and answers `off` without
      raising; `blocks_on_unknown()` is false below `enforce` regardless of
      `WORK_CONTEXT_REQUIRED`.
- [ ] T6. `tests/test_context_snapshot.py` — seal with a `WorkContextRef`;
      two executions differing only in `execution_id` seal to different
      `snapshot_id`s; `from_dict` rejects an unknown key inside
      `work_context`; a document without the key still loads; a child step
      snapshot whose `work_context` differs from its parent's fails
      `validate(parent=...)`; `to_log_dict()` contains `work_item_id` and
      `execution_id` and does not contain `actor_id`.
- [ ] T7. `tests/test_context_snapshot.py` — the re-cut golden fixture
      verifies via `recompute_content_hash`.
- [ ] T8. `tests/test_run_issue_investigator.py` — flag parsing and every
      rejection path from task 10; `investigate(url, tmp_path)` positional
      call still succeeds through the existing `_investigate_harness`;
      provenance is recorded at mode `observe` and the store is never
      contacted at mode `off`.
- [ ] T9. `tests/test_dev_loop_workflow.py` — under the existing
      `WorkflowEnvironment.start_time_skipping()` + `tests/temporal_harness.py`
      `Worker`: a first execution launched with a work item reference; a
      `resume` signal from a second surface producing a second
      `ExecutionRef` with a new `execution_id`; the `work_context` query
      correlating both to one `work_item_id`.
- [ ] T10. `tests/test_dev_loop_workflow.py` — duplicate resume with the same
      `execution_id` is a no-op; a concurrent resume with a different
      `execution_id` while one is pending is rejected and appears in
      `work_context().resume_rejections`; a mismatched `work_item_id` is
      rejected.
- [ ] T11. `tests/test_dev_loop_workflow.py` — a resume changing surface/actor
      clears approval: the loop parks again on `wait_condition` and only a
      fresh `approve` from the new actor lets it proceed; a same-surface
      resume does not clear approval.
- [ ] T12. `tests/test_workflow_replay.py` + `tests/replay_scenarios.py` — a
      recorded pre-`work-context-resume` history replays without a
      nondeterminism error. This is the merge gate for task 14.
- [ ] T13. `tests/test_worker_isolation.py` — unchanged and passing:
      importing the worker must still not pull in `claude_agent_sdk` or
      `orchestrator.run_implementer` after the new package lands.

## Rollback

Three independent levers, smallest first.

1. **Env only, no deploy.** Set `WORK_CONTEXT_ROLLOUT_MODE=off` (or unset it —
   `off` is the default). The store is never contacted, no work-context key is
   merged into `investigate_params`, and the investigator behaves exactly as it
   does today. This is the intended first response to anything odd, and it is
   why the whole change ships defaulted to `off`.
2. **Break-glass inside `enforce`.** Set `WORK_CONTEXT_REQUIRED=false` to make
   an unreachable work-item store stop blocking mutating steps, restoring
   fail-open behaviour during an mctl-api outage without changing the mode.
3. **Revert the PR.** Safe for the CLI, the new package and the snapshot
   schema: nothing persists a `work_context` block anywhere durable, and no
   migration ran. The one thing a revert must *not* do is remove the
   `workflow.patched("work-context-resume")` marker from a worker while a
   history that recorded it is still replayable — per the convention at
   `dev_loop.py:845-852`, drop to `workflow.deprecate_patch` only once no
   pre-revert execution can still be running. If a revert is needed while such
   loops are in flight, revert everything except the marker first, then remove
   the marker in a follow-up.

Because the `WorkItem` store, the CWFT and the operation registry all live in
other repositories and are untouched here, no rollback step requires a
cross-repo change.
