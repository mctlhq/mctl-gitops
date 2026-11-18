# Design: issue-1096-spike-devloop-evaluate-claude-code-code

## Current state

Inspected revision: mctl-agents `main` at
`2227b47427e82bd2f66a7b2c784042cd76691000` (2026-11-17).

**How agents reach the model.** Every DevLoop agent runs headless through the
Agent SDK. `ClaudeSDKClient` is used in `orchestrator/run_issue_investigator.py`,
`run_implementer.py`, `run_shepherd.py`, `run_incident_responder.py`,
`run_service_agent.py`, `run_mentor.py`, `run_scout.py` and
`run_authoring_canary.py`, plus `mcp_guard.py`, `subagent_wait.py`,
`tracing.py` and `usage_ledger.py`. `pyproject.toml` pins
`claude-agent-sdk==0.2.174` and says the wheel bundles the Claude Code CLI,
"so the pin below also fixes the CLI version". The Dockerfile no longer
installs `@anthropic-ai/claude-code` separately. Options are built in
`orchestrator/options.py` (`build_issue_investigator_options*`,
`build_implementer_agent_options`, `build_shepherd_options`, ...). Temporal
orchestration lives in `orchestrator/temporal/` (`dispatcher.py`,
`activities/`), and Argo CWFTs run the runners in pods.

**Per-call governance (the unit Code Mode changes).**
- `orchestrator/options.py` `_PolicyCheckpointHook`: a `PreToolUse` hook that
  sends every MCP tool call through `orchestrator/policy_checkpoint.py`
  (`decide`, `enforce`, `args_digest_of`; ADR 014). It fails closed: any
  exception is a deny. It skips only the `mcp__capability__` prefix, whose
  calls the gateway checks itself.
