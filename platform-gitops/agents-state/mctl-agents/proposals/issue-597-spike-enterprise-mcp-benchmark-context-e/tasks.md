# Tasks: issue-597-spike-enterprise-mcp-benchmark-context-e

**Disposition: CHANGES REQUESTED — RESEARCH INTAKE ONLY.** This is an
evidence-backed proposal specification and a review amendment only.
DO NOT send Temporal approval: it accepts the proposal and launches Tier 2.
No benchmark tools, docs PR, fixtures, runtime changes, live probes,
Portal modifications, actual model runs or merge are authorized.

## Authorized research-plan corrections

- [x] R1. Inventory eager/discovery paths and the existing benchmark's
  `n=1`, 61,213 -> 23,392 initial tokens, and 30 vs 52 turns.
  Record the `-62%` reduction as *structural*, not end-to-end savings.
- [x] R2. Define three comparable MCP-using classes: TC1 roadmap,
  TC2 platform triage, TC3 agent operations; all have independent
  read-only mctl-api oracles. TC4 Telegram cross-upstream is a distinct
  applicability case and may be `not measurable` in discovery.
- [x] R3. Separate expected capability calls (task correctness)
  from the allowed/excluded capabilities (authorization). The latter
  comes only from the pinned/sealed execution profile and policy.
- [x] R4. Define the required identity/audit join:
  `run_id -> parent_execution_id -> child_call_id ->
  policy_decision_id -> invocation_outcome -> durable_trace_id`.
  Every call, including denied and repeated identical-argument calls,
  needs unique, stable IDs and matching actor/tenant/argument digests.
  Existing client logs are `UNOBSERVED` until proven sufficient.
- [x] R5. Remove any automatic eager fallback. Policy/identity/catalog/
  tenant/approval/unknown failures fail closed. Any future
  allowlisted non-security recovery must preserve the sealed set
  and independent audit.
- [x] R6. Replace the permissive 4/5 adoption criterion with no observed
  correctness regression plus independent 100% permission/audit gates.
  Five runs per cell are exploratory and require a separately reviewed
  confirmatory plan before adoption.
- [x] R7a. Amend this proposal for the three PR #2803 review findings:
  (1) sanitized-only recursive usage projection, (2) mode-sensitive NEG
  exposure vs invocation authorization, (3) conjunctive/alternative oracle
  groups for TC1–TC3. These are specifications, not executable code.
- [ ] R7b. Independent reviewer on the **new HEAD** confirms the fixes,
  including complete nested-field and NEG-mode tests as future criteria,
  and verifies no implementation was authorized.

## Candidate future tooling/doc slice — new owner GO required

These are **not tasks for the currently parked implementer**.

- [ ] F1. If the owner separately authorizes offline tooling, add
  `tools/bench_tasks/{tc1-roadmap,tc2-triage,tc3-agent-ops,
  tc4-cross-upstream,neg-consequential}.yaml` with pinned oracle inputs:
  `required_all` and `required_any_of` (nested nonempty alternatives),
  `excluded_capabilities`, `argument_constraints`, `answer_facts`,
  `consequential`, `pinned_inputs`. Validate TC1 and TC3 either-path
  correctness, TC2 two-tool conjunction, and NEG with empty positive
  obligations. No production data and no real consequence-capable action.
- [ ] F2. If separately authorized, define `usage_summaries[]` as a
  **numeric allowlisted projection**, never raw `result_messages` or SDK
  `ResultMessage` objects. Project in RAM, recursively validate the
  entire record (including nested maps/arrays, tool traces and usage),
  then persist atomically only if every field is safe. Injected nested
  `result`, `content`, `text` or `message_text` must refuse the write.
  Implement pure `aggregate` in `tools/capability_bench.py` without
  changing legacy `compare` read-side behavior. Preserve cumulative
  token delta math and separate sanitized first-turn counters.
  Every child needs stable call/parent/decision IDs, actor/tenant,
  argument digest and outcome, or explicit `INCOMPLETE`.
  Never infer a retry from identical hashes.
- [ ] F3. If separately authorized, update only the existing
  `docs/benchmarks/capability-discovery.md` with a versioned task set,
  original baseline, unexecuted results, mode matrix, #63 M8 FAIL,
  #1096 adjunct and bounded experiment plan. No competing benchmark.
- [ ] F4. Run pure offline tests for (a) nested raw SDK text/result/payload
  rejection with zero persisted bytes, even inside arrays or model-usage
  maps, and stable `compare` output; (b) one-of TC1/TC3 and all-of TC2
  invocation/answer-fact scoring, malformed any-of groups, NEG with no
  positive requirement; (c) eager visible-but-DENIED/no execution vs
  discovery filtered-not-visible/no execution, with separate exposure
  metrics; (d) missing/multimatched audit IDs, independently eligible
  sets, and fail-closed recovery. Confirm `NOT_RUN` stays `NOT_RUN`.

## Candidate experiment and decision — a *second* distinct GO

- [ ] E1. Obtain pinned model/identity/profile/catalog/fixtures/owner,
  explicit isolation/rollback, confirmatory sample-size plan and USD cap.
  Portal `search_and_execute` stays PARK/M8 blocked, and current
  production `code_mode: off` must not change.
- [ ] E2. Only after experiment GO, perform authorized read-only repeated
  tests; record every unmeasurable and unexecuted cell accurately.
- [ ] E3. Apply the pre-registered strict governance and no-regression
  rule. Without enough measured evidence, recommendation is `DEFER`,
  not ADOPT; owner files any actual rollout follow-ups separately.

## Current review acceptance

- [ ] Every measured result and negative probe is `NOT_RUN`.
- [ ] Every proposed persisted usage summary has a strict recursive
  allowlist and no raw SDK result; injections of nested text fail with
  no record write.
- [ ] TC1/TC3 alternative-capability success and TC2 conjunctive
  success have explicit deterministic oracles, independently of policy.
- [ ] Eager NEG policy-DENY without execution is not confused with
  the broader advertised schema; discovery checks filtered exposure.
- [ ] The sealed eligibility set is independent of task oracle expectations.
- [ ] Eager/discovery audit joins require unique child and decision IDs and
  deny ambiguous, missing or absent-policy records.
- [ ] TC1–TC3 are comparable; TC4's unavailable provider is explicit.
- [ ] No automatic fallback to a wider tool surface; negative tests
  remain specified but unexecuted.
- [ ] No code, fixtures, benchmark report PR, Portal, runtime, status flip,
  implementer, approval, merge or deployment is performed under this GO.

**Rollback:** Revert this GitOps proposal-text amendment if needed.
