# Operator-only workflow to execute the REA live benchmark for spike #796

## Context

Spike #796 asks whether REA (`morluto/rea`) improves DevLoop investigations of
source-owned binaries, and whether current Claude models complete such
workflows. PR #802 merged the fixtures (`docs/spikes/796/fixtures/native-codec`,
`docs/spikes/796/fixtures/packaged-app`), the oracles, the stage prompts
(`docs/spikes/796/stages/`) and the harness `tools/rea_spike.py`. The report
`docs/spikes/796-rea-investigation-evidence.md` and `docs/spikes/796/rea-version.md`
stay `STATUS: DRAFT` because nobody has run a live measurement yet. The harness
refuses to call models or REA unless `--allow-live` is passed, and no execution
surface exists that passes it with the repository's Claude credential.

Issue #815 asks for one narrow, manually triggered GitHub Actions workflow. It
runs the merged harness once against the two fixtures, pins and records the
exact REA, model and toolchain identity, and uploads a bounded artifact bundle
with enough evidence to fill the #796 report without a rerun. A model refusal
must stay a measurement. A setup, tool or runtime failure must never be read as
an REA or model result. The workflow writes nothing to `main`. The verdict goes
in through a separate reviewed change.

## User stories

- AS the #796 spike owner I WANT a manual workflow that runs `tools/rea_spike.py` live on the source-owned fixtures SO THAT the report can get real baseline, REA MCP, REA CLI, schema-footprint and stage-probe measurements.
- AS a reviewer of the verdict I WANT the exact REA commit SHA, install method, model id, SDK/CLI versions, toolchain versions and fixture digests in the artifact SO THAT the run can be reproduced and audited.
- AS a platform security owner I WANT the workflow to be read-only and to keep credentials and unbounded REA output out of every artifact SO THAT a spike cannot leak secrets or become a hidden production capability.

## Acceptance criteria (EARS)

- WHEN an operator dispatches `.github/workflows/rea-spike-796.yml` THE SYSTEM SHALL run the benchmark. The workflow SHALL declare `workflow_dispatch` as its only trigger: no `schedule`, `push`, `pull_request`, `issue_comment`, `repository_dispatch` or `workflow_run`.
- WHILE a run of the workflow is in progress THE SYSTEM SHALL queue a second dispatch and SHALL NOT cancel the first or run both at once (`concurrency: group: rea-spike-796, cancel-in-progress: false`).
- THE SYSTEM SHALL set top-level `permissions: {}`. The job SHALL get only `contents: read`. Every `actions/checkout` SHALL use `persist-credentials: false`. No GitHub token SHALL be placed in the environment of any harness, REA or fixture process.
- THE SYSTEM SHALL authenticate Claude only through the existing `secrets.CLAUDE_CODE_OAUTH_TOKEN`, which `diagrams-refresh.yml` and `claude-review.yml` already use. It SHALL NOT introduce a new repository secret.
- WHEN the operator supplies the `rea_ref` input THE SYSTEM SHALL fetch `https://github.com/morluto/rea` and resolve the ref to a full 40-hex commit SHA. It SHALL check out exactly that SHA and write the input ref, the resolved SHA, the package version and the install method to `rea-metadata.json` in the bundle.
- IF `rea_ref` cannot be resolved, or the REA install fails, THEN THE SYSTEM SHALL record an infrastructure failure, skip every REA-dependent arm and the schema footprint, and fail the run after uploading the bundle. No REA result SHALL be fabricated.
- THE SYSTEM SHALL build `native-codec` with its `build.sh` and `packaged-app` with its `build.sh` JVM jar fallback. It SHALL record each fixture's sha256, the artifact kind (`elf` / `jar`) and the toolchain versions (`cc --version`, `make --version`, `strip --version`, `javac -version`, `jar --version`) in `fixtures.json`. It SHALL NOT download or analyse any binary that is not built from `docs/spikes/796/fixtures/`.
- THE SYSTEM SHALL run every measurement by invoking `tools/rea_spike.py` with `--allow-live`:
  - `run` for each fixture x arm (`baseline`, `rea-mcp`, `rea-cli`);
  - `schema-bytes` once;
  - `probe-stages` for each fixture on the `probe_arm` input (default `rea-mcp`).

  It SHALL NOT reimplement scoring, classification or probing in the workflow.
