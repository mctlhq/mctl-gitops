# Spike: OpenAI-compatible function calling for the Telegram assistant tool loop

## Context
mctlhq/.github#293 (source mctlhq/mctl-telegram#1088, phase P5 of the managed
runtime epic mctl-telegram#1002, ADR mctl-telegram `docs/adr/0008-managed-runtime.md`)
asks a measured question. Can an OpenAI-compatible model reached through the
Cloudflare AI gateway drive the Telegram assistant's 11-tool loop? The
candidates are Hetzner Qwen3.8-27B and Qwen3.6-35B-A3B via `custom-hetzner`,
and Nebius GLM-5.1 via `custom-nebius`. The loop must use `tool_choice: auto`,
take the function schemas unchanged from `mcplib.Tool.InputSchema`, and pass
the C1 gate: >= 29/32, 0 leaks, 0 binding violations and 0 wrong auto-sends.
The spike must also report p50/p95 latency and cost per job. The answer decides
whether the planned Go `OpenAIRunner` can reuse the tool definitions of
`buildToolSet` unchanged, and which provider serves preview and which serves
production for the managed tier. Users of the managed tier have no Anthropic
credential of their own.

The deliverable lives in this repository. It is a spike report at
`docs/spikes/telegram-openai-tool-loop.md` plus a `SpikeDefinition` at
`roadmap/spikes/telegram-openai-tool-loop.yaml`. Measurements run in
mctl-telegram; no runtime code is merged by this spike. The timebox is a
decision by 2026-11-10, before the Anthropic promo credit ends on 2026-11-11.

## User stories
- AS the mctl-telegram owner I WANT measured evidence that the existing tool schemas work under OpenAI function calling SO THAT I can choose between building `OpenAIRunner` with no adapter and building a bounded schema adapter first.
- AS the platform owner I WANT p50/p95 latency, cost per job and the 429 count per candidate model SO THAT I can choose the preview provider and the production provider for the managed tier.
- AS a security reviewer I WANT the spike to keep gateway logging off and to keep message bodies out of every artefact SO THAT the evaluation leaks no user content.
- AS the roadmap maintainer I WANT a schema-valid `SpikeDefinition` with the four allowed outcomes SO THAT the decision is tracked like every other spike.

## Acceptance criteria (EARS)
- WHEN the spike is delivered THE SYSTEM SHALL contain `roadmap/spikes/telegram-openai-tool-loop.yaml` with kind `SpikeDefinition`, issue binding mctlhq/.github#293, outcomes `GO_HETZNER_DEV_NEBIUS_PROD`, `GO_NEBIUS_ONLY`, `NEEDS_SCHEMA_ADAPTER`, `NOT_A_FIT`, `timebox.decisionBy: "2026-11-10"`, `evidence.report: docs/spikes/telegram-openai-tool-loop.md`, and the manifest SHALL pass `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes`.
- WHILE the owner has not recorded a decision THE SYSTEM SHALL keep the manifest at `lifecycle: proposed` (or `active`) with no `decision` block. The report SHALL carry only a proposed verdict.
- WHEN the owner decides THE SYSTEM SHALL record `decision.verdict` (one of the four outcomes), `decidedAt`, `decidedBy` and the follow-up issues, and set `lifecycle: decided`.
- WHEN the smoke test runs THE SYSTEM SHALL record, for each of the 11 tools, whether the mcp-go v1.4 `Tool.InputSchema` marshals to a valid OpenAI `tools[].function.parameters` object without changes. Any keyword that a provider rejects or ignores SHALL be named.
- WHEN the smoke test runs THE SYSTEM SHALL record, per model, the result of 5 fixtures under `tool_choice: auto`: whether `get_context` was called, whether a proposal was made, whether the run ended with `complete_agent_job`, any hallucinated tool names, and any argument parse failures.
- WHEN the smoke test runs THE SYSTEM SHALL record whether `cf-aig-collect-log: false` and `cf-aig-skip-cache: true` are honoured on custom providers. Honoured means the gateway log total stays 0 and there are no cache hits.
- WHEN the smoke test runs THE SYSTEM SHALL answer whether a pool-level `audit_logs` row can have a NULL `user_id` under the Postgres foreign key, or whether auditing under the job's user is the only option.
- WHEN the runner interface of mctl-telegram slice 3 exists THE SYSTEM SHALL run the full C1 suite (`AGENT_C1_EVAL_PROMPT=catalog`) per model and record HarnessVersion, the suite digest, the classification score out of 32, leaks, binding violations, wrong auto-sends, p50/p95 latency, cost per fixture and the 429 count.
- IF the slice-3 runner interface does not exist before the timebox THEN THE SYSTEM SHALL say so in the report, mark the full-suite rows "not run" (never as a pass or a zero), and base any proposed verdict on the smoke test only, labelled as provisional.
- WHEN cost is reported THE SYSTEM SHALL compute it from the response `usage` tokens and the price table (Nebius GLM-5.1 1.40 / 4.40 USD per MTok; Hetzner 0), because the gateway reports cost 0 for custom providers.
- WHILE the spike runs THE SYSTEM SHALL change no production values, spend no more than USD 5 on Nebius, run Hetzner with `AGENT_OPENAI_MIN_INTERVAL=6s`, take keys only from Vault `secret/platform/mctl-support/model` (`hetzner-api-key`, `nebius-api-key`) and the gateway run token from Vault, and never use a laptop Keychain key.
- WHILE the spike runs THE SYSTEM SHALL keep gateway logging off, and no artefact (report, tables, logs) SHALL contain a message body, a secret or a token.
- IF the Nebius spend reaches USD 5 THEN THE SYSTEM SHALL stop the Nebius runs and report the partial results as partial.
- WHEN the report is written THE SYSTEM SHALL give a one-line verdict per model and a single proposed outcome, chosen by the decision rule in design.md.
- WHEN the report is merged THE SYSTEM SHALL list it under `# Spikes` in `AGENTS.md`.

## Out of scope
- Merging `OpenAIRunner` or any other runtime code into mctl-telegram. The schema adapter, if needed, is the follow-up of `NEEDS_SCHEMA_ADAPTER`.
- Changing any production or preview values in mctl-gitops, including `services/labs/mctl-telegram*/values.yaml` and `services/admins/mctl-support/values.yaml`.
- Evaluating Anthropic models or providers other than the three named candidates.
- Recording the owner's decision on the owner's behalf.
- Adding spikes to the RoadmapPublication (not supported yet, per `roadmap/README.md`).

## Open questions
- The mctl-telegram source was not available in this clone, so `buildToolSet`, the 11 tool names, the C1 harness, the `AGENT_OPENAI_MIN_INTERVAL` knob and the slice-3 runner interface were not read. Whether slice 3 lands before 2026-11-10 is unknown. The proposal handles this with a provisional, smoke-only verdict.
- The issue names two Hetzner models but outcome `GO_HETZNER_DEV_NEBIUS_PROD` treats "Hetzner" as one candidate. Assumption: Hetzner passes if at least one of the two models passes, and the report names that model.
- "Too slow" for Hetzner (outcome `GO_NEBIUS_ONLY`) has no threshold. Assumption: the report proposes a threshold based on `AGENT_TURN_MAX_WAIT`, and the owner confirms it.
- Whether `audit_logs` (mctl-telegram schema) permits a NULL `user_id` is unverified here. It is a smoke-test question, not a blocker.
- Where the C1 run executes (laptop with Vault-issued keys, or a cluster job) is not specified. Assumption: anywhere Vault keys are used directly, never a Keychain key.
