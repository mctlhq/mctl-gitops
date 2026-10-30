# Tasks: issue-663-feat-models-migrate-cheap-profile-from-c

- [ ] 1. Find out the CLI version bundled in the pinned `claude-agent-sdk==0.2.163` (for example `python -c` against `claude_agent_sdk._bundled`, or `claude --version` from the bundled binary). — DoD: the version is recorded in the PR body, along with whether it is at least 2.1.296.
- [ ] 2. In `config/model-policy.yaml`, set `profiles.cheap.model` to `claude-haiku-5-5`. Keep `model_env: CLAUDE_CHEAP_MODEL`, leave `balanced` and `tasks:` unchanged, and add a one-line comment that routing a task to `cheap` needs separate evaluation. — DoD: `git diff` touches only the `cheap.model` line and that comment.
- [ ] 3. In `.env.example`, set `CLAUDE_CHEAP_MODEL=claude-haiku-5-5`, with a comment naming `claude-haiku-4-5` as the rollback value. — DoD: the line changes and `CLAUDE_BALANCED_MODEL` is unchanged.
- [ ] 4. (depends on 2) Add committed-policy tests to `tests/test_model_policy.py` (T1-T3). — DoD: `uv run pytest tests/test_model_policy.py` passes.
- [ ] 5. Add `tools/model_smoke.py`: resolve `cheap` through `config.model_policy`, run one tool-less, single-turn `claude_agent_sdk` query, assert success and a matching model key, and print usage, latency and cost. Make it opt-in, outside pytest collection. — DoD: the script exists, and `--help` runs offline.
- [ ] 6. (depends on 1, 2, 5) Run the smoke check twice: with no override (expect `claude-haiku-5-5`) and with `CLAUDE_CHEAP_MODEL=claude-haiku-4-5` (expect the rollback model). If the first run fails because the CLI does not know the model, bump `claude-agent-sdk` in `pyproject.toml` and `uv.lock` to the lowest version whose CLI accepts the id, and re-run. — DoD: the output of both runs is pasted in the PR.
- [ ] 7. (depends on 5) Add an evaluation mode with the two fixed mechanical workloads (commit-type classification and URL extraction, 10 inputs each, JSON output), run it on both models, and write `docs/benchmarks/haiku-5-5-cheap-profile.md` with:
  - correctness;
  - malformed-JSON rate;
  - latency;
  - input/output tokens;
  - cost;
  - the exact reproduction command;
  - a statement that this is not evidence for judgement tasks.

  — DoD: the note is committed, and both models were run on identical inputs.
- [ ] 8. Write the `claude-haiku-4-5` audit (in the benchmark note or the PR body), classifying the remaining references:
  - `CHANGELOG.md`
  - `docs/benchmarks/capability-discovery.md`
  - `tests/fixtures/model-usage-records.json`
  - `tests/test_usage_ledger.py`

  All four are historical and preserved. — DoD: after the change, `grep -rn claude-haiku-4-5` shows only the audited references and the rollback docs.
- [ ] 9. Run the full offline suite, including the manifest validation (`orchestrator/validate_manifest.py`) and `tests/test_manifest.py` / `tests/test_resolver.py`. — DoD: everything passes, with no task or profile errors.

## Tests
- [ ] T1. `ModelPolicy.load(DEFAULT_POLICY_PATH)`, with `CLAUDE_CHEAP_MODEL` and `MODEL_POLICY_PATH` unset: the `cheap` profile (resolved through a synthetic `probe: cheap` task built from the loaded profiles) gives `model == "claude-haiku-5-5"` and `source == "policy"`.
- [ ] T2. Committed routing boundary:
  - `service_agent`, `mentor_digest` and `review_findings_normalize` each resolve to `("balanced", "claude-sonnet-5-5")` when the legacy and profile env vars are unset;
  - no committed task maps to `cheap`;
  - `balanced.model_env == "CLAUDE_BALANCED_MODEL"`.
- [ ] T3. Rollback: with `CLAUDE_CHEAP_MODEL=claude-haiku-4-5`, the cheap probe resolves to `claude-haiku-4-5` with `source == "CLAUDE_CHEAP_MODEL"`.
- [ ] T4. The existing tests in `tests/test_model_policy.py`, `tests/test_usage_ledger.py` and `tests/test_manifest.py` stay green with their fixtures unmodified.
- [ ] T5. Manual live check: `tools/model_smoke.py` passes for `claude-haiku-5-5` and for the `claude-haiku-4-5` override (task 6).

## Rollback
- Immediate, no code change: set `CLAUDE_CHEAP_MODEL=claude-haiku-4-5` in the runtime env, for example as an env entry in mctl-gitops `cwft-mctl-agents-run.yaml`. Profile env overrides take precedence over the YAML default in `ModelPolicy.resolve()`.
- Full: revert the PR. This restores `cheap.model: claude-haiku-4-5` and the `.env.example` default. If the SDK pin was bumped in task 6, reverting also restores the earlier harness.
- No data needs restoring, because historical usage records are untouched.