- `_audit_pre_tool_use` prints `AUDIT tool=Bash cmd=...` with the execution
  context id. `_ReadOnlyDirsHook`, the deadline guard (`_deadline_guard_hook`,
  `orchestrator/exec_budget.py`) and `_ci_log_guard_hook` are also
  `PreToolUse` hooks. The gh-global-flag comment near line 630 records an
  earlier finding: command matching must follow command semantics, not exact
  spelling (#423).
- `orchestrator/decision_records.py` writes one durable decision per
  checkpoint decision, with attempts, to mctl-api (`MCTL_DECISION_RECORDS`).
  It tracks open MCP calls between `PreToolUse` and `PostToolUse` and sends
  digests only: actor, tenant scope, trace id, args digest.
- `orchestrator/execution_identity.py` (`Actor`, `Executor`, `Scope`,
  `Trigger`; ADR 011) supplies the sealed actor/tenant every decision names.
- `orchestrator/redaction.py` (`contains_credential`, `safe_scalar`) is the
  existing redaction primitive.

**Capability gateway.** `orchestrator/capability_gateway.py` (ADR 017)
exposes `capability_search` / `capability_describe` / `capability_invoke`
over one sealed `CapabilitySet`. Each underlying invocation gets its own
`PolicyCheckpoint`. `docs/benchmarks/capability-discovery.md` measured one
run per mode: 92 vs 3 first-turn schemas and a 61,213 vs 23,392 first-turn
prompt. `tools/capability_bench.py` (`schema-bytes`, `compare`) holds the
#597 counting rule that spike 796 reused
(`docs/spikes/796-rea-investigation-evidence.md`).

**Observability.** `orchestrator/tracing.py` / `tracing_sdk.py` export OTLP
http/protobuf only when `OTEL_EXPORTER_OTLP_*` is set
(`docs/observability/execution-traces.md`). There is no handling of
`DISABLE_TELEMETRY` or of Claude Code's own CLI telemetry in this repo
(grep: no matches). `orchestrator/usage_ledger.py` (ADR 012) records
per-model usage and cost.

**Assurance.** ADR 022/023 (`orchestrator/runtime_assurance.py`,
`assurance_harness.py`) define scenario-fixture probes. They are the pattern
#181/#151 asks to reuse for negative tests.

**Spike conventions.** Spike issues are detected by title
(`orchestrator/spike_issue.py`, `SPIKE_TITLE_RE`). The implementer emits
`Refs`, not `Closes`, and the owner records `decision.verdict` by hand.
Reports live at `docs/spikes/<n>-<slug>.md` with artefacts in
`docs/spikes/<n>/` (e.g. `917-claude-ultra-capacity.md` +
`917/fixture-manifest.json`, `records-schema.md`, with
`STATUS: PENDING_EVIDENCE` and "not observed" cells).

**Interactive operator workflows.** No `.claude/` directory, settings or
hook configuration exists in this repository, so how operators use
interactive Claude Code is UNKNOWN from here. Code Mode references: none in
the repo (grep for "code mode", "programmatic tool": no matches).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: image
  `ghcr.io/mctlhq/mctl-agents:1.117.0`. Auth is `CLAUDE_CODE_OAUTH_TOKEN`
  from a secret (around line 231-243). This confirms that the deployed
  runtime is the headless SDK with an OAuth token, not an interactive
  terminal.
- `services/admins/mctl-agents-worker-exec/values.yaml` and
  `mctl-agents-worker-implement/values.yaml`: `MCTL_TRACE_WORKFLOW_TYPES:
  DevLoopWorkflow`, `MCTL_TRACE_ARGO_PARAM: "true"` (tracing scoped to
  DevLoop).
- mctl MCP tools were not called. No deployed service config beyond the
  gitops values above is needed for a docs-only spike.
- Code Mode docs (code.claude.com/docs/en/code-mode) were not fetched in this
  run. Every Code Mode claim is from the issue body, see Open questions.

## Proposed solution

The deliverable is documentation only and follows the existing spike layout.
Nothing under `orchestrator/`, `agents/` or `tools/` changes, and neither do
`pyproject.toml`, `uv.lock` or the `Dockerfile`. One offline structural test
is the only non-doc file, matching the `tests/test_spike_757_attention.py`
precedent (item 5).

### Deliverable files

1. `docs/spikes/1096-claude-code-code-mode.md`: the report, with
   `STATUS: PENDING_EVIDENCE` and `Refs mctlhq/mctl-agents#1096`. Sections:
   - **Sources and pins**: table of URL, retrieval date, CLI version named,
     plus mctl-agents commit and mctl-gitops paths. Each row is labelled
     `OFFICIAL`, `NEWS` or `VENDOR_CLAIM`.
   - **No-duplicate / ownership map**: #597 owns benchmark reports (this
     spike only contributes a protocol). #63 is PARK with audit M8 FAIL; it
     used a different executor (Cloudflare Dynamic Worker) and is not
     reopened. #242/#517: the CapabilityGateway, and the limitation that
     first-turn reduction is not E2E savings. #181/#151: reuse the
     checkpoint/decision-record/assurance fixtures, no second policy engine.
     #35/#165 are the adoption gate. #343 is orthogonal.
   - **Inventory**: the Current state above, with file paths and the commit.
     Interactive operator column marked UNKNOWN.
   - **Surface matrix**: rows are the six surfaces. Columns are runtime,
     eligibility, hook semantics (per call vs per script), limits, billing,
     audit unit, security boundary, task fit, and MCTL applicability. The
     headless DevLoop row is "Code Mode: not available (VENDOR_CLAIM per
     issue; re-pin)". The table also states that the CapabilityGateway and
     Code Mode overlap in goal (context efficiency) but cannot replace each
     other: different runtimes and a different policy unit.
   - **Threat model**: one row per threat from the issue. Each row gives the
     attack, which existing control applies (e.g. `_PolicyCheckpointHook`
     per child if hooks fire per child; `_audit_pre_tool_use` semantics vs
     `cd ... &&` composition), and the status: `HOLDS_BY_DOC`, `UNKNOWN` or
     `GAP`. Attacker-supplied tool output that steers runtime-derived
     arguments is treated as the central risk. The auto-mode classifier
     judges code before execution, so runtime-derived arguments can only be
     governed by per-child hooks.
   - **Per-child governance requirements**: for each child call, (a) actor
     and tenant equal to the parent session's sealed `execution_identity`,
     never derived from script data; (b) `args_digest_of` over the exact
     runtime arguments; (c) its own `policy_checkpoint.decide` at action
     time; (d) a `decision_records` row plus attempt events, correlated to a
     script id and child ordinal. Anything unobservable is fail-closed:
     deny, and the recommendation is capped at `FURTHER_RESEARCH`.
   - **Observability**: what `Ctrl+O` must show (script text, child calls,
     hook verdicts) as checks for the run, each `NOT_RUN`. A comparison of
     the CLI transcript with MCTL durable records. A redaction proposal that
     reuses `orchestrator/redaction.py` rules for any transcript excerpt
     committed as evidence.
   - **Recommendation memo**: provisional recommendation `FURTHER_RESEARCH`
     for an operator-only CLI pilot and `REJECT` for headless/DevLoop
     transfer while it is officially unsupported. Gate: owner GO plus #597
     owner co-sign plus a security permission review of the settings/hooks
     used. Expected cost: 3 tasks x 2 modes x 5 reps = 30 runs; the
     per-run price is taken from the #597 and benchmark doc numbers once
     pinned, and stated as UNKNOWN until then. Hard blockers are the
     per-child hook visibility and telemetry compatibility unknowns. What
     carries over to the runtime is principles only (fewer round trips
     through a governed gateway, e.g. a future batched `capability_invoke`
     with per-item checkpoints), handed to #242/#597 as a note, not built.
