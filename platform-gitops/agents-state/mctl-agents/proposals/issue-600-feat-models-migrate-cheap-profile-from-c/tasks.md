# Tasks: issue-600-feat-models-migrate-cheap-profile-from-c

- [ ] 1. Change `profiles.cheap.model` in `config/model-policy.yaml` to `claude-haiku-5-5`, with a dated comment naming #600 and the `CLAUDE_CHEAP_MODEL` rollback — DoD: `balanced` and `tasks:` are byte-identical; `ModelPolicy.load()` succeeds.
- [ ] 2. Change `.env.example` `CLAUDE_CHEAP_MODEL` to `claude-haiku-5-5` and add a rollback comment (`claude-haiku-4-5`) — DoD: the diff touches only that block.
- [ ] 3. (depends on 1) Add committed-policy tests to `tests/test_model_policy.py`: cheap default, rollback override, balanced-routing guard, and "no committed task maps to cheap" — DoD: the tests pass with the new YAML, and fail if the YAML is reverted or a judgement task is moved to `cheap`.
- [ ] 4. (depends on 1) Add the opt-in live smoke test `tests/test_model_smoke_live.py` (marker `live`, gated on credentials plus `MCTL_LIVE_MODEL_SMOKE=1`), registering the marker in `pyproject.toml` if needed — DoD: skipped in the default run; when run live, it proves `claude-haiku-5-5` works and that the `claude-haiku-4-5` override works; the results are pasted in the PR.
- [ ] 5. Add `tools/cheap_tier_eval.py` and fixtures under `tests/fixtures/cheap_tier_eval/` (log summary to JSON, issue classification, review-comment extraction; about 10 cases each, with expected answers) — DoD: the script runs both models on identical inputs and emits per-model correctness, latency, tokens, SDK `costUSD`, and malformed-JSON rate.
- [ ] 6. (depends on 5) Run the evaluation and check in `docs/benchmarks/haiku-5-5-cheap-tier.md` — DoD: the note gives the results table, sample size, exact command, SDK version, date, and an explicit statement that it does not license routing judgement tasks to `cheap`.
- [ ] 7. Audit `claude-haiku-4-5` references and record the classification table in the PR body (migrated: policy, `.env.example`; preserved: `CHANGELOG.md`, `docs/benchmarks/capability-discovery.md`, `tests/fixtures/model-usage-records.json`, `tests/test_usage_ledger.py` `HAIKU`) — DoD: `grep -rn claude-haiku-4-5` shows only preserved or rollback-documentation hits.
- [ ] 8. Add a dated clarifying note to `docs/adr/012-model-usage-cost-attribution-contract.md` about the current routing (`mentor_digest`/`review_findings_normalize` on `balanced` since 2026-10-01; `cheap` now Haiku 5.5) — DoD: historical rows unchanged; the note is accurate against the YAML.
- [ ] 9. Check mctl-gitops for an explicit `CLAUDE_CHEAP_MODEL` in the agents' CWFT/env and note the result in the PR — DoD: the PR states whether a deployed override exists and pins 4.5.

## Tests
- [ ] T1. `pytest tests/test_model_policy.py` — the committed `cheap` resolves to `claude-haiku-5-5`, `source=policy`, with all relevant env vars cleared.
- [ ] T2. Same file — `CLAUDE_CHEAP_MODEL=claude-haiku-4-5` resolves to `claude-haiku-4-5`, `source=CLAUDE_CHEAP_MODEL`.
- [ ] T3. Same file — `service_agent`, `mentor_digest` and `review_findings_normalize` resolve to `balanced`/`claude-sonnet-5-5`; no committed task maps to `cheap`.
- [ ] T4. `pytest tests/test_resolver.py tests/test_manifest.py tests/test_agent_inventory.py` stay green (`model_policy_version` still matches `v1+sha256:`).
- [ ] T5. Full default `pytest` run is green and the live smoke test reports as skipped.
- [ ] T6. Manual: `MCTL_LIVE_MODEL_SMOKE=1 pytest -m live tests/test_model_smoke_live.py` passes for both the default and the rollback model.

## Rollback
- Immediate, with no code change: set `CLAUDE_CHEAP_MODEL=claude-haiku-4-5` in the deployment env. `ModelPolicy.resolve()` gives the profile env precedence over the YAML default.
- Permanent: revert the PR (a two-line change to `config/model-policy.yaml` and `.env.example`, plus tests and docs). No data migration is involved, and no historical usage records were changed.
