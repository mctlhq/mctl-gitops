# Design: issue-556-spike-governance-compare-jev-and-clef-de

## Current state

The authoritative governance path is deterministic and already complete for its scope.

- `orchestrator/policy_checkpoint.py` (ADR 014, `docs/adr/014-policy-checkpoint.md`) is the single decision point:
  - `ActionRequest -> decide() -> ALLOW | DENY | REQUIRE_APPROVAL`.
  - `ActionRequest` describes an action without its payload: `action_kind`, `operation`, `target`, `args_digest`, `execution_id`, `actor`, `grants`, and `metadata` (safe values only).
  - `evaluate()` is a pure first-match over `Policy.rules` using fnmatch on `operation`, with an optional `requires_grant`.
  - `decide()` never raises. Every failure maps to a DENY code; `UNDECIDED_CODES` covers evaluator, identity and approval-lookup errors.
  - Every decision is emitted as a `POLICY_DECISION` line.
- `BUILTIN_POLICY` (`mctl-agents/policy/v1`) is closed-world:
  - Each orchestrator mutation has its own exact ALLOW rule: `github-push-new-branch`, `github-pr-merge`, `mctl-seal-context-snapshot`, and others.
  - MCP read verbs (`get_`, `list_`, `read_`, `search_`, `describe_`) are ALLOW behind a grant.
  - Every other `mcp__mctl__*` tool hits `mctl-mcp-default-approval` (REQUIRE_APPROVAL).
  - Anything unlisted is `no_matching_rule`, which is a DENY.
  - Variants (`MERGE_APPROVAL_POLICY`, and the misconfigured-DENY policy from `configured_policy()`) only ever tighten.
