# Design: issue-815-feat-spike-add-operator-workflow-to-exec

## Current state

### Harness: `tools/rea_spike.py` (merged in #802)

- **Subcommands.**
  - `run`, `probe-stages` and `schema-bytes` are live. Each needs `--allow-live` (`_require_live`) and returns 2 without it.
  - `score` and `report` are offline.
  - `ARMS = ("baseline", "rea-mcp", "rea-cli")`.
  - `STAGES` = five stage prompts read from `docs/spikes/796/stages/<stage>.md`.
- **Model and REA inputs.**
  - The model comes from `--model`, or else from env `ISSUE_INVESTIGATOR_MODEL` (`_read_active_model`).
  - The REA MCP server command comes from env `REA_SPIKE_MCP_CMD`, split on whitespace.
  - `_live_stage` registers it as the `rea` MCP server only for the `rea-mcp` arm. Without it, that arm returns a `CLIENT_TOOL_ADMISSION` signal.
  - The `rea-cli` arm relies on a `rea` binary on `PATH`. `_is_rea_tool_use` detects `rea` invoked from Bash.
- **`_live_stage`.** Calls `claude_agent_sdk.query` with `ClaudeAgentOptions(model, cwd=fixture_dir, mcp_servers, allowed_tools=[Read, Glob, Grep, Bash, mcp__rea__*])`. It passes no `env`, so the bundled Claude CLI and its tool subprocesses inherit the job environment.
- **`_cmd_run`.**
  - Prints one JSON record with `kind=run`, fixture, arm, model, `wall_clock_s`, turns, `tool_calls`, usage, and `final` (a `bounded_summary`: 4 KiB plus sha256, `MAX_SUMMARY_BYTES`).
  - Returns `0 if sig.get("ok") else 1`.
  - The record does not include `classify(sig)`, so a refusal and an REA or transport failure both look like "exit 1, same record shape". This is the gap the issue's failure-semantics requirement hits.
- **`_cmd_probe`.**
  - Runs `run_probe`: each stage once, stop at the first failure, classify it.
  - Prints a `kind=probe` record and returns 0 even when a stage is refused, which is correct for this issue.
  - Failure text is a 200-char normalized reason plus sha256 unless `--store-text`.
- **`_cmd_schema_bytes`.** Lists REA tools over stdio MCP and prints `{"tool_count", "schema_bytes"}` using `orchestrator.context_snapshot.canonical_json`, so it needs the project venv (`uv sync`).
- **`report`.** Renders the metrics table and `model_matrix`. Models with no probe record render `not-run (no #791 endpoint supplied)`. `REA_SPIKE_ALT_BASE_URL` is mentioned in a comment (`MATRIX_MODELS`), but no code path reads it, so the cross-model rows cannot run today.
- **Grading.** `_score_rows` reads `grading.entries[]` with `fixture`, `arm`, `claims[]` (`label`, `cites_rea`) and `actionable`.
- **Tests.** `tests/test_rea_spike.py` covers `classify`, `score`, `_collect` and the rea-mcp fail-fast, with no network.

### Fixtures and version files

- `docs/spikes/796/fixtures/native-codec/build.sh` runs `make -B -s codec` (`cc -O2 -fno-ident`, then `strip -s`) and prints the sha256.
- `docs/spikes/796/fixtures/packaged-app/build.sh` runs `javac --release 17` and `jar --date 2026-01-01T00:00:00Z`, and prints the jar sha256.
- `.gitignore` excludes the built outputs.
- `docs/spikes/796/rea-version.md` lists every REA identity field as `unobserved`.

### Existing manual-workflow patterns

- `.github/workflows/diagrams-refresh.yml`:
  - top-level `permissions: {}`, job-level `contents: read`;
  - non-cancelling `concurrency` group;
  - SHA-pinned actions: checkout `3d3c42e5…` v7.0.1, upload-artifact `ea165f8d…` v4.6.2;
  - `persist-credentials: false` on secondary checkouts;
  - artifact `retention-days: 14`;
  - Claude authenticated via `secrets.CLAUDE_CODE_OAUTH_TOKEN`.
