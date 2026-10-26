# Design: issue-824-feat-policy-provider-seam-for-non-anthro

## Current state
- `config/model-policy.yaml` (version 1) defines `profiles` (`cheap`, `balanced`), each with `model` and an
  optional `model_env`, plus a `tasks` -> profile map (`service_agent`, `mentor_digest`,
  `review_findings_normalize`, `scout_relevance`, `scout_scoring`).
- `config/model_policy.py`: `ModelPolicy.__init__` checks `version == 1`, that profiles and tasks are
  non-empty, and in `_validate()` that each profile has a non-empty `model` and a string `model_env`, and
  that every task names a known profile. Unknown profile keys are not rejected. `resolve()` returns a frozen
  `ModelSelection(task, profile, model, source)`. Precedence is the legacy env override, then `model_env`,
  then the YAML default. The policy can express a model name and nothing about an endpoint or credential.
- Consumers:
  - `config/settings.py` resolves five tasks at import time and exports plain model strings
    (`SERVICE_AGENT_MODEL`, `MENTOR_MODEL`, `SHEPHERD_MODEL`, ...).
  - These strings are passed to `orchestrator/options.py` builders (`build_service_agent_options(service_dir,
    model)`, `build_implementer_agent_options`, `build_mentor_options`, `build_shepherd_options`, ...).
  - `orchestrator/resolver.py::execute()` calls `resolve_model(profile.model_policy_task, ...)` and puts
    `model_selection.model` into the immutable `ExecutionPlan`, together with `model_policy_version`. That
    value is `v<version>+<content hash>` of `DEFAULT_POLICY_PATH`, from `_model_policy_version()`.
  - `build_issue_investigator_options_from_plan(plan, ...)` consumes `plan.model`.
- `orchestrator/options.py::_scrubbed(options)` is the mandatory wrapper for every `ClaudeAgentOptions` in
  that module. `tests/test_usage_ledger.py` enforces that every `ClaudeAgentOptions(...)` there is its
  direct argument. It blanks the usage-writer, evidence and `MCTL_TOKEN` tokens in `options.env` (or in
  `os.environ` when no env was passed). It does nothing about endpoints or Anthropic credentials.
- The spike transform `tools/hetzner_inference_spike.py::hetzner_session_env` is the only way in today. It
  keeps an allowlist (`_CANDIDATE_ENV_ALLOW`), blanks `_BLANKED_ENV` (Anthropic OAuth/API keys and GitHub
  tokens), sets `_ISOLATION_ENV` (including `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`), pins
  `_MODEL_SLOTS` to the model, and sets `ANTHROPIC_BASE_URL`/`ANTHROPIC_AUTH_TOKEN`. It is covered by
  `tests/test_hetzner_inference_spike.py::test_hetzner_session_env_blanks_every_credential`.
- The spike record `docs/spikes/791-hetzner-inference.md` gives the endpoint `https://inference.hetzner.com/api`
  and says to use `ANTHROPIC_AUTH_TOKEN` (Bearer), not `ANTHROPIC_API_KEY`. The spike harness reads
  the key from `HETZNER_INFERENCE_API_KEY`.
- `orchestrator/validate_manifest.py` (`_check_model_policy_task`, `_check_catalog_model_policy_task`) reads
  only the `tasks` keys of the policy, so it is unaffected by new profile keys.

Deployed state checked:
- `$MCTL_GITOPS_ROOT` (`/workdir/mctl-gitops/platform-gitops`), grep of `argo-workflows/` and
  `agent-platform/` for `MODEL_POLICY_PATH`, `HETZNER` and `ANTHROPIC_BASE_URL`: only comments about Hetzner
  Cloud volumes matched. No deployed workflow sets a provider endpoint, an alternate policy path or a
  Hetzner inference credential.
- `services/` and `tenants/` grep for `ANTHROPIC_BASE_URL`/`hetzner`: the only hits were in
  `services/labs/mctl-telegram{,-preview}/values.yaml`, and they concern the kube-hetzner cluster, not
  inference. No service is configured with a provider today.
- mctl MCP tools were not called. The change is internal to the mctl-agents code and its offline tests, and
  no deployed config was needed to ground it beyond the gitops grep above.

## Proposed solution
### 1. Schema (`config/model-policy.yaml`, still `version: 1`)
A profile may add an optional `provider` mapping:
```yaml
profiles:
  experimental_hetzner:
    model: Qwen/Qwen3.6-35B-A3B-FP8
    provider:
      name: hetzner                      # label for logs/plan; [a-z0-9-]+
      api: anthropic-messages            # only accepted value
      base_url: https://inference.hetzner.com/api
      credential_env: HETZNER_INFERENCE_API_KEY
      pin_model_slots: true              # must be true
      fallback: none                     # must be none
```
The key stays optional, so existing documents remain valid and `version` stays 1. This change does NOT add
the profile to the committed policy. It lives in a test fixture, `tests/fixtures/model-policy-provider.yaml`.
The committed file, and therefore every existing plan's `model_policy_version`, is byte-for-byte unchanged.

### 2. Validation (`config/model_policy.py`)
- New frozen dataclass `ProviderSpec(name, api, base_url, credential_env)`. `ModelSelection` gains
  `provider: ProviderSpec | None = None`, and `log()` appends `provider=<name>` when it is set.
