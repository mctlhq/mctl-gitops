# Spike report: Agentic Trading Lab patterns for reproducible MCTL agent experiments (mctlhq/.github#313)

## Context

Issue mctlhq/.github#313 asks whether MCTL can reuse the experiment methodology of the upstream
Agentic Trading Lab (https://github.com/Open-Finance-Lab/AgenticTrading). That methodology covers
traceable agent decisions, comparable baselines and the separation between an agent and its
simulated execution environment. The goal is to make DevLoop evaluation reproducible without
adding another runtime, evaluator, evidence store or governance framework. Trading itself is out of
scope. The issue fixes four outcomes (`REUSE_EXISTING_ONLY`, `ADAPT_EXISTING_EVALS`,
`BOUNDED_SANDBOX_PILOT`, `NO_ADOPTION`). Its default is `REUSE_EXISTING_ONLY` unless a measurable
gap is demonstrated.

This repository (`mctlhq/.github`) holds spike reports (`docs/spikes/*.md`), SpikeDefinition
manifests (`roadmap/spikes/*.yaml`, schema `roadmap/schemas/spike-definition.schema.json`) and the
spike index in `AGENTS.md`. The deliverable has three parts: a source-pinned report, a
`lifecycle: proposed` SpikeDefinition with the four outcomes and no `decision` block, and an index
entry. The investigation found that mctl-agents `main` already has most of the patterns the issue
names: fixture-pinned baseline/candidate benches (#791), a deterministic bounded harness (#695),
replay contracts (#694/#698) and context-eval replay (#526). The proposed verdict is therefore
`REUSE_EXISTING_ONLY`, and the owner records the final decision.

## User stories

- AS the spike owner I WANT a source-pinned map of which upstream patterns are implemented versus
  marketing SO THAT the adoption decision rests on code, not on README claims.
- AS the mctl-agents#310 owner I WANT a dedup matrix against #310, #526, #698, #854, #195 and #199
  SO THAT no second evaluation schema, gate or store is proposed.
- AS a reviewer I WANT a bounded, read-only experiment protocol with pinned fixtures, a negative
  control and explicit `observed`/`estimated`/`not measured`/`unknown` metrics SO THAT any later
  run is comparable and no result is invented.
- AS the roadmap maintainer I WANT a valid `lifecycle: proposed` SpikeDefinition SO THAT the spike
  is tracked without implying an owner decision.

## Acceptance criteria (EARS)

- WHEN the report is written THE SYSTEM SHALL pin every upstream claim to commit
  `5a49d00a963e99b94b6c559d08a74cb03e1e3da2` of Open-Finance-Lab/AgenticTrading with permalinks.
  Each claim SHALL be classified as `implemented` (source and tests present), `documented only` or
  `not verified`.
- WHEN the report describes the upstream license THE SYSTEM SHALL record it as OpenMDW-1.0 (GitHub
  reports `NOASSERTION`) and SHALL state conceptual reuse only: no vendored code and no dependency.
- WHEN the report describes MCTL current state THE SYSTEM SHALL pin mctl-agents commit
  `96b1f542b3a2e7b872e066c627742b0c1c3e7426`. It SHALL separate "on main" from "future scope" for
  #310 (no `EvaluationSuite` on main), #526 (closed; `orchestrator/context_eval.py`,
  `orchestrator/run_context_eval.py`), #698 (open; contracts in `orchestrator/runtime_assurance.py`,
  harness in `orchestrator/assurance_harness.py`), #854 (closed spike), #195 and #199 (closed;
  ADR 018 evidence envelope).
- WHEN the experiment protocol is written THE SYSTEM SHALL name exact fixtures by id and sha256, the
  baseline and candidate arms, repetitions, per-cell budget, the deterministic oracle and at least one
  negative control. It SHALL reuse `tools/hetzner_inference_spike.py` and its fixtures rather than a
  new harness.
- IF the experiment was not run THEN THE SYSTEM SHALL label every result cell `not measured`. It
  SHALL record the precise blocker with proof and SHALL NOT present a second LLM sample as a
  deterministic replay.
- WHEN decision criteria are listed THE SYSTEM SHALL provide at least three measurable criteria. For
  each it SHALL give the baseline source, the candidate source and its status (`observed`,
  `estimated`, `not measured` or `unknown`).
- WHILE any invariant is scored THE SYSTEM SHALL use a deterministic check (oracle, policy
  checkpoint decision or allowlist), never only an LLM judge.
- WHEN the SpikeDefinition is added THE SYSTEM SHALL validate with
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes`. It SHALL carry
  `lifecycle: proposed`, exactly the four issue outcomes and `github.issue` `mctlhq/.github#313`,
  with no `decision` block.
- WHEN the report states a verdict THE SYSTEM SHALL state exactly one proposed verdict from the four
  outcomes. It SHALL list rejected alternatives and SHALL say the decision belongs to the owner.
- IF the report names follow-ups THEN THE SYSTEM SHALL describe them as suggestions to existing
  owners (mctl-agents#310, #698) that require owner approval. It SHALL NOT create issues, edit
  EpicDefinitions or change CI gates.
- WHILE this spike is open THE SYSTEM SHALL NOT mutate production, install upstream dependencies or
  write to GitHub/GitOps as part of the experiment.

## Out of scope

- Trading, backtesting, market data, brokers, payments or investment content.
- Any new runtime, control plane, evaluation database, trace store, dashboard or approval/policy
  gate.
- Running the experiment against production workers, live user data or credentials.
- Editing `roadmap/epics/agent-runtime-assurance.yaml` or any other EpicDefinition.
- Recording the `decision` block (the owner does this after review).
- Changes to mctl-agents code, `.github/workflows/*` or release gates.

## Open questions

- The investigator could not read the live agent release binding or usage ledger. Both
  `mctl_resolve_agent issue-investigator production` and `mctl_get_usage_summary` were refused as
  outside the investigate scope. Baseline cost and latency for the investigator are therefore
  `unknown` here, and the report uses the committed #791 baseline records instead. An operator run
  could fill this in.
- Should the bounded experiment actually be run before the owner decides, and if so with what
  budget? The proposal assumes not: the report ships the protocol with results `not measured`,
  matching the issue's "results if actually run" wording.
- The upstream "decision tape" keeps raw model intent and post-gate actions per decision. Whether
  this adds anything to #310 beyond the per-call `policy_checkpoint.decide` transcript in
  `assurance_harness.py` is undemonstrated. Only the #791 bench records keep aggregate counters
  (`policy_denials`, `policy_bypasses`). The report records it as a candidate input to #310, not a gap.
- No `timebox.decisionBy` was given in the issue, so the manifest omits it (allowed for `proposed`).
