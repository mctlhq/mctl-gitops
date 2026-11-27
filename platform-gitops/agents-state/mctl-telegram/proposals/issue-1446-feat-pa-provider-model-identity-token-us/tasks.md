# Tasks: issue-1446-feat-pa-provider-model-identity-token-us

- [ ] 1. Inventory and contract doc: write the "PA usage telemetry" section in `docs/agent-worker.md` (fields, null-not-zero rule, cost bases `estimated_list|measured_billed|subscription|unknown`, price provenance env vars, reconciliation of reported vs. settled cost, budget-independence guarantee) — DoD: doc reviewed; field names checked against `internal/audit/redact.go`.
- [ ] 2. Parse provider identity and usage details in `internal/agentworker/openaiclient.go` and `openaistream.go`: optional cached/reasoning token pointers, `ChatResult.ResponseModel` (sanitized, 128-byte cap) — DoD: `Prices.Cost` and `UsageReported` unchanged; existing tests pass untouched.
- [ ] 3. (depends on 2) Add `internal/agentworker/pausage.go` with `PACallUsage`/`PARunUsage`, bounded call list, model match classification, closed outcome/finish-reason sets — DoD: unit tests for each field's absent/present behaviour.
- [ ] 4. (depends on 3) Wire the aggregator into `PAWorker.chat()` (one record per provider attempt) and `run()` (parallel to existing `cost`/`costKnown`, never read by them) and extend the `pa worker: job finished` log — DoD: diff shows no change to cost-limit, tool-cap or turn logic.
- [ ] 5. Add optional env `MODEL_PRICE_VERSION`, `MODEL_PRICE_SOURCE`, `MODEL_PRICING_MODE`, `AGENT_PROVIDER_LABEL` in `cmd/agent-worker/pa_mode.go` with validation — DoD: `pa_mode_test.go` covers defaults and invalid mode refusal.
- [ ] 6. (depends on 3) Send `usage` on reply and abandon reports; on the server add `usage` to `replyRequest` in `internal/pa/runloop.go`, raise `maxReplyBody` by the summary bound, validate the summary (drop and count when malformed) — DoD: reply with/without/malformed usage settles identically.
- [ ] 7. (depends on 6) Schema: additive `pa_usage` columns and `pa_usage_calls` table in `internal/db/pa_jobs.go`; `RecordPAUsage` inside the finish/abandon transaction, idempotent on `(job_id, attempt)`, never touching `status`, `cost_usd`, `reported_cost_usd`, `reserved_usd`; purge `pa_usage_calls` in the principal purge — DoD: SQLite and Postgres tests green.
- [ ] 8. (depends on 7) Metrics in `internal/metrics/pa.go`: model calls, tokens, cost counter and run-cost histogram, model match, usage missing, usage reports; `UsageProvider` bounded like `UsageModel`; label-set equality tests — DoD: metrics emitted once per first recorded summary.
- [ ] 9. (depends on 8) Example PromQL (cost per run, tokens by model, error rate by provider/model/outcome) in the doc from task 1 — DoD: queries use only the new metric names and labels.

## Tests
- [ ] T1. Fake provider, normal usage: prompt/completion/cached/reasoning recorded; run totals equal the sum of calls and equal `cost_usd`; `usage_consistent=true`.
- [ ] T2. Fake provider, missing usage (absent and all-zero): fields null, basis `unknown`, `cost_usd` null on reply, settlement at full reservation as before; no zero token metric increments.
- [ ] T3. Alias: configured `zai-org/GLM-5.3-Flash`, returned a different string -> `alias`; absent -> `unknown`; oversized or invalid-charset string sanitized.
- [ ] T4. Retry/timeout: 429 then 503 then success -> three attempt records, failed ones `not_returned` and excluded from totals; timeout mid-stream -> abandon report carries partial usage, hold amount unchanged.
- [ ] T5. Partial usage: one call with usage, next without -> per-call costs listed, run estimate null, basis `unknown`, run ends with `errPACostLimit` exactly as today.
- [ ] T6. Multiple tool rounds: N rounds produce N+1 model call records with monotonic `seq`; tool cap behaviour unchanged.
- [ ] T7. Subscription and unversioned pricing: basis `subscription`, price version `unversioned` when unset; `cost_usd` sent for settlement unchanged.
- [ ] T8. Idempotency: same summary twice -> one set of rows, metrics incremented once; different summary for the same `(job_id, attempt)` -> ignored, `conflict` counted.
- [ ] T9. Budget invariance: table-driven run of existing reply/abandon scenarios with and without usage (and malformed usage) asserting identical `pa_usage.status`, `cost_usd`, `reported_cost_usd`, `paWindowSums`, worker outcomes and fencing/read-only guards (`PA_WRITES_ENABLED=false` paths).
- [ ] T10. Redaction: scrape the metrics registry and capture slog output in a run whose prompt, answer and tool arguments contain sentinel strings and synthetic principal/Telegram ids (personas Alice/Bob); assert none appear.
- [ ] T11. Compatibility: old-shape reply (no `usage`) recorded as `absent`; new worker against a server stub that ignores `usage` still settles.
- [ ] T12. Body bound: maximal answer plus maximal summary does not hit the overflow path.
- [ ] T13. Purge: principal deletion removes its `pa_usage_calls` rows.

All tests use fake providers and in-process servers; no live provider call or deployment.

## Rollback
All changes are additive. To roll back: revert the worker image to the previous tag (the server
then records `absent`), or revert the server (the worker's `usage` field is ignored by the lenient
reply decoder). New columns and the `pa_usage_calls` table can stay in place unused; nothing in
budget or settlement reads them. If metrics cardinality misbehaves, the new collectors can be
removed in a follow-up without schema change.
