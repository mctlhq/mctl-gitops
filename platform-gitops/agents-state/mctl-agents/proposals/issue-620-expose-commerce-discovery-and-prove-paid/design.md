# Design: issue-620-expose-commerce-discovery-and-prove-paid

## Current state

Read in the clone at `19c8a1d`:

- `docs/adr/020-capability-commerce-contract.md` is the contract. Sec. 12
  defines the descriptor `commerce` summary and the tenant reads (receipt,
  budget, invocation list). Sec. 14 makes mctl-api the only owner of commerce
  state and says commerce stays disabled "until C5 delivers its evidence and
  rollout procedure". Invariants 11 (8 of 9 at EUR 0.12 / EUR 1.00), 16
  (telemetry loss changes no ledger total) and 17 (cross-tenant
  indistinguishability) are assigned to C5. The "C4 implementation notes"
  section records what #619 shipped.
- `orchestrator/capability.py`: `CommerceSummary` (around lines 340-425) holds
  `terms_id`, `terms_version`, `price_mode`, `currency`, `amount_minor`,
  `funds_mode` and `meter`, plus the derived `quote_required` and
  `billable_on` (`BILLABLE_ON`). `CapabilityDescriptor.commerce` is optional
  and omitted from `to_dict()` when absent, which keeps `content_hash`
  stable. `consequence` is a closed vocabulary from
  `config/capability-consequence.yaml`.
- `orchestrator/capability_gateway.py`:
  - `_discover(..., commerce=...)` and `_commerce_summary()` (lines ~597-650)
    read the current terms from mctl-api and seal them into the descriptor.
  - `CapabilityGateway.search()` (line ~899) returns only `capability_id`,
    `title`, `summary` and `consequence`. `describe()` (line ~931) returns
    title, summary, consequence and `input_schema`. **Neither surfaces
    `descriptor.commerce`.** This is the discovery gap the issue names.
  - `PolicyDecidePolicyCheckpoint` (line ~737) wraps
    `orchestrator/policy_checkpoint.checkpoint` and returns only
    allowed/denied.
  - `invoke()` routes paid descriptors to `_invoke_paid` (line ~1120), which
    calls `commerce_gateway.PaidInvocation`.
- `orchestrator/commerce_gateway.py`: `CommerceRuntime(client, tenant_id,
  admitted_providers, approvals, ...)` is constructed **only in tests**
  (`grep CommerceRuntime(` finds no production call site). Without a
  runtime, paid descriptors are refused (fail closed). `PaidInvocation`
  implements ADR 020 secs. 7-11: precheck, approval check, quote, accept,
  re-validate, reserve, dispatch fence, provider outcome, finalize/release.
- `orchestrator/commerce.py`: `CommerceClient` has write and lookup routes
  (`current_terms`, `precheck`, `mint_quote`, `accept`, `find_invocation`,
  `get_invocation`, `reserve`, `dispatch`, `transition`, `finalize`,
  `release`, `dispatch_keys`). It has **no budget read, no receipt read and
  no invocation-list read**. Every failure is a `CommerceAnswer(UNKNOWN)`,
  never an exception.
- `orchestrator/commerce_provider.py`: `ProviderIngress._verify` refuses a
  call without a valid ed25519 `DispatchAuthorization`. It has a durable
  acceptance table, `outcome(key)`, and the pilot
  `pilot_lookup_status_ingress` (`PILOT_PROVIDER_ID = "pilot-provider"`,
  `PILOT_TOOL = "lookup_status"`).
- `orchestrator/policy_checkpoint.py`: `evaluate()` returns
  `(rule, code, reason)`, where `CODE_APPROVAL_REQUIRED` marks a
  `REQUIRE_APPROVAL` rule. That is the source for an advisory approval hint.
- `tests/test_commerce_gateway.py` has a `FakeLedger`, `FakeApprovals`,
  `Clock` and `World` harness plus `_restart()`, and already covers most of
  the sec. 11 fault table in unit form: concurrency, crash points,
  revocation, approvals, late results. There is no 8-of-9 budget test, no
  cross-tenant read test and no telemetry-off test.
- Observability: `orchestrator/temporal/tracing.py` imports OpenTelemetry
  lazily and only when configured. No OTel metrics instruments exist in the
  orchestrator today. `docs/observability/execution-traces.md` documents
  trace attributes.
