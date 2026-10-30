# Design: issue-785-feat-implementer-run-the-ci-mypy-check-i

## Current state

- `Dockerfile`: the runtime image installs Python deps with `uv sync --locked --no-dev --no-cache` (comment: "--no-dev: `dev` is a default group in uv, so without this the production image ships pytest (and later ruff and mypy)") and puts `/app/.venv/bin` on `PATH`. `uv` 0.11.11 is in the image at `/usr/local/bin/uv`. mypy is therefore absent from the image.
- `pyproject.toml`: `mypy~=2.3` and `types-pyyaml` are in the `dev` group; `[tool.mypy]` sets `files = ["orchestrator", "config", "tools"]`, `python_version = "3.12"`, `warn_unused_ignores`, `warn_redundant_casts`, and an override silencing `tests.*`.
- `.github/workflows/pr-validation.yml`, job `lint`: `uv sync --locked`, then `uv run --locked ruff check orchestrator config tests tools`, then `uv run --locked mypy` (no path args, so `[tool.mypy].files` is authoritative).
- `.gitignore` ignores `.venv/` but not `.mypy_cache/`.
- `orchestrator/run_implementer.py`:
  - `_clone_target` clones `mctlhq/<service>` into a temp dir (depth 10).
  - `_stage_implementer_agent` copies `agents/<service>/.claude/agents/implementer.md` into the clone and registers it in `.git/info/exclude`.
  - `_build_prompt` builds the first-run prompt and the review-follow-up prompt; neither mentions a type check.
  - The first-run flow in `implement_one` runs the SDK session (`_run_implementer_agent`, with a `CommandBudgetLedger`), checks `_has_new_commits`, runs the chart MAJOR-version guard (`_detect_chart_major_bumps`), then calls `_push_and_open_pr` (step "7. Push + PR"). `_pr_title_and_body` builds the PR body.
  - `_AttemptObservations` collects per-attempt facts (`commits_present`, `chart_guard_passed`, `budget_ledger`, ...); `_verification_records` turns them into `ic.VerificationRecord`s. The four required checks are fixed by `REQUIRED_CHECKS_V1ALPHA1` in `orchestrator/implementation_completion.py`; non-required records (e.g. `command_budget`) may be appended. Allowed results: `pass`, `fail`, `unknown`, `not_run`; classifications: `exit_zero`, `exit_nonzero`, `timeout`, `budget_denied`, `not_applicable`, `observation_failed`.
- `agents/mctl-agents/.claude/agents/implementer.md` "Sanity check" lists `python -c "import ..."`, targeted `pytest`, and `--help`; no mypy. `agents/_manifests/implementer/agent.yaml` declares `timeoutSeconds: 900` as the manifest default.
- `orchestrator/ci_checks.py` already parses CI mypy/ruff annotations for the review-remediation path (after the fact), which is the cost this proposal moves earlier.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`: the agent container (`image: {{workflow.parameters.agent_image}}`, `activeDeadlineSeconds: 7200`) has `requests: { cpu: 200m, memory: 3Gi, ephemeral-storage: 10Gi }` and `limits: { cpu: 3000m, memory: 8Gi, ephemeral-storage: 11Gi }`. This contradicts the issue's "250m CPU"; recorded under Open questions.
- `$MCTL_GITOPS_ROOT/agent-platform/execution-profiles/implementer-default/profile.yaml`: production `timeoutSeconds: 5400` (budget $20.00), so a cold mypy run of tens of seconds fits the envelope.
- Not checked: whether the implement pod's network policy permits PyPI egress at run time. The mctl MCP tools were not used; the create-tenant tool description states Argo Workflow pods get internet egress, but that was not verified for this namespace. Recorded under Open questions; task 1 verifies it empirically.

## Proposed solution

### Step 0 (gating): measure (task 1)

Before any code change, measure and post on #785: (a) image size delta of `uv sync --locked` (with dev) vs. `--no-dev` for the mctl-agents lock; (b) wall time of `uv sync --locked` into a fresh clone inside an implement pod (warm vs. empty `UV_CACHE_DIR`); (c) cold and warm `uv run --locked mypy` wall time inside a pod with the CPU limit actually in force (3000m per the deployed CWFT; also at 250m to answer the issue's figure). The chosen shape below is the default; task 2 confirms or switches it from the numbers.

### Default shape: run-start install of the target's own dev group

The check runs in the target clone with the target's own lock and config: `uv run --locked mypy`. `uv run` in the clone creates `<clone>/.venv` from the clone's `uv.lock` including the default `dev` group, which is exactly what CI does (`uv sync --locked` then `uv run --locked mypy`). This is parity even when the proposal itself edits `pyproject.toml`/`uv.lock`, which an image-baked mypy plus `/app/.venv` cannot give (the image's venv is the lock of the image build, not of the branch). It needs PyPI egress at run time; if task 1 shows egress is blocked or the install is too slow, task 2 switches to the image alternative below.

Environment hygiene for the subprocess: unset `VIRTUAL_ENV` and drop `/app/.venv/bin` from the child's `PATH`, so `uv` uses the clone's project environment and does not warn or reuse the image venv; set `UV_CACHE_DIR` under the run's workdir so the agent's run and the orchestrator's re-run share one download cache.

### Registry of type-check commands

Add to `config/settings.py` a small mapping `TYPECHECK_COMMANDS: dict[str, tuple[str, ...]]`, starting with `{"mctl-agents": ("uv", "run", "--locked", "mypy")}`. Explicit, not auto-detected: a heuristic scan of the target's workflow YAML could run a check CI does not run, or miss one, and a wrong guess is reported as a real result. A test asserts the mctl-agents entry matches the `Run mypy` step in `.github/workflows/pr-validation.yml`, so the two cannot drift silently. Services without an entry are untouched.

### Sub-agent side (the fix loop)

In `_build_prompt`, for a service with a registered command, add one workflow line to both the first-run and the review-follow-up prompts: before committing, run `<command>` from the repository root, synchronously, and fix every reported error that is in scope; if errors remain that are pre-existing on the base branch or outside scope, say so in the final message rather than editing unrelated code. Also update `agents/mctl-agents/.claude/agents/implementer.md` "Sanity check" to name `uv run --locked mypy`. Only the first run is cold; later invocations reuse `.mypy_cache`.

### Orchestrator side (the honest record)

New helper in `orchestrator/run_implementer.py`:

```python
@dataclass(frozen=True)
class TypecheckResult:
    result: str            # pass | fail | unknown | not_run
    classification: str    # exit_zero | exit_nonzero | timeout | budget_denied | not_applicable | observation_failed
    error_count: int | None
    summary: str           # one line, no source text beyond mypy's "Found N errors" line

