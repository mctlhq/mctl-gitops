# Expose commerce discovery and prove Paid Capabilities (C5, single-tenant, simulated credits)

## Context

Issue mctlhq/mctl-agents#620 is item C5 (`paid-capabilities-proof`) of the
Agent Commerce epic (mctlhq/.github#173). ADR 020
(`docs/adr/020-capability-commerce-contract.md`) fixes the contract. C4
(`governed-invocation`, #619) has landed the runtime in this repo:
`CommerceSummary` on `CapabilityDescriptor` (`orchestrator/capability.py`),
the terms read at discovery (`capability_gateway._commerce_summary`), the
paid invocation state machine (`orchestrator/commerce_gateway.py`
`PaidInvocation`), and the provider ingress with signed dispatch
authorizations (`orchestrator/commerce_provider.py` `ProviderIngress`).
Three things are still missing. The model-facing `capability_search` and
`capability_describe` answers do not show the price, even though the sealed
descriptor carries it. Nothing in this repo reads a tenant's budget or an
invocation receipt. Nothing constructs a `CommerceRuntime` outside tests, so
nothing is enabled, and no rollout or disable procedure exists.

C5 has to expose discovery and tenant reads, then prove the whole chain end
to end on simulated credits for one tenant: EUR 0.12 `per_successful_call`
against a EUR 1.00 budget, with every fault and denial case in the issue. The
result must be pinned, reproducible evidence and a documented rollout and
disable procedure. Enabling a shared tenant was split out to
mctlhq/mctl-agents#631 and is not part of this work. Real money, wallets,
payouts and payment rails are explicitly excluded.

## User stories

- AS an agent running in a governed execution I WANT `capability_search` and `capability_describe` to show the price, currency/unit, payment mode, quote requirement and expected approval/consequence of a capability SO THAT I can decide whether calling it is worth the cost before I call it.
- AS a tenant admin I WANT tenant-scoped reads of my simulated budget (available, reserved, committed, pending liability) and of receipts for each paid invocation SO THAT existing surfaces (MCP, API, Telegram, portal) can show spend without a marketplace UI.
- AS a platform operator I WANT a single switch that stops new paid acceptances while reconciliation keeps running SO THAT I can disable commerce without stranding liability.
- AS the epic owner I WANT a reproducible, version-pinned proof with attached evidence for every acceptance scenario SO THAT the milestone can be signed off without trusting prose.

## Acceptance criteria (EARS)

### Discovery

- WHEN `capability_search` returns a row for a descriptor whose `commerce` summary is present THE SYSTEM SHALL include `commerce: {price_mode, price: {currency, amount_minor}, price_display, funds_mode, meter, quote_required, billable_on, terms_id, terms_version}` taken only from the sealed descriptor.
- WHEN `capability_describe` returns an `ok` entry THE SYSTEM SHALL include the full `commerce` summary (when present), the `consequence`, and an advisory `approval_expected` value (`required` | `not_required` | `unknown`) computed from the configured policy's rule for that tool, without reading arguments or contacting mctl-api.
- WHILE a descriptor has no `commerce` summary THE SYSTEM SHALL return search and describe rows byte-identical to today's (no `commerce` key, never `null`).
- IF a capability id is not in the sealed set THEN THE SYSTEM SHALL answer `not-found` with no price and no approval information, exactly as today.
- THE SYSTEM SHALL NOT emit any discovery field named allow/deny/permit/grant/authorized (ADR 017's existing test), and the values `approval_expected` and `price_display` SHALL be documented as advisory: `capability_invoke` re-runs identity, policy, quote and budget checks.

### Tenant reads

- WHEN a caller with tenant authority asks for the tenant budget THE SYSTEM SHALL return `available`, `reserved`, `committed` and `pending_liability` as integer minor units with `currency` and `funds_mode`, read from mctl-api.
- WHEN a caller with tenant authority asks for an invocation receipt THE SYSTEM SHALL return the ADR 020 sec. 12 receipt: ids, terms version, quote digest, the five facts, `phase`, `reason_code`, timestamps and the `approval_id`, `execution_id` and policy decision references.
- IF the invocation or budget belongs to another tenant, or does not exist THEN THE SYSTEM SHALL return the same `not-found` answer in both cases.
- IF mctl-api cannot be reached THEN THE SYSTEM SHALL report the read as `unknown`, never as a zero balance or an empty list.
- THE SYSTEM SHALL NOT return arguments, results, payment proofs or `external_ref` contents from any read.

### Proof scenarios (simulated EUR, one proof tenant)

- WHEN 12 or more distinct paid invocations of the pilot capability (EUR 0.12 `per_successful_call`) run concurrently against a EUR 1.00 simulated budget THE SYSTEM SHALL capture at most 8, and every invocation beyond the 8th SHALL be refused with `budget-exhausted`.
- WHEN the 9th sequential invocation is attempted after 8 captures THE SYSTEM SHALL refuse it with `budget-exhausted`, and committed SHALL equal 96 minor units.
- WHEN a provider confirms failure on a `per_successful_call` invocation THE SYSTEM SHALL release the reservation and the budget's available amount SHALL return to its prior value.
- WHEN the same idempotency key is retried with the same arguments THE SYSTEM SHALL return the original invocation, and the provider execution count and the capture count SHALL both stay at 1.
- IF the same idempotency key is reused with changed arguments THEN THE SYSTEM SHALL refuse with `idempotency-conflict` and the original invocation SHALL be unchanged.
- IF the pilot provider is called directly without a valid mctl-api dispatch authorization THEN THE SYSTEM SHALL refuse at the provider ingress and execute nothing.
- IF a caller from tenant B reads or invokes against tenant A's invocation or budget THEN THE SYSTEM SHALL answer `not-found` and change nothing.
- IF the execution's permission is revoked between acceptance and dispatch THEN THE SYSTEM SHALL refuse or release before funds move, with no dispatch.
- WHILE an approval for a paid call is pending THE SYSTEM SHALL hold no funds. IF the approval is denied THEN THE SYSTEM SHALL refuse with no reservation.
- WHEN the gateway process is killed after acceptance, after reservation, after the dispatch fence, or after the provider ran THE SYSTEM SHALL resume on restart without re-executing the provider and SHALL capture at most once.
- WHEN capture or settlement answers `unknown` after a confirmed success THE SYSTEM SHALL keep `settlement_status: pending`, retry only settlement on the same derived key, and never re-dispatch.
- WHEN the proof run ends THE SYSTEM SHALL report zero invocations in a non-terminal phase, or name each one with its reason (no unexplained liability).

### Observability and ledger durability

- THE SYSTEM SHALL emit commerce metrics whose attribute set is bounded and closed: `price_mode`, `funds_mode`, `phase`, `reason_code`, `provider_id` (bounded by the admission list). Invocation, quote, approval, execution and tenant ids SHALL NOT be metric attributes, and monetary amounts SHALL NOT be span attributes.
- IF telemetry export is disabled or unavailable THEN THE SYSTEM SHALL produce identical ledger totals and identical receipts.

### Rollout and disable

- WHILE `MCTL_COMMERCE_ENABLED` is not `true` THE SYSTEM SHALL construct no `CommerceRuntime`, so every paid descriptor is refused at invocation (fail closed, today's behaviour), and legacy capabilities SHALL be unchanged.
- WHEN commerce is disabled after paid invocations exist THE SYSTEM SHALL stop new paid acceptances while mctl-api's reconciler continues to resolve outstanding invocations, and tenant reads SHALL keep working.
- THE SYSTEM SHALL refuse to start with commerce enabled if the configured `funds_mode` is anything other than `simulated` or if the admitted-provider list is empty.

### Evidence

- WHEN the proof completes THE SYSTEM SHALL write a machine-readable evidence bundle naming the mctl-agents and mctl-api commit SHAs, the image tags, the provider contract version (`mctl-commerce-dispatch/v1`, `mctl-commerce-quote/v1`, `mctl-commerce-terms/v1`), the terms id and version, and the per-scenario expected and observed results. The bundle SHALL be summarized in `docs/benchmarks/paid-capabilities-proof.md`.

## Out of scope

- Shared-tenant enablement and the final role model (mctlhq/mctl-agents#631, mctl-api#377, mctl-api#489). The milestone rule (tenant admin) from ADR 020 sec. 12 is used.
- `funds_mode: live`, real money, wallets, top-ups, payouts, refunds flows, x402/MPP (C6, mctl-api#549), marketplace UI (mctl-api#23).
- Remote (`mcp-remote`) paid providers and paid streaming/long-running tasks. They stay refused with `unsupported-execution`.
- Implementing ledger, reservation or receipt storage in mctl-agents. mctl-api owns all commerce state (ADR 020 sec. 14). This proposal only consumes and references the mctl-api endpoints and MCP tools.
- Changing ADR 020's encodings, reason-code vocabulary or state machine.

## Owner decisions (2026-10-11)

These resolve the open questions below; where they differ, the decisions win.

1. Proof tenant: a dedicated new tenant `commerce-proof`, created by an operator with the owner's OK. Never `admins`.
2. Accept-only kill switch reason code: `unsupported-execution`. No ADR 020 amendment, no `commerce-disabled` code.
3. Settlement-only retry: proven offline only against the `FakeLedger` harness. mctl-api gets no fault-injection hook. The evidence bundle marks the scenario `offline-only`.
4. `approval_expected` stays in discovery, advisory, as specified.
5. Routes: see tasks.md task 3 (mctlhq/mctl-api#569 receipt + MCP tools, mctlhq/mctl-api#570 accept-only switch).

## Open questions

- Which tenant hosts the single-tenant proof? None of the existing tenants (admins, erpact, karabu, labs, mctl, ovk) is designated. Assumption: a dedicated proof tenant created by an operator. Using `admins` would mix it with platform operations.
- Exact mctl-api read routes and MCP tool names for budget, receipt and invocation list (C2/C3). This proposal assumes `GET /api/v1/commerce/tenants/{t}/budget`, `GET .../invocations/{id}/receipt` and `GET .../invocations?capability_id=&phase=&since=`, plus MCP tools `mctl_get_commerce_budget`, `mctl_get_commerce_receipt` and `mctl_list_commerce_invocations`. Each must be confirmed against mctl-api before task 2 merges. None of them is in the MCP tool list available to this run.
- How the settlement-only retry is triggered against live simulated credits. The C3 simulated `PaymentAuthorizer` settles at once, so the scenario needs a fault-injection hook in mctl-api's simulated authorizer that only the proof tenant can use. Without that hook, the scenario is proven only offline against the `FakeLedger` harness.
- The reason code mctl-api returns while its kill switch refuses new acceptances. ADR 020 sec. 13 is closed and names none. Assumption: `unsupported-execution`, so no ADR amendment is needed. An owner may prefer a dedicated `commerce-disabled` code, which would require an ADR 020 amendment.
- Whether `approval_expected` belongs in discovery at all. It is advisory and computed from policy rules without arguments, so an argument-dependent rule reports `unknown`.