- `_validate()` gains `_validate_provider(profile_name, block)`. It rejects unknown keys, a missing `name`,
  `api` or `base_url`, `api != "anthropic-messages"`, and a `base_url` that `urllib.parse.urlsplit` does not
  parse to `scheme == "https"` with a host and no userinfo, query or fragment. It rejects a `credential_env`
  not matching `^[A-Z][A-Z0-9_]*$` or matching an Anthropic credential name (`ANTHROPIC_*`,
  `CLAUDE_CODE_OAUTH_TOKEN*`). It rejects `pin_model_slots is not True`, `fallback != "none"`, and
  `model_env` on the same profile. Every rejection is a `ModelPolicyError` naming the profile. Each provider
  profile is validated once, at load time.
- `resolve()`: for a provider profile, a non-empty `legacy_model_env` value raises `ModelPolicyError`
  instead of overriding the model, so env outside the policy cannot change what goes to the third party.
  Without a provider, precedence is unchanged.

### 3. Session env (new pure function, `config/model_policy.py`)
`provider_session_env(provider, model, env) -> dict[str, str]`:
- Copies `env`, blanks every key starting with `ANTHROPIC_` plus `CLAUDE_CODE_OAUTH_TOKEN`,
  `CLAUDE_CODE_OAUTH_TOKEN_SECONDARY` and `ANTHROPIC_API_KEY_SECONDARY`, and blanks `provider.credential_env`.
- Sets `ANTHROPIC_BASE_URL = provider.base_url`, `ANTHROPIC_AUTH_TOKEN = env[provider.credential_env]`,
  every name in a module constant `MODEL_SLOTS` (the same six names as the spike's `_MODEL_SLOTS`) to
  `model`, and `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`.
- Raises `ModelPolicyError` if the credential is unset or empty. It does not fall back.
- Afterwards it asserts that no value in the result equals any original Anthropic credential value. This is
  a belt-and-braces check that also catches a credential copied under another name, such as an
  `ANTHROPIC_AUTH_TOKEN` equal to an OAuth token.
It is pure and has no I/O, so it is testable offline. Keeping it beside the policy keeps one owner for the
provider contract.

### 4. Wiring
- `orchestrator/options.py::_scrubbed(options, *, provider: ProviderSpec | None = None)`. After the existing
  scrubbing, when `provider` is set, it applies `provider_session_env(provider, options.model, options.env)`,
  asserts `options.fallback_model is None`, and refuses an empty `options.model`. With `provider=None` its
  behaviour is unchanged, so every existing builder produces identical options.
- `orchestrator/resolver.py`: `ExecutionPlan` gains `provider: ProviderSpec | None` (default None), filled
  from `model_selection.provider`. `build_issue_investigator_options_from_plan` passes
  `provider=plan.provider` to both of its `_scrubbed` calls. This is the one path where a provider can reach
  a session in this change, and it is the declarative path every new lane is meant to take.
- `config/settings.py`: after resolving the module-level selections, it raises `ModelPolicyError` if any of
  them carries a provider. The `*_MODEL` string constants cannot carry the endpoint, so routing those tasks
  to a provider profile must fail at import instead of sending a Qwen model name to Anthropic or bypassing
  the seam.

### 5. Spike harness
`tools/hetzner_inference_spike.py` is left as is. The task list includes an optional follow-up that
expresses `hetzner_session_env`'s provider part through `provider_session_env`, keeping the spike's stricter
allowlist on top. It is not required for the acceptance criteria.

## Alternatives
- Keep a per-run env transform (status quo / generalize `hetzner_session_env`). Dropped: the env would live
  outside the policy, outside `model_policy_version` and outside review, which is exactly the gap the
  issue names.
- A top-level `providers:` map referenced by name from profiles. It would be cleaner with several profiles
  per endpoint, but there is one endpoint today and the issue asks for a per-profile block. It can be
  introduced later without breaking the per-profile form.
- Put the endpoint and credential on the v1alpha2 `ExecutionProfile` (resolver catalog) instead of the
  model policy. Dropped: the model choice lives in the model policy (`modelPolicyRef.task`), and splitting
  endpoint from model would allow pairing a Qwen model with the Anthropic endpoint or the reverse.
  `ModelPolicy` is also the validator the issue names.
- Bump the policy to `version: 2`. Not needed: the block is optional, and the existing `version == 1` check
  plus the content hash in `model_policy_version` already change the pin when a provider is added.

## Platform impact
- Migrations: none. The committed policy is unchanged, so no deployed workflow, plan pin or gitops file
  changes.
- Backward compatibility: profiles without `provider` behave identically. `_scrubbed(options)` without a
  provider is unchanged. `ExecutionPlan.provider` defaults to None. Unknown keys inside `provider` are
  rejected, but unknown profile-level keys elsewhere are still tolerated as today.
- Security: this is the main risk. A bug in the transform could leak an Anthropic key to a third party.
  Mitigations: blank every key by prefix rather than by list, run the value-equality assertion at build
  time, run the offline leak test with every credential seeded, refuse an Anthropic-named `credential_env`
  at validation, require `https`, allow no fallback, and fail closed on string-only paths. The third-party
  model still sees whatever non-Anthropic env the builder passes, such as `GITHUB_TOKEN` (see the open
  question in requirements.md). Adoption must decide on that before routing a real task.
- Resource and cost: none in this change. Provider sessions would not be billed by Anthropic, and the
  ledger's handling of that is spike follow-up 3.
- Ops: adoption will need `HETZNER_INFERENCE_API_KEY` injected into the relevant workflow pod via mctl-gitops.
  That is tracked separately.

## Open questions
- Whether provider sessions should also blank GitHub tokens (see requirements.md).
- Whether loopback `http://` should be allowed for local proxies.
- Whether to commit an unrouted `experimental_hetzner` profile now or only at adoption. Committing it would
  change `model_policy_version` for every plan, which is why this design does not commit it.
