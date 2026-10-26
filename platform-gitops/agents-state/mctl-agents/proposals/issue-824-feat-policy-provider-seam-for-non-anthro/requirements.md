# Provider seam in the model policy for non-Anthropic Messages endpoints

## Context
Spike mctlhq/mctl-agents#791 (verdict `ADOPT_EXPERIMENTAL_PROVIDER`, `docs/spikes/791-hetzner-inference.md`)
ran Claude Code CLI sessions against Hetzner's Anthropic-Messages-compatible endpoint
(`https://inference.hetzner.com/api`). It could only do so through a spike-only env transform,
`hetzner_session_env` in `tools/hetzner_inference_spike.py`. That transform sets `ANTHROPIC_BASE_URL` and
`ANTHROPIC_AUTH_TOKEN`, pins every CLI model slot (`_MODEL_SLOTS`) and blanks the Anthropic credentials
(`_BLANKED_ENV`). `config/model-policy.yaml` and its loader `config/model_policy.py` (`ModelPolicy`) can name
a model but not an endpoint or a credential. So any experimental lane would have to bypass the policy, the
plan's `model_policy_version` pin (`orchestrator/resolver.py::_model_policy_version`) and its review trail.

This proposal adds an optional, validated `provider` block to a model-policy profile. Selecting such a
profile becomes the only thing needed to route a session to the third-party endpoint. The session env is
then derived from the policy alone: base URL, the credential read from a named env var, every model slot
pinned, no fallback, and no Anthropic credential passed through. The issue states that adopting the
experimental provider depends on this seam. Adoption itself, meaning routing a real task to the provider, is
not part of this proposal.

## User stories
- AS a platform operator I WANT to declare a non-Anthropic Messages endpoint in `config/model-policy.yaml`
  SO THAT an experimental model lane is reviewed, versioned and pinned like every other model choice.
- AS a security reviewer I WANT a provider session to be unable to receive an Anthropic credential
  SO THAT subscription or API keys never reach a third party.
- AS an agent author I WANT a provider misconfiguration to fail at policy load or session build
  SO THAT a session never silently falls back to Anthropic or to another model.

## Acceptance criteria (EARS)
- WHEN a profile in the model policy declares a `provider` block with `base_url`, `credential_env`,
  `pin_model_slots: true` and `fallback: none` THE SYSTEM SHALL load it and expose it on the resolved
  `ModelSelection` as a typed `ProviderSpec`.
- WHEN a `provider` block is missing a required key, has an unknown key, has a `base_url` that is not an
  absolute `https://` URL with a host and no credentials, query or fragment, or has a `credential_env` that
  is not an upper-case env var name THE SYSTEM SHALL raise `ModelPolicyError` at load time.
- IF `credential_env` names an Anthropic credential (`ANTHROPIC_API_KEY*`, `ANTHROPIC_AUTH_TOKEN`,
  `CLAUDE_CODE_OAUTH_TOKEN*`, or any `ANTHROPIC_*` name) THEN THE SYSTEM SHALL raise `ModelPolicyError`.
- IF a provider profile sets `model_env`, or sets `fallback` to anything other than `none`, or sets
  `pin_model_slots` to anything other than `true` THEN THE SYSTEM SHALL raise `ModelPolicyError`.
- IF a task routed to a provider profile is resolved while its legacy env override holds a non-empty value
  THEN THE SYSTEM SHALL raise `ModelPolicyError` and not use the override.
