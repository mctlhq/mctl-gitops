# Spike #791: benchmark Hetzner experimental inference on current MCTL agent workloads

## Context

Issue mctlhq/mctl-agents#791 asks for a bounded, live benchmark of Hetzner's experimental
Inference service (https://experiments.hetzner.com, free during the experimental phase)
against the current mctl-agents execution path. Four owner-selected models are to be tried,
if live discovery shows them: `Kimi-K2.7-Code`, `DeepSeek-V4-Flash-0731`, `GLM-5.2-NVFP4`
and `Qwen/Qwen3.6-35B-A3B-FP8`. Each is compared with the active MCTL baseline on the same
prompt, context and tool surface across four workloads: investigation, implementation,
review, and a multi-call tool-use task. The spike ends with exactly one verdict:
`ADOPT_EXPERIMENTAL_PROVIDER`, `LIMITED_BENCH_ONLY` or `REJECT`.

This matters because every MCTL agent today runs through the Claude Agent SDK
(`claude_agent_sdk.ClaudeAgentOptions`, built in `orchestrator/options.py`). The SDK speaks
the Anthropic Messages protocol, and model choice comes only from `config/model-policy.yaml`.
The real question is whether a free OpenAI-style endpoint can sit behind that path without a
second agent loop and without weakening the policy checkpoint (`_policy_hooks`) or the
token scrubbing (`_scrubbed`). Nothing in production may depend on Hetzner during the spike.

## User stories

- AS the #791 owner I WANT a timestamped live catalog and capability snapshot of Hetzner
  inference SO THAT I judge the service on what it actually offers, not on its marketing.
- AS the #791 owner I WANT each available selected model measured against the current MCTL
  baseline, on identical pinned fixtures, SO THAT I can record exactly one verdict.
- AS a platform maintainer I WANT the benchmark to reuse the existing SDK session builders,
  policy hooks and model-policy shape SO THAT the answer covers the real execution path and
  leaves no competing framework behind.
- AS a security reviewer I WANT credentials, private payloads and disallowed tools kept out
  of the benchmark and its artifacts SO THAT a free experimental provider cannot become a
  way around MCTL governance.

## Acceptance criteria (EARS)

Live capability snapshot

- WHEN the spike harness runs `snapshot` THE SYSTEM SHALL query the documented Hetzner
  model catalog endpoint (`GET /v1/models` or the documented equivalent). It SHALL record
  the exact model IDs returned, the endpoint URL, the HTTP status and a UTC timestamp in
  `docs/spikes/791/snapshot.json`.
- WHEN an owner-selected model ID is missing from the live catalog THE SYSTEM SHALL mark
  that model `UNAVAILABLE_AT_RUN_TIME`, attach the catalog evidence, continue with the other
  models and never put another model in its place.
- WHEN the snapshot runs for each available selected model THE SYSTEM SHALL send one trivial
  completion and one tool/function-call round-trip. The round-trip is: a tool call is
  requested, a tool result is supplied, and a final answer is returned. For each it SHALL
  record status, finish/stop reason, token usage when reported, latency, and any
  rate-limit headers.
- WHEN the snapshot runs THE SYSTEM SHALL probe whether the endpoint accepts Anthropic
  Messages requests (`POST /v1/messages`) as well as OpenAI Chat Completions requests. It
  SHALL record which protocol(s) are accepted, because that decides whether an adapter is
  needed at all.

Integration boundary

- WHILE a benchmark session runs against Hetzner THE SYSTEM SHALL build it with the same
  `orchestrator/options.py` builder, the same `allowed_tools`, the same hooks and the same
  `_scrubbed` env as the baseline session. Only the model ID and the Anthropic endpoint and
  credential variables may differ.
- IF the live endpoint does not accept Anthropic Messages requests THEN THE SYSTEM SHALL use
  a loopback-only translation shim. The shim covers only Messages to Chat Completions text
  and tool_use/tool_result, with no agent logic, and the report SHALL record its existence as
  the concrete missing abstraction.
- WHILE a session targets Hetzner THE SYSTEM SHALL remove `CLAUDE_CODE_OAUTH_TOKEN`,
  `ANTHROPIC_API_KEY` and their `_SECONDARY` variants from the session env, so that no
  Anthropic credential is sent to a non-Anthropic endpoint.
- WHILE a session targets Hetzner THE SYSTEM SHALL pin every model slot the CLI may use
  (main model and small/fast model) to the model under test, and SHALL configure no fallback
  model.
- IF a Hetzner request fails (an error, a 429, a timeout or a malformed response) THEN THE
  SYSTEM SHALL record the failure against that `(task, model, repetition)` cell. It SHALL
  never retry the cell on the baseline or on another model.

Workloads and baseline

- WHEN the benchmark runs THE SYSTEM SHALL execute four pinned workloads: investigation,
  implementation, review with seeded findings, and multi-call tool use. Each uses a fixture
  identity that names its directory, its content hash and the repo revision.
- WHEN the benchmark starts THE SYSTEM SHALL capture the baseline at that moment. The
  baseline is the model that `config/model-policy.yaml` resolves for the workload's task,
  with env overrides honoured, plus the model-policy version, the AgentDefinition and
  ExecutionProfile versions, the prompt hash, the tool catalogue, the turn and output limits,
  and temperature/reasoning settings where exposed. All of this is written to the run
  manifest.
- WHEN rate limits allow THE SYSTEM SHALL run at least 3 repetitions per `(task, model)`. IF
  a provider limit prevents that THEN THE SYSTEM SHALL record the achieved count and the
  limiting evidence.
- WHEN each cell completes THE SYSTEM SHALL record: oracle result; test result where
  applicable; seeded findings caught and missed; valid, invalid and hallucinated tool calls;
  turns; retries; input, output and reasoning tokens when observable; time to first token and
  wall-clock time when observable; provider errors, 429s and timeouts; context or payload
  limits hit; and current monetary cost. Current cost is kept apart from future-cost
  unknowns.

Model-specific checks

- WHEN an available selected model is benchmarked THE SYSTEM SHALL check each of the
  following and record pass, fail or unknown:
  - a long-context request at a practical MCTL prompt size is accepted;
  - structured/tool-call output is well formed;
  - reasoning does not exhaust the output budget;
  - stop/finish reasons on failed tool turns are reported;
  - the model recovers after a tool error or refusal result;
  - the model complies with an explicit read-only, no-side-effect instruction.

Safety and governance

- WHILE any benchmark session runs THE SYSTEM SHALL route every tool call through the
  existing `_policy_hooks` / `policy_checkpoint` path. It SHALL deny any tool not in the
  session's `allowed_tools`, including a disallowed tool that the model names directly, and
  record the denial.
- WHILE the benchmark runs THE SYSTEM SHALL block every consequential external action. The
  investigation and review fixtures expose no mctl mutation tools. The implementation fixture
  writes only inside a temporary fixture checkout, and nothing is pushed.
- WHEN any artifact is written under `docs/spikes/791/` THE SYSTEM SHALL screen it with
  `orchestrator.redaction.contains_credential` and refuse to write content that matches.
  Artifacts SHALL contain only sanitized or public fixture content.
- THE SYSTEM SHALL treat all provider output as untrusted data. It is scored by
  deterministic oracles and is never followed as an instruction by the harness.
- WHEN the benchmark completes THE SYSTEM SHALL produce `docs/spikes/791-hetzner-inference.md`.
  The report SHALL contain the snapshot, the compatibility note, the benchmark matrix, the
  reliability observations, plausible MCTL roles (if any), and exactly one decision token.
- WHEN the spike PR is opened THE SYSTEM SHALL reference #791 with `Refs`, not `Closes`.

## Out of scope

- Any change to `config/model-policy.yaml`, the ExecutionProfiles in `agents/_manifests/`,
  the deployed worker values, or any production routing.
- A maintained Hetzner provider, a second agent loop, a second tool protocol, or
  provider-specific policy semantics.
- Benchmarking catalog models other than the four owner-selected ones.
- Estimating a future Hetzner price, or treating "free today" as a production cost.
- Claiming stable model availability from one snapshot.
- Writing benchmark usage into the production model-usage ledger.

## Open questions

- Hetzner API protocol: from this offline run it is not known whether the service exposes
  Anthropic Messages, OpenAI Chat Completions or both. The proposal handles both. The probe
  decides at run time whether the shim is needed.
- Credential ownership: the issue implies a test account exists but does not name its owner
  or where the key is stored. The proposal assumes a Vault path chosen by the owner, exposed
  to the run only as `HETZNER_INFERENCE_API_KEY`. The run is blocked until the key exists.
- Run location: a workstation run differs from the `admins` worker egress path. The proposal
  defaults to a one-off pod in the `admins` namespace, following the spike-556 precedent. A
  workstation run is a recorded deviation.
- Baseline quota: the deployed workers authenticate with a Pro/Max OAuth token
  (`CLAUDE_CODE_OAUTH_TOKEN` in `admins/mctl-agents-worker` values). Twelve baseline sessions
  (4 tasks x 3 repetitions) spend subscription quota. The proposal caps each session at the
  ExecutionProfile's `budgetUsd`.
- #310 (eval direction) was not readable offline. The proposal reuses the fixture-corpus
  pattern of `tools/semantic_decision_spike.py` and `tools/model_smoke.py`, as spike 556
  recommends for #310. The reviewer should confirm this matches #310's intent.
- Where the SpikeDefinition manifest for #791 lives (the `tests/fixtures/spike_manifests/`
  shape, with the canonical copy presumably in mctlhq/.github) is outside this repo. The
  report proposes a verdict, and the owner records `decision.verdict` there.
