# Evaluate agent payment rail interoperability (x402, MPP, account-funded, Hedera)

## Context

Issue mctlhq/mctl-api#549 (roadmap item `payment-interop`, optional, epic
mctlhq/.github#173 Agent Commerce) asks for an evidence-driven decision on the
first external payment rail shape that can plug into the existing MCTL commerce
core without creating a second authorization path. The core already exists in
`internal/commerce`: a ledger with an immutable `quote_digest`, a phase machine
(`accepted -> reserved -> dispatching -> dispatched -> finalized`, plus
`outcome_unknown`), tenant budgets that are limits and never balances, finite
prepaid entitlements backed by an `invoice_ref`, a signed dispatch fence, and one
`PaymentAuthorizer` interface (`Authorize`, `Capture`, `Void`, `Status`) whose
only implementation is `SimulatedAuthorizer`. `checkAdapter` refuses any adapter
that lacks `auth_capture`, `void` or `status_lookup`, or that does not support
`funds_mode: simulated`; `funds_mode: live` is refused everywhere.

The deliverable is a decision record that compares x402, MPP, account-funded /
enterprise allowance and Hedera Agent Accounts against that same contract,
classifies each rail's real adapter capabilities instead of assuming
authorize/capture/void/refund, defines a rail-independent external receipt /
reconciliation envelope, and ends in exactly one token: `ADOPT_X402`,
`ADOPT_MPP`, `ADOPT_ACCOUNT_FUNDED`, `ADOPT_HEDERA`, `MULTI_RAIL_FOUNDATION` or
`DEFER_EXTERNAL_PAYMENT`. It matters because a rail adopted without this
mapping would either fake adapter operations it cannot perform (for example a
`Void` on an already-settled x402 `exact` transfer) or let a payment proof act
as authority, both of which break the MCTL invariant:
`has funds AND authorized AND within policy AND within budget AND approved when
required -> execute`, where payment proof never grants capability authority.

## User stories

- AS a platform owner I WANT one evidence-backed rail decision against the
  existing `PaymentAuthorizer` / ledger / governance contract SO THAT the next
  implementation slice does not introduce a second authorization path.
- AS a commerce-core maintainer I WANT each rail's lifecycle classified into
  the adapter feature vocabulary already in `internal/commerce/budget.go`
  (`auth_capture`, `void`, `status_lookup`, `partial_capture`, `refund`,
  `async_settlement`, `simulation`) SO THAT no adapter claims an operation the
  rail cannot perform.
- AS a reconciliation operator I WANT a canonical rail-independent receipt
  envelope that keeps accounting currency and settlement asset separate SO
  THAT ambiguous settlements can be resolved without blind re-execution or
  implicit FX.
- AS a security reviewer I WANT custody of signing keys proven or rejected
  per rail SO THAT MCTL never holds customer wallet keys.
- AS the roadmap owner I WANT the decision to name one next step and, if a
  rail is adopted, a bounded scope for one governed external-payment proof (or,
  if deferred, concrete re-entry criteria) SO THAT follow-up work is ready to
  pick up.

## Acceptance criteria (EARS)

- WHEN the decision record is written THE SYSTEM SHALL contain one comparison
  matrix row per rail (x402, MPP, account-funded, Hedera) covering every field
  the issue lists: quote/challenge binding (payer, canonical principal, tenant,
  capability/action digest, expiry); lifecycle (exact, spend cap,
  reserve/authorize, capture, void, refund, status/reconcile); signer custody;
  replay/idempotency under client retry, gateway retry and concurrency;
  lost-response recovery; execution-uncertainty reconciliation; settlement
  asset vs accounting currency; fee, latency and minimum sensible charge; MCP
  error semantics; streaming and long-running support; generic-client vs
  binding-aware buyer; secrets/merchant/KYC/eligibility; ledger mapping.
- WHEN a material protocol claim is recorded THE SYSTEM SHALL cite a pinned
  source (commit SHA, spec draft revision, SDK version or dated vendor page),
  and IF a claim cannot be pinned THEN THE SYSTEM SHALL mark it `unpinned` and
  SHALL NOT rely on it for the decision.
- WHEN x402 is evaluated THE SYSTEM SHALL consume the current state of
  mctlhq/mctl-api#616 and draft PR #617 and SHALL state that no live testnet
  transfer, external-wallet signature or hosted-facilitator conformance proof
  has been performed unless #616 records one.
