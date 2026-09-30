# Tasks: issue-542-fix-work-context-a-resume-onto-a-closed

- [ ] 1. Add the typed-outcome fields to `InvestigateResult` in
  `orchestrator/run_issue_investigator.py` — `outcome_code: str = "succeeded"`,
  `outcome_reason: str = ""`, `context_only: bool = False` — plus a small private
  validator that lazily imports `orchestrator/execution_evidence.py` and asserts
  `outcome_code in OUTCOME_CODES` and that `outcome_reason` matches that module's slug
  rules. — DoD: `uv run mypy` and `uv run ruff check orchestrator config tests` pass; every
  existing `InvestigateResult(...)` construction in `orchestrator/` and `tests/` compiles
  unchanged; no new vocabulary is defined in this file.

- [ ] 2. Set `outcome_code`/`outcome_reason` on every existing early return in
  `_investigate` (depends on 1) — `proposal-terminal` for the `_OVERWRITABLE_STATUSES`
  guard, `work-item-mismatch` for the issue/work-item cross-check, `work-item-terminal`
  for `TERMINAL_WORK_ITEM_STATES`, `dry-run` for the dry-run return, and the refusal
  string's own condition for `_resolve_work_context_ref`. Reuse
  `run_issue_directive_poller.py`'s existing `"not-overwritable"` spelling only if the
  owner prefers it; otherwise keep `proposal-terminal`. — DoD: every `return
  InvestigateResult(...)` in `_investigate` carries a non-empty `outcome_reason`; a test
  asserts there is no return path that leaves it empty while `skipped_reason` is set.

- [ ] 3. Add `_is_dispatched_resume(...)` (depends on 1) — true when
  `resume_from_execution_id` is set, or when `execution_request_id` is set and
  `execution_id` passes `orchestrator/work_context/snapshots.py::is_store_execution`.
  Import lazily inside the function body. — DoD: `tests/test_worker_isolation.py` still
  passes (no new module-scope import); unit tests cover all four input combinations.

- [ ] 4. Split the idempotency guard in `_investigate` into `rewrite_allowed` plus a
  context-only fall-through (depends on 2, 3). Keep the non-resume skip exactly where it is
  today, before any store contact or clone. Let only a dispatched resume with
  `_context_mode() != "off"` fall through past the work-context block into the `try`. —
  DoD: with `ISSUE_INVESTIGATOR_CONTEXT_MODE=off` the stdout of a skipping run is
  byte-identical to today's; a test asserts `_clone_repo` is never called on the
  non-resume path.

- [ ] 5. Gate the `try` body's steps on `rewrite_allowed` (depends on 4): run
  `_clone_repo` and `_assemble_context`; skip `_staging_dir`, `_service_skills_prompt_block`,
  `_build_prompt`, `_run_agent`, the staging verification block, `write_status_yaml`,
  `_carry_forward`, the publish swap and the issue comment. Leave the `finally` clone
  cleanup untouched. — DoD: a context-only run makes no Claude Agent SDK call (asserted by
  a stub that raises if invoked) and creates no `.staging-*` directory.

- [ ] 6. Force `shadow` assembly semantics on the context-only path (depends on 5) by
  passing `mode="shadow"` to `_assemble_context` regardless of `_context_mode()`, and add a
  `fatal: bool` parameter so an exception is re-raised instead of warned. Record the
  failure as `outcome_code="failed"`, `outcome_reason="context-assembly-failed"`. — DoD:
  the docstring states why `on` is not used (no prompt is built on this path); a test with
  `ISSUE_INVESTIGATOR_CONTEXT_MODE=on` proves the snapshot is sealed and the prompt is
  never built; a test proves an assembly exception produces a non-zero exit.

- [ ] 7. Change `_OwnExecution.finish`'s predicate (depends on 1) from
  `result.error is None and result.skipped_reason is None` to
  `result is not None and result.error is None and result.outcome_code == "succeeded"`. —
  DoD: a context-only result advances to `PHASE_SUCCEEDED`; a `refused` result still
  advances to `PHASE_FAILED`; the `MCTL_ENGINE_FINAL_ATTEMPT=false` carve-out is unchanged.

