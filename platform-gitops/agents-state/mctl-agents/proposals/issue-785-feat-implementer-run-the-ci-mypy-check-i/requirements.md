# Run the target repository's CI mypy check in the implementer pod before the first push

## Context

The Tier 2 implementer (`orchestrator/run_implementer.py`, entrypoint `implement_one`) clones the target repository, lets the `implementer` sub-agent commit, and then pushes and opens the PR (`_push_and_open_pr`). Nothing in that path runs a type checker. The implementer image is built with `uv sync --locked --no-dev --no-cache` (`Dockerfile`), and mypy is only in the `dev` dependency group (`pyproject.toml`, `mypy~=2.3`), so neither the sub-agent nor the orchestrator can run it today. The sub-agent's own sanity-check guidance for mctl-agents (`agents/mctl-agents/.claude/agents/implementer.md`) mentions only imports, `pytest` and `--help`. CI (`.github/workflows/pr-validation.yml`, job `lint`, step "Run mypy") runs `uv run --locked mypy` against the `[tool.mypy]` config in `pyproject.toml`, so a type error is first seen there, after the push.

Issue #785 (follow-up to the #707 verdict `KEEP_MYPY`) measured 6 of 69 first pushes of `feat/agents-*` PRs failing mypy in CI (9%), up to 11 of 69 (16%) counting runs where ruff failed first. Each costs a CI round plus a review-remediation run. This proposal makes the implementer run the same mypy check CI runs, with the target repository's own config, before its first push, lets the sub-agent fix what it reports, and records the outcome honestly (passed, failed, or not run) instead of implying a clean tree. Step 1 of the issue (measure image size and cold wall time) is a gating task: the shape of the install is chosen from those numbers.

## User stories

- AS the platform owner I WANT the implementer to catch mypy errors before it pushes SO THAT first-push CI failures and the remediation runs they trigger drop.
- AS a PR reviewer I WANT the PR and the attempt's completion evidence to say whether the pre-push mypy check passed, failed, or did not run SO THAT a skipped check is never mistaken for a clean one.
- AS a maintainer of a target repository without mypy in CI I WANT the implementer to leave my repository's flow unchanged SO THAT a check my CI does not run never blocks or slows my PRs.

## Acceptance criteria (EARS)

- WHEN the implementer runs for a target service that has a registered CI type-check command THE SYSTEM SHALL instruct the `implementer` sub-agent, in the prompt built by `_build_prompt`, to run that exact command in the target clone before committing and to fix every error it reports within the proposal's scope.
- WHEN the sub-agent session has produced commits and before `_push_and_open_pr` is called for the first push of a run THE SYSTEM SHALL run the registered type-check command itself in the target clone on the committed HEAD, bounded by the remaining command budget.
- THE SYSTEM SHALL use the target repository's own configuration for the check (for mctl-agents: `uv run --locked mypy` with no path arguments, reading `[tool.mypy]` from the target's `pyproject.toml`), never a config shipped in the implementer image.
- IF the target service has no registered type-check command THEN THE SYSTEM SHALL not run any type check, SHALL not add the instruction to the prompt, and SHALL record the check as `not_run` with classification `not_applicable`.
- IF the type-check command exits zero THEN THE SYSTEM SHALL record a non-required verification record `typecheck` with result `pass` and classification `exit_zero`.
- IF the type-check command exits non-zero THEN THE SYSTEM SHALL record `typecheck` as `fail` / `exit_nonzero`, SHALL state "pre-push mypy: failed" with the error count in the PR body, and SHALL still push (CI remains the authoritative gate).
- IF the type-check command times out, is denied by the command budget, or cannot be started (for example the dev dependencies cannot be installed) THEN THE SYSTEM SHALL record `typecheck` as `unknown` (or `not_run` when it was never started) with the matching classification (`timeout`, `budget_denied`, `observation_failed`) and SHALL state in the PR body that the check did not complete; it SHALL never report such a run as passed.
- WHILE the check runs THE SYSTEM SHALL keep its artefacts (`.venv/`, `.mypy_cache/`) out of the commit by registering them in the clone's `.git/info/exclude`.
- THE SYSTEM SHALL keep the `typecheck` record non-required: `REQUIRED_CHECKS_V1ALPHA1` in `orchestrator/implementation_completion.py` is unchanged, so a `fail`/`unknown` typecheck never changes the attempt's completion outcome.
- WHEN the check is wired in THE SYSTEM SHALL have a test proving a seeded type error is reported as `fail` before the push and a test proving a clean tree is reported as `pass`.

## Out of scope

- Pyrefly in any form, including a shadow Pyrefly run in CI.
- Running ruff or pytest as a pre-push gate (ruff hiding mypy is noted in the baseline but is a separate change).
- Blocking the push on a mypy failure (see Open questions).
- Type-check commands for non-Python target repositories (Go `go vet`, TypeScript `tsc`).
- Changing CI (`pr-validation.yml`) or the `[tool.mypy]` configuration.
- Changes to the `mctl-agents-implement` ClusterWorkflowTemplate in mctl-gitops, unless step 1 shows a resource change is required; that would be a separate mctl-gitops PR.

## Open questions

- CPU limit discrepancy: the issue says the pod has 250m CPU, but the deployed `mctl-gitops` template `argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml` shows the agent container at `requests: cpu 200m` / `limits: cpu 3000m`. Task 1 must measure under the limit actually in force and record which value was used.
- Install shape (image vs. run-start `uv sync`) is decided by task 1's numbers. This proposal defaults to a run-start `uv sync --locked` of the target's default groups (including `dev`), because it is exact CI parity even when a proposal changes `uv.lock`; the alternative is recorded in design.md.
- Should a failed pre-push mypy block the push (and hand the run back for another turn) rather than be reported? This proposal reports and pushes, because the sub-agent has a single turn and a blocked push produces no PR at all; revisit after the 30-PR measurement.
- Which other target services run mypy in CI? Only mctl-agents was verified (its clone is the one available). The registry starts with mctl-agents only; other Python targets are added when their CI is confirmed.
- Run-time PyPI egress from the implement pod was not verified (no MCP or network-policy read was made for it). Task 1 checks it; if egress is blocked, the image-baked shape in design.md applies.
