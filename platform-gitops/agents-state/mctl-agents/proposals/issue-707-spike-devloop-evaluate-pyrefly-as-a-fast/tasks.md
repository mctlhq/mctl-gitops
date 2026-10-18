# Tasks: issue-707-spike-devloop-evaluate-pyrefly-as-a-fast

- [ ] 1. Pin the environment: resolve the measured SHA (issue's `68f10afc...`
  if reachable, else merge-base with main), choose the exact Pyrefly release,
  record Python, uv, mypy (2.3.1 from `uv.lock`), Pyrefly, CPU and OS — DoD:
  an "Environment" section in `docs/spikes/707-pyrefly-type-check.md` with all
  values filled and the SHA explained.
- [ ] 2. Baseline mypy exactly as CI (`uv sync --locked`, `uv run --locked mypy`)
  (depends on 1) — DoD: exit code, diagnostic count and raw output saved to
  `docs/spikes/707/diagnostics/mypy.txt`.
- [ ] 3. Pyrefly config (A): run `uvx pyrefly==<pin> check` with no Pyrefly
  config so it discovers `[tool.mypy]`; capture the effective config
  (depends on 1) — DoD: effective settings documented; output in
  `diagnostics/pyrefly-A.txt`; no file written at the repo root.
- [ ] 4. Pyrefly config (B): write `docs/spikes/707/pyrefly.toml` reproducing
  `files = ["orchestrator", "config", "tools"]`, Python 3.12, the venv search
  path and the `tests.*` error-suppression override; run with `--config`
  (depends on 3) — DoD: checked-file lists of mypy and Pyrefly (B) diffed and
  shown empty (or every difference explained); output in
  `diagnostics/pyrefly-B.txt`.
- [ ] 5. Mutation corpus: at least 7 patches under
  `docs/spikes/707/mutations/` covering Optional-to-non-optional, incompatible
  assignment, wrong argument/keyword type, wrong return type, attribute on
  Optional/union, coroutine misuse (in `orchestrator/temporal/` if both tools
  support it), and an `Any`/untyped boundary; each applies cleanly with
  `git apply --check` at the measured SHA (depends on 1) — DoD: patches
  committed, never applied on the branch; `mutations/README.md` lists source
  pattern per patch.
- [ ] 6. Harness `docs/spikes/707/bench.py` (stdlib only): `cold` (10 fresh
  runs per checker, mypy cache cleared, plus a labelled warm-mypy run),
  `edit` (20 apply/check/revert iterations per checker), `loop`
  (checker -> Ruff -> targeted pytest on 4-6 mutations), `lint-job`
  (clean-clone setup + sync + Ruff + checker, phases timed separately);
  refuses a dirty tree, always reverts patches (depends on 4, 5) — DoD:
  writes `docs/spikes/707/results.json` with median and p95 per metric.
- [ ] 7. Diagnostic comparison: normalise to (path, line, category), match,
  hand-classify every unmatched Pyrefly finding into the five issue buckets
  and every mypy-only finding as meaningful/non-meaningful loss (depends on
  2, 4) — DoD: classification table in the report; no source fixes made.
- [ ] 8. Mutation detection table: per patch, caught by mypy / Pyrefly, error
  code, actionable file:line:cause, repairable-from-diagnostic yes/no
  (depends on 6) — DoD: table in `mutations/README.md` and summarised in the
  report.
- [ ] 9. Compatibility notes: outcome of each of the 10 `# type: ignore[...]`
  comments in scope (`capability_gateway.py`, `run_implementer.py`,
  `run_issue_investigator.py` x2, `run_shepherd.py`, `runtime_assurance.py` x4,
  `temporal/worker.py`) incl. `warn_unused_ignores` interaction; stub/inference
  notes for `temporalio`, `mcp`, `yaml`/`types-pyyaml`, `httpx`,
  `claude_agent_sdk`; install-size delta (depends on 4) — DoD: report sections
  filled.
- [ ] 10. Inner-loop assessment: where a check would run (default candidate:
  `agents/mctl-agents/.claude/agents/implementer.md` service notes), how the
  checker reaches the `--no-dev` runtime image (per-run `uvx` vs pinned image
  layer, with measured cost), and how version/config are pinned
  (depends on 6, 8) — DoD: report section with a concrete command line.
- [ ] 11. Recommendation: exactly one of `REPLACE_MYPY`,
  `PYREFLY_INNER_LOOP_ONLY`, `KEEP_MYPY`, argued criterion-by-criterion; if
  not `KEEP_MYPY`, include a ready-to-file follow-up issue body (and, for
  inner-loop-only, the statement that a Pyrefly pass never satisfies the mypy
  gate) (depends on 7-10) — DoD: report filled in, metrics table complete.
- [ ] 12. Guard test `tests/test_spike_707_report.py` (depends on 11) — DoD:
  tests T1-T3 pass under `uv run --locked pytest tests/test_spike_707_report.py`.

## Tests

- [ ] T1. The report contains exactly one of the three decision tokens on the
  "Recommendation:" line, and the metrics table has a non-empty value for
  every row and both columns.
- [ ] T2. Gate invariant: `pyproject.toml` still has
  `files = ["orchestrator", "config", "tools"]` under `[tool.mypy]`, `mypy` is
  in `[dependency-groups].dev`, no `pyrefly` appears in `pyproject.toml` or
  `uv.lock`, no `pyrefly.toml` exists at the repo root, and the `lint` job in
  `.github/workflows/pr-validation.yml` still runs `uv run --locked mypy`.
- [ ] T3. Every file under `docs/spikes/707/mutations/*.patch` touches only
  paths under `orchestrator/`, `config/` or `tools/` (so it is a mutation of
  checked scope) and none of those mutations is present in the working tree
  (`git apply --check` forward succeeds, or the test skips with a reason when
  the source has moved past the measured SHA).
- [ ] T4. Existing `lint` job (Ruff + mypy) and full test suite stay green on
  the spike PR.

## Rollback

The spike adds only `docs/spikes/707-pyrefly-type-check.md`, `docs/spikes/707/`
and `tests/test_spike_707_report.py`; revert the PR. No config, lockfile, CI,
image or runtime change exists to undo, and Pyrefly is fetched only into the
spike machine's uv cache (`uv cache clean pyrefly` removes it).
