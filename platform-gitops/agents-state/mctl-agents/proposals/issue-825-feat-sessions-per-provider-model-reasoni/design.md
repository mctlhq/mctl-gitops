# Design: issue-825-feat-sessions-per-provider-model-reasoni

## Current state
- `config/model-policy.yaml`: two Anthropic profiles (`cheap`, `balanced`), each with `model` and
  `model_env`, plus a `tasks` map. There is no effort key.
- `config/model_policy.py`:
  - `ModelPolicy._validate` checks `model` and `model_env` and, when a profile has a `provider:` block,
    calls `_validate_provider`. That validator has a closed key set (`_PROVIDER_KEYS`), requires https,
    `pin_model_slots: true` and `fallback: none`, and returns `ProviderSpec`.
  - `ModelPolicy.resolve()` returns a `ModelSelection(task, profile, model, source, provider)`.
  - `provider_session_env()` derives the provider session env and blanks Anthropic credentials.
  - Nothing reads or validates an effort.
- `orchestrator/resolver.py`: `ExecutionPlan` has `provider: ProviderSpec | None = None`, filled from
  `model_selection.provider` (around line 1152). `to_log_dict()` logs provider name and base_url.
- `orchestrator/options.py`:
  - Every builder wraps its `ClaudeAgentOptions(...)` in `_scrubbed(options, *, provider=None)`. This is
    enforced by `tests/test_usage_ledger.py`.
  - `_scrubbed` blanks writer, evidence and mctl tokens. For a provider session it refuses
    `fallback_model`, applies `provider_session_env` and uses a temporary `CLAUDE_CONFIG_DIR`.
  - Only `build_issue_investigator_options_from_plan` passes `provider=plan.provider`. No builder ever
    sets `effort`.
