# Tasks: issue-824-feat-policy-provider-seam-for-non-anthro

- [ ] 1. Add `ProviderSpec` and `ModelSelection.provider` to `config/model_policy.py`. Parse and validate the
  optional `provider` block in `ModelPolicy._validate()` with a `_validate_provider()` helper. The rules
  cover: allowed keys; `api == "anthropic-messages"`; an `https` `base_url` with a host and no
  userinfo/query/fragment; an upper-case `credential_env` that is not `ANTHROPIC_*` or
  `CLAUDE_CODE_OAUTH_TOKEN*`; `pin_model_slots: true`; `fallback: none`; no `model_env` on a provider
  profile. — DoD: the committed `config/model-policy.yaml` loads unchanged, the fixture policy loads, and
  each invalid variant raises `ModelPolicyError` naming the profile.
- [ ] 2. (depends on 1) In `ModelPolicy.resolve()`, attach the profile's `ProviderSpec` to the selection and
  raise `ModelPolicyError` when a provider profile's legacy env override is non-empty. Extend
  `ModelSelection.log()` with `provider=<name>`. — DoD: resolution for non-provider profiles is byte-identical
  (the existing `tests/test_model_policy.py` passes unchanged).
- [ ] 3. (depends on 1) Add `MODEL_SLOTS` and the pure `provider_session_env(provider, model, env)` to
  `config/model_policy.py`. It blanks every `ANTHROPIC_*` key, `CLAUDE_CODE_OAUTH_TOKEN*` and the raw
  credential env. It sets `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, all six model slots and
  `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`. It raises on a missing or empty credential and asserts that
  no original Anthropic credential value survives. — DoD: the function has no I/O and is covered by T3-T5.
- [ ] 4. (depends on 3) Add `provider: ProviderSpec | None = None` to `orchestrator/options.py::_scrubbed`.
  When set, apply `provider_session_env` after the existing token scrubbing, require `fallback_model is None`
  and a non-empty `options.model`. — DoD: with `provider=None` all existing tests in `tests/test_options.py`
  and `tests/test_usage_ledger.py` pass unchanged.
- [ ] 5. (depends on 2, 4) Add `provider: ProviderSpec | None = None` to `orchestrator/resolver.py::ExecutionPlan`,
  filled from `model_selection.provider` in `execute()`. Pass `provider=plan.provider` from both `_scrubbed`
  calls in `build_issue_investigator_options_from_plan`. — DoD: the existing plan and equivalence tests pass,
  and a plan built against the fixture policy carries the provider into the session env.
- [ ] 6. (depends on 2) In `config/settings.py`, raise `ModelPolicyError` at import if any module-level
  selection (`SERVICE_AGENT_SELECTION`, `MENTOR_SELECTION`, `SHEPHERD_SELECTION`, `SCOUT_*_SELECTION`)
  carries a provider. — DoD: the committed policy imports fine, and a policy routing `service_agent` to a
  provider profile fails at import (T7).
- [ ] 7. (depends on 1) Add `tests/fixtures/model-policy-provider.yaml`. It holds the current profiles plus
  `experimental_hetzner` (`model: Qwen/Qwen3.6-35B-A3B-FP8`, `base_url: https://inference.hetzner.com/api`,
  `credential_env: HETZNER_INFERENCE_API_KEY`) and a test-only task routed to it. Document the `provider`
  block in `docs/model-policy-providers.md` (not in `config/model-policy.yaml`, whose bytes stay unchanged). — DoD:
  the fixture is used by T1-T6, `config/model-policy.yaml` is byte-identical, so `model_policy_version` of
  existing plans does not change.
- [ ] 8. (optional, depends on 3) Express the provider part of `tools/hetzner_inference_spike.py::hetzner_session_env`
  through `provider_session_env`, keeping its allowlist, HOME and GitHub-token blanking. — DoD:
  `tests/test_hetzner_inference_spike.py` passes unchanged.

## Tests
- [ ] T1. `tests/test_model_policy.py`: the fixture policy loads, and `resolve(<test task>)` returns
  `provider.base_url == "https://inference.hetzner.com/api"` and `credential_env == "HETZNER_INFERENCE_API_KEY"`.
- [ ] T2. Parametrized rejection cases: missing `base_url`; `http://` URL; URL with userinfo or query;
  `credential_env: ANTHROPIC_API_KEY`; `credential_env: CLAUDE_CODE_OAUTH_TOKEN`; lower-case env name;
  `fallback: claude-sonnet-5-5`; `pin_model_slots: false`; `model_env` alongside `provider`; unknown key;
  `api: openai`. Each must raise `ModelPolicyError`.
- [ ] T3. Offline leak test, the acceptance test. Seed an env with distinct sentinel values for
  `ANTHROPIC_API_KEY`, `ANTHROPIC_API_KEY_SECONDARY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN`,
  `CLAUDE_CODE_OAUTH_TOKEN_SECONDARY` and an extra `ANTHROPIC_FOO`, plus `HETZNER_INFERENCE_API_KEY=hz-sentinel`.
  Build the options through `build_issue_investigator_options_from_plan` with a plan resolved from the
  fixture policy (monkeypatched `os.environ`, no network). Assert that no Anthropic sentinel value appears
  in any value of `options.env`, that `ANTHROPIC_AUTH_TOKEN == "hz-sentinel"`, that `ANTHROPIC_BASE_URL`
  matches the policy, that all six slots equal the model, that `HETZNER_INFERENCE_API_KEY == ""` in the
  child env, and that `fallback_model is None`.
- [ ] T4. `provider_session_env` raises `ModelPolicyError` when `HETZNER_INFERENCE_API_KEY` is unset or empty.
- [ ] T5. `provider_session_env` raises when the provider credential value equals an Anthropic credential
  value (copied credential).
- [ ] T6. A provider profile with a non-empty legacy env override raises in `resolve()`. A non-provider profile
  keeps today's precedence.
- [ ] T7. Re-importing `config.settings` with `MODEL_POLICY_PATH` pointing at a policy that routes
  `service_agent` to the provider profile raises `ModelPolicyError`.
- [ ] T8. Regression: with the committed policy, `_scrubbed(options)` and every builder produce the same env as
  before (existing `tests/test_options.py` equivalence tests).

## Rollback
The change is additive and dormant: no committed profile declares a provider. To roll back, revert the PR.
Nothing deployed depends on it, the committed `config/model-policy.yaml` routing is unchanged, and no
gitops change is involved. If a later adoption PR routes a task to a provider profile and misbehaves, revert
that routing line in `config/model-policy.yaml` (or remove the `provider` block). The session falls back to
the Anthropic profile through the normal policy path, not through an implicit runtime fallback.
