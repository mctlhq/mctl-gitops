# Tasks: issue-488-dispatcher-residual-p3s-after-461-option

- [ ] 1. **(mctl-api, companion PR — prerequisite)** Add the kind-neutral
  reject reason `engine_ref_too_long` to mctl-api's execution-request reject
  vocabulary, beside `no_runnable_target`, `unsupported_kind`, `loop_active`
  and `engine_run_ended`. Keep `resume_refused:engine-ref-too-long` accepted.
  — DoD: mctl-api accepts a reject carrying `engine_ref_too_long` and still
  accepts the legacy spelling; mctl-api's own tests cover both; merged and
  deployed before task 3 merges.

- [ ] 2. Add `ENGINE_REF_TOO_LONG = "engine_ref_too_long"` to
  `orchestrator/work_context/execution_requests.py`, in the typed reject-reason
  block (beside `LOOP_ACTIVE`, lines 53-98), with a docstring naming
  `issue_ref.request_engine_ref`, mctl-api's `workitems.MaxEngineRefBytes`, and
  #488. Update the `RESUME_REFUSAL_REASONS` docstring (lines 68-75) so
  `"engine-ref-too-long"` is described as retained read-side vocabulary for rows
  written before #488, not as a reason this build mints. Do **not** remove the
  member. — DoD: constant exists; `"engine-ref-too-long"` still in
  `RESUME_REFUSAL_REASONS`; `uv run ruff check orchestrator` and `uv run mypy`
  pass.

- [ ] 3. (depends on 2) In `orchestrator/temporal/dispatcher.py::_dispatch`
  (lines 402-406), replace `f"{xr.RESUME_REFUSED}:engine-ref-too-long"` with the
  new kind-neutral reason, via a private
  `_reject_engine_ref_too_long(request, token, loop)` helper that calls
  `_reject` with `xr.ENGINE_REF_TOO_LONG` and, only if the outcome is
  `DEFERRED`, retries `_reject` exactly once with the legacy
  `f"{xr.RESUME_REFUSED}:engine-ref-too-long"`. Keep the existing "mctl-api
  would refuse the fulfil with a 400 that defers for ever" comment and add the
  40-bytes-plus-loop-id arithmetic from design.md. Leave lines 427-429 and
  `TemporalClientPort.deliver`'s `RESUME_REFUSAL_REASONS` normalisation
  untouched. — DoD: no code path emits `resume_refused:engine-ref-too-long`
  except the fallback retry; `grep -rn "engine-ref-too-long" orchestrator/`
  shows only `execution_requests.py` and the dispatcher fallback line.

- [ ] 4. (depends on 3) Update `docs/adr/011-work-item-resume-contract.md`: the
  sentence around line 322 ("The dispatcher adds `engine-ref-too-long` itself")
  becomes a statement that the dispatcher refuses an over-long engine ref with
  the kind-neutral top-level `engine_ref_too_long`, for `start` and `resume`
  alike, and that `resume_refused:engine-ref-too-long` stays readable for older
  rows. Leave the loop-validator reason list, lines 273 and 390, and every other
  `dev-loop-xr_` mention in the ADR alone. — DoD: ADR and code agree; no other
  ADR section edited.