- `config/settings.py` (around lines 198-215): the string-only `*_SELECTION` constants (service agent,
  mentor, shepherd, scout) fail closed at import if a selection has a provider ("string-only model paths
  cannot carry" it).
- SDK `claude-agent-sdk==0.2.168` (`pyproject.toml`):
  - `ClaudeAgentOptions.effort: EffortLevel | None`, where
    `EffortLevel = Literal["low", "medium", "high", "xhigh", "max"]`.
  - `_internal/transport/subprocess_cli.py` adds `--effort <value>` only when it is not None. Today's
    `None` therefore means "CLI default", which is `high`.
- `tools/hetzner_inference_spike.py`:
  - `cell_options()` builds cells from the real builders: `build_issue_investigator_options` /
    `build_implementer_agent_options`.
  - `make_sdk_runner(..., effort=None)` sets `options.effort` on candidate cells from the CLI flag
    `bench --effort {low,medium,high,xhigh,max}`.
  - `run_bench` records `effort` per record and `candidate_effort` in the manifest.
  - `_cmd_bench` refuses `--effort` into `docs/spikes/791/` and with any arm except `candidate`.
    `_refuse_exploratory` keeps any non-`cli-default` run out of the pre-registered `decide()`.
  - Candidate env comes from `hetzner_session_env` (allowlist env plus ANTHROPIC_* overrides), with base
    URL and key from `HETZNER_INFERENCE_BASE_URL` / `HETZNER_INFERENCE_API_KEY` (`_live_env`).
  - Errors are recorded as `error: "api_error_status=<n>"`.
- `docs/spikes/791-hetzner-inference.md`, "Follow-up issue bodies" item 2, is the origin of this issue.
  `docs/spikes/791/exploratory-qwen38-effort-medium/` holds the `--effort medium` run: 0 provider errors.
- Tests: `tests/test_model_policy.py`, `tests/test_model_policy_provider.py` (with fixture
  `tests/fixtures/model-policy-provider.yaml`, profile `experimental_hetzner` on Qwen3.6),
  `tests/test_options.py`, `tests/test_resolver.py`, `tests/test_hetzner_inference_spike.py`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/` lists `mctl-agents-worker`, `mctl-agents-worker-exec` and
  `mctl-agents-worker-implement` (tenant `admins`).
- A grep for `model-policy`, `MODEL_POLICY` and `HETZNER` over `$MCTL_GITOPS_ROOT/services` and
  `$MCTL_GITOPS_ROOT/tenants` found nothing. No deployed worker overrides the policy path or carries a
  Hetzner credential, so deployed workers load the committed `config/model-policy.yaml`, which has no
  provider and, after this change, no effort.
- mctl MCP tools were not called. Deployed config came only from the gitops checkout, and that was
  enough for this change: the committed default stays unchanged.

## Proposed solution

### 1. Model policy: optional `effort` per profile (`config/model_policy.py`)
- Add `EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")`. Pin it with a test that asserts
  equality with `typing.get_args(claude_agent_sdk.types.EffortLevel)`, so an SDK bump that changes the set
  fails CI instead of drifting.
- In `ModelPolicy._validate`, the optional profile key `effort` must be a string in `EFFORT_LEVELS`.
  Otherwise raise `ModelPolicyError(f"profile {name!r} effort must be one of ...")`.
- The key sits at profile level, not inside `provider:`. A profile already names exactly one model and at
  most one provider, so a profile-level effort is per provider/model. It also works for an Anthropic
  profile, and `_PROVIDER_KEYS` stays closed.
- `ModelSelection` gains `effort: str | None = None`, set from the profile in `resolve()`. `log()`
  appends ` effort=<v>` when it is set.
- The env overrides (`model_env`, legacy env) change only the model, never the effort. Effort is
  policy-file-only. That avoids a model and effort mismatch hidden in env vars, and it is visible in
  `MODEL_POLICY_PATH`-selected files.

### 2. Plan and builder (`orchestrator/resolver.py`, `orchestrator/options.py`)
- `ExecutionPlan.effort: str | None = None` is set from `model_selection.effort`. `to_log_dict()` adds
  `"effort": self.effort`, an additive key.
- `_scrubbed(options, *, provider=None, effort=None)`: when `effort` is not None, set `options.effort`.
  If `options.effort` is already set to a different value, raise `ValueError`. With the default
  `effort=None` it is a no-op, so every existing builder output is unchanged.
- `build_issue_investigator_options_from_plan` passes `effort=plan.effort` on both branches.
- `config/settings.py`: extend the existing fail-closed loop so that a string-only selection with an
  effort also raises `ModelPolicyError`. A string cannot carry the effort, and silently dropping it would
  reproduce the #791 failure.

### 3. Harness: policy-sourced effort (`tools/hetzner_inference_spike.py`)
- New `bench` options `--model-policy PATH` and `--policy-task TASK`, which must be given together and
  are mutually exclusive with `--effort`. They are valid only with `--arm candidate`. The policy is loaded
  with `ModelPolicy.load(Path(args.model_policy)).resolve(task, log=False)`.
- Refuse with `SpikeError` before any live call when any of these holds:
  - `selection.provider is None`;
  - `selection.provider.name != "hetzner"`;
  - `selection.provider.base_url` differs from `HETZNER_INFERENCE_BASE_URL` after stripping trailing `/`;
  - `selection.model` is not AVAILABLE in the snapshot (via `bench_models`). This rule also rejects
    `--models` lists that disagree with the policy.
- `make_sdk_runner` / `run_bench` take `effort` and `effort_source` (`"flag" | "policy"`).
  - Candidate records get `effort` and `effort_source`; the manifest gets `candidate_effort`,
    `candidate_effort_source`, `model_policy_path` and the policy file's sha256.
  - With `effort_source == "policy"`, the harness sets the effort by calling
    `orchestrator.options._scrubbed(built, effort=...)`, the production seam, instead of assigning
    `options.effort` directly. The bench therefore exercises the code under test.
- The existing guards stay: no non-default effort into `SPIKE_DIR`, and `_refuse_exploratory` for
  `decide()`. `report --exploratory DIR` renders the run and prints the effort source.
- Add a helper `count_http_400(records)` and print it in the exploratory report, as the acceptance metric.

### 4. Re-bench artifacts (`docs/spikes/825/`)
- Committed bench policy `docs/spikes/825/model-policy-qwen38.yaml`:
  - version 1;
  - the `cheap` and `balanced` profiles copied from the committed policy;
  - a profile `experimental_hetzner_qwen38` with `model: Qwen/Qwen3.8-27B`, `effort: medium` and the same
    `provider:` block as the test fixture;
  - task `bench_candidate: experimental_hetzner_qwen38`.
- Run command, documented in `docs/spikes/825-qwen38-effort-rebench.md`:
  - `snapshot --allow-live --out docs/spikes/825/snapshot.json`
  - `bench --allow-live --arm candidate --out-dir docs/spikes/825 --snapshot docs/spikes/825/snapshot.json`
    `--model-policy docs/spikes/825/model-policy-qwen38.yaml --policy-task bench_candidate`
- Records and manifest are committed. The doc reports the HTTP-400 count, which the acceptance requires
  to be 0, and links #791/#822.

## Alternatives
- **Effort inside the `provider:` block.** Rejected: it ties effort to third-party endpoints only, though
  Anthropic models also accept an effort. It would also widen `_PROVIDER_KEYS`, which is deliberately
  closed and security-reviewed.
- **Per-model map in the policy (`efforts: {model_id: level}`).** Rejected: profiles already bind exactly
  one model. A second map keyed by model id would duplicate that and could disagree with a
  `model_env`-overridden model.
- **Env var override (`<PROFILE>_EFFORT`) or keeping the harness `--effort` flag as the mechanism.**
  Rejected: the issue's acceptance in #791 explicitly requires "no harness-only override". An env-only
  knob would also be invisible in the policy file and its version hash.
- **Threading effort through every string-only builder signature.** Deferred: it touches the service
  agent, mentor, shepherd, scout and implementer call sites for no current need. Fail-closed at import
  covers the risk.

## Platform impact
- **Migrations:** none. The policy schema stays `version: 1`, and `effort` is optional and additive.
- **Backward compatibility:** the committed policy declares no effort, so every builder resolves
  `effort=None` and the CLI command line is unchanged. A test asserts identical options for the existing
  equivalence cases in `tests/test_options.py`. `ExecutionPlan.to_log_dict()` gains one key; log
  consumers that parse strictly should be checked, but the existing `provider` key was added the same way.
- **Resource impact:** none in production. The re-bench is one candidate arm: 4 tasks x 2 reps x 1
  model, on Hetzner credits and run by an operator.
- **Risks and mitigations:**
  - SDK `EffortLevel` drift: mitigated by the `EFFORT_LEVELS` pin test.
  - A provider later rejecting `medium`: the bench measures it, and the policy can change without code.
  - A string-only task routed to an effort profile: fails at import, which is loud and has no silent
    downgrade. Deployed workers are unaffected because no deployed config changes the policy path
    (see Deployed state).
  - The harness importing private `_scrubbed`: it already imports `orchestrator.options` builders. If
    reviewers object, expose a public `apply_policy_effort(options, effort)` that `_scrubbed` calls.

## Open questions
- Whether `effort` should be required on provider profiles. This design keeps it optional; see
  requirements.md.
- `medium` versus `xhigh` for Qwen3.8-27B. This design pins `medium`, the value with evidence.
- The live re-bench is an operator step that needs Hetzner credentials. The code PR can land first and
  the artifacts can follow.
- MCP tools were not used to inspect running workers. The gitops checkout was the only deployed-state
  source.
