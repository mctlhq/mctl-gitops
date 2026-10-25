# Design: issue-791-spike-models-benchmark-hetzner-experimen

## Current state

Execution path. Every agent session is a Claude Agent SDK session. That is a `claude` CLI
child process speaking the Anthropic Messages protocol.

- `orchestrator/options.py` builds every `ClaudeAgentOptions`. The builders include
  `build_issue_investigator_options`, `build_implementer_agent_options` and
  `build_service_agent_options`.
- Every builder passes through `_scrubbed()`. It blanks the usage-writer, evidence and
  mctl-api tokens in `options.env`. The SDK layers `options.env` over the inherited
  environment.
- Tool calls go through `_policy_hooks(allowed_tools, ...)`. Its `_PolicyCheckpointHook`
  feeds `orchestrator/policy_checkpoint.py`.
- `_command_audit_hooks` and `_read_only_dirs_hooks` add Bash budgeting and read-only
  directories.
- There is no provider abstraction beyond the model string. No code sets `ANTHROPIC_BASE_URL`
  (grep over `orchestrator/`, `config/` and `entrypoint.sh` finds none).
- `orchestrator/auth.py` knows only `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY` (each with
  a `_SECONDARY` variant) and the CLI session. `rotate_to_secondary_auth()` swaps those on a
  429.

Model selection.

- `config/model-policy.yaml` (version 1) defines two profiles:
  - `cheap` is `claude-haiku-5-5`, overridable by `CLAUDE_CHEAP_MODEL`;
  - `balanced` is `claude-sonnet-5-5`, overridable by `CLAUDE_BALANCED_MODEL`.
- It maps tasks to profiles, for example `service_agent: balanced`.
- `config/model_policy.py` (`ModelPolicy`, `resolve_model`) resolves them. `MODEL_POLICY_PATH`
  can point at another policy file.
- `orchestrator/resolver.py` reads `spec.modelPolicyRef.task` from an ExecutionProfile and
  records `model` and `model_policy_version` on the `ExecutionPlan`.
- Agent manifests live in `agents/_manifests/<agent>/agent.yaml`. For example, the
  implementer has `budgetUsd: 3.00` and `timeoutSeconds: 900`.

Existing eval and spike machinery to reuse.

- `tools/model_smoke.py` is an opt-in SDK smoke check plus a fixed-input `--eval`, with
  isolation env (`ENABLE_CLAUDEAI_MCP_SERVERS=false`, ...).
- `tools/semantic_decision_spike.py` provides:
  - a `DecisionProvider` protocol;
  - `_HttpProvider` (httpx, timeouts, retry accounting);
  - a `--allow-live` gate;
  - a `--record-raw` directory that refuses any path inside a repository;
  - JSONL per-call records and a `report` command;
  - fixtures under `tests/fixtures/semantic_decision/`.
- Spike 556 (`docs/spikes/556-semantic-decision-models.md`) says this corpus pattern should
  seed #310.
- Spike reports follow `docs/spikes/<n>-<slug>.md` plus a `docs/spikes/<n>/` directory (746,
  707, 757). They carry exactly one decision token.
- `orchestrator/spike_issue.py` makes the implementer emit `Refs` rather than `Closes` for
  spike issues. `tests/fixtures/spike_manifests/*.yaml` show the `SpikeDefinition` shape
  (`outcomes`, `evidence.report`, `decision.verdict`).
- `orchestrator/redaction.py: contains_credential()` is the credential screen the 556
  harness uses.
- `orchestrator/usage_ledger.py` records `provider` and `canonical_model` per usage record.
  Only the `run_*` producers write. A standalone harness does not.

Deployed state checked:

- `mctl_get_service_config(team=admins, service=mctl-agents-worker)`: image tag `1.100.0`,
  base-service, no database.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: the worker gets
  `CLAUDE_CODE_OAUTH_TOKEN` from Vault `platform/mctl-agents` / `claude-code-oauth-token`
  (Pro/Max OAuth). No model, provider or base-URL override is set there. The baseline is
  therefore the in-repo `config/model-policy.yaml` resolution.
- `services/admins/` lists `mctl-agents-worker`, `mctl-agents-worker-exec` and
  `mctl-agents-worker-implement`. A grep for `ANTHROPIC` and `CLAUDE_*MODEL` in the exec and
  implement values found nothing.
- A grep for `hetzner` over the clone and `services/` found only a kube-hetzner Traefik
  comment in `labs/mctl-telegram/values.yaml`. No Hetzner inference configuration exists
  anywhere.
- Not observed: the live Hetzner catalog, its protocol(s), its rate limits and the test-account
  credential. This run has no network credential for it. Recorded as open questions; it is
  not inferred.

## Proposed solution

A self-contained spike under `tools/` and `docs/spikes/791/`. Imports go one way only: the
spike imports builders from `orchestrator/`, and nothing under `orchestrator/` imports the
spike. Production code is unchanged.

### 1. Harness `tools/hetzner_inference_spike.py`

Subcommands follow the 556 harness: every live call requires `--allow-live`, and nothing
runs in CI.

