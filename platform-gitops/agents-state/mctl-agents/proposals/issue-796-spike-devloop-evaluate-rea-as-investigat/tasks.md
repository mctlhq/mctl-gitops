# Tasks: issue-796-spike-devloop-evaluate-rea-as-investigat

All commits and PRs use `Refs mctlhq/mctl-agents#796`, never `Closes`.

- [ ] 1. Pin REA. Record the upstream URL, commit SHA, release/package version, install command and the local dependencies the chosen fixtures need, in `docs/spikes/796/rea-version.md`. — DoD: the file names an exact SHA and date. Dependencies are listed only for fixtures actually used.
- [ ] 2. Write the duplicate/current-state map against #242, #597, #746 and #791, citing `orchestrator/capability_gateway.py`, `docs/benchmarks/capability-discovery.md` and `docs/spikes/746-portable-runtime.md`. Also record the #791 provider path, if found, or an explicit `not observed`. — DoD: the report section exists, and each item states "reused", "not duplicated" or "unknown".
- [ ] 3. Build the corpus under `docs/spikes/796/fixtures/`. Create `native-codec/` (C, pinned Makefile) and `packaged-app/` (APK, or a JVM jar fallback stated in the report). Add the optional `js-bundle/` only if the pinned REA has a distinct JS path. Each fixture gets `build.sh`, `oracle.yaml`, `task.md` and source. (depends on 1) — DoD: `build.sh` is deterministic and prints the artefact sha256. The oracle is written before any run. No auth, licence, DRM or anti-tamper code. No built binary is committed.
- [ ] 4. Write fixed stage prompts `docs/spikes/796/stages/{1-discovery,2-static,3-trace,4-synthesis,5-implement}.md`, all using the same investigation goal. (depends on 3) — DoD: the prompts are benign, identical across models, and contain nothing aimed at getting around a refusal.
- [ ] 5. Add the harness `tools/rea_spike.py` with `run`, `probe-stages`, `schema-bytes --server rea`, `score` and `report`. `classify`, `score` and `report` are pure functions. Live calls require `--allow-live`. REA results are truncated to 4 KiB summaries plus sha256. There is one attempt per stage and no retry. `orchestrator/` never imports it. (depends on 3, 4) — DoD: `uv run python tools/rea_spike.py --help` works offline. Without `--allow-live`, live subcommands exit non-zero.
- [ ] 6. Add the draft report `docs/spikes/796-rea-investigation-evidence.md`. It holds every section listed in design.md section 5, the metrics table and cross-model matrix with `not-run`/`unobserved` placeholders, the evidence-contract mapping onto `ContextSource`/`EvidenceRef`/`ToolCallRef`/`Provenance`/`Gap`, and the MCP-versus-CLI comparison skeleton. It also carries `STATUS: DRAFT` and no decision token. (depends on 2, 5) — DoD: the report guard passes in draft state.
- [ ] 7. Operator step (outside the implementer sandbox): run the baseline, `rea-mcp` and `rea-cli` arms on each fixture with the active Claude model, re-reading `ISSUE_INVESTIGATOR_MODEL` from the investigate CWFT. Then run `probe-stages`, then `schema-bytes --server rea`, then the missing/misconfigured-REA checks. Run alt-model rows only through an existing #791 endpoint. Commit the JSONL records and `grading.yaml` under `docs/spikes/796/results/`. (depends on 5, 6) — DoD: every matrix cell holds a value, `unobserved` or `not-run (<reason>)`. Every refusal has a stage and a class.
- [ ] 8. Finalize the report: fill the tables from `report`, decide whether the evidence contract can be reused or name the smallest extension, choose exactly one decision token against the issue's criteria, remove `STATUS: DRAFT`, and list narrowly scoped follow-up issues only for proven gaps. (depends on 7) — DoD: exactly one token is present, and every claim cites a results record.

## Tests

- [ ] T1. `tests/test_rea_spike.py`: for recorded fixture records, `classify` returns each of the six classes: an empty tool list maps to `CLIENT_TOOL_ADMISSION`, a schema error to `MCP_SCHEMA_OR_CONTEXT_FAILURE`, a REA error result to `REA_TOOL_FAILURE`, a transport error to `PROVIDER_RUNTIME_FAILURE`, a decline with no tool error to `MODEL_POLICY_REFUSAL`, and any other record to `UNKNOWN`.
- [ ] T2. `score` counts oracle hits, unsupported claims and REA-cited claims correctly from a sample `grading.yaml`, and renders missing values as `unobserved`.
- [ ] T3. `report` renders unrun models as `not-run (<reason>)`, never as zero.
- [ ] T4. The probe makes exactly one attempt per stage: a stubbed refusal at stage 2 leads to no stage 3-5 calls and no second stage-2 call.
- [ ] T5. Live subcommands without `--allow-live` exit non-zero and make no network or subprocess call.
- [ ] T6. `tests/test_spike_796_report.py`: the report carries `STATUS: DRAFT` or exactly one token from the four. No path under `orchestrator/`, `config/` or `agents/_manifests/` differs from the merge base. Files under `docs/spikes/796/` contain no ELF, `PK\x03\x04` or `dex\n` magic, and none exceeds the byte ceiling. Every `oracle.yaml` parses with non-empty facts.

## Rollback

Everything lives in new files: `docs/spikes/796*`, `tools/rea_spike.py`, and
`tests/test_rea_spike.py` and `tests/test_spike_796_report.py`. Revert the spike
PR, or delete those paths. No runtime, profile, CWFT or model-policy state
changes, so there is nothing to undo in mctl-gitops or the cluster. If the
owner's verdict is not adopted, the follow-up that records it deletes the guard
test, matching the #707 convention.
