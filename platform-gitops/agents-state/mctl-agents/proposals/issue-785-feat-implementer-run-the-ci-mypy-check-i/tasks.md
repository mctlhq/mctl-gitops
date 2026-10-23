# Tasks: issue-785-feat-implementer-run-the-ci-mypy-check-i

- [ ] 1. Measure, change nothing: in an implement pod built from the current image, record (a) image size delta of `uv sync --locked` with vs. without the `dev` group for the mctl-agents lock, (b) `uv sync --locked` wall time into a fresh clone with an empty and a warm `UV_CACHE_DIR`, and whether PyPI egress works from that pod, (c) cold and warm `uv run --locked mypy` wall time under the CPU limit in force (3000m per `cwft-mctl-agents-implement.yaml`) and at 250m. — DoD: numbers posted as a comment on mctlhq/mctl-agents#785, stating which CPU limit each figure used.
- [ ] 2. Decide the install shape from task 1 (depends on 1). Default: run-start `uv sync --locked` in the target clone; switch to image-baked mypy only if egress is blocked or sync time exceeds the check's timeout cap. — DoD: decision and reason recorded on #785; if switched, design.md's Alternative 1 is the implemented path.
- [ ] 3. Add `TYPECHECK_COMMANDS` to `config/settings.py` with `{"mctl-agents": ("uv", "run", "--locked", "mypy")}` and `IMPLEMENTER_TYPECHECK_TIMEOUT_SECONDS` (default 300). — DoD: importable; mypy and ruff clean.
- [ ] 4. Implement `TypecheckResult` and `_run_pre_push_typecheck` in `orchestrator/run_implementer.py` (depends on 2, 3): exclude `.venv/` and `.mypy_cache/` via `.git/info/exclude`; run `uv sync --locked` then `uv run --locked --no-sync mypy` with `VIRTUAL_ENV` unset and `/app/.venv/bin` removed from the child PATH; bound by the `CommandBudgetLedger` remainder and the cap; classify into pass/fail/unknown/not_run with the classifications listed in design.md. — DoD: unit-tested classification for each arm.
- [ ] 5. Wire it into `implement_one` between the chart MAJOR-version guard and `_push_and_open_pr` (first-push path only); add `_AttemptObservations.typecheck`; append a non-required `VerificationRecord("typecheck", ...)` in `_verification_records`. (depends on 4) — DoD: push proceeds for every result; completion outcome unchanged; `REQUIRED_CHECKS_V1ALPHA1` untouched.
- [ ] 6. Add the pre-push mypy line to the PR body via `_pr_title_and_body` for registered services (passed / FAILED (N errors) / did not complete (reason)). (depends on 5) — DoD: no line for unregistered services; a skipped or failed check never renders as passed.
- [ ] 7. Prompt changes: in `_build_prompt` (first-run and review-follow-up prompts) add the instruction to run the registered command before committing and fix in-scope errors; update the "Sanity check" bullet in `agents/mctl-agents/.claude/agents/implementer.md` to name `uv run --locked mypy`. (depends on 3) — DoD: prompt text appears only for registered services.
- [ ] 8. After rollout, track first-push mypy failures over the next 30 implementer PRs against the 6-11 of 69 baseline. — DoD: result posted on #785.

## Tests

- [ ] T1. Seeded error: in a temp git repo with a minimal `pyproject.toml` (`[tool.mypy] files = ["pkg"]`) and a file containing `x: int = "a"`, `_run_pre_push_typecheck` returns `fail` / `exit_nonzero` with `error_count == 1` (marked as an integration test that needs `uv` and network, or uses a fake subprocess runner in the unit variant).
- [ ] T2. Clean tree: same fixture without the error returns `pass` / `exit_zero`.
- [ ] T3. Unregistered service returns `not_run` / `not_applicable` and starts no subprocess.
- [ ] T4. Timeout, budget exhausted, and `uv sync` failure map to `unknown`/`timeout`, `not_run`/`budget_denied`, `unknown`/`observation_failed`; none renders as passed in the PR body.
- [ ] T5. `_verification_records` includes a `typecheck` record with `required=False`, and a `fail` typecheck does not change the completion outcome (extend `tests/test_run_implementer_completion.py`).
- [ ] T6. Ordering: in `implement_one` the typecheck runs after the chart guard and before `_push_and_open_pr`, and the push happens for a `fail` result (pattern of `tests/test_run_implementer_chart_guard.py`).
- [ ] T7. Parity: `TYPECHECK_COMMANDS["mctl-agents"]` matches the `run:` of the "Run mypy" step in `.github/workflows/pr-validation.yml`.
- [ ] T8. `.venv/` and `.mypy_cache/` are present in the clone's `.git/info/exclude` after the check.
- [ ] T9. `_build_prompt` contains the mypy instruction for `mctl-agents` and not for an unregistered service.

## Rollback

Remove the `mctl-agents` entry from `TYPECHECK_COMMANDS` (one-line config change, released through the normal image release): the prompt line, the subprocess, and the PR line all disappear, and the record falls back to `not_run`/`not_applicable`. A full revert of the PR is also safe: no schema, no gitops, and no required-check changes. If task 2 chose the image shape, revert the Dockerfile change as part of the same revert.