- WHEN a rail is mapped onto `PaymentAuthorizer` THE SYSTEM SHALL classify each
  operation as `native`, `emulated-with-evidence` or `unsupported`, and SHALL
  NOT mark `Void` or `Capture` as supported for a rail that settles at
  authorization time.
- WHILE any rail is evaluated THE SYSTEM SHALL treat payment proof as an input
  to `PaymentAuthorizer.Authorize` only (per `PaymentRequest` in
  `internal/commerce/budget.go`) and never as authorization, policy, budget or
  approval evidence.
- WHEN custody is evaluated THE SYSTEM SHALL record for each rail whether MCTL
  can remain non-custodial, and IF a rail requires MCTL to hold a payer private
  key THEN THE SYSTEM SHALL reject that rail configuration.
- WHEN ambiguity is evaluated THE SYSTEM SHALL describe, per rail, how a lost
  response or unknown settlement maps to `payment_status: unknown` /
  `outcome_unknown` and which status API resolves it, and SHALL show whether a
  retry can avoid a duplicate economic charge.
- WHEN streaming and long-running calls are evaluated THE SYSTEM SHALL record
  each rail as supporting them with a cited mechanism or explicitly rejecting
  them for the first proof.
- WHILE accounting currency and settlement asset differ THE SYSTEM SHALL keep
  them as distinct fields and SHALL NOT convert between EUR, USDC or HBAR.
- WHEN the envelope is defined THE SYSTEM SHALL include at least: invocation
  id, quote digest / action digest, payer principal, tenant, rail, network,
  asset, accounting amount (ISO 4217 minor units), settlement amount (asset
  atomic units), external payment reference, payment state, execution state and
  reconciliation state.
- WHEN the decision is recorded THE SYSTEM SHALL name exactly one token from
  the six allowed, and SHALL explain why it beats each rejected alternative.
- IF the token adopts a rail or `MULTI_RAIL_FOUNDATION` THEN THE SYSTEM SHALL
  draft a bounded scope for one governed external-payment proof through
  canonical identity -> authorization -> policy -> budget -> approval ->
  payment -> execution -> ledger/reconciliation, testnet only.
- IF the token is `DEFER_EXTERNAL_PAYMENT` THEN THE SYSTEM SHALL define
  measurable re-entry criteria and name the leading candidate to retest first.
- WHEN the adapter classification is encoded in code THE SYSTEM SHALL keep
  `checkAdapter` refusing an adapter without `auth_capture`, `void` and
  `status_lookup`, and SHALL keep `funds_mode: live` refused.

## Out of scope

- Mainnet or production funds, live `funds_mode`, production rollout of any
  rail (separately reviewed scope).
- MCTL custody of private wallet keys; stored card data; a stored-value or
  top-up product.
- Provider marketplace or onboarding, payouts, revenue share.
- Tax, VAT or FX engine.
- Redefining canonical authorization, policy or approval semantics.
- Implementing an external `PaymentAuthorizer` adapter in this proposal.
- Closing #616 or merging #617; they require their own live testnet acceptance.

## Open questions

- Pinned sources for MPP and Hedera were not fully read during investigation:
  MPP is published by Tempo/Stripe (github.com/tempoxyz/mpp-specs, IETF
  `draft-ryan-httpauth-payment`) with `charge` and `session` intents; whether
  a session maps to reserve/capture/void must be read from a pinned revision.
  Hedera Agent Accounts were announced in October 2026 with a limited partner
  testnet in Q4 2026 and public testnet targeted for Q1 2027 (secondary
  sources only); hands-on evaluation may be impossible inside this slice. The
  proposal treats any rail without a testable pinned artifact as `unpinned`.
- The x402 `exact` scheme settles on `/settle`; there is no void. Whether a
  future adapter class "settle-on-finalize" (authorize = verify only, capture =
  settle, void = never settle) is acceptable inside ADR 020 sec. 10 is a
  contract question for mctl-agents ADR 020, not decided here.
- ADR 020 (`mctlhq/mctl-agents docs/adr/020-capability-commerce-contract.md`)
  and `docs/plans/agent-commerce.md` are not in this clone; the design relies on
  `docs/commerce-ledger.md`, which summarizes them.
- The deployed configuration of mctl-api (whether `COMMERCE_*` variables are
  set in production) could not be observed from the available gitops checkout;
  it does not change this research deliverable but must be checked before any
  proof is deployed.
- Whether the final token may be `ADOPT_ACCOUNT_FUNDED` given that the issue
  limits account-funded to "comparison/design only": this proposal reads that
  as "may be recommended, but its proof uses existing invoice-backed
  entitlements and budgets, never a new stored-value product".