2. `docs/spikes/1096/protocol.yaml`: a machine-readable benchmark protocol.
   - `pins`: CLI version, model, effort, prompt hash, settings/profile hash,
     identity label (no token), fixture digests.
   - `modes`: `cli-normal`, `cli-code-mode`.
   - `reps: 5`, with randomized interleaving.
   - `tasks`:
     - A: repo research over a pinned mctl-agents commit. The oracle is a
       fixed answer key, e.g. the list of `PreToolUse` hook classes in
       `orchestrator/options.py`, compared exactly.
     - B: CI evidence over a sanitized fixture of `gh run view` JSON, served
       by a read-only shim like the "gh shim blocked writes" in the
       capability-discovery benchmark. The oracle is the expected failing
       job/step set.
     - C: aggregation of two fixture MCP servers (sanitized, local, no
       network). The oracle is a deterministic joined record set.
   - Each task lists `failure_cases`: wrong answer, partial answer, write
     attempted, permission denial, timeout.
   - `metrics`: initial and total input/output/cache tokens per #597 rules
     via `tools/capability_bench.py compare`, turns, tool invocations, child
     calls per script, p50/p95 wall clock, JS startup overhead, cost (ADR 012
     fields), correctness, denials, per-child correlation completeness.
   - Every `result` is `NOT_RUN`.
3. `docs/spikes/1096/negative-matrix.yaml`: one row per threat-model case.
   Each row has `id`, `threat`, `fixture`, `expected` (deny/flag), `oracle`
   and `status: NOT_RUN`. Cases include: a child write tool under a
   read-only profile; `cd x && <denied cmd>`; an argument computed from
   injected tool output; a parallel fan-out above the limit; mid-script
   cancellation leaving a partial attempt; a retry duplicating a
   non-idempotent call; egress to a non-allowlisted host; a secret-shaped
   value in the transcript; a hook raising (must deny); tenant B data
   reaching a tenant A call.
4. `docs/spikes/1096/surface-matrix.yaml`: the matrix in data form, with a
   `source` and `evidence_class` (`OFFICIAL` / `VENDOR_CLAIM` / `OBSERVED` /
   `UNKNOWN`) per cell, so the markdown table can be checked against it.

5. `tests/test_spike_1096_protocol.py`: an offline test, stdlib + `yaml`
   only. It checks that the three YAML files parse and that every
   `result`/`status` cell is `NOT_RUN`. It also checks that every
   negative-matrix row has an `expected` and an `oracle`, that `reps >= 5`
   for each task and mode, that both modes share identical `pins`, and that
   no file matches `orchestrator.redaction.contains_credential`.

The PR uses `Refs mctlhq/mctl-agents#1096` (spike rule) and leaves the issue
open for the owner's verdict.

## Alternatives

- **Run the 30-run experiment now.** Dropped: the issue explicitly forbids
  any Code Mode run or settings toggle without a separate owner GO.
  Unexecuted cells must be `NOT_RUN`.
- **Fold the protocol into #597's benchmark doc
  (`docs/benchmarks/capability-discovery.md`).** Dropped: #597 owns those
  reports, and an un-run protocol for a different surface would mix
  measured and unmeasured data. The spike links to #597 instead.
- **Prototype a JS orchestration layer or a batched `capability_invoke` in
  the gateway.** Dropped: this is a non-goal ("no new platform-wide JS
  sandbox or gateway"), and Code Mode is not available on the SDK surface the
  runtime uses. It is recorded only as a candidate idea for #242.

## Platform impact

- Migrations: none. Backward compatibility: unaffected. No runtime, profile,
  dependency or gitops change.
- Resource impact: none at merge. A future approved run costs about 30 model
  sessions on an operator account. The amount stays UNKNOWN until pinned.
- Risk: the report could be read as authorization to experiment or to adopt
  Code Mode in CI. Mitigation: `STATUS: PENDING_EVIDENCE`, all result cells
  `NOT_RUN`, an explicit "no headless applicability" statement, and `Refs`
  rather than `Closes`.
- Risk: vendor claims treated as fact. Mitigation: per-cell `evidence_class`,
  and everything not observed is `VENDOR_CLAIM`/`UNKNOWN`.
- Risk: committing private content in fixtures. Mitigation: synthetic or
  sanitized fixtures only, checked with `redaction.contains_credential`
  before commit, and no live user data.
