# Design: issue-549-evaluate-agent-payment-rail-interoperabi

## Current state

The commerce core lives in `internal/commerce` and is documented in
`docs/commerce-ledger.md` (C2 #547, C3 #548, C4 server half of
mctl-agents#619, entitlements #614).

- **Adapter contract.** `internal/commerce/budget.go` defines
  `PaymentAuthorizer` with `Adapter() AdapterInfo`, `Authorize(ctx, q,
  PaymentRequest)`, `Capture(ctx, q, key, authorizationID, Money)`,
  `Void(ctx, q, key, authorizationID)` and `Status(ctx, q, key)`. Every
  operation is idempotent on its key (`mctl-pay/v1:<invocation_id>:<operation>`);
  the same key with different parameters is `ErrPaymentConflict`. The comment
  on the interface already anticipates that "a future external rail ignores
  [the querier] and the core treats its answer as unknown until status
  confirms it". `PaymentRequest` is the only place a payment proof may enter
  ("A payment proof, when a future rail needs one, is an input here and
  nowhere else").
- **Feature negotiation.** Constants `FeatureAuthCapture`, `FeatureVoid`,
  `FeatureStatusLookup`, `FeaturePartialCapture`, `FeatureRefund`,
  `FeatureAsyncSettlement`, `FeatureSimulation`;
  `requiredFeatures = {auth_capture, void, status_lookup}`. `checkAdapter`
  refuses an adapter missing any required feature or not listing
  `FundsModeSimulated`; `Store.UseAuthorizer` runs it at install time.
- **Only adapter.** `SimulatedAuthorizer` records operations in
  `commerce_payment_operations` inside the ledger transaction and denies
  anything not `funds_mode: simulated` with `funds-mode-unavailable`.
- **Unknown is never denied.** An unclassifiable or missing adapter answer
  leaves the hold with `payment_status: unknown` (409 `payment-unknown`);
  `reserved -> dispatching` is refused until a `…/reserve` retry resolves it
  via `Status` on the same key, never a fresh authorize
  (`TestUnknownAuthorizationIsNeverDenied`, budget_test.go:609). Capture and
  void are preceded by the same status lookup.
- **Money and currency.** `Money` in `internal/commerce/types.go` is integer
  minor units with an ISO 4217 code validated against `currencyExponents`
  (EUR, USD, GBP, CHF, PLN, CZK, SEK, ...). There is no asset type for USDC
  or HBAR, and budgets fix their currency once used.
- **Binding.** `quote_digest` (`mctl-commerce-quote/v1`) and
  `terms_binding` (`mctl-commerce-terms/v1`) are pinned to golden vectors in
  `digest_test.go`. `tenant_id`, `principal_id`, `payer_account_id`
  (`acct_tenant_<tenant>`) are derived server-side, never from a body.
- **Dispatch fence.** `internal/commerce/dispatch.go` signs an Ed25519
  `mctl-commerce-dispatch/v1` authorization over invocation, provider
  operation key, capability, schema hash, args digest, tenant and deadline;
  replays are deterministic and providers dedupe on `provider_operation_key`.
- **Account-funded today.** `commerce_entitlements` grant finite units
  against a verified `invoice_ref` (admin only), held on `…/reserve` and
  captured/released on finalize; budgets are monthly limits, never balances.
  This is already an "invoice funds an allowance consumed by governed usage"
  shape with no external rail at execution time.
- **Receipt.** `internal/commerce/receipt.go` `Receipt` is an explicit
  allowlist (ids, quote digest, terms, tenant, payer account, principal,
  price, five facts, phase, policy decision ref) and carries no payment proof
  or `external_ref` contents. It has no rail, network, asset or settlement
  amount fields.
- **Routing/MCP.** `internal/api/router.go` wires `Commerce *commerce.Store`;
  MCP read tools `mctl_get_commerce_budget`, `mctl_list_commerce_invocations`,
  `mctl_get_commerce_receipt` exist.
- **x402 evidence (#616 / draft PR #617, branch
  `feat/x402-mcp-check-testnet`, last updated 2026-10-13, OPEN, not merged).**
  An isolated Node 24 experiment under `experiments/x402-mcp-check`: x402 v2
  `exact` / EIP-3009 only, Base Sepolia `eip155:84532`, test USDC
  `0x036CbD53842c5426634e7929541eC2318f3dCF7e`, fixed 10000 atomic units
  (0.01 USDC), facilitator `https://x402.org/facilitator` (`/supported`,
  `/verify`, `/settle`), MCP profile `2025-06-18`, JSON-response only (SSE
  rejected as a profile limitation). Specs pinned at x402-foundation/x402
  commit `6c470a80c6145b27fcbb4f6359c47a6a8cfe5887` (`specs/transports-v2/mcp.md`,
  `specs/schemes/exact/scheme_exact_evm.md`); hosted facilitator version is
  not pin-able. Buyer is binding-aware (signs a nonce bound to request,
  endpoint, payer and terms); generic-client interoperability is not
  established; server never accepts private keys. 42 offline tests pass with
  injected facilitator and chain fixtures. PR text: "No live testnet transfer,
  external wallet signature, hosted-facilitator conformance proof or real
  public target proof has been performed." It also states the simulated
  `PaymentAuthorizer` is not treated as an x402 reserve/capture/void adapter
  and introduces no EUR/USDC conversion.
- **External sources skimmed (unpinned, secondary).** MPP: Tempo + Stripe,
  submitted to IETF as `draft-ryan-httpauth-payment`; intents `charge`
  (settles per request) and `session` (lock funds, off-chain vouchers,
  periodic settlement); spec repo github.com/tempoxyz/mpp-specs, docs mpp.dev.
  Hedera Agent Accounts: announced October 2026; per-agent accounts with
  total/daily/per-transaction caps and payee allowlists enforced by smart
  contract, revocable by owner, MCP server + REST + relayer ("Agentic Payment
  Services"), HBAR/USDC, stated x402 compatibility; limited partner testnet
  Q4 2026, public testnet targeted Q1 2027. None of these were read at a
  pinned revision during investigation.

Deployed state checked:

- `gh pr view 617 -R mctlhq/mctl-api` and `gh issue view 616`: both OPEN; PR
  draft, unmerged; body and README quoted above.
- `$MCTL_GITOPS_ROOT/services/` listing: tenants `admins`, `karabu`, `labs`;
  no `mctl-api` service directory, and `grep -r COMMERCE_` found nothing.
  The deployed mctl-api configuration (whether `COMMERCE_DB_URL`,
  `COMMERCE_ACCEPT_DISABLED` or dispatch keys are set) could not be observed
  from this checkout. This is recorded as a gap, not as "commerce disabled".
- mctl MCP tools were not called; this proposal changes no deployed
  configuration.

## Proposed solution

The work is primarily a decision record, plus a small, inert code slice that
makes the classification and envelope machine-checkable. No adapter is
installed, no route changes, `funds_mode: live` stays refused.

### 1. Decision record `docs/payment-rail-interop.md`

Sections:

1. **Contract under test.** The `PaymentAuthorizer` operations, required
   features, phase machine and the invariant, quoted from
   `internal/commerce/budget.go` and `docs/commerce-ledger.md`. Every rail is
   measured against this exact contract; nothing is relaxed per rail.
2. **Source pins.** A table: rail, artifact (spec commit / draft revision /
   SDK version / vendor page + access date), what it was used for. Unpinned
   claims are flagged and excluded from the decision.
3. **Comparison matrix.** One column per rail, one row per field listed in
   the issue. Lifecycle cells use the classification below.
4. **Adapter capability classification.** For each rail and each of
   `Authorize`, `Capture`, `Void`, `Status`, `partial_capture`, `refund`,
   `async_settlement`: `native`, `emulated-with-evidence` (and how), or
   `unsupported`. Working hypotheses to verify against pins:
   - x402 `exact`: verify-then-settle; no hold, no void after settle.
     Mapping candidate "authorize = facilitator verify (no funds move),
     capture = settle at finalize, void = never call settle (nonce expires)";
     must check EIP-3009 `validBefore` vs dispatch + finalize window and that
     an unsettled signed authorization cannot be settled by a third party
     after "void" (it can, until expiry, by anyone holding it: classify void
     as `unsupported` unless the facilitator or nonce cancellation
     (`cancelAuthorization`, payer-signed) provides it). Refund
     `unsupported` in-protocol. Status = facilitator response + chain
     reconciliation from #617's `reconcile.mjs`.
   - MPP `charge`: like x402 exact. MPP `session`: closest to
     reserve/capture (locked deposit, cumulative vouchers, close); classify
     only from the pinned spec.
   - Account-funded: maps natively onto existing entitlement hold/capture/
     release and budget holds; the external rail (invoice/top-up/chargeback)
     sits before execution, outside `PaymentAuthorizer`'s hot path.
   - Hedera: owner-signed caps enforced on-chain; agent requests spend; no
     known hold/void primitive; classify from pinned docs or mark
     `unpinned` if only partner testnet exists.
5. **Custody.** Per rail: who signs, where the key lives, whether MCTL can stay
   non-custodial. x402/MPP: payer wallet signs (as in #617's external
   signing-bundle helper); Hedera: owner wallet sets limits, agent key or
   relayer submits; account-funded: no payer key at all.
6. **Ambiguity and retries.** Per rail, map lost authorize/settle responses to
   `payment_status: unknown`, name the status/reconcile API (x402: facilitator
   `/settle` replay + chain `AuthorizationUsed` log by nonce; MPP: per pinned
   spec; Hedera: mirror node / HCS record; account-funded: ledger-local), and
   show that the idempotency key `mctl-pay/v1:<invocation_id>:<op>` plus a
   rail-level nonce derived from the invocation prevents a duplicate economic
   charge. Execution uncertainty stays on the existing `outcome_unknown` path
   and provider `provider_operation_key` dedupe; no rail permits blind
   re-execution.
7. **Currency.** Accounting currency (ISO 4217 in `Money`) and settlement
   asset (CAIP-19-style `network` + `asset` + atomic amount) are separate.
   A rail whose terms are priced in its asset needs the terms themselves to be
   priced in that asset, which `currencyExponents` does not allow today; the
   record states this as a blocker per rail rather than inventing FX.
8. **Fees, latency, minimum charge; MCP errors; streaming/long-running;
   generic client; eligibility/KYC/secrets.** One subsection each, cells
   cited. Streaming and long-running calls are rejected for the first proof
   unless a rail natively supports metered sessions (MPP session is the only
   candidate) and the dispatch fence (60 s `dispatch_deadline`) can cover it.
9. **External receipt / reconciliation envelope** (see 2).
10. **Decision.** Exactly one token with a rubric (below), why it beats every
    rejected alternative, and either the bounded proof scope or the re-entry
    criteria.

### 2. Canonical envelope (inert type + golden test)

Add `internal/commerce/rail.go` with:

```go
// ExternalPaymentEnvelope is the rail-independent receipt/reconciliation
// record of docs/payment-rail-interop.md. Not yet persisted or served.
type ExternalPaymentEnvelope struct {
    SchemaVersion       int    // 1
    InvocationID        string
    QuoteDigest         string
    ActionDigest        string // args_digest-bound action, from the dispatch fence
    PayerPrincipalID    string
    TenantID            string
    PayerAccountID      string
    Rail                string // "x402", "mpp", "account", "hedera", "simulated"
    Network             string // e.g. "eip155:84532"; "" for account
    Asset               string // e.g. CAIP-19 asset id; ISO code for account
    AccountingAmount    Money  // ISO 4217 minor units, the ledger price
    SettlementAmount    string // decimal string of asset atomic units
    ExternalPaymentRef  string // tx hash / payment id, opaque
    PaymentState        string // the ledger payment_status vocabulary
    ExecutionState      string // execution_outcome vocabulary
    ReconciliationState string // "pending", "matched", "mismatch", "unresolved"
}
```

and `RailCapability` / `ClassifyRail` constants (`native`,
`emulated-with-evidence`, `unsupported`) holding the classification table from
the record, plus a function `RequiredFeaturesSatisfied(rail) bool` that reuses
`requiredFeatures`. Nothing calls it from `Store`; it exists so the decision's
claim "rail X cannot pass `checkAdapter` as specified" is a unit test, not
prose. The envelope never carries payment proofs, signatures or idempotency
keys, matching the `Receipt` allowlist rule.

### Decision rubric (applied after evidence collection)

A rail may be adopted only if, from pinned evidence, all hold: (a) binding to
quote digest + payer + tenant + expiry is possible; (b) MCTL stays
non-custodial; (c) every required feature is `native` or
`emulated-with-evidence` without faking; (d) lost-response recovery exists
without blind re-execution; (e) a testnet path is available now; (f) the
settlement asset can be priced without FX. Otherwise:
`MULTI_RAIL_FOUNDATION` only if two or more rails pass (c) through the same
contract change; `DEFER_EXTERNAL_PAYMENT` if none passes.

**Provisional expectation from the evidence available today (to be confirmed
or overturned by task 2-4, not preselected):** x402 fails (c) for `Void` as
the contract stands and (e) for live proof (#616 has none); MPP and Hedera fail
(e)/pinning (Hedera public testnet not yet available); account-funded passes
(a)-(d) but is not an external rail at execution and the issue bars a new
stored-value product. The likely outcome is `DEFER_EXTERNAL_PAYMENT` with x402
as the leading retest candidate. Re-entry criteria to record if so:
1. #616 live Base Sepolia transfer with an external-wallet signature,
   facilitator settle, and chain reconciliation of a deliberately lost settle
   response;
2. an accepted ADR 020 amendment for a "settle-on-finalize" adapter class
   (authorize = verify, capture = settle, void = payer-side cancellation or
   proven expiry) or a rail with native void;
3. a terms pricing decision for non-ISO settlement assets (asset-priced terms,
   no FX);
4. a pinned MPP session spec revision or a Hedera public testnet, whichever
   arrives first, retested against the same matrix.

If the evidence instead supports adoption, the record drafts one governed
testnet proof: canonical principal -> tenant authority -> policy ->
`…/budget/precheck` -> approval -> `…/reserve` (adapter `Authorize`) ->
`…/dispatch` fence -> provider execution -> `…/finalize` (`Capture`/`Void`)
-> envelope + reconciliation, with `funds_mode` remaining non-live until a
separate review.

## Alternatives

- **Adopt x402 now on the strength of #617.** Rejected for this slice: #617 is
  offline-fixture evidence only, uses its own SQLite store and identity, and
  explicitly is not a reserve/capture/void adapter. Adopting it would either
  fake `Void` or add a second ledger/authorization path.
- **Relax `requiredFeatures` so exact-settle rails install.** Rejected: it
  would let a rail that has already moved funds be "voided" by the ledger
  while money stays transferred, contradicting the release/finalize rules in
  `docs/commerce-ledger.md`. A contract change belongs in ADR 020 and is a
  re-entry criterion, not a side effect of this research.
- **Purely prose decision with no code.** Considered; the small inert
  classification and envelope type is kept because it makes the
  "cannot pass `checkAdapter`" claims test-checked and gives the next slice a
  fixed envelope shape. It can be dropped without affecting the decision if
  reviewers prefer docs only.

## Platform impact

- No migrations, no new routes, no MCP tool changes (the `server_test.go`
  tool count is unchanged), no env vars.
- `internal/commerce/rail.go` is unexported from the request path; no
  behaviour change. `checkAdapter`, `requiredFeatures` and live-funds refusal
  are untouched and covered by an added test.
- Risk: the record makes claims about fast-moving third-party protocols.
  Mitigation: every material claim pinned with revision and access date;
  unpinned claims excluded from the decision.
- Risk: the record is read as authorizing real payments. Mitigation: a header
  stating it authorizes no funds, wallets, payouts or production rails, as the
  issue requires.
- Resource impact: none at runtime.
