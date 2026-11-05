# Design: issue-313-spike-evaluate-agentic-trading-lab-patte

## Current state

### This repository (`mctlhq/.github`, clone HEAD `dc359d4`)

- Spike reports live in `docs/spikes/<name>.md`. The nearest prior art in form is
  `docs/spikes/journey-intent-correlation.md`: evidence pins table, evidence tags `[CODE]`,
  `[CONFIG]`, `[LIVE]`, `[DOC]`, "unknown (not observed)" never read as absent, proposed verdict
  only.
- SpikeDefinition manifests live in `roadmap/spikes/*.yaml`, validated against
  `roadmap/schemas/spike-definition.schema.json`. The required fields are `title`, `question`,
  `lifecycle`, `github.issue` and `outcomes` (at least 2, `^[A-Z][A-Z0-9_]*$`). A `decision` block
  is forbidden unless `lifecycle: decided`. The command is
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` (`roadmap/README.md` line 133).
  Tests are in `roadmap/tests/test_validate_spike.py`. CI runs `.github/workflows/roadmap-validate.yml`.
- `roadmap/spikes/journey-intent-correlation.yaml` and `roadmap/spikes/hetzner-inference-benchmark.yaml`
  show the proposed and decided shapes. There is no manifest for #313 yet.
- `roadmap/epics/agent-runtime-assurance.yaml` (epic .github#151, `lifecycle: active`, serialized
  required chain #694 -> #695 -> #696 -> #697 -> #698 -> #699 -> #700). The issue forbids adding a
  work item here, and this design does not touch it.
- `AGENTS.md` keeps the "Spikes" index list that the new report is linked from.
- A grep of this clone for `EvaluationSuite`, `AgenticTrading`, `mctl-agents#310`, `#526`, `#698`
  and `#854` returns nothing, so no existing report covers this question.

### Upstream: Open-Finance-Lab/AgenticTrading at `5a49d00a963e99b94b6c559d08a74cb03e1e3da2`

Read with `gh api` (1888 tree entries, pushed 2026-11-01, not archived):

| Pattern | Source evidence | Classification |
| --- | --- | --- |
| Decision tape: per decision, raw model intent vs post-gate actions, fills and rejections; versioned (`TAPE_VERSION = 3`); allow-listed fields; payload cap 60 KiB; an over-long field marks the order `unreplayable` instead of dropping the bar; "observational only" | `dashboard/backend/domain/backtesting/decision_tape.py`; tests `dashboard/backend/tests/domain/backtesting/test_decision_tape.py`, `test_decision_tape_engine.py`, `dashboard/backend/tests/test_trace_decision_tape.py`; spec `docs/superpowers/specs/2026-10-08-backtest-decision-tape-design.md` | implemented |
| Replay of a fixed decision sequence through two engines, so differences are attributable to the engine and not the model | docstring of `decision_tape.py` | implemented (as stated in code) |
| Deterministic reference agent used as baseline, pure and domain-only | `dashboard/backend/domain/backtesting/reference_agent.py` | implemented |
| Paired baselines (index, buy-and-hold) on the same window | `dashboard/backend/baseline_resolver.py`, `dashboard/backend/domain/leaderboard/baselines.py` | implemented; the time-window matching heuristic is domain-specific |
| Provenance honesty: billed `llm_calls` is never the coverage numerator; `llm_decisions` coverage guard (H6) catches runs where the model drove nothing | `dashboard/backend/domain/backtesting/provenance.py`; `dashboard/backend/tests/test_architecture_boundaries.py` | implemented |
| Trace store with export | `dashboard/backend/domain/traces/*.py` | implemented (Postgres-backed product store) |
| Local no-credentials mode | `dashboard/scripts/run_local_safe.sh`, `docs/local-run.md` (README: "blanks broker, LLM, DB, mail, Stripe and iFinD keys") | script present; not executed by this investigation (`not verified`) |
| FinAgent orchestration / agent pools / FinProtocol | `orchestration/FinAgents/**`, `docs/source/orchestration/*.rst` | documented, partly demo code; `not verified` |

License: the `LICENSE` file is OpenMDW-1.0 ("Model Materials", permissive, keep notices, patent
retaliation clause). GitHub reports SPDX `NOASSERTION`. The upstream is a full product (FastAPI,
Postgres, Stripe, Discord, brokers), and none of it is suitable as a dependency.

### MCTL current state: mctlhq/mctl-agents at `96b1f542b3a2e7b872e066c627742b0c1c3e7426`

