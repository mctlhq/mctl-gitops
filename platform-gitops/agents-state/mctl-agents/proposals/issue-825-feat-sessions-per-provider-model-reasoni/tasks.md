# Tasks: issue-825-feat-sessions-per-provider-model-reasoni

- [ ] 1. Add `EFFORT_LEVELS` and optional profile `effort` validation to `config/model_policy.py`
  (`ModelPolicy._validate`), add `ModelSelection.effort`, set it in `resolve()`, and add it to `log()`.
  — DoD: the committed policy still loads; a profile with `effort: medium` resolves to
  `selection.effort == "medium"`; invalid values raise `ModelPolicyError` naming the profile.
- [ ] 2. (depends on 1) Fail closed in `config/settings.py` when a string-only `*_SELECTION` has an
  effort, by extending the existing provider loop. — DoD: reloading settings with such a policy raises
  `ModelPolicyError`; with the committed policy it imports unchanged.
- [ ] 3. (depends on 1) Add `ExecutionPlan.effort` in `orchestrator/resolver.py`, set from
  `model_selection.effort`, and add `effort` to `to_log_dict()`. — DoD: a plan resolved from an effort
  profile carries and logs it; plans from the committed policy have `effort=None`.
- [ ] 4. (depends on 3) Add the `effort` keyword to `_scrubbed` in `orchestrator/options.py`, with the
  conflict check, and pass `effort=plan.effort` on both branches of
  `build_issue_investigator_options_from_plan`. — DoD: options carry the plan's effort; all existing
  `tests/test_options.py` equivalence tests pass unchanged.
- [ ] 5. (depends on 4) Add `bench --model-policy/--policy-task` to `tools/hetzner_inference_spike.py`:
  - pre-flight refusals (no provider, provider name or base_url mismatch, model not AVAILABLE, combined
    with `--effort`, arm other than `candidate`);
  - effort applied through `_scrubbed(..., effort=...)`;
  - `effort_source` recorded in records and manifest, plus policy path and sha256;
  - `count_http_400` printed in the exploratory report.
  — DoD: offline tests with a fake runner cover each refusal and the recorded fields; `--effort`
  behaviour is unchanged.
- [ ] 6. (depends on 5) Commit `docs/spikes/825/model-policy-qwen38.yaml` (Qwen/Qwen3.8-27B,
  `effort: medium`, hetzner provider, task `bench_candidate`) and
  `docs/spikes/825-qwen38-effort-rebench.md` with the exact snapshot and bench commands. — DoD: the bench
  policy loads with `ModelPolicy.load`, and a test asserts it resolves to provider `hetzner` with effort
  `medium`.
- [ ] 7. (depends on 6; operator, live credentials) Run the snapshot and the candidate bench from the
  bench policy into `docs/spikes/825/`, commit `snapshot.json`, `records-candidate.jsonl` and
  `run-manifest-candidate.json`, and fill in the result section of the doc. — DoD: every candidate
  record has `effort: medium` and `effort_source: policy`, and the HTTP-400 count is 0.

## Tests
- [ ] T1. `tests/test_model_policy.py`: `EFFORT_LEVELS == typing.get_args(claude_agent_sdk.types.EffortLevel)`.
- [ ] T2. `tests/test_model_policy.py`: a valid effort resolves; the values `"HIGH"`, `"none"`, `3`, `""`
  are each rejected; a profile without effort resolves `effort is None`; `model_env` and legacy env
  overrides do not change the effort.
- [ ] T3. `tests/test_model_policy_provider.py`: the fixture provider profile with an added
  `effort: medium` yields `selection.effort == "medium"`, and the committed policy has no effort on any
  task.
- [ ] T4. `tests/test_model_policy_provider.py`: the settings import fails closed for a string-only task
  routed to an effort profile.
- [ ] T5. `tests/test_resolver.py`: the plan carries `effort`, and `to_log_dict()["effort"]` matches.
- [ ] T6. `tests/test_options.py`: `build_issue_investigator_options_from_plan` sets `options.effort` on
  both the gateway and non-gateway branches; a plan without effort gives `options.effort is None`;
  `_scrubbed` raises on a conflicting pre-set effort.
- [ ] T7. `tests/test_hetzner_inference_spike.py` (offline, fake runner):
  - the `--model-policy` refusals: no provider, base_url mismatch, model not AVAILABLE, `--effort`
    combined, wrong arm, out-dir equal to `SPIKE_DIR`;
  - the records and manifest carry `effort_source: policy`;
  - `_refuse_exploratory` still rejects policy-effort runs;
  - `count_http_400` counts `api_error_status=400` cells.
- [ ] T8. `tests/test_hetzner_inference_spike.py`: the committed `docs/spikes/825/model-policy-qwen38.yaml`
  loads and resolves to `Qwen/Qwen3.8-27B` / `medium` / `hetzner`.

## Rollback
- Code: revert the PR. Effort is optional and absent from the committed policy, so production behaviour
  is identical before and after the revert.
- If an effort profile misbehaves after it is adopted later: remove the `effort` key from that profile in
  the policy file. Sessions return to the CLI default without a code change.
- Bench artifacts under `docs/spikes/825/` are documentation only. Delete them or leave them; nothing
  consumes them at runtime.
