# Spike: Jev vs Clef-flash as advisory semantic guardrails beside the #197 policy checkpoint

## Context

Issue mctlhq/mctl-agents#556 asks for a bounded spike. It compares two cheap
hosted "decision models", TypeSafe Jev (`jev-latest`) and Cloudflare
Clef-flash (`@cf/cloudflare/clef-flash`), with deterministic policy alone. The
question is whether a probabilistic semantic classifier can add useful risk
signals (risk category, `LOW_RISK | REVIEW | HIGH_RISK` recommendation,
missing evidence, DevLoop triage) beside the authoritative runtime policy
checkpoint in `orchestrator/policy_checkpoint.py` (ADR 014). It must do this
without becoming a second authorization authority. The spike ends with one
recommendation: `ADOPT_JEV`, `ADOPT_CLEF_FLASH`, `LIMITED_GO` or `NO_GO`.

Scope decision (owner, 2026-10-23): this spike is **replay-only**. No provider
credentials exist and no one owns the vendor accounts or their spend, so the
live provider run (task 7) does not happen in this spike and the spike spends
nothing. Without live measurements no GO criterion can be met, so the report's
recommendation is `NO_GO`, qualified on its own line as "NO_GO-pending: live
behaviour not measured". That qualifier is not a fifth token; the closed
vocabulary above is unchanged. A live run with a hard spend cap and a named
approver is a separate follow-up issue, filed by the report.

This matters because the checkpoint today is closed-world and
deterministic. `BUILTIN_POLICY` names every permitted orchestrator mutation
exactly. Every unlisted `mcp__mctl__*` tool falls to the
`mctl-mcp-default-approval` REQUIRE_APPROVAL rule. Unknown kinds get
`no_matching_rule` and are denied. So a semantic signal can add value in only
one place: escalating an action that the rules already ALLOW, or attaching
context to a REQUIRE_APPROVAL request for the human approver. The spike must
measure whether that value is real. A model integration is a new runtime
dependency, a new egress path and a new data-exposure surface, so the cost is
real too. No production code path changes in this spike.

## User stories