- THE SYSTEM SHALL make exactly one harness invocation per fixture/arm/stage-probe. It SHALL NOT retry, rephrase or re-run a step after a refusal or a failure.
- WHEN a harness `run` invocation exits 0 or 1 and prints exactly one parseable JSON record THE SYSTEM SHALL append that record to `records.jsonl` as a measurement. The record SHALL carry `outcome` and `failure_class` (harness extension, see design), so `MODEL_POLICY_REFUSAL` is kept as a valid result and not raised as a job failure.
- IF a harness invocation exits with any other code, or prints no parseable JSON record, THEN THE SYSTEM SHALL append a `{"kind": "infra-failure", ...}` record naming the fixture, arm, step and exit code, plus a 4 KiB bounded stderr summary with its sha256. At the end of the job it SHALL mark the workflow run failed, so the affected cell cannot be read as an REA or model result.
- THE SYSTEM SHALL record the model id it used (input `model`, default `claude-opus-5-5`), the `claude-agent-sdk` version, the bundled Claude Code CLI version and the `mcp` package version in `run-metadata.json`. IF the model input differs from `ISSUE_INVESTIGATOR_MODEL` in mctl-gitops `cwft-mctl-agents-investigate.yaml` THEN THE SYSTEM SHALL record both values and a `model_matches_investigator: false` flag. It SHALL NOT substitute a model silently.
- WHILE no #791 provider endpoint is available to this workflow THE SYSTEM SHALL leave the Kimi K2.7 Code, DeepSeek V4 Flash, GLM 5.2 and Qwen 3.6 rows as `not-run` with an explicit reason, through the harness's existing `model_matrix`. It SHALL NOT add a new provider integration.
- THE SYSTEM SHALL launch REA (both the MCP server command and the CLI on `PATH`) through a wrapper that strips `CLAUDE_CODE_OAUTH_TOKEN` and any `GITHUB_*`/`ACTIONS_*` token variables from REA's environment.
- THE SYSTEM SHALL check the bundle immediately before upload. IF any bundle file contains the literal value of `CLAUDE_CODE_OAUTH_TOKEN` or `GITHUB_TOKEN`, or any file other than `records.jsonl` exceeds the configured size cap, THEN THE SYSTEM SHALL withhold that bundle from upload and fail the run.
- THE SYSTEM SHALL upload one artifact `rea-spike-796-<run_id>` with `retention-days: 14`. The bundle SHALL contain:
  - `records.jsonl`;
  - `report.md` (the output of `tools/rea_spike.py report`);
  - `rea-metadata.json`;
  - `fixtures.json`;
  - `schema-bytes.json`;
  - the probe records;
  - `run-metadata.json`;
  - an empty grading template, `grading-template.yaml`, in the shape `_score_rows` reads.
- THE SYSTEM SHALL NOT commit, push, open a PR or comment on an issue from the workflow.

## Out of scope

- Updating `docs/spikes/796-rea-investigation-evidence.md` or `docs/spikes/796/rea-version.md` with results. That is a separate, human-reviewed change after the artifact is inspected.
- A new provider integration for the cross-model rows, or any change to `docs/spikes/791/shim.py`.
- An Android SDK/Gradle APK build of `packaged-app`. The JVM fallback is used and recorded as such.
- In-workflow human grading. Only the empty template is shipped.
- Any change under `orchestrator/`, any CWFT, any scheduled trigger, or any generic reverse-engineering capability.
- Dispatching the first run and posting its link to #796. This is an operator action after merge. It is listed in tasks.md but no automation performs it.

## Open questions

- REA install method and entrypoints: the clone does not say how `morluto/rea` is installed (pip/uv, npm or cargo) or what its MCP-server and CLI commands are, and upstream was not read during this investigation. The implementer must read upstream at the pinned SHA and set the install step, `REA_SPIKE_MCP_CMD` and the CLI wrapper target accordingly. If REA has no CLI or no MCP mode, that arm is recorded as `infra-failure` with reason `rea-mode-unsupported`.
- Default `rea_ref`: the issue asks for a pinned, recorded SHA but names none. Proceeding with a required `rea_ref` input with no default, so the operator must choose a ref and the resolved SHA is always recorded.
- Whether a Claude Code OAuth token in the Bash tool's environment is acceptable for the spike. The Claude CLI needs it, so the model's own Bash tool can read it. The proposal strips it from REA subprocesses and blocks it from artifacts, but cannot hide it from the model's own shell. See the design risks.
- Cost ceiling: the harness has no per-session budget flag. Six runs plus two five-stage probes on Opus are bounded only by `timeout-minutes`. The owner may want a lower `probe_arm` scope or a cheaper first run.