def _run_pre_push_typecheck(repo_dir: Path, service: str, ledger: CommandBudgetLedger | None) -> TypecheckResult
```

- No registered command: `not_run` / `not_applicable`; no subprocess.
- Registers `.venv/` and `.mypy_cache/` in `.git/info/exclude` (same mechanism `_stage_implementer_agent` uses) before running.
- Timeout = min(remaining command budget from the ledger, a cap `IMPLEMENTER_TYPECHECK_TIMEOUT_SECONDS`, default 300). No remaining budget: `not_run` / `budget_denied`. Timeout: `unknown` / `timeout`. Start/install failure (uv exits non-zero before mypy prints its summary, or `OSError`): `unknown` / `observation_failed`. mypy exit 0: `pass` / `exit_zero`. mypy exit 1 with a "Found N errors" summary: `fail` / `exit_nonzero` with `error_count=N`.
- Distinguishing an install failure from a mypy failure: run `uv sync --locked` first as its own subprocess, then `uv run --locked --no-sync mypy`; only the second step's exit code is a type-check result.

Called in `implement_one` between the chart guard and step 7 (`_push_and_open_pr`), only on the first-push path. The result is stored on a new `_AttemptObservations.typecheck` field and `_verification_records` appends a non-required `VerificationRecord("typecheck", ...)`. `_pr_title_and_body` gains an optional line, e.g. `Pre-push mypy: passed`, `Pre-push mypy: FAILED (3 errors) - CI will report them`, or `Pre-push mypy: did not complete (timeout) - not a clean result`. No line for services without a command. The push proceeds in every case; CI stays the gate.

Why the orchestrator re-runs it rather than trusting the sub-agent: the agent's report is prose; the record must be a fact observed by the orchestrator (the same principle as `budget_ledger` in mctl-agents#430), and a skipped or failed check must never read as clean.

## Alternatives

1. **mypy (and the target's dev group) baked into the implementer image.** Fast start, no egress. Dropped as default: the image venv is pinned to the image build's lock, not the branch's, so a proposal that adds a dependency or bumps mypy type-checks against the wrong environment; it also grows the image for every agent that uses it (service agents, shepherd, investigator) and re-ships the dev group the `Dockerfile` comment deliberately excludes. Kept as the fallback if task 1 shows no egress or an unacceptable install time; then the check would use `/app/.venv` plus the clone's config, and records would note the lock mismatch when `uv.lock` differs from the image's.
2. **Block the push on a mypy failure.** Dropped for now: the sub-agent has one turn; a blocked push means no PR and a needs-triage proposal, which costs more than one CI round plus remediation. Recorded as an open question for after the 30-PR measurement.
3. **Auto-detect from the target's `.github/workflows/*.yml`.** Dropped: brittle YAML/shell parsing, and a wrong guess would be reported as a real check. An explicit registry plus a parity test is simpler and honest.
4. **Pyrefly as the inner check.** Out of scope per the issue: it is not the CI gate, so the inner loop could pass while CI fails.

## Platform impact

- Migrations: none. No schema change; `typecheck` is a new non-required verification record, accepted by the existing `VerificationRecord` validation (`required=False`, check id not in `REQUIRED_CHECKS_V1ALPHA1`). Consumers that list verification records see one more entry; completion outcomes are unchanged.
- Backward compatibility: services without a registry entry behave exactly as today (no prompt line, no subprocess, `not_run`/`not_applicable` record).
- Resources: one `uv sync` per run (download size measured in task 1; venv lives in the clone's emptyDir, counted against the 10-11Gi ephemeral-storage the CWFT already grants) and one or more mypy runs (cold ~12-32 s per the issue; warm runs reuse the cache). Memory: mypy on ~6k lines is well under the 8Gi limit. Cost: no extra model call; the sub-agent spends some turns fixing errors, which is the intended trade against a remediation run.
- Risks and mitigations:
  - PyPI egress blocked or slow: classified `observation_failed`/`timeout`, reported, push proceeds; task 1 detects it before rollout and task 2 can switch to the image shape.
  - Command budget consumed by the check: bounded by the ledger and a hard cap; a denied check is `budget_denied`, never `pass`.
  - Artefacts committed by `git add -A`: `.venv/` is already ignored in mctl-agents; both `.venv/` and `.mypy_cache/` are added to `.git/info/exclude` for every registered target.
  - Pre-existing errors on `main` would show as `fail` for an unrelated change: the prompt tells the agent not to fix out-of-scope code; the PR line reports the count so the reviewer sees it. CI would fail on them anyway.
  - Registry drift from CI: guarded by the parity test.