- `.github/workflows/spike-707-bench.yml` is the measurement-only spike precedent. It uses `astral-sh/setup-uv@37802adc…` (uv 0.11.11, Python 3.12), `uv sync --locked`, and an `if: always()` artifact upload.
- `pyproject.toml` pins `claude-agent-sdk==0.2.168`, which bundles the CLI, and `mcp==1.29.0`. The Dockerfile comment confirms that the CLI version comes from the SDK wheel.
- No workflow linter (actionlint/zizmor) runs in `pr-validation.yml` or `security.yml`.

### #791 path

`docs/spikes/791/shim.py` is a loopback Anthropic-to-OpenAI codec. It needs an upstream OpenAI-compatible endpoint and a credential. No such endpoint or secret is referenced by any workflow in `.github/workflows/`, so it is not directly reusable here.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml` (line ~938) pins `ISSUE_INVESTIGATOR_MODEL: "claude-opus-5-5"`. This is the current investigator model and the proposed default for the `model` input.
- `$MCTL_GITOPS_ROOT/agent-platform/execution-profiles/issue-investigator-default/profile.yaml` confirms that `ISSUE_INVESTIGATOR_MODEL` is a `legacyEnvOverride` that outranks `task: service_agent`.
- No tenant service is involved: the change is a GitHub Actions workflow in `mctl-agents`, so no `services/<tenant>/` values or mctl MCP service tools apply. No mctl MCP calls were made.
- Not observed: whether repository secret `CLAUDE_CODE_OAUTH_TOKEN` exists today and is usable on `workflow_dispatch`. This is inferred only from its use in `diagrams-refresh.yml` and `claude-review.yml`; Actions secrets are not readable from the clone.
- Not observed: the `morluto/rea` upstream (install method, CLI and MCP entrypoints, licence). It was not fetched. See Open questions.

## Proposed solution

There are three changes. All of them are spike-scoped and are deleted when #796 closes, matching `spike-707-bench.yml`.

### 1. Minimal harness extension (`tools/rea_spike.py`)

`_cmd_run` adds two fields to its record:

- `"outcome": "ok" | "failed"`;
- `"failure_class": classify(sig) if not ok else None`.

When the stage is not ok, it also adds `"failure": failure_text_record(text, store_text=False)`. The exit code stays 0/1. This reuses the existing pure `classify`, so nothing is duplicated. It is the only way the workflow can separate `MODEL_POLICY_REFUSAL` from `REA_TOOL_FAILURE` or `PROVIDER_RUNTIME_FAILURE` for `run` cells. Add a matching unit test.

No other harness behaviour changes: no retries, and the env contract stays the same.

### 2. REA isolation wrapper (`docs/spikes/796/rea-env.sh`)

A POSIX script:

```
exec env -u CLAUDE_CODE_OAUTH_TOKEN -u GITHUB_TOKEN -u GH_TOKEN \
  -u ACTIONS_RUNTIME_TOKEN -u ACTIONS_ID_TOKEN_REQUEST_TOKEN \
  -u ACTIONS_ID_TOKEN_REQUEST_URL "$@"
