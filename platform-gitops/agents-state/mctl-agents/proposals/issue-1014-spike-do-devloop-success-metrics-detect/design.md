# Design: issue-1014-spike-do-devloop-success-metrics-detect

## Current state

What counts as "success" today, by source:

- **Bench pass-rate (model swaps).** `tools/hetzner_inference_spike.py` produced the #791 records
  (`docs/spikes/791/...`, report `docs/spikes/791-hetzner-inference.md`), and #825
  (`docs/spikes/825-qwen38-effort-rebench.md`) reuses that shape. Each cell carries an oracle verdict
  `pass`/`fail` plus `turns`, `tool_calls`, input and output tokens, `wall_clock_s`, `outcome`,
  `failure_class` and stop reason. #796 records (`docs/spikes/796/results/*/records.jsonl`) have the same
  fields plus `classifier_interruptions` and a truncated `final.summary` with a sha256. The verdicts read
  oracle passes per cell. #791 line 72 notes that raw transcripts were not recorded, so answers "cannot be
  re-scored". In those tables Sonnet and Qwen investigation cells both `pass` with very different token
  and turn counts. That is an existing real example of equal pass-rate and different secondary metrics.
- **Mechanical eval.** `tools/model_smoke.py --eval` reports accuracy on two fixed workloads. Its own
  docstring says it is no evidence for judgement tasks.
- **Lifecycle outcome.** mctl-gitops `agents-state/<service>/proposals/<slug>/.status.yaml`, written by
  `orchestrator/proposal_state.py` and the DevLoop activities. For mctl-agents (180 proposals): 113
  `merged`, 11 `rejected`, 10 `needs-triage`, 28 `accepted`, 16 `proposed`, 2 `implemented`. The
  `completion.authoritative` block (`orchestrator/implementation_completion.py`, ADR 021) carries
  `outcome`, `stop_reason` (53 `gates_passed`, 6 `no_commits`) and
  `verification.required_passed/required_total`.
- **Retrieval quality.** `orchestrator/context_eval.py` (ADR 015) scores what the model was shown,
  explicitly not what it did. ADR 019 requires `evidence.kind: context-eval` only for
  context-strategy promotion.
- **Usage and cost.** `orchestrator/usage_ledger.py` `UsageRecorder` sends per-turn token deltas to
  mctl-api, which aggregates them per DevLoop stage.
- **Traces.** `orchestrator/tracing.py` `AgentRunObserver`. Spike #854
  (`docs/spikes/854-agent-observability-gaps.md`) lists what is missing: G1 eval results on the trace,
  G2 run outcome attributes, G3 agent RED metrics (#871 to #873 filed), and G4 to G7 (deferred).
- **Finding validity.** Spike #918 (`docs/spikes/918-finding-oracle-classes.md`,
  `tools/spike_918_finding_oracles.py`) classifies which review findings have a deterministic oracle.
  Its offline-harness, `origin: real|control` and `unknown`-is-not-zero conventions are reused here.
- **Release gates.** mctl-gitops `release-gates.yaml` guards image-tag grouping and version holds only.
  It checks no quality metric.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker-exec/values.yaml`: image tag `1.117.0`,
  `otel.enabled: true`, `MCTL_TRACE_WORKFLOW_TYPES: DevLoopWorkflow`, `MCTL_TRACE_ARGO_PARAM: "true"`.
  DevLoop traces are exported, and other workflow types are not.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/*/.status.yaml` (180 files, grep counts above):
  `execution.version` is `''` in all 108 records that carry an `execution` block, so no outcome is
  attributable to an agent or model version from this source. `review_attempts`, `ci_blockers` and
  `ci_infra_retries` appear in 1 file. No field records a revert or a follow-up fix of a merged PR.
- `$MCTL_GITOPS_ROOT/release-gates.yaml`, `release-bindings.yaml`: image and version gates only.
- `mctl_get_usage_summary` (group_by outcome): **refused**, HTTP 403 `agent_scope_denied`. Live per-stage
  cost and latency were not observed. That is not the same as absent.
- Article URL via WebFetch: **HTTP 403**. Its seven modes were not observed.
- mctlhq/.github#313 and mctl-agents#848 bodies: not observed (no GitHub read in this run). #848 is
  referenced in `docs/spikes/670-decision-context.md` line 159 as timing the owner on high-risk approvals.

## Proposed solution

A docs and offline-harness spike in the style of #918. It changes no runtime behaviour.

1. **Duplicate map** (`docs/spikes/1014-regression-metrics.md`, section 1). For #918, #854 (and #871 to
   #873), #848, .github#313, ADR 015/019/021 and #60, record read/not-observed and which mode each
   already owns. Every follow-up is attached to one of these owners.