- [ ] 5. **(mctl-gitops, companion PR — cosmetic, independent)** In
  `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`,
  rewrite the comment on the `temporal_workflow_id` parameter to describe the
  issue-keyed `dev-loop-<owner>-<repo>-<n>` shape (#461 option A). The parameter,
  its default and every consumer stay exactly as they are — `issue_ref.loop_workflow_id`
  still prefers the id the loop passed. — DoD: diff is comment-only; the
  template renders and a `mctl_trigger_issue` run still passes
  `--temporal-workflow-id` unchanged.

- [ ] 6. **(mctl-api, companion PR — cosmetic, independent)** In
  `internal/api/handlers_write_devloop_params_test.go`, replace the sample value
  `dev-loop-xr_0000` with an issue-keyed sample such as
  `dev-loop-mctlhq-mctl-agents-488`. — DoD: no assertion semantics changed; the
  Go test suite passes; no `dev-loop-xr_` literal remains in that file.

- [ ] 7. (depends on 3, 4) Confirm no in-repo `dev-loop-xr_` mention was touched:
  `dispatcher.PRE_ISSUE_KEYED_DISPATCH_PREFIX`, `execution_requests.ENGINE_RUN_ENDED`,
  `workflows/dev_loop.py` lines 305/319/2374, `tests/test_investigator_loop_identity.py`,
  and the `tests/fixtures/histories/` replay fixtures all stay byte-identical.
  — DoD: `git diff --stat` on the mctl-agents PR lists only
  `orchestrator/work_context/execution_requests.py`,
  `orchestrator/temporal/dispatcher.py`,
  `docs/adr/011-work-item-resume-contract.md` and
  `tests/test_execution_request_dispatch.py`.

## Tests

All in `tests/test_execution_request_dispatch.py` unless stated. There is no
existing coverage of the over-long branch, so T1 is the first.

- [ ] T1. `test_an_over_long_engine_ref_rejects_a_start_kind_neutrally` — build a
  `DispatchFakeApi` whose work item's issue URL has a repo name long enough to
  push `request_engine_ref(loop, rid)` past `MAX_ENGINE_REF_BYTES` (about 200
  characters of repo, still matching `_ISSUE_URL_RE`), create a `start` request,
  run `dispatch_once`. Assert the outcome is `REJECTED`, the stored reason is
  exactly `xr.ENGINE_REF_TOO_LONG`, and that it does not start with
  `xr.RESUME_REFUSED`.
- [ ] T2. `test_an_over_long_engine_ref_rejects_a_resume_with_the_same_reason` —
  same fixture with `kind="resume"`; assert the identical reason, proving
  kind-neutrality.
- [ ] T3. `test_an_over_long_engine_ref_never_delivers_or_fulfils` — same fixture;
  assert `FakeTemporal` recorded no `deliver` and no `loop_state` call, and that
  `DispatchFakeApi.requests` contains no `/fulfil` POST, so no `we_` was minted.
- [ ] T4. `test_a_reject_refused_by_an_older_mctl_api_falls_back_to_the_legacy_reason`
  — make the fake's reject route answer 400 for `engine_ref_too_long` and 200 for
  the legacy spelling. Assert exactly two reject POSTs, the second carrying
  `resume_refused:engine-ref-too-long`, the outcome `REJECTED`, and two `reject`
  audit lines in the `EXECUTION_REQUEST_DISPATCH` capsys output.
- [ ] T5. `test_a_reject_refused_twice_defers_without_a_third_attempt` — reject
  route answers 400 for both spellings. Assert outcome `DEFERRED` and exactly two
  reject POSTs (the fallback is one-shot, never a loop).
- [ ] T6. `test_the_legacy_resume_refusal_reason_stays_readable` — in
  `tests/test_work_context_*`: assert `"engine-ref-too-long" in xr.RESUME_REFUSAL_REASONS`,
  so a row written before #488 never normalises to `RESUME_REFUSAL_UNSPECIFIED`.
- [ ] T7. Regression: the existing loop-refusal tests (the `DELIVERY_REFUSED`
  path through `_dispatch` line 429, e.g. the `work-item-mismatch` and
  `resume-already-pending` cases) still assert `resume_refused:<reason>`
  unchanged.
- [ ] T8. Full suite green: `uv run pytest tests/`, `uv run ruff check orchestrator config tests`,
  `uv run mypy` — the three checks `.github/workflows/pr-validation.yml` runs.

## Rollback

The mctl-agents change is one constant, one branch and a docs paragraph, all on
a path that cannot be reached with a real GitHub repository name, so rollback is
low-stakes in every direction.

1. **Preferred: revert the mctl-agents PR.** `git revert` the merge commit on
   `main` and redeploy the worker image. The dispatcher returns to emitting
   `resume_refused:engine-ref-too-long`, which mctl-api still accepts (task 1 is
   purely additive and leaves the legacy spelling valid). No rows need fixing.
2. **Do not revert the mctl-api vocabulary addition on its own** while an
   mctl-agents build emitting the new reason is deployed. If it must be
   reverted, revert mctl-agents first, or rely on the task-3 fallback, which
   already converts that skew into a legacy-spelling reject plus two audit lines
   rather than a stranded request.
3. **If a surface breaks on the unknown reason**, revert the mctl-agents PR
   (step 1) — that is faster than a surface hotfix, and it restores a reason
   every surface already handles.
4. Tasks 5 and 6 are comment/fixture-only and independent; revert either on its
   own with no coordination, and with no runtime effect whatsoever.
5. Rows already rejected under the new reason (only reachable via a hand-crafted
   test environment) need no migration: `engine_ref_too_long` stays valid
   mctl-api vocabulary after an mctl-agents revert.