- WHEN a session is built for a selection with a provider THE SYSTEM SHALL set `ANTHROPIC_BASE_URL` to the
  policy `base_url`, set `ANTHROPIC_AUTH_TOKEN` to the value of the env var named by `credential_env`, set
  every CLI model slot (`ANTHROPIC_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`,
  `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `CLAUDE_CODE_SUBAGENT_MODEL`) to the
  resolved model, set `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`, and set `fallback_model` to none, with
  no env set outside the policy other than the credential value itself.
- WHILE a session targets a provider THE SYSTEM SHALL blank every Anthropic credential
  (`ANTHROPIC_API_KEY`, `ANTHROPIC_API_KEY_SECONDARY`, `CLAUDE_CODE_OAUTH_TOKEN`,
  `CLAUDE_CODE_OAUTH_TOKEN_SECONDARY`, and any other inherited `ANTHROPIC_*` value it does not set itself),
  and blank the raw `credential_env` variable in the child env. The child env here is the **effective** env
  the CLI receives: the inherited process environment overlaid with the builder's `options.env`, because the
  SDK layers `env` over `os.environ`. A builder that passes a sparse `env` SHALL NOT let an inherited
  Anthropic credential through.
- WHILE a session targets a provider THE SYSTEM SHALL set `CLAUDE_CONFIG_DIR` to an empty per-session
  directory, so the CLI cannot read a stored Anthropic login from the worker's home and send it to the
  third-party `base_url`.
- WHEN the session env is checked for surviving Anthropic credential values THE SYSTEM SHALL ignore original
  values that are empty, so an inherited `ANTHROPIC_API_KEY=""` does not fail a session that leaks nothing.
- IF the env var named by `credential_env` is unset or empty when a provider session is built THEN THE
  SYSTEM SHALL raise and build no session. It SHALL NOT fall back to Anthropic.
- WHILE a selection carries a provider THE SYSTEM SHALL refuse it on any path that consumes only a model
  string (the `config/settings.py` module constants), so the provider cannot be dropped silently.
- WHEN no profile declares a provider THE SYSTEM SHALL produce session options identical to today's.
- WHEN a plan is resolved THE SYSTEM SHALL compute `model_policy_version` from the policy file that was
  actually loaded (`MODEL_POLICY_PATH` when set, else the committed default), so the pin always covers the
  file that supplied the provider endpoint. With `MODEL_POLICY_PATH` unset the value is unchanged.
- WHEN a plan carrying a provider is logged THE SYSTEM SHALL include the provider `name` and `base_url` in
  `ExecutionPlan.to_log_dict()`.
- IF a module-level selection in `config/settings.py` resolves to a provider profile THEN THE SYSTEM SHALL
  fail at import, which stops the whole worker process rather than one task. This is intended fail-closed
  behaviour and SHALL be documented as such.
- WHEN the offline test suite runs THE SYSTEM SHALL include a test that builds a provider session from a
  fixture policy targeting `https://inference.hetzner.com/api`, with an environment seeded with every
  Anthropic credential, and asserts that no Anthropic credential value appears anywhere in the resulting
  session env. The test makes no network call.

## Out of scope
- Routing any production task in `config/model-policy.yaml` to a provider profile (the adoption decision).
- Per-provider/model reasoning effort (spike follow-up 2) and usage-ledger cost/token correction for
  third-party models (spike follow-up 3).
- Providers that do not speak the Anthropic Messages API (OpenAI-compatible endpoints need a proxy and are
  not covered).
- Changing the GitHub/mctl/evidence/usage token handling of production sessions beyond what `_scrubbed`
  already does. The spike's stricter env allowlist was for isolating bench runs and is not adopted.
- Provisioning the Hetzner credential in Vault/ExternalSecrets or the Argo workflow templates (mctl-gitops).
- Removing or refactoring `tools/hetzner_inference_spike.py`.

## Decisions (owner review, 2026-10-27)
- A non-`https` `base_url` is rejected, including loopback. Tests use an `https://` URL and make no network
  call.
- The Hetzner profile lives only in a test fixture until adoption. The committed policy and the
  `model_policy_version` of existing plans do not change.
- `GITHUB_TOKEN`/`GH_TOKEN` stay as they are in this change, because no task is routed to a provider. Before
  any task is routed to a provider profile (adoption), the provider session must either blank them or get a
  read-only token. This is a precondition of adoption, not part of this change.

## Open questions
- Which string-only call sites (e.g. `SERVICE_AGENT_MODEL` in `run_service_agent.py`, `run_implementer.py`)
  should later learn to carry a provider? For now they fail closed when routed to one.
