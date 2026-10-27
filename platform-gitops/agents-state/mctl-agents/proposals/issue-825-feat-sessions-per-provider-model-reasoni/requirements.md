# Per-provider/model reasoning effort in the model policy; re-bench Qwen3.8-27B

## Context
Spike mctlhq/mctl-agents#791 (verdict `ADOPT_EXPERIMENTAL_PROVIDER`, `docs/spikes/791-hetzner-inference.md`)
found that Hetzner `Qwen3.8-27B` rejects the Claude CLI's default reasoning effort `high`
(`Unexpected reasoning effort high. Supported types are xhigh (default), medium, and low.`). Every
candidate cell for that model failed with an HTTP 400 (24/24). An exploratory run with `--effort medium`
had 0 provider errors. That flag exists only in the spike harness (`tools/hetzner_inference_spike.py`,
`make_sdk_runner(effort=...)`); production session builders cannot express it.

Issue #825 asks for the effort to be declared next to the model in the model policy
(`config/model-policy.yaml`, validated by `config/model_policy.py::ModelPolicy`). The session builder then
passes it to the SDK (`ClaudeAgentOptions.effort`, rendered by the SDK as CLI `--effort`). `Qwen3.8-27B`
is then re-benched with the #791 harness, taking its effort from the policy rather than from a harness flag.

## User stories
- AS a platform operator I WANT to declare a reasoning effort on a model-policy profile SO THAT a model
  that rejects the CLI default effort can run sessions without code changes.
- AS a platform operator I WANT the #791 bench to take the candidate's model, provider and effort from a
  model-policy file SO THAT the bench proves the policy path rather than a harness-only override.
- AS a maintainer I WANT every profile without an effort to behave exactly as it does today SO THAT
  Anthropic-backed tasks are unaffected.

## Acceptance criteria (EARS)
- WHEN a model-policy profile declares `effort` with a value in `low`, `medium`, `high`, `xhigh`, `max`
  THE SYSTEM SHALL load the policy and expose that value as `ModelSelection.effort` for every task routed
  to the profile.
- IF a profile's `effort` is not one of those five values, or is not a string, THEN THE SYSTEM SHALL raise
  `ModelPolicyError` when the policy is loaded, naming the profile.
- WHILE a profile declares no `effort` THE SYSTEM SHALL resolve `ModelSelection.effort` as `None` and
  build `ClaudeAgentOptions` with `effort=None`, so the CLI receives no `--effort` flag. The options must
  be field-for-field identical to the ones built today.
- WHEN the resolver builds an `ExecutionPlan` from a selection with an effort THE SYSTEM SHALL carry it
  as `ExecutionPlan.effort` and include `effort` in `ExecutionPlan.to_log_dict()`.
- WHEN `build_issue_investigator_options_from_plan` builds options from a plan with an effort THE SYSTEM
  SHALL set `ClaudeAgentOptions.effort` to that value, on both the gateway and the non-gateway branch.
- IF a builder passes an effort to `_scrubbed` while the options already hold a different non-None
  `effort` THEN THE SYSTEM SHALL raise `ValueError` rather than silently pick one.
- IF a task read through the string-only `*_SELECTION` constants in `config/settings.py` resolves to a
  profile with an `effort` THEN THE SYSTEM SHALL fail closed at import with `ModelPolicyError`, the same
  way it already does for a provider profile.
- WHEN `tools/hetzner_inference_spike.py bench` is run with `--model-policy PATH --policy-task TASK`
  THE SYSTEM SHALL take the candidate model and effort from the resolved selection. It SHALL record
  `effort` and `effort_source: policy` on every candidate record and in the run manifest.
- IF `--model-policy` is combined with `--effort`, or the resolved selection has no provider, or the
  provider's `base_url` differs from `HETZNER_INFERENCE_BASE_URL`, or the resolved model is not AVAILABLE
  in the snapshot THEN THE SYSTEM SHALL refuse the bench with `SpikeError` before making any live call.
- WHILE a run has a non-default effort (flag or policy) THE SYSTEM SHALL keep refusing to score it with the
  pre-registered #791 `decide()`, and SHALL refuse to write it into `docs/spikes/791/`.
- WHEN the re-bench of `Qwen/Qwen3.8-27B` is run from the committed bench policy THE SYSTEM SHALL produce
  committed records with 0 cells whose error is `api_error_status=400`. That covers all HTTP 400s, which
  is a stricter condition than 0 effort-related 400s.

## Out of scope
- Routing any production task to a provider profile, or adding a provider profile to the committed
  `config/model-policy.yaml`. The committed policy stays provider-free and effort-free.
- Replacing the harness's `hetzner_session_env` with `config.model_policy.provider_session_env`. The
  harness keeps its stricter env allowlist.
- Passing effort through the string-only builders (`build_service_agent_options`,
  `build_mentor_options`, `build_shepherd_options`, the scout builders, `build_implementer_agent_options`).
  Those paths fail closed instead.
- Per-request effort negotiation, or discovering supported efforts from the provider's catalog.
- The usage-ledger follow-up from #791 (fake cost, cache-creation tokens).
- Changing the #791 verdict or re-running its baseline arm.

## Open questions
- Should `effort` be required on provider profiles (fail closed when it is absent), given that the CLI
  default broke one of the two Hetzner models? This proposal keeps it optional: Qwen3.6 accepts the
  default, and a required key would force a value onto profiles that do not need one. The reviewer may
  want it to be required.
- Which effort to pin for `Qwen3.8-27B`: `medium` (proven 24/24 in the exploratory run) or `xhigh` (the
  provider's default, never benched). This proposal pins `medium` because it is the one with evidence.
- The re-bench needs live Hetzner credentials (`HETZNER_INFERENCE_BASE_URL`,
  `HETZNER_INFERENCE_API_KEY`) and `--allow-live`. The implementer can land the code and offline tests,
  but the acceptance run is an operator step. Its artifacts may arrive in a follow-up commit or PR.
- The harness records only `api_error_status`, not the provider's error text. So "effort-related" is
  approximated by "any HTTP 400". If a non-effort 400 appears, the acceptance fails conservatively.