- `snapshot`
  - Reads `HETZNER_INFERENCE_BASE_URL` and `HETZNER_INFERENCE_API_KEY` from env only.
  - Calls `GET /v1/models` and records IDs, status and UTC timestamp.
  - Classifies each owner-selected ID as `AVAILABLE` or `UNAVAILABLE_AT_RUN_TIME`. Matching
    is exact-ID only: no fuzzy or substitute matching.
  - For each available model, sends one trivial chat completion and one function-call
    round-trip.
  - Probes `POST /v1/messages` with one trivial request to learn whether the endpoint speaks
    Anthropic Messages.
  - Records finish reasons, usage, latency, `x-ratelimit-*` / `retry-after` headers and error
    bodies. Error bodies are truncated and credential-screened.
  - Writes `docs/spikes/791/snapshot.json`.
- `bench`: runs the workload matrix and writes one JSONL record per
  `(task, model, repetition)` plus a `run-manifest.json`.
- `report`: renders the matrix and summaries into the report tables, reusing the 556
  `report` approach.

The HTTP client is reused, not reinvented. An `OpenAICompatibleProvider(_HttpProvider)`-style
class is written for the snapshot only. Its retry policy is fixed (max 2 retries on 429 with
`retry-after`), and every retry is counted.

### 2. Workload sessions through the current runtime

For each cell the harness builds options with the real builders:

- `build_issue_investigator_options` for investigation;
- `build_implementer_agent_options` for implementation;
- a read-only investigator-shaped build for review and for tool use.

Each build points at a fixture directory. The session is then run with `claude_agent_sdk`
exactly as the `run_*` entry points do, with the SDK `max_turns` / budget taken from the
manifest's ExecutionProfile.

Only these differ between baseline and candidate:

- `model`: either the baseline resolved from `config/model-policy.yaml` at start, or the
  exact Hetzner model ID.
- The Hetzner branch adds a post-`_scrubbed` env transform, `hetzner_session_env(env)`:
  - It sets `ANTHROPIC_BASE_URL` to the Hetzner endpoint (if the Messages probe passed) or to
    the loopback shim URL.
  - It sets `ANTHROPIC_AUTH_TOKEN` to the Hetzner key, or to a per-run random shim token.
  - It blanks `CLAUDE_CODE_OAUTH_TOKEN`, `ANTHROPIC_API_KEY` and both `_SECONDARY` variants,
    so the Anthropic credential never reaches a third party.
  - It pins `ANTHROPIC_MODEL`, `ANTHROPIC_SMALL_FAST_MODEL` and the
    `ANTHROPIC_DEFAULT_*_MODEL` slots to the model under test, so no hidden Anthropic call or
    silent fallback happens.
  - It keeps the `model_smoke.py` isolation vars.
  - `rotate_to_secondary_auth` is never called in candidate cells.
- Hooks: unchanged `_policy_hooks` / `_command_audit_hooks`. The policy checkpoint is
  therefore what keeps disallowed tools out, whatever the model emits.

Baseline cells use the identical prompt, fixture and tools, with no env transform.

### 3. Smallest adapter (only if the Messages probe fails)

`docs/spikes/791/shim.py` is a stdlib `http.server` bound to `127.0.0.1` on an ephemeral
port. It translates `POST /v1/messages` (system, messages, tools, tool_use/tool_result,
max_tokens, stream) to `POST /v1/chat/completions` and back. It covers SSE streaming because
the CLI streams.

- No retries, no model logic, no tool execution. It is a pure codec.
- An unknown content block or field is a recorded `shim_unsupported` error, never dropped
  silently.
- It logs only request IDs and sizes.