2. **MCTL breakage-mode taxonomy** (section 2), each mode with its existing signal or `missing`:

   | id | mode | existing signal (producer) | state |
   |---|---|---|---|
   | M1 | cost inflation at equal outcome | bench `usage`; `usage_ledger.UsageRecorder` | emitted (bench, ledger) |
   | M2 | latency / turn inflation | bench `wall_clock_s`, `turns`; `attempt.started_at/finished_at` | emitted, not compared |
   | M3 | tool churn / tool errors | bench `tool_calls`; trace `execute_tool` spans | emitted, no metric (G3) |
   | M4 | silent scope narrowing (fewer tasks done, `no_commits`) | `completion.stop_reason`, `verification.required_*` | partial |
   | M5 | review/CI loop inflation | `review_attempts`, `ci_blockers` (.status.yaml) | 1 of 180 records |
   | M6 | post-merge regression (revert, follow-up fix) | none | missing |
   | M7 | guardrail pressure (policy denials, classifier interrupts, 429s) | `mctl.policy.decision` events; #796 `classifier_interruptions` | partial (G4 deferred) |
   | M8 | unscored answer-quality drift (output truncated, not re-scorable) | #796 `final.sha256` only | missing |
   | A0 | attribution: which agent/model version produced the outcome | `.status.yaml execution.version` (empty); mctl-api agent executions | broken in gitops |

   The section ends with the open mapping to the article's seven modes, marked not observed.

3. **Offline harness** `tools/spike_1014_regression_metrics.py` (stdlib plus `yaml`, already a
   dependency):
   - Inputs, all committed: the #791, #796 and #825 `records.jsonl` and snapshot files, plus a
     `docs/spikes/1014/status-corpus.yaml` extract of the mctl-agents `.status.yaml` fields listed above.
     The extract is copied by the implementer from mctl-gitops, contains no secrets, and every record is
     checked with `orchestrator.redaction.contains_credential` before it is committed.
   - Real comparison: for each bench pair at equal pass-rate (for example Sonnet vs Qwen on #791
     investigation), report per arm pass-rate, success, tokens, turns, wall clock, tool calls and error
     counts, with `unknown` where a field is absent.
   - Perturbation controls: for each mode M1 to M8, apply a deterministic transform to a copy of real
     baseline records (for example tokens x1.5, +3 turns, +2 failed tool calls, `no_commits` on 1 in 5,
     +1 review round, truncated final) that keeps the oracle `pass` unchanged where the mode is
     pass-preserving. Mark the result `origin: control`.
   - Detection rule: a mode is `DETECTED_BY_PASS_RATE` if pass-rate moves by at least one cell,
     `DETECTED_ONLY_BY_SECONDARY` if pass-rate does not move but a listed secondary metric crosses its
     provisional threshold, `UNDETECTED` if neither moves, and `UNKNOWN` if the inputs are missing
     (M6 today).
   - Lifecycle side: from the status corpus, compute what an outcome-rate metric (merged / terminal) can
     and cannot localize. That includes the A0 count of records with an empty version, and the
     coverage of M4 and M5 fields.
   - Output `docs/spikes/1014/results.json`, with a `--results` flag and a deterministic sort. Each run
     is costed (0 USD, no model) and timed.

4. **Recommendation and follow-ups** (section 4). One decision token, owner to confirm. The likely
   follow-up candidates, filed only if the evidence proves them:
   (a) populate `execution.version` (A0), owner: proposal-state writer and DevLoop activities;
   (b) add secondary metrics to the #791/#825 bench report template;
   (c) add a post-merge revert or follow-up signal, folded into #871 (G1 `pr.outcome`) and not a new
   producer;
   (d) persist review and CI round counts for every proposal, owner: shepherd.

Why this way: it falsifies the question on real MCTL records without spending model budget and without
touching authority paths. It follows the accepted #918 and #854 spike conventions. Every follow-up stays
under an existing owner.

## Alternatives

- **Live A/B DevLoop run on two models.** It gives the strongest evidence, but costs about $3 or more
  per investigator run, needs rollout of a candidate binding, and widens authority during a spike.
  Dropped. Recommend it as a follow-up only if the offline result is inconclusive.
- **Adopt the article's seven modes verbatim.** That is not possible (source not observed), and it would
  rest on vendor claims that the issue rules out.
- **Implement the G3 RED metrics now and observe.** That duplicates #873 and is implementation before
  the decision, which the issue's non-goals forbid.

## Platform impact

- No migrations. No runtime, gitops, CWFT or policy change. New files only under `docs/spikes/1014*` and
  `tools/spike_1014_regression_metrics.py`, plus one test.
- Resource impact: none at runtime. The harness runs in under a second locally.
- Risks:
  - Controls prove only that a metric can see an injected change, not a production rate. Mitigation:
    real and control metrics are reported separately, with the #918-style caveat.
  - Copying status data could leak something sensitive. Mitigation: field allowlist plus a
    `contains_credential` screen and a test asserting it.
  - Thresholds may be read as gates. Mitigation: a non-authorization statement as in ADR 015 and #854,
    and the test also asserts nothing in `orchestrator/` imports the tool.
