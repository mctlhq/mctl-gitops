# Tasks: issue-815-feat-spike-add-operator-workflow-to-exec

- [ ] 1. Extend `_cmd_run` in `tools/rea_spike.py` to add `outcome` (`ok`/`failed`) and `failure_class` (`classify(sig)` when not ok, else `None`) to the record. When not ok, also add `failure` (`failure_text_record(text, store_text=False)`). Keep exit codes 0/1 and add no retry. — DoD: the record shape is documented in the module docstring, and the existing tests pass.
- [ ] 2. Add `docs/spikes/796/rea-env.sh`, which execs its arguments with these variables unset: `CLAUDE_CODE_OAUTH_TOKEN`, `GITHUB_TOKEN`, `GH_TOKEN`, `ACTIONS_RUNTIME_TOKEN`, `ACTIONS_ID_TOKEN_REQUEST_TOKEN`, `ACTIONS_ID_TOKEN_REQUEST_URL`. — DoD: the script is POSIX `sh` and covered by T3.
- [ ] 3. Read `morluto/rea` upstream at a candidate SHA. Decide the install method, the CLI entrypoint and the MCP-server entrypoint, and record them as constants in the workflow with a comment citing the upstream file they came from. — DoD: the install and the entrypoints are pinned in the workflow. If REA lacks a CLI or MCP mode, the affected arm is wired to emit `infra-failure` with reason `rea-mode-unsupported`.
- [ ] 4. (depends on 1, 2, 3) Add `.github/workflows/rea-spike-796.yml` as specified in design.md:
  - `workflow_dispatch` only, with inputs `rea_ref` (required), `model` (default `claude-opus-5-5`) and `probe_arm`;
  - `permissions: {}` at the top level and `contents: read` on the job;
  - `concurrency: rea-spike-796`, no cancel;
  - pinned action SHAs reused from `diagrams-refresh.yml` and `spike-707-bench.yml`;
  - `persist-credentials: false`;
  - inputs passed through `env:` only;
  - REA resolve, pin and metadata;
  - fixture build, digests and toolchain;
  - run metadata, including the comparison against `ISSUE_INVESTIGATOR_MODEL` from mctl-gitops;
  - the single-attempt measurement sequence;
  - report and grading template;
  - bundle guard;
  - upload with `retention-days: 14`;
  - the final infra gate.

  The header comment states that the workflow is spike-only and is deleted when #796 closes. — DoD: the YAML parses, T4–T6 pass, and no step writes to the repository or to issues.
- [ ] 5. (depends on 4) Add a short "How to run" section to `docs/spikes/796/rea-version.md`. It covers the workflow name, the inputs, where the artifact appears, and the rule that results reach `main` only through a reviewed PR. Leave all `unobserved` fields untouched. — DoD: the doc change is in the same PR.
- [ ] 6. (operator, after merge) Dispatch `rea-spike-796` once from `main` with the chosen `rea_ref`. Post the run URL and artifact name on #796. — DoD: the comment is on #796. The report update is a separate PR.

## Tests

- [ ] T1. `tests/test_rea_spike.py`: drive `_cmd_run` with `_live_stage` monkeypatched to return `{"ok": False, "declined": True, "text": "no"}`. Assert that exit = 1 and that the printed record has `outcome == "failed"` and `failure_class == "MODEL_POLICY_REFUSAL"`. Repeat with `{"ok": False, "transport_error": True}`, expecting `PROVIDER_RUNTIME_FAILURE`, and with `{"ok": False, "tool_error": True}`, expecting `REA_TOOL_FAILURE`.
- [ ] T2. `_cmd_run` with an ok stage gives exit 0, `outcome == "ok"` and `failure_class is None`. `final` and `failure` stay within `MAX_SUMMARY_BYTES` for a 10 KiB input.
- [ ] T3. `tests/test_rea_spike_workflow.py`: run `sh docs/spikes/796/rea-env.sh env` with `CLAUDE_CODE_OAUTH_TOKEN` and `GITHUB_TOKEN` set. Assert that neither appears in the output and that an unrelated var does.
- [ ] T4. Same test file, parsing `.github/workflows/rea-spike-796.yml` with `yaml.safe_load`. Note that PyYAML maps the `on` key to `True`, so read it as `wf.get("on", wf.get(True))`. Assert:
  - the triggers are exactly `{"workflow_dispatch"}`;
  - the top-level `permissions == {}`;
  - every job's permissions are a subset of `{contents: read}`;
  - `concurrency.cancel-in-progress is False`;
  - no `secrets.` reference other than `secrets.CLAUDE_CODE_OAUTH_TOKEN`;
  - every `uses:` is pinned to a 40-hex SHA;
  - every `actions/checkout` has `persist-credentials: false`;
  - upload `retention-days == 14`.
- [ ] T5. Same file: assert that the workflow invokes `tools/rea_spike.py` with `--allow-live` for `run`, `probe-stages` and `schema-bytes`. Assert that no `run:` block contains `${{ inputs.` or `${{ github.event.inputs.` (no shell interpolation of inputs) and that no step contains `git push`, `gh pr` or `gh issue`.
- [ ] T6. Same file: assert that the workflow never passes `--store-text` and contains no retry construct, such as a `for` loop over attempts or `continue-on-error` on measurement steps.

## Rollback

All changes are additive and spike-scoped:

- Revert the PR, or delete `.github/workflows/rea-spike-796.yml` and `docs/spikes/796/rea-env.sh` and revert the `_cmd_run` field addition.
- If a run misbehaves mid-flight, cancel it from the Actions UI and delete the run's artifact.
- If a credential leak is ever suspected, rotate `CLAUDE_CODE_OAUTH_TOKEN`. No data reaches `main`, gitops or the cluster, so there is no state to unwind.
