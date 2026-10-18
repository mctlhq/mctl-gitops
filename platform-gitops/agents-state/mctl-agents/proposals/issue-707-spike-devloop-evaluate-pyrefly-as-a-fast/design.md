# Design: issue-707-spike-devloop-evaluate-pyrefly-as-a-fast

## Current state

Type checking in `mctl-agents` today:

- `pyproject.toml` `[dependency-groups].dev` pins `mypy~=2.3` (locked to
  `mypy 2.3.1` in `uv.lock`), `ruff~=0.16`, `pytest~=9.0` and
  `types-pyyaml~=6.0`. `requires-python = ">=3.12,<3.13"`.
- `[tool.mypy]`: `python_version = "3.12"`,
  `files = ["orchestrator", "config", "tools"]`, `warn_unused_ignores = true`,
  `warn_redundant_casts = true`, soft mode (no `strict`, no
  `disallow_untyped_defs`). One override: `[[tool.mypy.overrides]]
  module = "tests.*"`, `ignore_errors = true`, because
  `tools/record_workflow_history.py` imports `tests.replay_scenarios` and mypy
  follows that import into `tests/`. Any Pyrefly config that does not
  reproduce this will either check `tests/` or skip `tools/` signatures —
  exactly the scope mismatch the issue warns about.
- `.github/workflows/pr-validation.yml`, job `lint`: checkout, `setup-uv`
  (uv `0.11.11`, Python `3.12`, cache on), `uv sync --locked`,
  `uv run --locked ruff check orchestrator config tests tools`,
  `uv run --locked mypy` (no CLI paths, so `[tool.mypy].files` is the source of
  truth). The job comment states Ruff and mypy together take "a couple
  seconds", so setup dominates CI time.
- Suppressions in scope: 10 `# type: ignore[...]` comments (7 `arg-type`,
  2 `union-attr`, 1 `operator`) in `orchestrator/capability_gateway.py`,
  `orchestrator/run_implementer.py`, `orchestrator/run_issue_investigator.py`,
  `orchestrator/run_shepherd.py`, `orchestrator/runtime_assurance.py` and
  `orchestrator/temporal/worker.py`. Pyrefly's handling of mypy error codes in
  these comments, combined with `warn_unused_ignores`, is a concrete
  compatibility question.
- Scope size: about 78,900 lines of Python across `orchestrator/`, `config/`
  and `tools/` (`wc -l`), large enough that checker latency may be noticeable.
- Inner loop today: `agents/mctl-agents/.claude/agents/implementer.md`
  ("Service-specific notes") tells the implementer to sanity-check with
  `python -c "import orchestrator.<module>"` and targeted `pytest`; it does not
  run mypy. Type errors reach the implementer only after CI, via
  `orchestrator/ci_checks.py`, which turns failing check-run annotations
  ("A `mypy`/`ruff` failure is ...") into a bounded excerpt for the shepherd's
  review-fix loop.
- Runtime image: `Dockerfile` runs `uv sync --locked --no-dev --no-cache`, so
  the image the implementer runs in ships neither mypy nor Ruff nor pytest from
  this repo's dev group. Any inner-loop checker therefore needs an explicit
  delivery path (image layer, `uvx` at run time, or a dev sync in the target
  clone), which the spike must cost out.