```

The workflow uses it in two places:

- `REA_SPIKE_MCP_CMD="sh docs/spikes/796/rea-env.sh <rea-mcp-entrypoint>"`, which works because the harness splits on whitespace.
- A generated `$RUNNER_TEMP/rea-bin/rea` shim on `PATH` that execs the wrapper around the real REA CLI. Only this shim directory is prepended to `PATH`. The real binary sits outside `PATH`, so the model's `rea` calls always go through the shim.

### 3. Workflow `.github/workflows/rea-spike-796.yml`

**Trigger and job settings**

- `on: workflow_dispatch` only, with these inputs:
  - `rea_ref`: string, required, no default;
  - `model`: string, default `claude-opus-5-5`;
  - `probe_arm`: choice `rea-mcp` | `rea-cli`, default `rea-mcp`.
- `permissions: {}` at the top level. One job, `bench`, with `permissions: contents: read`.
- `concurrency: { group: rea-spike-796, cancel-in-progress: false }`.
- `runs-on: ubuntu-latest`, `timeout-minutes: 120`.
- `GITHUB_TOKEN` is never exported to the environment.

**Steps, in order:**

1. `actions/checkout` (pinned SHA, `persist-credentials: false`). Then `actions/checkout` of `mctlhq/mctl-gitops` into `_gitops`, sparse on `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`, `persist-credentials: false`. This only reads `ISSUE_INVESTIGATOR_MODEL`. If the checkout fails, record `investigator_model: unobserved`; do not guess.
2. `astral-sh/setup-uv` (same pin as spike-707), then `uv sync --locked`. Then `actions/setup-java` (SHA-pinned, temurin 17) so `javac --release 17` is deterministic.
3. **Resolve REA.**
   - Run `git ls-remote https://github.com/morluto/rea "$REA_REF"`, or accept a full SHA as-is. Pass the input to the shell via `env:`, never via `${{ }}` interpolation into `run:`.
   - `git init`, `git fetch --depth 1 origin <sha>`, `git checkout <sha>` into `$RUNNER_TEMP/rea`.
   - Assert `git rev-parse HEAD` equals the resolved SHA.
   - Install REA by the method its upstream documents at that SHA (pinned by the implementer; see Open questions), into an isolated prefix under `$RUNNER_TEMP`.
   - Write `rea-metadata.json` with:
     - `repository`;
     - `input_ref`;
     - `resolved_sha`;
     - `package_version` (from REA's own `--version` or manifest; else `unobserved`);
     - `install_method`;
     - `install_command`;
     - `cli_entrypoint`;
     - `mcp_entrypoint`;
     - `date_utc`.
   - On failure, set `rea_ok=false` and continue.
4. **Build fixtures.** Run each `build.sh` and capture its stdout digest. Write `fixtures.json` with, per fixture:
   - `name`;
   - `kind` (`elf` / `jar`; `packaged-app` is always `jar-jvm-fallback`);
   - `sha256`;
   - `build_rc`.

   Also write `toolchain` (`cc --version`, `make --version`, `strip --version`, `javac -version`, `jar --version`, `uname -a`), with each version string capped to its first line.
5. **Run metadata.** Write `run-metadata.json` with:
   - `model_input`;
   - `investigator_model` (from `_gitops`);
   - `model_matches_investigator`;
   - `claude_agent_sdk` (`uv run python -c "import importlib.metadata as m; print(m.version('claude-agent-sdk'))"`);
   - `claude_cli` (bundled CLI `--version`);
   - `mcp`;
   - `python`;
   - `runner_os`;
   - `run_id`;
   - `git_sha` of mctl-agents.
6. **Measurement steps.** A single `run:` step with `set -u`, not `set -e`. It calls a small sequencing function once per invocation, in a fixed order:
   1. `schema-bytes`;
   2. `run` x {native-codec, packaged-app} x {baseline, rea-mcp, rea-cli};
   3. `probe-stages` x {native-codec, packaged-app} on `probe_arm`.

   Environment for this step only: `CLAUDE_CODE_OAUTH_TOKEN`, `ISSUE_INVESTIGATOR_MODEL=$MODEL`, `REA_SPIKE_MCP_CMD`, and `PATH` with the shim.

   For each invocation:
   - stdout goes to a temp file and stderr to a temp file.
   - If rc ∈ {0, 1} and stdout has exactly one line that parses as a JSON object, append it to `records.jsonl` (schema-bytes goes to `schema-bytes.json` instead).
   - Otherwise, append `{"kind":"infra-failure","step":...,"fixture":...,"arm":...,"rc":...,"stderr":bounded_summary}` and set `infra_failed=1`. A small inline `uv run python -I -c` calls `tools.rea_spike.bounded_summary`, so the 4 KiB rule is reused rather than re-coded.
   - If REA did not install, the REA-dependent invocations (`schema-bytes`, `rea-mcp`, `rea-cli`) are not executed and are written as `infra-failure` with reason `rea-unavailable`. Only baseline runs.

   Raw stderr temp files are never copied into the bundle and never echoed to the public job log, apart from the bounded summary.
7. **Report.** Run `uv run python tools/rea_spike.py report records.jsonl > report.md`. Write `grading-template.yaml` with one `entries[]` item per fixture x arm: `claims: []`, `actionable: unobserved`, `grader: ""`. Append `report.md` to `$GITHUB_STEP_SUMMARY`.
8. **Bundle guard.** Run with `if: always()`; it receives the two secrets via `env`:
   - `grep -rF` for the literal `CLAUDE_CODE_OAUTH_TOKEN` and `github.token` values over the bundle directory;
   - a per-file size cap: 256 KiB for everything except `records.jsonl`, which is capped at 2 MiB.

   On any hit it deletes the bundle and fails, so the upload has nothing to send. The step never prints the secret values or matching lines.
9. `actions/upload-artifact` (pinned v4.6.2), with:
   - `if: always()`;
   - `name: rea-spike-796-${{ github.run_id }}`;
   - `path: $RUNNER_TEMP/rea-spike-796/`;
   - `retention-days: 14`;
   - `if-no-files-found: error`.
10. **Final gate.** If `infra_failed=1` or `rea_ok=false`, exit 1 with a `::error::` naming the affected cells. Refusals inside valid records never trigger this.

**Why this way**

It reuses the merged harness for every measurement, classification, bounded summary and report. It reuses the repository's existing secret and its action pins. Its only new code is the classification field the issue's failure semantics require, plus a shell wrapper. Cross-model rows stay `not-run (no #791 endpoint supplied)` through the existing `model_matrix` default, which is the explicit reason the issue asks for.

### First live run (operator)

After merge, the operator dispatches the workflow once from `main` with a chosen `rea_ref`, then posts the run and artifact URL on #796. Results reach `main` only through a later reviewed PR that edits the report and `rea-version.md`.

## Alternatives

- **Argo CWFT / mctl-agents-run style execution in-cluster** (same image, same runtime as the investigator). Dropped:
  - it would add a CWFT to mctl-gitops for a throwaway spike;
  - it would give REA network reach inside the cluster;
  - the issue explicitly prefers a `workflow_dispatch` and asks that this not become platform capability.
- **`anthropics/claude-code-action` instead of the harness.** Dropped: it would duplicate the harness's arm wiring, stage probing and classification, which the issue forbids ("execute the merged harness, do not duplicate it").
- **Make `_cmd_run` return 0 on refusal and leave the record unchanged.** Dropped: the workflow could no longer tell refusal from REA/provider failure for `run` cells. Adding `failure_class` to the record keeps the exit-code contract and makes the distinction explicit.
- **Passing an explicit sanitized `env` through `ClaudeAgentOptions`.** Deferred: the Claude CLI itself needs the OAuth token, so the model's Bash tool would still see it. Stripping at the REA boundary plus the bundle guard gives the isolation the issue asks for (REA/fixture subprocesses) without touching SDK option semantics.

## Platform impact

- **Migrations / backward compatibility.** None. The only harness change adds record fields; `report` and `_score_rows` ignore unknown keys. No `orchestrator/` change and no gitops change.
- **Resources and cost.** One GitHub-hosted runner for at most 120 min per dispatch. Claude subscription usage is 6 `run` sessions plus up to 10 probe sessions on `claude-opus-5-5`. Nothing is scheduled, so cost occurs only on operator dispatch.
- **Risk: the model's Bash tool can read `CLAUDE_CODE_OAUTH_TOKEN`.**
  - Mitigations:
    - fixtures and prompts are MCTL-owned;
    - the runner is ephemeral;
    - no GitHub token is present;
    - REA subprocesses get the token stripped;
    - the pre-upload guard blocks the literal value from artifacts;
    - Actions log masking covers the job log.
  - Residual risk is recorded as an open question for the owner.
- **Risk: REA upstream is third-party code executed on the runner.** Mitigations:
  - pinned to a recorded SHA;
  - the job token is read-only and not exported;
  - no write permissions;
  - the artifact is bounded.
- **Risk: raw REA or model output in a public job log.** Mitigation: harness stdout and stderr go to temp files, and only bounded summaries are logged or bundled.
- **Risk: the workflow is mistaken for a production capability.** Mitigations: the header comment states it is spike-only and is deleted when #796 closes; it is manual only and has no `orchestrator/` import.
