# Tasks: issue-791-spike-models-benchmark-hetzner-experimen

- [ ] 1. Scaffold `tools/hetzner_inference_spike.py` with `snapshot`, `bench` and `report`
  subcommands.
  - It needs the `--allow-live` gate, and it reads `HETZNER_INFERENCE_BASE_URL` /
    `HETZNER_INFERENCE_API_KEY` from env only.
  - It writes to the repo only after the `orchestrator.redaction.contains_credential` screen
    passes.
  - Add the `--record-raw DIR` guard that refuses paths inside a repository, copied from
    `tools/semantic_decision_spike.py`.
  - DoD: without `--allow-live` the tool makes no network call. It runs offline against a fake
    httpx transport.
- [ ] 2. Implement `snapshot` (depends on 1).
  - Call `GET /v1/models` and match the 4 owner-selected IDs exactly, marking each `AVAILABLE`
    or `UNAVAILABLE_AT_RUN_TIME`.
  - For each available model send a trivial completion and a function-call round-trip.
  - Probe `POST /v1/messages`.
  - Capture rate-limit headers, finish reasons and errors.
  - DoD: `docs/spikes/791/snapshot.json` is produced with a UTC timestamp and the endpoint,
    with no credential in it. There is no substitution logic.
- [ ] 3. Add `hetzner_session_env(env, *, base_url, token, model)` in the spike module
  (depends on 1).
  - It applies after `orchestrator.options._scrubbed`.
  - It sets `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` and pins every CLI model slot to
    `model`.
  - It blanks `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY` and both `_SECONDARY` vars.
  - DoD: unit-tested, and no Anthropic credential survives.
- [ ] 4. Write the loopback shim `docs/spikes/791/shim.py`: Anthropic Messages to OpenAI Chat
  Completions, including tool_use/tool_result and SSE, bound to 127.0.0.1 and guarded by a
  per-run token (depends on 2).
  - Unsupported blocks raise a recorded `shim_unsupported`.
  - It is used only if the Messages probe in task 2 failed.
  - DoD: offline round-trip tests pass for text, tool_use, tool_result and stream framing.
- [ ] 5. Create the fixtures under `docs/spikes/791/fixtures/{investigation,implementation,review,tool-use}/`
  (depends on 1).
  - Each has a `fixture.yaml` giving id, sha256, oracle and limits.
  - Include the long-context investigation variant, at about 60k tokens, recorded.
  - Include 4 seeded review findings plus 2 decoys.
  - Include the tool-use task with a scripted tool error and a disallowed-tool temptation.
  - DoD: every fixture is public or synthetic, its oracle is deterministic, and its hash is
    recorded.
- [ ] 6. Implement `bench` (depends on 3, 4, 5).
  - Capture the baseline at start: `config/model_policy.resolve_model` for each workload's
    task, `model_policy_version`, AgentDefinition/ExecutionProfile versions from
    `agents/_manifests/`, prompt hash, tool catalogue, `max_turns` and budget.
  - Build each session with the real `orchestrator/options.py` builders, pointed at a temp
    fixture copy.
  - Run 3 repetitions per `(task, model)` for the baseline and for each available model.
  - Write one JSONL record per cell with every field listed in design section 5.
  - Assert that the observed `usage.model` equals the model under test.
  - Record provider failures and never retry them on another model.
  - DoD: a dry run with a fake SDK transport produces a complete `run-manifest.json` and
    records.
- [ ] 7. Run the live benchmark once the owner has provisioned the key in Vault (depends on 2
  and 6).
  - Run location: a one-off pod in the `admins` namespace, or a recorded workstation run.
  - Order: snapshot at start, then bench, then snapshot at end.
  - DoD: snapshot, records and manifest are committed under `docs/spikes/791/`, credential
    screen passed, and achieved repetition counts recorded.
- [ ] 8. Implement `report` and write `docs/spikes/791-hetzner-inference.md` (depends on 7).
  - Contents: environment, snapshot, compatibility note, matrix, model-specific checklist,
    reliability, plausible roles, exactly one decision token chosen by the pre-registered rule
    in design.md, and follow-up issue bodies only for gaps the run proved.
  - DoD: the report renders from the committed records, and the PR description uses
    `Refs #791`.

## Tests

- [ ] T1. Snapshot classification: given a fake catalog that is missing one selected ID, that
  model is `UNAVAILABLE_AT_RUN_TIME` and no other ID is substituted.
- [ ] T2. `hetzner_session_env`: given an env holding all four Anthropic credential vars plus
  the mctl/usage/evidence tokens, the output has them all blank. The base URL, auth token and
  every model slot are set to the inputs.
- [ ] T3. Policy invariant: a candidate session's options come from the same builder as the
  baseline, with identical `allowed_tools` and hooks. A scripted `tool_use` for
  `mcp__mctl__mctl_deploy_service` is denied by `_policy_hooks` and counted in
  `policy_denials`.
- [ ] T4. Shim codec: Messages requests and responses with text, tool_use, tool_result and SSE
  framing round-trip. An unknown block produces `shim_unsupported`. The server refuses
  non-loopback binds and missing or wrong tokens.
- [ ] T5. Artifact safety: a record containing a credential-shaped value is refused by the
  writer, and `--record-raw` inside a repository is refused.
- [ ] T6. No silent fallback: a fake response whose `model` differs from the model under test
  marks the cell `model_mismatch` and failed.
- [ ] T7. Import direction: no module under `orchestrator/` imports
  `tools/hetzner_inference_spike` or `docs/spikes/791` (same as the 556 test).
- [ ] T8. Oracles: each fixture's oracle scores a known-good and a known-bad canned answer
  correctly.

## Rollback

The spike adds only `tools/hetzner_inference_spike.py`, `docs/spikes/791/**`,
`docs/spikes/791-hetzner-inference.md` and offline tests. Nothing in production imports or
deploys them, so rollback is a revert of the spike PR.

If a live run misbehaves, stop the pod or process, revoke the Hetzner test key in Vault, and
delete any out-of-repo `--record-raw` directory. No model-policy, manifest or gitops state was
changed, so nothing else needs restoring.