- Spike precedent: `docs/spikes/655-openspec-contract.md`,
  `docs/spikes/659-openspec-grammar.md`, `docs/spikes/661-canonical-capabilities.md`
  plus `docs/spikes/661/` assets; benchmarks live in `docs/benchmarks/`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker-implement/values.yaml`:
  the implementer worker runs image `ghcr.io/mctlhq/mctl-agents` tag `1.84.0`,
  i.e. the `--no-dev` image built from `Dockerfile`; no type checker present.
- `$MCTL_GITOPS_ROOT/services/admins/` also holds `mctl-agents-worker` and
  `mctl-agents-worker-exec`; not otherwise relevant, as the spike changes no
  deployed service.
- Clone history: shallow clone at `cd068a8e2a2e45fd767bd4ac7989b037ab554f61`;
  the issue's pinned SHA `68f10afc...` could not be resolved locally (recorded
  under Open questions).
- mctl MCP tools were not called: the spike is dev/CI tooling only and asserts
  nothing about runtime configuration beyond the image tag above.

## Proposed solution

A documentation-and-scripts spike, merged as one PR that touches only
`docs/spikes/707-pyrefly-type-check.md`, `docs/spikes/707/` and one guard test. Nothing in
`pyproject.toml`, `uv.lock`, `.github/workflows/`, `Dockerfile` or runtime code
changes.

The PR also adds one guard test, `tests/test_spike_707_report.py` (see
tasks.md), so the "no gate change" invariant is checked mechanically.

1. **Pinned environment.** Measure on the issue's SHA (or, if unreachable,
   the spike branch's merge-base with main, stated in the report). Pyrefly is
   run as `uvx pyrefly==<exact version>` so it never enters the lockfile; mypy
   is run as `uv run --locked mypy` (2.3.1). Record Python, uv, both versions,
   CPU model/cores, OS.

2. **Configurations, kept separate.**
   - (A) auto-migrated: run Pyrefly at the repo root with no Pyrefly config so
     it discovers `[tool.mypy]`; capture the effective config (via Pyrefly's
     config dump / `pyrefly init` output into a scratch dir) and record it in
     the report.
   - (B) explicit: `docs/spikes/707/pyrefly.toml` — `project-includes`
     `orchestrator`, `config`, `tools`; Python 3.12; search path to the
     `uv sync` venv site-packages; error suppression for `tests.*` mirroring
     the mypy override; nothing stricter. Passed via `--config`, never placed
     at the repo root or in `pyproject.toml`.
   - (C) optional stricter run, reported in its own section only.
   The harness lists the files each checker actually checked (mypy
   `--verbose`/`-v` module list or a files-from report; Pyrefly's checked-file
   listing) and diffs them; the report shows the diff is empty for (B).

3. **Benchmark harness** `docs/spikes/707/bench.py` (stdlib only, run with
   `uv run --locked python docs/spikes/707/bench.py`):
   - `cold`: N=10 fresh-process runs per checker with caches cleared
     (`.mypy_cache` removed; Pyrefly has no persistent cache in CLI mode, which
     the report states), wall-clock via `time.perf_counter`, median and p95.
   - `warm-mypy`: also report mypy with its incremental cache kept, since that
     is the fair "repeated" comparison for mypy.
   - `edit`: 20 iterations per checker: apply one mutation patch from the
     corpus (`git apply`), run the checker, revert (`git apply -R`), alternating
     mutations over the same representative files.
   - `loop`: for 4-6 mutations, time `checker -> ruff check <file> ->
     pytest <targeted test>` for each checker; record checker latency and
     total static-feedback latency (checker + Ruff).
   - output: a JSON results file `docs/spikes/707/results.json` plus the raw
     diagnostic outputs `docs/spikes/707/diagnostics/{mypy,pyrefly-A,pyrefly-B}.txt`.
   - `lint-job`: one timing of the lint-job-equivalent from a clean clone
     (`uv sync --locked` with an empty uv cache, then Ruff, then checker),
     with each phase timed separately; plus venv size delta of adding Pyrefly
     (`du` of the `uvx` tool env vs mypy's installed footprint).

4. **Mutation corpus** `docs/spikes/707/mutations/NN-<class>.patch`, each a
   small diff against the pinned SHA on real code, at least:
   Optional flowing into a non-optional parameter; incompatible assignment;
   wrong keyword/argument type on a typed call; wrong return type; attribute
   on an Optional/union; un-awaited coroutine / awaiting a non-awaitable in
   `orchestrator/temporal/` (if both tools support it); and one call across an
   `Any`/unannotated boundary typical of the soft-mode code. Candidate sites:
   `config/settings.py`, `orchestrator/ci_checks.py`, `orchestrator/proc.py`,
   `orchestrator/temporal/worker.py`. A `docs/spikes/707/mutations/README.md`
   table records per patch: caught by mypy / by Pyrefly, error code, whether
   the message names file:line and cause, and whether the defect is
   repairable from the diagnostic alone.

5. **Diagnostic comparison.** Normalise both outputs to
   `(path, line, category)`; match by path+line (±2 lines) and category;
   hand-classify every unmatched finding into the issue's five buckets; record
   the outcome of each of the 10 existing `# type: ignore[...]` comments and
   any stub/inference issue for `temporalio`, `mcp`, `yaml`, `httpx`,
   `claude_agent_sdk`.

6. **Report** `docs/spikes/707-pyrefly-type-check.md` in the style of the
   #661 spike: environment, the issue's metrics table filled in, lint-job
   timing, config complexity, suppression compatibility, library notes,
   inner-loop assessment, and exactly one recommendation evaluated
   criterion-by-criterion against the issue's decision rules.
   - For `PYREFLY_INNER_LOOP_ONLY`/`REPLACE_MYPY`, the report names the
     integration point. The default candidate is the implementer prompt's
     "Service-specific notes" in `agents/mctl-agents/.claude/agents/implementer.md`
     invoking `uvx pyrefly==<pin> check --config <committed config>`, with the
     open delivery question (the `--no-dev` image) costed: per-run `uvx`
     download vs a pinned image layer. The report includes a ready-to-file
     follow-up issue body; the spike does not apply it.

Why this way: it answers the issue's question with data on this codebase,
keeps every measurement reproducible from committed scripts and pinned
versions, and structurally cannot weaken the gate because no gate file is
touched.

## Alternatives

- **Add Pyrefly to the `dev` group and a non-blocking CI step now.** Faster to
  wire, but it changes `uv.lock` and CI during a spike, which the issue's
  invariants forbid, and presumes the answer.
- **Measure only clean-main error counts and checker speed.** Cheaper, but the
  issue states clean-main counts are insufficient; without the mutation oracle
  a faster checker that misses `Optional` misuse would look like a win.
- **Run the spike entirely in a GitHub Actions workflow.** Gives runner-native
  numbers, but needs a new workflow file in this repo, and hosted-runner noise
  makes p95 less stable; kept as an optional second environment instead.

## Platform impact

- Migrations: none. Backward compatibility: unaffected; mypy stays the only
  configured checker and the `lint` job is unchanged.
- Resource impact: a few minutes of local compute; a Pyrefly binary fetched by
  `uvx` into the uv cache only on the spike machine.
- Repo footprint: one Markdown report and a small `docs/spikes/707/` directory
  (script, explicit config, patches, results JSON, raw diagnostics). Raw
  diagnostic files are kept small by storing normalised output; if they
  exceed a few hundred KB, store a summary instead.
- Risks and mitigations:
  - Mutation patch accidentally applied to source on the branch: the harness
    reverts in a `finally` block and refuses to start on a dirty tree; a test
    asserts the spike PR leaves the gate files unchanged; review checks the
    diff touches only `docs/spikes/707*` and `tests/test_spike_707_report.py`.
  - Scope mismatch skews results: file-set diff is a required section of the
    report.
  - Pyrefly reading `[tool.mypy]` from `pyproject.toml` differently than
    documented: config (A) is reported as observed, config (B) is the
    decision-quality comparison.
  - Measurement noise: medians/p95 over the required N; machine idle state and
    CPU recorded.