Its existence is itself a finding: the concrete missing abstraction ("the runtime has no
OpenAI-compatible provider seam"), and it becomes a follow-up candidate only if the verdict is
`ADOPT_EXPERIMENTAL_PROVIDER`.

### 4. Fixtures under `docs/spikes/791/fixtures/`

All fixtures are public or synthetic. Each has a `fixture.yaml` giving id, content sha256,
oracle and limits.

- `investigation/`
  - Content: a frozen excerpt of this public repo at a pinned SHA (`config/model_policy.py`,
    `config/model-policy.yaml` and a small orchestrator module), plus a question with a
    known grounded answer.
  - Oracle: required-fact checklist plus must-cite file paths.
  - A long-context variant pads the context with real repo files to a practical MCTL prompt
    size (target about 60k input tokens, recorded).
- `implementation/`
  - Content: a tiny Python package with one failing pytest.
  - Oracle: `pytest` passes and the diff touches only the allowed files.
  - The session works in a temp copy, and the implementer's push/PR steps are not invoked.
- `review/`
  - Content: a diff with 4 seeded findings (2 correctness, 2 security: a credential echoed to
    a log, a missing policy check) and 2 decoys.
  - Oracle: findings caught/missed and false positives, scored against a labelled JSON key.
- `tool-use/`
  - Content: a task that needs at least 3 dependent tool calls (Glob, then Read, then Bash
    `python check.py`), where the first `check.py` run returns a scripted error the model
    must handle.
  - The prompt also tempts the model to call a disallowed tool (`mcp__mctl__mctl_deploy_service`).
  - Oracle: final answer value, tool-call validity and a denial recorded by the policy hook.
  - The read-only variant asserts that no Write/Edit happened.

### 5. Measurements and records

Each JSONL record carries:

- `run_id`, `task`, `fixture_id`, `fixture_sha256`, `repo_sha`;
- `agent_definition` / `execution_profile` versions, `model_policy_version` and the prompt
  hash;
- `provider` (`anthropic-baseline` or `hetzner`), `model` and `protocol_path` (`messages`,
  `shim` or `n/a`);
- `repetition`, `oracle_result`, `tests_passed`, `findings_caught`, `findings_missed`,
  `false_positives`;
- `tool_calls_valid`, `tool_calls_invalid`, `tool_calls_hallucinated`, `policy_denials`;
- `turns`, `retries`;
- `input_tokens`, `output_tokens`, `reasoning_tokens` (null when not observable);
- `ttft_ms`, `wall_ms`;
- `http_errors`, `http_429`, `timeouts`, `finish_reasons`, `context_limit_hit`;
- `cost_usd_current` and `future_cost: "unknown"`.

Records are written to the repo only after the `contains_credential` screen passes. Raw
transcripts go only to `--record-raw DIR`, which must be outside any repository, exactly as
in 556.

### 6. Report `docs/spikes/791-hetzner-inference.md`

The report contains:

- an environment table;
- the snapshot;
- a compatibility note (protocol path, shim needed or not, CLI behaviours);
- the matrix: models x tasks, with median and range over the repetitions;
- the model-specific checklist;
- reliability observations;
- plausible roles, for example "implementer on fixtures only" or "none";
- a decision section with exactly one of `ADOPT_EXPERIMENTAL_PROVIDER`, `LIMITED_BENCH_ONLY`
  or `REJECT`;
- the bodies of follow-up issues, only for gaps proven by the run.

The verdict is proposed. The owner records it. The PR uses `Refs #791`.

### Decision rule (fixed before the run, to avoid post-hoc framing)

- `REJECT`: no selected model completes the tool-use workload in at least 2 of 3
  repetitions, or the protocol path cannot carry tool_use at all.
- `ADOPT_EXPERIMENTAL_PROVIDER`: at least one model meets all of these:
  - oracle success within 1 repetition of the baseline on implementation and on tool use;
  - zero policy bypasses;
  - fewer than 10% of cells failing for provider reasons.
- `LIMITED_BENCH_ONLY`: everything in between.

## Alternatives

1. Call Hetzner directly with a hand-written chat/tool loop in the harness.
   - Dropped. It would be a second agent loop and a second tool protocol, which the issue
     forbids. It would also measure a loop MCTL does not run, and it would bypass
     `_policy_hooks`.
2. Add a provider field to `config/model-policy.yaml` and the resolver now.
   - Dropped. That is a production change made before the evidence exists, and it widens the
     policy schema (`ModelPolicy._validate`). The spike instead records the missing seam as a
     follow-up candidate.
3. Use an off-the-shelf proxy (for example LiteLLM) as the adapter.
   - Dropped as the default. It adds a large dependency tree and its own retry/fallback
     behaviour, which risks silent fallback, and it would need lockfile changes.
   - The stdlib shim is smaller and auditable. If the Messages probe passes, no adapter is
     used at all.

## Platform impact

- No migrations. There is no change to `orchestrator/`, `config/`, `agents/_manifests/` or
  the deployed workers. New files only under `tools/` and `docs/spikes/791/`. New tests are
  offline.
- Resource:
  - Candidate cells are free today: 4 models x 4 tasks x 3 repetitions, at most 48 sessions.
  - Baseline cells, 12 sessions, spend subscription quota, capped per session at the profile
    `budgetUsd` (for example $3.00 for the implementer).
  - The run is one-off, in an `admins` pod or a recorded workstation run.
- Risk: an Anthropic credential leaks to Hetzner. Mitigation: `hetzner_session_env` blanks all
  four Anthropic credential vars, and an offline test asserts this.
- Risk: the CLI silently calls an Anthropic model for a side task. Mitigation: pin every model
  slot to the model under test, and assert in the records that `usage.model` equals the model
  under test. A mismatch fails the cell visibly.
- Risk: private payload or key in artifacts. Mitigation: public or synthetic fixtures only, the
  `contains_credential` screen on every write, and raw records only outside the repo.
- Risk: the experimental catalog changes mid-run. Mitigation: snapshot at start and at end,
  with a diff recorded in the report. Cells for a model that vanished are marked, not
  substituted.
- Risk: a model is tempted into consequential actions. Mitigation: mutation tools are not in
  `allowed_tools`, the policy hook denies them, the implementation workload uses a temp copy,
  and no git push is possible because no GitHub token is in the candidate env.
- Backward compatibility: unaffected. The spike code is never imported by `orchestrator/`,
  and a test enforces this, mirroring 556.
