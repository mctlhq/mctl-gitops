# Tasks: issue-1446-feat-pa-provider-model-identity-token-us

Implementation is on HOLD until an owner GO (issue #1446). These tasks are the plan for when it
is lifted. No provider call, migration execution, deployment or pilot GO is part of them. Gates:
ADR 0011 and mctlhq/mctl-telegram#1319.

- [ ] 1. Inventory and contract doc: write the "PA usage telemetry" section in `docs/agent-worker.md` (fields, null-not-zero rule per field, the four cost notions: estimate with basis `estimated_list|subscription_shadow`, `verified_billed`, the unchanged settled ledger cost, `unknown`; cost completeness; the statement that shadow estimates are not billed spend; price provenance env vars; capability negotiation; reconciliation of reported vs. settled cost; budget-independence guarantee; known crash gaps and metric/DB consistency limits) — DoD: doc reviewed; field names checked against `internal/audit/redact.go`.
- [ ] 2. Parse provider identity and usage details in `internal/agentworker/openaiclient.go` and `openaistream.go`: optional cached/reasoning token pointers, `ChatResult.ResponseModel`; one sanitizer (128-byte cap, fixed charset, `invalid`) applied to both returned and configured model strings — DoD: `Prices.Cost` and `UsageReported` unchanged; existing tests pass untouched.
- [ ] 3. (depends on 2) Add `internal/agentworker/pausage.go` with `PACallUsage`/`PARunUsage`, bounded call list, model match classification (`exact|verified_alias|mismatch|unknown`, aliases only from `AGENT_MODEL_ALIASES`), billing and cost completeness, closed outcome/finish-reason sets — DoD: unit tests for each field's absent/present behaviour.
- [ ] 4. (depends on 3) Wire the aggregator into `PAWorker.chat()` (one record per provider attempt; failed or interrupted attempts billing `unknown`) and `run()` (parallel to existing `cost`/`costKnown`, never read by them) and extend the `pa worker: job finished` log — DoD: diff shows no change to cost-limit, tool-cap or turn logic.
- [ ] 5. Add optional env `MODEL_PRICE_VERSION`, `MODEL_PRICE_SOURCE`, `MODEL_PRICING_MODE`, `AGENT_PROVIDER_LABEL`, `AGENT_MODEL_ALIASES` in `cmd/agent-worker/pa_mode.go` with validation — DoD: `pa_mode_test.go` covers defaults, invalid mode refusal and invalid alias entries.
- [ ] 6. (depends on 3) Transport: add a server switch `PA_USAGE_TELEMETRY_ADVERTISE` (default off) and advertise `usage_telemetry: 1` in the claim response only while it is on; it is turned on only after every server replica runs the headroom-aware reply reader; the worker sends `usage` on reply and abandon reports only when the claim advertised a supported version, otherwise the legacy payload. On the server add `usage` to `replyRequest` in `internal/pa/runloop.go`, read every reply/abandon body with the outer limit `maxReplyBody + paUsageReadHeadroom` on every headroom-aware replica, independent of its advertisement switch (headroom strictly above `paUsageMaxBytes` plus the `,"usage":` wrapper, see design.md section 3; a body above the outer limit follows today's overflow rule), apply today's `maxReplyBody` rule to the reply as if `usage` were absent, and validate `usage` against its own bound (drop and count when malformed or oversized) — DoD: reply with/without/malformed/oversized usage settles identically; `maxReplyBody` and the overflow path are unchanged; with the switch off no claim advertises `usage_telemetry` and the worker sends the legacy payload.
- [ ] 7. (depends on 6) Schema: additive `pa_usage` columns and `pa_usage_calls` table in `internal/db/pa_jobs.go`; `RecordPAUsage` after the finish/abandon commit, in its own short transaction with `paUsageWriteTimeout`, keyed by the verified token's `(job_id, attempt)`, conditional on a settled row, idempotent, never touching `status`, `cost_usd`, `reported_cost_usd`, `reserved_usd`; failures recovered and counted; purge `pa_usage_calls` in the principal purge — DoD: SQLite and Postgres tests green; a forced storage error leaves the reply response and ledger unchanged.
- [ ] 8. (depends on 7) Metrics in `internal/metrics/pa.go`: model calls, tokens, cost counter and run-cost histogram (basis and completeness labels), model match, usage missing, usage reports (including `not_negotiated`, `refused`, `write_failed`); `UsageProvider` bounded like `UsageModel`; label-set equality tests — DoD: metrics emitted once per first recorded summary, after its commit.
- [ ] 9. (depends on 8) Example PromQL (cost per run by basis and completeness, tokens by model, error rate by provider/model/outcome) in the doc from task 1 — DoD: queries use only the new metric names and labels, and none sums shadow estimates as spend.
- [ ] 10. (before pilot GO) Dashboards and correlation: agree the shared `job_id` + `attempt` correlation and dashboard plan with mctlhq/mctl-telegram#1445 and mctlhq/mctl-gitops#3004 — DoD: one agreed plan, no new metric labels.

## Tests

The split follows the rule in design.md "Verification tiers": settlement, budget, fencing and
reply isolation, security and privacy, the null-versus-zero contract and backward compatibility
are required before merge; crash-timing depth, streaming faults, provider-specific evidence and
operational artefacts are required before the pilot GO.

### Required before merge

- [ ] T1. Fake provider, normal usage: prompt/completion/cached/reasoning recorded; run totals equal the sum of calls and equal `cost_usd`; `usage_consistent=true`; completeness `complete`.
- [ ] T2. Missing vs zero: usage absent -> all token fields null; usage supplied as all-zero -> the supplied zeros are stored as 0 (not null) but the usage counts as unreported for costing; in both cases basis `unknown`, `cost_usd` null on reply, settlement at full reservation as before, no zero token metric increments; then each of input, output, cached and reasoning absent alone and supplied as 0 alone -> only the absent field is null and a supplied 0 stays 0.
- [ ] T3. Model identity and redaction of identifiers: configured `zai-org/GLM-5.3-Flash` returned identically -> `exact`; a listed `AGENT_MODEL_ALIASES` pair -> `verified_alias`; an unlisted different string -> `mismatch`; absent -> `unknown`; oversized or invalid-charset returned and configured strings are sanitized before records, logs and labels.
- [ ] T4. Partial usage across calls: one call with usage, next without -> per-call costs listed, run estimate null, basis `unknown`, completeness `partial`, run ends with `errPACostLimit` exactly as today.
- [ ] T5. Multiple tool rounds: N rounds produce N+1 model call records with monotonic `seq`; tool cap behaviour unchanged.
- [ ] T6. Subscription and unversioned pricing: basis `subscription_shadow`, never `verified_billed`; price version `unversioned` when unset; `cost_usd` sent for settlement unchanged.
- [ ] T7. Idempotency: same summary twice -> one set of rows, metrics incremented once; different summary for the same `(job_id, attempt)` -> ignored, `conflict` counted.
- [ ] T8. Telemetry failure isolation and budget invariance: table-driven run of existing reply/abandon scenarios with and without usage, with malformed and oversized usage, and with an injected `pa_usage_calls`/`RecordPAUsage` storage error and timeout, asserting the same reply response, identical `pa_usage.status`, `cost_usd`, `reported_cost_usd`, `paWindowSums`, worker outcomes, outbox delivery and fencing/read-only guards (`PA_WRITES_ENABLED=false` paths), and `write_failed` counted.
- [ ] T9. Fencing and attempt identity: a summary for a fenced or superseded attempt, or for a `(job_id, attempt)` without a settled row, writes nothing and counts `refused`; the identity comes from the token, not the summary.
- [ ] T10. Redaction and bounded metrics: scrape the metrics registry and capture slog output in a run whose prompt, answer and tool arguments contain sentinel strings and synthetic principal/Telegram ids (personas Alice/Bob); assert none appear, and that model labels stay within the `UsageModel`/`UsageProvider` slots.
- [ ] T11. Compatibility and negotiation: new worker against a server stub with no capability or an unknown version sends a byte-identical legacy payload; old-shape reply to a new server recorded as `absent`; old/new worker x old/new server all settle identically.
- [ ] T12. Answer-size semantics: with and without `usage`, an answer at today's limit is accepted and one past it overflows exactly as today; a maximal answer plus a maximal valid `usage` (including the JSON wrapper overhead) fits the outer read limit and keeps the answer's outcome; a maximal answer plus an oversized `usage` that still fits the headroom (between `paUsageMaxBytes` and `paUsageReadHeadroom` minus the wrapper) keeps the answer's outcome and the `usage` is dropped and counted as `oversized`; a body above the outer limit follows today's overflow rule.
- [ ] T13. Purge: principal deletion removes its `pa_usage_calls` rows, and a summary arriving after the purge writes nothing; a `RecordPAUsage` interleaved with the purge (Postgres, two connections) leaves no orphan `pa_usage_calls` row.
- [ ] T14. Rollout matrix: claim on an advertising replica, reply on a headroom-aware replica with advertisement off -> a maximal answer plus maximal valid `usage` keeps the answer's outcome.

### Required before pilot GO

- [ ] P1. Crash-between-commit fault matrix: process kill after the settlement commit and before the telemetry write, and after the telemetry write and before metric emission; settlement intact, the row reads "telemetry missing" or metrics lag as documented, never zero usage.
- [ ] P2. Partial streamed usage: timeout or disconnect mid-stream -> abandon report carries the partial usage, completeness `partial`, hold amount unchanged.
- [ ] P3. Potentially billed failed attempts: 429, 503, timeout after send and transport error -> attempt records with billing `unknown`, excluded from token totals, run completeness never `complete`.
- [ ] P4. Alias verification breadth: the aliases the provider routes in use actually return are captured from fake-provider fixtures and reviewed into `AGENT_MODEL_ALIASES`; case, prefix and version variants classify as `mismatch` unless listed.
- [ ] P5. Dashboards: task 10 is done with mctlhq/mctl-telegram#1445 and mctlhq/mctl-gitops#3004.

All tests use fake providers and in-process servers; no live provider call or deployment.

## Rollback
All changes are additive. To roll back: revert the worker image to the previous tag (the server
then records `absent`), or roll back the server in two steps: first turn `PA_USAGE_TELEMETRY_ADVERTISE` off and wait
for in-flight claims to drain (lease length), then revert the server image. Reverting the server
while the switch is on would let a claim advertised by a new replica reply to an old replica
under the old `maxReplyBody` limit. New columns and the `pa_usage_calls` table can stay in place unused; nothing in
budget or settlement reads them. If metrics cardinality misbehaves, the new collectors can be
removed in a follow-up without schema change.