- `orchestrator/action_approvals.py` is the durable single-use approval seam (mctl-api#366, #198).
- `orchestrator/options.py` (around line 916) installs the MCP `PreToolUse` hook that runs `policy_checkpoint.checkpoint` for `MCP_TOOL_CALL`. ADR 014 "Consequences" notes that this hook is synchronous and that a gated checkpoint can already wait about 20 s on approval-store calls.
- `orchestrator/execution_evidence.py` carries `PolicyDecisionRef` (`action_digest`, `verdict`, `code`, `policy_version`, `rule_id`, `approval_ref`) into the evidence envelope (ADR 018).
- `orchestrator/runtime_assurance.py` (ADR 022, #694) is the existing pattern for "model output that never becomes authority": models may only author bounded proposals or finding text, and a candidate stays a candidate until a deterministic replay confirms it. The same file states the reuse map, which says to reference `canonical_json`/`hash_bytes`, `redaction.contains_credential` and `PolicyDecisionRef`, never to copy them.
- `orchestrator/redaction.py` provides `contains_credential` and the key and value screens used by tracing and evidence.
- `orchestrator/capability_gateway.py` already treats MCP `ToolAnnotations` as advisory only (ADR 017 sec. 8), which is the same trust stance this spike needs for tool descriptions.
- Precedents for benchmark tooling outside `orchestrator/`:
  - `tools/capability_bench.py` keeps pure functions unit-tested from recorded fixtures, with thin I/O wrappers.
  - `tools/model_smoke.py` runs a fixed eval with constant inputs, JSON-only answers and a malformed-JSON count.
  - Results are written up as `docs/benchmarks/*.md` and `docs/spikes/*.md`, for example `docs/benchmarks/haiku-5-5-cheap-profile.md` and `docs/spikes/661-canonical-capabilities.md`.
- Dependencies (`pyproject.toml`): `httpx==0.28.1` is already a direct, pinned dependency. Neither a Cloudflare nor a TypeSafe SDK is present, and nothing in the repository references Clef, Jev or TypeSafe (checked with grep).

What the closed-world policy implies: a semantic signal cannot add a decision that is not already there. It can only:
1. escalate an action that a rule ALLOWs (the orchestrator's own narrow mutations, and granted MCP reads);
2. annotate a REQUIRE_APPROVAL request so the human approver sees a risk summary;
3. act as triage outside the checkpoint (scenarios C and D).

The spike has to test whether any of these is worth a dependency.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/` lists `mctl-agents-worker`, `mctl-agents-worker-exec` and `mctl-agents-worker-implement`. This confirms the agents run in tenant `admins`.
- `services/admins/mctl-agents-worker/values.yaml`:
  - The env block contains `TEMPORAL_*`, `LIFECYCLE_ROLLOUT_MODE: observe`, `MCTL_TRACE_*` and `LOG_LEVEL`.
  - It has no `MCTL_POLICY_APPROVALS` and no `MCTL_POLICY_MERGE_APPROVAL`, so the deployed worker runs `BUILTIN_POLICY` with `NO_APPROVALS`.
  - Nothing references Cloudflare, Workers AI, TypeSafe, Clef or Jev (grep over `services/`).
  - The root filesystem is read-only, with writable `/tmp` and `/home/app/.local`.
- `tenants/admins/values.yaml` sets `allowClusterEgress: true` and `allowInternetEgress: true`, so a one-off pod in that namespace can reach both vendor APIs.
- No mctl MCP tool calls were made. The gitops checkout covered the configuration questions. Live pod behaviour and region were not observed; the physical region of the cluster is not recorded in the files read, and it is listed under Open questions in requirements.md.
- The vendor APIs (`api.typesafe.ai`, Cloudflare Workers AI) were not reachable from this run and were not checked, so the model IDs, prices and context limits quoted in the issue are unverified.

## Proposed solution

The spike is a standalone harness plus fixtures plus a results document. Nothing is wired into production.

### 1. Location and isolation

- `tools/semantic_decision_spike.py` is a single file, following the precedent of `tools/capability_bench.py` (pure core, thin I/O shell). It imports from `orchestrator` only these read-only pieces:
  - `policy_checkpoint`: `ActionRequest`, `evaluate`, `BUILTIN_POLICY`, `MERGE_APPROVAL_POLICY`, and the verdict constants;
  - `context_snapshot.canonical_json` and `hash_bytes`;
  - `redaction.contains_credential`.
- Nothing in `orchestrator/` imports it. A test enforces that rule by grepping `orchestrator/` for `semantic_decision`.
- Network access uses `httpx`, which is already pinned. No new dependency is added to `pyproject.toml` or `uv.lock`.

### 2. Canonical contract (schema `semantic-decision/v1alpha1`)

```text
SemanticDecisionRequest
  schema_version, fixture_id, scenario (A|B|C|D)
  execution: execution_id, actor, agent, profile_version      # canonical identity only
  action: action_kind, operation, target, grants[]            # mirrors ActionRequest
  resource: environment (fixture|shadow|production), resource_kind, bounded attrs
  evidence: bounded list of {kind, present: bool}             # scenario C/D only
  untrusted: tool_description?, model_claims[]?               # always delimited, never facts
SemanticDecisionResult
  schema_version, provider, model, model_version, endpoint
  categories[] subset of {read_only, state_changing, production_impact, destructive,
                          external_comm, spend, credential_identity, approval_likely}
  confidence (0..1) | probabilities{label: p}
  recommendation in {LOW_RISK, REVIEW, HIGH_RISK}
  reason_codes[] (closed set), latency_ms, input_tokens, estimated_cost_usd
  signal_status in {ok, timeout, error, malformed, low_confidence}
```

- Requests are built from fixtures through a builder. The builder:
  - rejects any value for which `contains_credential` is true;
  - enforces per-field length bounds (256 characters, matching `redaction.MAX_ATTRIBUTE_CHARS`);
  - places tool descriptions and model claims only under `untrusted`.
- The results contain no field that expresses allow or grant. This mirrors the "Field authority" rule of ADR 022.

### 3. Providers (`DecisionProvider` protocol)

- `typesafe-jev`:
  - At start-up, call `GET /v1/models` and record the resolved name for `jev-latest`.
  - Send the decision request in whatever schema the vendor documents at `https://api.typesafe.ai/redoc`, and record the request schema.
- `cloudflare-clef-flash`:
  - Use the Workers AI REST endpoint for `@cf/cloudflare/clef-flash`, with the account ID and token taken from the environment.
- `cloudflare-clef` (optional): an accuracy reference, run only if Clef-flash quality is insufficient.
- `replay`: serves recorded, sanitized responses. This is what unit tests and CI use, so the suite makes no network calls.
- Every provider gets a hard client timeout (default 1 s), at most 1 retry, and the decoded body is validated against the result schema. Any deviation returns `signal_status != ok` with no recommendation.
- Vendor-specific semantics stay inside the provider, which maps them onto the closed vocabulary. Unmapped labels count as `malformed`.

### 4. Authority combinator (the core safety property)

```text
STRICTNESS = {ALLOW: 0, REQUIRE_APPROVAL: 1, DENY: 2}
combine(det_verdict, result, threshold) -> simulated_verdict:
  if det_verdict != ALLOW: return det_verdict
  if result.signal_status != ok: return det_verdict      # fail closed w.r.t. relaxation
  if result.recommendation == HIGH_RISK and conf >= threshold: return REQUIRE_APPROVAL
  return det_verdict
```

- The combinator never returns DENY on a model signal. Escalating to a human is the strongest effect a model may have, so the spike cannot invent a model-authored hard deny either.
- `REVIEW` is recorded only as an annotation.
- The simulated verdict is a measurement artefact. It is never passed to `decide()`.

### 5. Fixtures

- Location: `tests/fixtures/semantic_decision/v1/*.json`.
- Each fixture carries: the request, `deterministic_verdict` (recomputed and asserted in tests from `evaluate(BUILTIN_POLICY, ActionRequest(...))`), `expected_recommendation`, `danger` (bool), `label_status` (`agreed` or `contested`), `pair_id` (for minimal pairs), and `notes`.
- At least 40 fixtures in total, with at least 6 per scenario, covering the classes listed in requirements.md.
- At least 10 of them are `danger: true` with `deterministic_verdict: ALLOW` (the escalation-relevant set).
- Each fixture also records `labelled_by` and `confirmed_by` (two different people; the second labeler is a named reviewer on the spike PR).
- Historical shapes from mctl-agents#183 and mctl-telegram#602 are rewritten as synthetic, sanitized equivalents.

### 6. Measurement and report

- `run` command: fixtures x providers x N repeats. Output is a JSONL record per call containing the fields from requirements.md, plus the deterministic and simulated verdicts. Prompts and completions are excluded unless `--record-raw` is given.
- `report` command: a pure function from JSONL to markdown. It computes:
  - accuracy, broken down by scenario;
  - dangerous false negatives, listed per fixture;
  - escalation rate;
  - malformed rate;
  - p50 and p95 latency;
  - stability;
  - a calibration table (5 bins) and Brier score;
  - the adversarial subset;
  - cost at 1k, 100k and 1M decisions, using measured median tokens and the price recorded at run time.
- The deterministic-only baseline is computed from the fixtures alone, with zero latency and zero cost.
- Replay-only (owner, 2026-10-23): there is no live run in this spike. The live providers are written and tested against recorded or synthetic responses; the report shows the deterministic-only baseline and the harness output on replay data, and marks every live metric (latency, accuracy, cost, calibration per vendor) as "not measured". A live run, from a one-off pod in `admins` with a hard spend cap and a named approver, is a follow-up issue whose body the report includes.

### 7. Spike document

`docs/spikes/556-semantic-decision-models.md` contains:
- the metrics table from the issue;
- per-scenario findings;
- answers to the ten questions;
- the trust boundary and failure semantics (section 4 above);
- audit and trace fields;
- self-hosting notes;
- the recommendation, checked against each GO criterion.

What happens next depends on the recommendation:
- **Not `NO_GO`**: the document names the proposed integration point, most likely a post-`evaluate` annotation in `decide()` or a step in the `PreToolUse` hook in `options.py`, applied only to ALLOW-ruled actions. It also names the new `POLICY_DECISION` fields: `semantic.provider`, `semantic.model`, `semantic.recommendation`, `semantic.signal_status`, `semantic.latency_ms`. The integration itself is left for a follow-up issue.
- **`NO_GO`**: the document lists the deterministic `Rule`s that would cover the useful cases instead.
- **Reuse for .github#151 and #310**: the fixture set and the `report` function are proposed as an offline eval suite, independent of the runtime decision.

## Alternatives

1. **Put the adapter in `orchestrator/` behind a feature flag (for example `MCTL_SEMANTIC_SIGNAL=shadow`) and call it from `decide()` in shadow mode.** This would give real traffic data, but it puts a network call and a vendor dependency on the governed path and needs gitops secrets. The issue explicitly forbids production wiring before GO. Dropped.
2. **Use the existing Claude cheap profile (`claude-haiku-5-5`, `tools/model_smoke.py`) as the classifier instead of a dedicated decision model.** No new vendor is needed, but the measured median latency is about 1.3 s per query (`docs/benchmarks/haiku-5-5-cheap-profile.md`), which is too slow for synchronous gating. It also answers a different question from the one the issue asks. The design records it only as an optional third reference row if time permits, not as a required comparison.
3. **Skip the models and only author more deterministic rules.** This is the safest and cheapest option, and the spike keeps it as the baseline and as the default outcome (`NO_GO`). Choosing it a priori would leave the issue's questions unanswered, so it is measured against the models rather than assumed.

## Platform impact

- **Migrations and backward compatibility**: none. The spike adds new files under `tools/`, `tests/` and `docs/spikes/`. No production module, policy version, env var or gitops value changes. `BUILTIN_POLICY` and its version string stay untouched, so existing approval intent hashes are unaffected.
- **Resource impact**: none beyond CI. The spike is replay-only: no operator pod, no vendor calls, no spend. CI runs only the replay provider and makes no network calls. (For the follow-up: about 40 fixtures x 2 providers x 5 repeats = about 400 calls, under $0.05 at the quoted list prices, still to be capped and approved.)
- **Risks and mitigations**:
  - *Leakage to vendors*: only synthetic or sanitized fixtures are sent. The builder screens with `contains_credential` and enforces length bounds. There is no raw persistence by default.
  - *Accidental production import*: a test asserts that `orchestrator/` does not reference the spike module.
  - *Model output treated as authority*: there is a property test over every fixture x every possible result (each recommendation x each signal status x confidence extremes), asserting that `STRICTNESS[combine] >= STRICTNESS[det]` and that `combine` never yields ALLOW when `det != ALLOW`.
  - *Vendor facts drift or are wrong*: the harness records resolved model IDs and the run-time price input, and the document states the observation date.
  - *Fixture policy drift*: the recorded deterministic verdict is re-asserted against `evaluate` in tests, so a policy change shows up as a failing test, not as stale results.
  - *Credential handling*: no credentials exist or are created in this spike. In the follow-up, tokens are read only from env, never logged, and the JSONL writer drops any key matched by the redaction key screen.