- AS a platform owner I WANT a measured side-by-side comparison of deterministic-only, Jev-assisted and Clef-flash-assisted decisions on a versioned fixture set SO THAT the decision to add a runtime dependency rests on MCTL data, not on vendor benchmarks.
- AS a security reviewer I WANT proof that no model output can relax a deterministic DENY or REQUIRE_APPROVAL SO THAT the ADR 014 authority model stays intact whatever the spike concludes.
- AS an operator I WANT latency, error and cost numbers measured from the mctl cluster's own egress path SO THAT I can judge whether synchronous tool-call gating is feasible.
- AS the owner of the assurance and evaluation work (.github#151, #310) I WANT the fixture set and result contract to be reusable offline SO THAT a later evaluation suite does not have to rebuild them.
- AS a reviewer of DevLoop changes I WANT a clear verdict on whether semantic triage adds anything beyond CI, Ruff/Pyrefly and the configured reviewers SO THAT we do not add a redundant signal.

## Acceptance criteria (EARS)

Fixtures and contract

- THE SYSTEM SHALL provide a versioned fixture set under `tests/fixtures/semantic_decision/`. Every fixture SHALL carry a normalized `SemanticDecisionRequest`, the deterministic verdict produced by `policy_checkpoint.evaluate` against `BUILTIN_POLICY` (or a named variant), a human-labelled expected risk class, and a `danger` flag.
- THE SYSTEM SHALL include, at minimum, fixtures for each of these classes: obvious safe reads, obvious prohibited writes, ambiguous writes or tool calls, malformed or adversarial tool descriptions, model-authored claims of authority, sanitized shapes inspired by mctl-agents#183 and mctl-telegram#602, cases with a definitive deterministic answer, borderline semantic cases, and at least five minimal pairs that differ in exactly one critical attribute.
- THE SYSTEM SHALL cover all four issue scenarios (A risk classification, B approval recommendation, C evidence sufficiency, D DevLoop triage) with at least six fixtures each.
- THE SYSTEM SHALL include at least 10 fixtures with `danger: true` whose deterministic verdict is ALLOW. These are the only cases where a semantic signal can change the outcome, so the dangerous-false-negative metric is meaningless without them.
- WHEN a fixture is loaded THE SYSTEM SHALL check that its recorded deterministic verdict still equals the current `policy_checkpoint.evaluate` result, and SHALL fail the test suite if it has drifted.
- THE SYSTEM SHALL define one provider-neutral `SemanticDecisionRequest` / `SemanticDecisionResult` contract with an explicit `schema_version`. The result's `recommendation` SHALL be limited to the closed vocabulary `LOW_RISK | REVIEW | HIGH_RISK`, and its categories to a closed set.

Authority and failure semantics

- THE SYSTEM SHALL compute the combined, simulated verdict with one pure function, `combine(deterministic_verdict, result)`. That function SHALL be monotone in strictness (ALLOW < REQUIRE_APPROVAL < DENY): its output SHALL never be less strict than the deterministic verdict.
- IF the deterministic verdict is DENY or REQUIRE_APPROVAL THEN THE SYSTEM SHALL return that verdict unchanged, whatever the model says.
- IF the provider times out, errors, returns non-schema output, or returns confidence below the configured threshold THEN THE SYSTEM SHALL record `signal_status` as `timeout | error | malformed | low_confidence`, SHALL return the deterministic verdict unchanged, and SHALL never grant additional capability.
- THE SYSTEM SHALL contain no code path where a model result produces `ALLOW`, sets `Decision.permitted`, or satisfies any CI, type-check, test or approval evidence requirement.
- WHILE the spike is open THE SYSTEM SHALL NOT import the spike adapter from any `orchestrator/` module, and SHALL NOT call it from `policy_checkpoint.decide`, `enforce` or `checkpoint`, or from any Temporal activity.

Inputs and privacy

- THE SYSTEM SHALL build model inputs only from canonical fields: `ActionRequest.action_kind`, `operation`, `target`, `actor`, grants, the fixture's bounded and sanitized metadata, and the agent/profile version. It SHALL never use raw tool output, private prompts, credentials or model-authored claims presented as trusted facts.
- WHEN a request is built THE SYSTEM SHALL reject any string value that `orchestrator.redaction.contains_credential` flags, and any value that exceeds the contract's length bound.
- THE SYSTEM SHALL wrap untrusted fields (tool descriptions, model-authored claims) in a delimited `untrusted` section of the prompt. Fixtures SHALL test whether such content can move the recommendation.
- THE SYSTEM SHALL NOT persist prompts or completions by default. Raw responses SHALL be written only when the operator passes an explicit `--record-raw DIR` flag, and that directory SHALL never be a repository path.

Measurement

- WHILE this spike is open THE SYSTEM SHALL NOT call any live provider endpoint and SHALL spend nothing; the live providers are implemented and unit-tested against recorded or synthetic responses only.
- WHEN the harness runs live against a provider (in the follow-up, not this spike) THE SYSTEM SHALL record, per call: provider, resolved model ID and version (for Jev, the name returned by `GET /v1/models`), API endpoint and version, request schema version, input token count, latency, HTTP status, retry count, signal status, the parsed result, and the deterministic and combined verdicts.
- THE SYSTEM SHALL repeat each fixture N times (default 5) per provider. It SHALL report repeated-run stability as the share of fixtures with identical recommendations across all runs.
- THE SYSTEM SHALL report per provider: median and p95 latency, decision accuracy, dangerous false-negative rate (a `danger` fixture classed `LOW_RISK` or left unescalated), false-positive or escalation rate, malformed-output rate, a confidence calibration table (reliability bins and Brier score where probabilities exist), adversarial robustness, and cost per 1k, 100k and 1M decisions at the measured token sizes.
- THE SYSTEM SHALL report dangerous false negatives as their own line and SHALL NOT fold them into an aggregate score.
- WHEN the follow-up live run happens (never in this spike) THE SYSTEM SHALL run it from a pod in the `admins` tenant namespace of the mctl cluster, the same network path as `mctl-agents-worker`, and SHALL state the source location in its results document. Task 7's follow-up issue body carries this criterion.

Outcome

- WHEN the benchmark is complete THE SYSTEM SHALL publish `docs/spikes/556-semantic-decision-models.md`. It SHALL contain the side-by-side metrics table from the issue, the trust boundary, the failure semantics, answers to the issue's ten questions, and exactly one recommendation from `ADOPT_JEV | ADOPT_CLEF_FLASH | LIMITED_GO | NO_GO`, justified against every GO criterion in the issue.
- IF every useful case can be expressed as a deterministic `Rule` in `BUILTIN_POLICY` THEN THE SYSTEM SHALL conclude `NO_GO` and list those rules as follow-up candidates.
- IF Jev and Clef-flash are within measurement noise on dangerous false negatives and accuracy THEN THE SYSTEM SHALL recommend the option with the lower operational complexity, and SHALL NOT recommend both.
- WHERE the recommendation is not `NO_GO` THE SYSTEM SHALL name the exact proposed integration point (a function in `orchestrator/policy_checkpoint.py` or `orchestrator/options.py`, or a DevLoop step) and the trace fields it would add. It SHALL leave that integration unimplemented.

## Out of scope

- Any change to `policy_checkpoint.decide`, `enforce`, `BUILTIN_POLICY`, `action_approvals.py`, the MCP `PreToolUse` hook in `orchestrator/options.py`, or any Temporal workflow or activity.
- Any gitops change: no new env var, secret or ExternalSecret in `services/admins/mctl-agents-*`, and no production rollout.
- Replacing #197 policy, #198 human approval, or deterministic gates (Ruff, mypy/Pyrefly, tests, schema validation, approval digests).
- Self-hosting open-weight Clef. The spike only assesses its implications on paper, unless hosted Clef-flash fails on privacy or availability.
- A generic content-moderation service, and Basin, K2 or x402.
- Benchmarking against live production traffic.

## Open questions

- Vendor facts have not been verified. Today is 2026-10-18. The issue quotes pricing "as of 2026-10-19" plus vendor latency numbers, and this run could not check either vendor's API or documentation. The harness must re-record model IDs, prices and context limits at benchmark time. If a model or endpoint does not exist as described, the spike reports that, and the missing provider becomes a `NO_GO` input for that provider.
- RESOLVED (owner, 2026-10-23): provider credentials have no owner, so the live run is out of this spike (replay-only, no spend). A follow-up live run needs: an account owner for Cloudflare Workers AI and TypeSafe, a hard spend cap, and a named approver for that spend.
- DEFERRED to the live-run follow-up (owner, 2026-10-23: replay-only): the benchmark location is assumed. "Our actual deployment region" is taken to mean a one-off pod in the `admins` namespace. The tenant has `allowInternetEgress: true`, so the path is reachable. A run from an operator workstation would be recorded as a deviation.
- Ground-truth labelling: the spike author labels every fixture, and a second labeler (a named human reviewer on the spike PR, recorded per fixture as `labelled_by` and `confirmed_by`) confirms them. Labels the two disagree on are marked `contested` and excluded from accuracy, but included in the stability measurement.
- The DevLoop triage fixtures (scenario D) need sanitized PR metadata. Which historical PRs are acceptable to sanitize is left to the implementer, who should prefer synthetic fixtures.
- The latency budget for synchronous gating is not given in the issue. This proposal uses p95 <= 300 ms as the working envelope for an MCP `PreToolUse` gate, because the existing approval path already allows about 20 s only for REQUIRE_APPROVAL actions. This budget is an **owner-unconfirmed assumption**: the report labels it so, and no follow-up may use it as an acceptance criterion until the owner confirms it.