- [ ] 8. Emit the machine-readable outcome line and the exit code from `main()`
  (depends on 1, 6) — one `[outcome] code=... reason=... context_only=... snapshot_id=...
  execution_id=... work_item_id=...` line, then the existing human summary with a new `ctx`
  verdict for a context-only run. Exit 0 for `succeeded`/`refused`, 1 for `failed`. — DoD:
  the line is greppable from an Argo log and contains no secret, no path and no issue body
  text (consistent with `orchestrator/tracing.py`'s rules).

- [ ] 9. End the DevLoop run after a context-only investigate in
  `orchestrator/temporal/workflows/dev_loop.py` (depends on 8). Determine the outcome from
  the proposal status the loop already reads via its existing `find_proposal_slug` / gitops
  activities; return `DevLoopResult(investigate=investigate_result, implement=None,
  ended="investigate context-only: proposal-terminal")` without entering the approval wait
  or submitting implement. Gate it behind a new `workflow.patched("context-only-resume")`
  declared next to `DISPATCHED_NOT_RUN_FAILS_PATCH`. Do NOT reuse the existing
  `PROPOSAL_TERMINAL_PATCH = "proposal-terminal-end"` marker — that name is already taken
  by the unrelated merge-watch path and collides only textually. — DoD: the replay
  fixtures under `tests/fixtures/histories/` (`dev_loop_resumed.json` and siblings) replay
  clean; `advance_phase` is unchanged.

- [ ] 10. Document the decision (depends on 9): add a short subsection to
  `docs/adr/011-work-item-resume-contract.md` §8 recording that a dispatched resume onto a
  loop whose proposal is past `proposed` seals a context-only snapshot rather than doing
  nothing, and that the outcome is carried beside the phase because
  `executions.PHASE_*` is mctl-api's closed set. — DoD: the ADR names the `proposal-terminal`
  reason slug and links this issue and #431.

- [ ] 11. Confirm the read surface (depends on 6). `orchestrator/work_context/client.py`'s
  `ROUTES` has only the singular per-execution `execution_snapshot` route — there is no
  plural `/snapshots` list route in this repo. Verify against mctl-api whether the
  `/snapshots` listing the issue quotes is an mctl-api-side surface; if a client-side list
  is needed for the #431 proof, that is a separate `ROUTES` entry plus an `answer_from_*`
  classifier and should be filed as its own issue, not smuggled in here. — DoD: either a
  one-line comment in `client.py` recording that the listing is mctl-api-side, or a new
  issue link in this proposal's follow-ups.

## Tests

- [ ] T1. `tests/test_run_issue_investigator.py`: a dispatched resume (`work_item_id`,
  store `we_` `execution_id`, `resume_from_execution_id`, `execution_request_id`) onto a
  proposal whose `.status.yaml` is `merged`, with `ISSUE_INVESTIGATOR_CONTEXT_MODE=shadow`,
  seals a snapshot and returns `context_only=True`, `outcome_code="succeeded"`,
  `outcome_reason="proposal-terminal"`.
- [ ] T2. The same run leaves the proposal directory byte-identical: hash every file (and
  `.status.yaml` in particular) before and after and assert equality.
- [ ] T3. The sealed snapshot's `work_context` carries `work_item_id`, the store
  `execution_id`, `execution_sequence`, `prior_execution_ids` containing the
  `resume_from_execution_id`, and a `resumed_from_snapshot_id` resolved by
  `snapshots.resumed_from` — the #431 acceptance items 3, 4 and 7, asserted on C2.
- [ ] T4. With `ISSUE_INVESTIGATOR_CONTEXT_MODE=off`, the same dispatched resume returns
  the unchanged skip with `outcome_code="refused"`, `outcome_reason="proposal-terminal"`,
  and never clones.
- [ ] T5. A non-resume run (no work item, or a work item with no request/resume id) onto a
  `merged` proposal behaves exactly as today on every context mode: no clone, no assembly.
- [ ] T6. `ISSUE_INVESTIGATOR_CONTEXT_MODE=on` plus the context-only path seals under
  `shadow` semantics and never calls `_build_prompt`/`_run_agent`.
- [ ] T7. An exception from `_assemble_context` on the context-only path produces
  `outcome_code="failed"`, `outcome_reason="context-assembly-failed"` and a non-zero exit,
  and does NOT leave the execution reported as a success.
- [ ] T8. `_OwnExecution.finish` table test: `succeeded`/`refused`/`failed` outcome codes
  map to `PHASE_SUCCEEDED`/`PHASE_FAILED`/`PHASE_FAILED`, and to no call at all when
  `MCTL_ENGINE_FINAL_ATTEMPT=false` and the outcome is not `succeeded`.
- [ ] T9. `tests/test_execution_request_resume.py` / `tests/test_dev_loop_workflow.py`: a
  dispatched resume whose investigate came back context-only ends the loop with the typed
  `ended` reason, advances the dispatched execution to `Succeeded` exactly once, and never
  enters the approval wait.
- [ ] T10. Replay: `uv run pytest tests/test_execution_request_replay.py
  tests/test_dev_loop_workflow.py` passes against the checked-in histories with the new
  patch in place.
- [ ] T11. A property test that every `InvestigateResult` returned by `_investigate`
  carries an `outcome_code` in `execution_evidence.OUTCOME_CODES` and an `outcome_reason`
  that satisfies that module's slug validator.

## Rollback

Two independent levers, in increasing order of blast radius.

1. **Operator, no redeploy.** Set `ISSUE_INVESTIGATOR_CONTEXT_MODE=off`. `_context_mode()`
   is read fresh per call, exactly as its docstring promises, so the very next dispatched
   resume takes the unchanged skip path: no clone, no assembly, no seal. The only residue
   is the typed `outcome_code`/`outcome_reason` on a dataclass nothing downstream branches
   on yet. This reverts the behavioural change completely while leaving the code in place.

2. **Revert the commit.** The change is confined to `orchestrator/run_issue_investigator.py`
   and one patch-gated branch in `orchestrator/temporal/workflows/dev_loop.py`. Because the
   DevLoop branch is behind `workflow.patched("context-only-resume")`, a revert must follow
   Temporal's deprecation order: first `workflow.deprecate_patch("context-only-resume")` in
   one deploy, wait for every in-flight DevLoop run started under the patch to close, then
   remove the branch. Reverting the patch outright while a run is mid-flight wedges that
   run's replay — the same rule `DISPATCHED_NOT_RUN_FAILS_PATCH` and
   `PROPOSAL_TERMINAL_PATCH` already live under.

Nothing written by this change is persistent state that needs undoing: a context-only run
seals a `ContextSnapshot` in mctl-api and writes nothing to gitops, and an extra sealed
snapshot is additive, immutable and already handled by `snapshots.persist`'s
replay/divergence classification. No migration to reverse.