| Need named in #313 | MCTL owner and state | Code on main |
| --- | --- | --- |
| Candidate vs baseline on pinned fixtures, deterministic oracle, repetitions, cost and tool counters, agent manifest hashes, `future_cost: unknown` | spike #791 (decided 2026-10-26), re-bench #825 | `tools/hetzner_inference_spike.py`, `tests/test_hetzner_inference_spike.py`, `docs/spikes/791/fixtures/{investigation,implementation,review,tool-use}/fixture.yaml` (each with `id`, `sha256`, `oracle`, `limits`), `docs/spikes/791/run-manifest-baseline.json` (agent manifest sha256 per agent, model, `model_policy_version`, `candidate_isolation`), `docs/spikes/791/records-baseline.jsonl` (per cell: `fixture_sha256`, `repo_sha`, `oracle_result`, `policy_denials`, `policy_bypasses`, `cost_usd_current`, `repetition`) |
| Policy-denied mutation fixture | #791 | `docs/spikes/791/fixtures/tool-use/fixture.yaml` lists `mcp__mctl__mctl_deploy_service` in `disallowed_tools` |
| Promotion gate: EvaluationSuite, PASS/REVIEW/BLOCK, hard invariants never judged by an LLM | mctl-agents#310 OPEN | not on main: no `EvaluationSuite` path in the tree. This is future scope. |
| Stored-context replay, committed baseline, curated fixtures (stale, conflicting) | mctl-agents#526 CLOSED 2026-09-28 | `orchestrator/context_eval.py`, `orchestrator/run_context_eval.py`, `tests/fixtures/context_eval/baseline.json`, `cases/02-stale-source.json`, `cases/05-conflicting-prior-proposal.json`, ADR 015 |
| Deterministic bounded harness, per-call `policy_checkpoint.decide`, verdicts `unknown` on early stop, byte-identical records under injected clock and seed | mctl-agents#695 (epic .github#151) | `orchestrator/assurance_harness.py`, ADR 023, `tests/test_assurance_harness.py` |
| Exact-version replay, false-positive handling | mctl-agents#698 OPEN | contracts `orchestrator/runtime_assurance.py` (ADR 022), fixtures `tests/fixtures/assurance/replay-run.json`, `replay-result.json`, `finding-rejected.json`, `result-violated.json`; lifecycle enforcement still open |
| Workflow decision replay | mctl-agents#251 | `tests/replay_scenarios.py` + Temporal `Replayer` (deterministic, no model) |
| Evidence join by reference (`we_`, `cs_`, `xr_`, usage key, `aar_`, policy `action_digest`) | mctl-agents#199 CLOSED, ADR 018 | `orchestrator/execution_evidence.py`, `orchestrator/evidence_producer.py`, `tests/fixtures/evidence/investigator-evidence.json` |
| Traces | mctl-agents#195 CLOSED | DevLoop traced (see deployed state) |
| Cost attribution | ADR 012 | `orchestrator/usage_ledger.py`, `orchestrator/run_usage_collector.py` |
| Observability signal gaps | mctl-agents#854 CLOSED (scout spike) | no code obligation identified here |

Dedup: `gh search issues "Open-Finance-Lab/AgenticTrading" --owner mctlhq` returns only .github#313.

### Deployed state checked

- `mctl_get_service_status admins/mctl-agents-worker`: ArgoCD Healthy, Synced, image tag `1.117.0`.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: `MCTL_TRACE_WORKFLOW_TYPES:
  DevLoopWorkflow`, `MCTL_TRACE_ARGO_PARAM: "true"`, `otel.enabled: true`. Sibling
  `mctl-agents-worker-exec` and `mctl-agents-worker-implement` directories exist (their values were
  not re-read).
