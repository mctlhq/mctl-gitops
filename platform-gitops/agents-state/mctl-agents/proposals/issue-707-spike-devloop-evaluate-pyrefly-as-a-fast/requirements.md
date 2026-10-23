# Spike: evaluate Pyrefly as a fast type-check gate for DevLoop inner loops

## Context

`mctl-agents` type-checks with `mypy~=2.3` (locked at 2.3.1 in `uv.lock`) in soft
mode over `orchestrator/`, `config/` and `tools/` (`[tool.mypy]` in
`pyproject.toml`), run by the `lint` job of `.github/workflows/pr-validation.yml`
as `uv run --locked mypy`. Issue #707 asks for a measured, reproducible
benchmark/decision spike comparing Pyrefly (Meta's Rust type checker) against
that baseline on this repository, on the same scope, and for exactly one
recommendation: `REPLACE_MYPY`, `PYREFLY_INNER_LOOP_ONLY` or `KEEP_MYPY`.

The value being tested is the agent inner loop (edit -> fast type check ->
repair -> targeted tests), not CI wall-clock: the `lint` job comment already
says Ruff + mypy run in a couple of seconds. The spike also has to account for
a fact found while investigating: the production image runs
`uv sync --locked --no-dev` (`Dockerfile`), so the implementer runtime ships no
type checker at all today; any inner-loop recommendation must say how the
checker would get there. The spike changes no gate, no runtime code and no
production behaviour; it produces a report plus throwaway benchmark assets.

## User stories

- AS a DevLoop maintainer I WANT measured mypy-vs-Pyrefly latency and signal
  quality on this repo SO THAT the decision is not extrapolated from Google's
  or Meta's benchmarks.
- AS the Tier 2 implementer's owner I WANT to know whether a cheaper
  deterministic type check could run inside the implementation loop, and where
  it would be invoked, SO THAT agents repair type defects before CI does.
- AS a reviewer I WANT the current mypy gate untouched during the spike SO THAT
  the evaluation cannot weaken CI.

## Acceptance criteria (EARS)

- WHEN the spike report is published THE SYSTEM SHALL record the exact
  mctl-agents main SHA measured, Python, uv, mypy (from `uv.lock`) and Pyrefly
  versions, and the machine CPU and OS.
- WHEN the baseline is taken THE SYSTEM SHALL run `uv sync --locked` then
  `uv run --locked mypy` exactly as the CI `lint` job does and record its exit
  code and diagnostic count.
- WHEN Pyrefly is run THE SYSTEM SHALL report three results separately:
  (1) auto-migrated/discovered `[tool.mypy]` configuration with its effective
  settings documented, (2) an explicit temporary Pyrefly config reproducing
  the `files = ["orchestrator", "config", "tools"]` scope and the
  `tests.*` `ignore_errors` override, and (3) any stricter mode, only as an
  optional labelled extra.
- WHEN comparing results THE SYSTEM SHALL show that both checkers covered the
  same set of source files, and SHALL NOT call either better on a result where
  the checked file sets differ.
- WHEN latency is measured THE SYSTEM SHALL record median and p95 for at least
  10 fresh-process runs per checker and at least 20 edit/check iterations per
  checker on the same file set, excluding dependency installation.
- WHEN CI cost is reported THE SYSTEM SHALL report one full
  lint-job-equivalent timing (setup + `uv sync --locked` + Ruff + checker)
  separately from checker-only timings, and SHALL NOT present a checker-only
  speedup as a CI speedup.
- WHEN diagnostics on main are compared THE SYSTEM SHALL classify every
  Pyrefly finding as one of: also caught by mypy; credible additional defect;
  migration/config mismatch; unsupported typing behaviour; false
  positive/noise; and SHALL classify every mypy finding Pyrefly misses as a
  meaningful or non-meaningful loss of signal.
- WHEN the mutation corpus is run THE SYSTEM SHALL include at least the seven
  defect classes listed in the issue, derived from real repo patterns, and
  record per checker whether each is caught and whether the diagnostic names
  an actionable file, line and cause.
- WHEN the inner loop is prototyped THE SYSTEM SHALL time both sequences
  (patch -> Pyrefly -> Ruff -> targeted pytest, and patch -> mypy -> Ruff ->
  targeted pytest) on several seeded patches, recording checker latency and
  total static-feedback latency.
- WHEN the 10 existing `# type: ignore[...]` comments in the checked scope are
  encountered THE SYSTEM SHALL record whether Pyrefly honours, ignores or
  flags each one (including interaction with `warn_unused_ignores`).
- WHEN third-party typing is relevant THE SYSTEM SHALL note any stub or
  inference problems for `temporalio`, `mcp`, `PyYAML`/`types-pyyaml`,
  `httpx` and `claude-agent-sdk`.
- WHEN the report concludes THE SYSTEM SHALL state exactly one of
  `REPLACE_MYPY`, `PYREFLY_INNER_LOOP_ONLY`, `KEEP_MYPY`, justified against
  the issue's decision criteria.
- IF the recommendation is not `KEEP_MYPY` THEN THE SYSTEM SHALL name the
  integration point (implementer prompt command, local dev command, or
  image/dependency change), how the Pyrefly version and config are pinned,
  and SHALL leave a ready-to-file follow-up issue text rather than changing
  the gate.
- IF the recommendation is `PYREFLY_INNER_LOOP_ONLY` THEN THE SYSTEM SHALL
  state that a Pyrefly pass never satisfies the mypy gate.
- WHILE the spike is in progress THE SYSTEM SHALL keep `pyproject.toml`
  `[tool.mypy]`, `[dependency-groups].dev`, `uv.lock`, the `lint` job and all
  runtime code under `orchestrator/`, `config/`, `tools/` unchanged.
- WHILE the mutation corpus exists THE SYSTEM SHALL keep it as patch files
  under `docs/spikes/707/` that are never applied on a merged branch.

## Out of scope

- Replacing or weakening the mypy CI gate; adding Pyrefly to `pyproject.toml`,
  `uv.lock` or the CI `lint` workflow (`pr-validation.yml`). The spike-only
  measurement workflow `spike-707-bench.yml` is in scope; it gates nothing.
- Type-checking `tests/` or raising strictness (e.g. `disallow_untyped_defs`).
- Source changes made to reach parity between checkers.
- Shipping any checker in the production image (`Dockerfile`).
- Ruff or pytest replacement; `mctl-api` or any non-Python repo.
- An LLM-driven repair benchmark (optional only if trivially convenient).

## Open questions

- RESOLVED (operator review 2026-10-23): the issue's baseline SHA
  `68f10afcb8a96d7b1c54d5d56819d8e39979c275` resolves on mctl-agents (commit
  dated 2026-10-18). All measurements run on that SHA; there is no
  merge-base fallback.
- RESOLVED (operator review 2026-10-23): the measurement environment is one
  GitHub-hosted `ubuntu-latest` runner, driven by a spike-only workflow
  (`workflow_dispatch` plus `pull_request` on `docs/spikes/707/**`). The report
  records the runner's CPU model, core count, memory and OS as printed by the
  workflow. The implementer pod (250m CPU, 128Mi) is not a measurement
  environment: it is too small and too noisy for p95 timings.
- RESOLVED (operator review 2026-10-23): Pyrefly is pinned to `1.4.0` and
  invoked as `uvx pyrefly==1.4.0` so nothing enters `uv.lock`.
- The implementer runtime image has no type checker (`--no-dev`). Whether
  shipping one there is acceptable is a follow-up decision; the spike only
  measures and reports the size/latency cost of doing so.