- Evidence pattern: `tools/capability_bench.py` (pure report functions plus
  thin I/O wrappers, unit-tested from fixtures) and
  `docs/benchmarks/capability-discovery.md`. Rollout pattern:
  `docs/capability-pilot-status.md` ("what is live / what activates it /
  rollback").

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/` lists the tenants `admins`, `karabu`,
  `labs` and `ovk`. `tenants/` lists `admins`, `erpact`, `karabu`, `labs`,
  `mctl` and `ovk`. mctl-agents runs as
  `services/admins/mctl-agents-worker{,-exec,-implement}/values.yaml`.
- `grep -rln "commerce|COMMERCE"` over `services/` and `tenants/` found no
  matches. Commerce is not configured in any deployed values file. This
  matches the code: no production `CommerceRuntime`.
- No mctl MCP read tools were called for this run. The mctl-api commerce
  endpoints (C2/C3) and any commerce MCP tools are **not observed**. Their
  route shapes below are assumptions and are listed under Open questions.

## Proposed solution

There are five parts. All of them are additive, and everything paid stays
behind one default-off switch.

### 1. Discovery exposure (`orchestrator/capability_gateway.py`)

- Add `_commerce_view(summary: CommerceSummary) -> dict`. It returns
  `summary.to_dict()` plus `price_display`, a decimal string such as
  `"EUR 0.12"` built from integer minor units with the checked-in ISO 4217
  exponent table. This is display only (ADR 020 sec. 2). If no ISO table
  exists in `orchestrator/commerce.py`, add `MINOR_UNIT_EXPONENTS = {"EUR": 2,
  ...}` there.
- `search()` adds `"commerce": {price_mode, price, price_display,
  funds_mode, quote_required}` **only when** `descriptor.commerce is not
  None`. A legacy row is unchanged.
- `describe()` adds the full `_commerce_view` when present, plus
  `approval_expected`. It comes from a new pure helper
  `policy_checkpoint.expected_verdict(policy, action_kind, operation,
  grants) -> "required" | "not_required" | "unknown"`. The helper runs
  `evaluate()` on an empty-argument request and maps `CODE_APPROVAL_REQUIRED`
  to `required` and `CODE_ALLOWED` to `not_required`. Anything else, or any
  rule whose match could depend on arguments, maps to `unknown`. The gateway
  gets it through `PolicyDecidePolicyCheckpoint.resolved_policy()`. For a
  checkpoint that is not that adapter, the hint is `unknown`. `consequence`
  is already returned and acts as the risk field.
- Both outputs read only from the sealed set, so invisible capabilities show
  no price (ADR 020 sec. 12). The field names avoid
  allow/deny/permit/grant/authorized, so ADR 017's guard test still passes.
- Update the `sdk_tools()` descriptions for `capability_search` and
  `capability_describe`: price and approval are advisory, and invocation
  re-checks everything.

### 2. Tenant reads (`orchestrator/commerce.py` + mctl-api, cross-repo)

- `CommerceClient` gains three read-only methods: `get_budget(tenant_id)`,
  `get_receipt(tenant_id, invocation_id)` and `list_invocations(tenant_id,
  *, capability_id=None, phase=None, since=None, limit=50)`. They use the
  existing `_tenant` and `_invocation` path helpers and `CommerceAnswer`
  classification, so unreachable means `UNKNOWN`, never empty.
- Add a typed parser `BudgetView.from_dict` and `ReceiptView.from_dict` in
  `orchestrator/commerce.py`. It rejects floats in any money field (ADR 020
  invariant 2) and unknown `schema_version`.
- The authoritative API and MCP surface is mctl-api's. This proposal
  references the needed C2/C3 endpoints and MCP tools
  (`mctl_get_commerce_budget`, `mctl_get_commerce_receipt`,
  `mctl_list_commerce_invocations`, tenant-admin scoped, cross-tenant
  `not-found`) in a cross-repo issue on mctl-api linked from #620. mctl-agents
  does not serve an MCP surface for these. Its client exists for the proof
  harness and for existing agent surfaces (for example a Telegram or portal
  consumer) to reuse.

### 3. Enablement and disable switch (`orchestrator/commerce_gateway.py`, `run_issue_investigator.py`)

- Add `CommerceRuntime.from_env(tenant_id, approvals) -> CommerceRuntime |
  None`. It reads `MCTL_COMMERCE_ENABLED` (default unset, meaning off),
  `MCTL_COMMERCE_ADMITTED_PROVIDERS` (comma list) and
  `MCTL_COMMERCE_FUNDS_MODE` (must be `simulated`). It returns `None` when
  disabled, and raises at startup if enabled with an empty admission list or
  a non-simulated funds mode (fail at configuration time, ADR 020 sec. 10
  spirit).
- At the `CapabilityGateway.build(` call site in
  `orchestrator/run_issue_investigator.py` (line ~2457), pass
  `commerce=CommerceRuntime.from_env(...)`. When the switch is off, the code
  path is identical to today.
- The disable procedure has two layers. Layer 1 is mctl-api's switch
  (C2/C3), which refuses `POST .../invocations` (accept) while reserve,
  dispatch, finalize, release and the reconciler keep working. That is the
  authoritative stop, and it covers clients that ignore the env flag.
  Layer 2 is the mctl-agents env flag, which stops sealing terms into new
  descriptors and constructing runtimes. In-flight invocations are owned by
  mctl-api's reconciler (ADR 020 sec. 11 recovery table), so disabling
  mctl-agents strands nothing.

### 4. Metrics (`orchestrator/commerce_metrics.py`, new)

- Lazy OTel import, mirroring `orchestrator/temporal/tracing.py`. It is a
  no-op when OTel is not configured, and it is never imported at worker
  module scope (keep `tests/test_worker_isolation.py` green).
- Instruments follow OTel naming conventions (dot-namespaced, unit
  annotated):
  - `mctl.commerce.invocations` (counter, `{invocation}`), attributes
    `phase`, `reason_code`, `price_mode`, `funds_mode` and `provider_id`.
  - `mctl.commerce.invocation.duration` (histogram, `s`), attributes
    `phase`, `price_mode` and `provider_id`.
  - `mctl.commerce.outcome_unknown` (counter), attribute `provider_id`.
- The attribute values come only from closed vocabularies. `provider_id` is
  limited to the admission list, and any other value collapses to `other`.
  A unit test asserts the attribute key set and rejects any `*_id` key
  except `provider_id`.
- Emission happens in `PaidInvocation._note()` (the existing trace hook)
  and at the terminal answer. Trace events keep ids, as today. Amounts
  appear in neither.
- The ledger never depends on metrics. Test T9 runs the proof with OTel
  forced off and compares receipts and totals.

### 5. The proof (`tools/commerce_proof.py`, new, plus `docs/benchmarks/paid-capabilities-proof.md`)

The structure mirrors `tools/capability_bench.py`: pure scenario and report
functions with thin I/O wrappers. There are two backends:

- `--backend offline` (CI) runs against `FakeLedger` and `FakeApprovals`,
  promoted from `tests/test_commerce_gateway.py` into
  `tests/commerce_fakes.py` so the tool and the tests share them, plus the
  real `ProviderIngress` (sqlite, tmp dir). It is deterministic.
- `--backend live` uses a real `CommerceClient` against mctl-api for one
  proof tenant with simulated EUR, the real pilot ingress and the real
  dispatch keys from `dispatch_keys()`. It is operator-run and needs
  `MCTL_TOKEN` (tenant admin of the proof tenant) plus a second token for
  the cross-tenant scenario.

Scenarios (each records expected, observed, ledger deltas, provider
execution count and receipt ids):

| id | scenario | expected |
|---|---|---|
| S1 | 12 concurrent distinct calls, EUR 0.12 `per_successful_call`, budget 100 minor | <= 8 `ok`, rest `budget-exhausted`, committed <= 96, available >= 4 |
| S2 | sequential 9th after 8 captures | `budget-exhausted` |
| S3 | provider failure (pilot handler forced to fail) | released, available unchanged |
| S4 | same key + same args, twice | one invocation, executions=1, captures=1 |
| S5 | same key + changed args | `idempotency-conflict`, original unchanged |
| S6 | direct `ProviderIngress` call with no or forged authorization | refused, executions=0 |
| S7 | tenant B reads and invokes tenant A's invocation | `not-found`, same body as a random id |
| S8 | grant revoked after accept / after reserve | refused / released, no dispatch |
| S9 | approval pending, then denied | no reservation while pending, `refused` after deny |
| S10 | kill after accept, reserve, fence, provider-ran; restart | executions=1, captures<=1 |
| S11 | capture `unknown`, then settlement retry | `settlement_status` pending, then settled, executions=1 |
| S12 | OTel export off | identical totals to the run with OTel on |
| S13 | `MCTL_COMMERCE_ENABLED=false` and mctl-api switch off, with one invocation in `outcome_unknown` | new call refused, the pending one reconciles to terminal |
| S14 | end-of-run liability sweep via `list_invocations` | zero non-terminal invocations, or each one is named |

The evidence bundle is `evidence/commerce-proof-<utc>.json`, attached to #620
and summarized in the doc. It pins the mctl-agents SHA, the mctl-api SHA and
image tags, the encoding versions (`QUOTE_ENCODING_VERSION`,
`TERMS_ENCODING_VERSION`, `DISPATCH_AUTHORIZATION_VERSION`), the terms
id/version and the runtime config. It contains no arguments, results,
tokens or proofs.

`docs/capability-pilot-status.md` gains a "Paid capabilities" section, and a
runbook `docs/runbooks/commerce-enable-disable.md` covers: enable order
(mctl-api switch, then terms publication by a platform admin, then the
mctl-agents env flag on `mctl-agents-worker-exec` only), disable order (the
reverse, with the reconciler kept running), how to check for outstanding
liability with `list_invocations`, and the `reconciliation_deadline` alert.

## Alternatives

1. **Expose price only in `describe`, not `search`.** This would save a few
   bytes per search row. Dropped because the issue requires "search/describe"
   to expose price, and a model choosing among capabilities needs the price
   at search time. A compact subset in search keeps rows small.
2. **Serve budget and receipt reads as new mctl-agents MCP tools in the
   capability gateway.** Dropped because ADR 020 sec. 14 makes mctl-api the
   only owner of commerce state and tenant authorization. A second read
   surface here would re-derive tenant scoping and risk cross-tenant leaks.
   The reads belong in mctl-api and its MCP server. mctl-agents only consumes
   them.
3. **Run the proof purely offline against fakes.** Cheapest and
   deterministic, but it proves nothing about mctl-api's reservation
   atomicity or the real dispatch signing, and the issue requires pinned
   repo versions and the provider contract. Kept as the CI backend. The live
   backend is the one whose evidence signs off the milestone.
4. **Labelling metrics with tenant or invocation ids for per-tenant spend
   dashboards.** Rejected because the issue and ADR 012/020 forbid it
   (unbounded cardinality, and the ledger is the source of truth). Per-tenant
   spend is answered by the budget read.

## Platform impact

- **Migrations:** none in this repo. The mctl-api receipt read and MCP tools
  (mctlhq/mctl-api#569) and the accept-only kill switch (mctlhq/mctl-api#570)
  are cross-repo prerequisites. Owner decision 2026-10-11: no
  simulated-authorizer fault hook; settlement-only retry is offline-only.
- **Backward compatibility:** legacy descriptors produce byte-identical
  search and describe output. Sealed-set `content_hash` is untouched (no
  descriptor change). The env flag defaults off, so deploying this changes
  nothing until an operator enables it.
- **Resources:** one extra mctl-api read per paid descriptor at discovery
  (already present since C4). Metrics instruments are no-ops without OTel.
  The live proof spends only simulated credits and about 30 pilot calls.
- **Risks and mitigations:**
  - *Model treats the advisory `approval_expected` as authority.*
    Mitigation: the docstring and tool description say so, and invocation
    re-checks policy anyway.
  - *Enabling on the wrong worker or tenant.* Mitigation: startup refusal
    without an admission list or with non-simulated funds, and the runbook
    scopes it to the proof tenant only. Shared tenants wait for #631.
  - *mctl-api routes differ from the assumed shapes.* Mitigation: task 2 is
    gated on confirming them, and the client parsers fail closed on unknown
    `schema_version`.
  - *Settlement retry cannot be provoked live.* Mitigation: the offline
    backend proves it, and the evidence doc states which backend proved
    which scenario.