- `mctl_resolve_agent issue-investigator production`: refused ("outside the investigate scope of
  this agent run"). The live investigator release is unknown.
- `mctl_get_usage_summary agent=issue-investigator`: HTTP 403 `agent_scope_denied`. Live
  investigator cost and latency are unknown.
- The upstream service was not run, and no upstream dependency was installed.

## Proposed solution

One documentation-only PR in `mctlhq/.github` with three files. No code, CI, epic or production
change.

### 1. `docs/spikes/agentic-trading-lab-patterns.md` (report)

Sections, in the style of `docs/spikes/journey-intent-correlation.md`:

1. **Non-claims and evidence tags.** Same tag vocabulary. "Not measured" and "unknown" are never
   read as absent or PASS.
2. **Evidence pins.** The upstream and mctl-agents SHAs above, plus the .github HEAD at write time.
3. **Upstream capability, maturity and license map.** The table above with permalinks
   `https://github.com/Open-Finance-Lab/AgenticTrading/blob/5a49d00.../<path>`, plus the OpenMDW-1.0
   summary and the decision "conceptual reuse only".
4. **Dedup and current-state matrix.** The MCTL table above, with on-main vs future scope per
   issue.
5. **Smallest transferable patterns and where they already live.**
   - Agent/environment boundary: present as the assurance harness owning target, credential and
     policy, with the probe choosing only the next permitted call.
   - Fixture + oracle + baseline: present as #791 fixtures and records.
   - Replay of a fixed decision sequence through a changed engine: present for workflows
     (Temporal `Replayer`) and specified for findings (#698).
   - Intent vs post-gate record: partially present. It is per-call in the harness transcript and
     aggregate counters only in #791 records. This is recorded as an input to #310's record design,
     not as a proven gap.
   - Coverage honesty (did the candidate actually drive the decision?): partially present. #791
     records include `observed_models` (for example sonnet plus haiku in one cell). This is
     recorded as an input to #310.
6. **Experiment protocol (offline, read-only, not run).**
   - Harness: `tools/hetzner_inference_spike.py` at the pinned SHA, inside the
     `docs/spikes/791/bench.Dockerfile` throwaway container. Candidate Bash must never run on a host
     with credentials, per `candidate_isolation` in `run-manifest-baseline.json`. The MCP servers
     are dropped.
   - Fixtures:
     - T1, straightforward investigator: `investigation-model-policy-v1`, sha256 `362d1c84...6f6ede`.
       The oracle is deterministic `facts` plus `cite`.
     - T2, stale/conflicting evidence: `tests/fixtures/context_eval/cases/02-stale-source.json` and
       `05-conflicting-prior-proposal.json` via `python -m orchestrator.run_context_eval`, scored
       against `tests/fixtures/context_eval/baseline.json`. This is deterministic, uses no model and
       needs no repetitions.
     - T3, policy-denied mutation: `tool-use-check-v1`, sha256 `dbbef307...a22`. The oracle is
       `RESULT=42`, and `disallowed_tools` includes `mcp__mctl__mctl_deploy_service`. The hard
       invariant is `policy_bypasses == 0`.
   - Arms: the baseline is the configuration recorded in `run-manifest-baseline.json`
     (`claude-sonnet-5-5`, profile `balanced`, `model_policy_version: 1`, agent manifest sha256
     values). The default candidate is the identical configuration (A/A), which measures run-to-run
     variance without an owner choice. A named #310 candidate replaces it only after the owner
     selects one.
   - Repetitions: 3 per stochastic (task, arm) cell, matching #791. Budgets come from the fixture
     `limits` (T1 $1.00 and 12 turns; T3 $0.50 and 10 turns). The total cap is 2 arms x 2 stochastic
     tasks x 3 reps, at most about $9. Stop conditions: any `policy_bypasses > 0`, any credential
     match by `orchestrator.redaction.contains_credential`, any budget exceeded, or any MCP call
     reaching a live server. Stopped cells are reported `unknown`.
   - Negative controls: (a) `tests/fixtures/assurance/result-violated.json` must be reported
     violated by `tests/test_assurance_harness.py`. (b) A T3 oracle with `RESULT=41` must FAIL.
     If either passes, the run is invalid.
   - Replay demonstration: deterministic replay is shown with `tests/test_workflow_replay.py` over
     recorded histories and with assurance `replay-run.json`. A live single-decision reconstruction
     from `we_`/`cs_`/`aar_` references is **blocked** for this agent run, as the scope denials above
     prove. A second LLM sample is never called a replay.
7. **Evidence schema reuse.** Run ids (`run_id`, `we_`, `wi_`), versions and hashes
   (`fixture_sha256`, `repo_sha`, agent manifest sha256, `model_policy_version`, AssuranceScenario
   `content_hash`), trace (DevLoop OTel), and immutable references (ADR 018 `EvidenceRef`). Each
   outcome is labelled deterministic or stochastic.
8. **Decision criteria.**

   | # | Criterion | Baseline source | Candidate | Status |
   | --- | --- | --- | --- | --- |
   | C1 | Deterministic invariant pass rate (oracle, `policy_bypasses == 0`) | #791 `records-baseline.jsonl` | A/A or a #310 candidate | baseline observed; candidate not measured |
   | C2 | Task success per (task, arm) and its variance across 3 reps | #791 records (tool-use 0/3 documented as an oracle artifact) | same | baseline observed; candidate not measured |
   | C3 | Cost per successful task | #791 `cost_usd_current` (observed, harness-reported); live usage ledger | same | estimated from #791; live unknown (403) |
   | C4 | p50/p95 latency | none meaningful at n=3 | n/a | not measured |
   | C5 | Trace/evidence coverage (fraction of cells joinable to `we_` + EvidenceRef) | bench cells have no `we_` | n/a | unknown |
   | C6 | Gap test: does any upstream pattern detect a regression that the existing artifacts miss? | analysis in section 5 | n/a | no demonstrated case |

9. **Security, privacy, policy and license review and stop conditions.** No credentials, no
   unredacted content, no live MCP, no production. Identity, approval and policy remain canonical.
   License review as above.
10. **Ownership map.** Promotion gating and record design go to mctl-agents#310. Replay
    confirmation goes to mctl-agents#698. Context replay is #526 (done). There is no new owner and
    no new surface.
11. **Proposed verdict: `REUSE_EXISTING_ONLY`.** C6 shows no demonstrated gap, and every transferable
    pattern has an existing MCTL owner. Rejected alternatives:
    - `ADAPT_EXISTING_EVALS`: the adapter target (`EvaluationSuite`) is not on main yet, so an
      adapter now would precede its owner's schema.
    - `BOUNDED_SANDBOX_PILOT`: no surviving gap.
    - `NO_ADOPTION`: the concepts are cheap to cite, carry no license or security risk, and are
      useful to #310.

    Suggested (not filed) follow-up: an owner-approved comment on mctl-agents#310 listing the two
    record-design inputs (intent vs post-gate per decision; decision-coverage honesty).

### 2. `roadmap/spikes/agentic-trading-lab-patterns.yaml`

```yaml
# Proposed verdict (REUSE_EXISTING_ONLY) lives in the report only. The owner
# records the decision block; an agent does not record its own approval.
apiVersion: roadmap.mctl.ai/v1alpha1
kind: SpikeDefinition
metadata:
  name: agentic-trading-lab-patterns
  owner: mctlhq/.github
spec:
  title: Agentic Trading Lab patterns for reproducible MCTL agent experiments
  question: >-
    Can MCTL reuse Agentic Trading Lab's traceable agent-experiment,
    comparable-baseline and sandbox simulation patterns to improve
    reproducible DevLoop evaluation without creating another runtime,
    evaluator or governance framework?
  lifecycle: proposed
  github:
    issue:
      repository: mctlhq/.github
      number: 313
  outcomes:
    - REUSE_EXISTING_ONLY
    - ADAPT_EXISTING_EVALS
    - BOUNDED_SANDBOX_PILOT
    - NO_ADOPTION
  execution:
    devloop: true
  evidence:
    report: docs/spikes/agentic-trading-lab-patterns.md
```

There is no `epic` link. The issue says the relationship with .github#151 is a discovery relationship,
not a materialized edge.

### 3. `AGENTS.md`

Append one bullet to the "Spikes" list, following the existing format:
`- [Agentic Trading Lab patterns](docs/spikes/agentic-trading-lab-patterns.md): spike report for
mctlhq/.github#313, proposed verdict REUSE_EXISTING_ONLY.`

## Alternatives

- **Write an adapter now under mctl-agents (`ADAPT_EXISTING_EVALS`).** Dropped because #310 has
  no `EvaluationSuite` on main. An adapter would fix a schema its owner has not defined, which the
  issue explicitly forbids ("do not duplicate its schema or gates").
- **Run the experiment inside this spike before writing the report.** Dropped as the default. The
  investigate scope cannot reach the usage ledger or the release binding, and running candidate
  arms needs a credential-free throwaway host and owner budget. The protocol is shipped ready to
  run, and results stay `not measured`.
- **Add a required work item to .github#151.** Dropped. The issue forbids it, and #698 already owns
  replay confirmation.
- **Vendor upstream `decision_tape.py`.** Dropped. It is coupled to the trading engine and
  Postgres trace store, OpenMDW requires notice retention, and the concept is about 20 lines of
  record design.

## Platform impact

- Migrations: none. Backward compatibility: one new manifest. `validate.py` enforces unique spike
  names and issue bindings, and .github#313 is not bound anywhere else.
- Resource impact: none. The experiment is not executed by this change. If the owner later runs it,
  the cap is about $9 on a throwaway host.
- Risk: the report could be read as an owner decision. Mitigation: `lifecycle: proposed`, no
  `decision` block, and "proposed verdict" wording, as in the journey-intent-correlation precedent.
- Risk: claims about mctl-agents go stale. Mitigation: every claim is SHA-pinned and tagged.
- Risk: invented results. Mitigation: every unmeasured cell is labelled `not measured` or `unknown`,
  and the scope-denial blockers are quoted.
