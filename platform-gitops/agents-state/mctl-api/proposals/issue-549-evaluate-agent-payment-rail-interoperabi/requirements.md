# Agent payment rail interoperability evaluation (x402, MPP, account-funded, Hedera) -- decision: DEFER_EXTERNAL_PAYMENT

## Context

Issue mctlhq/mctl-api#549 (roadmap id `payment-interop`, optional item of the
Agent Commerce epic mctlhq/.github#173) asks for a decision on the first
external payment rail that can plug into the existing commerce core without
creating a second authorization path. The commerce core in this repo
(`internal/commerce`, documented in `docs/commerce-ledger.md`) already holds
the whole MCTL invariant -- canonical principal, tenant authority, approval
binding (`approval_id`), budget holds, the `PaymentAuthorizer` interface and
an idempotent per-invocation payment key -- but the only adapter is
`SimulatedAuthorizer`, `funds_mode: live` is refused everywhere
(`checkFundsMode` in `internal/commerce/types.go`), and the adapter contract
requires `auth_capture`, `void` and `status_lookup` (`requiredFeatures` in
`internal/commerce/budget.go`). The x402 pilot (mctl-api#616 / PR #617) is not
present in this clone and has not passed live testnet acceptance.

This proposal compares x402, MPP, account-funded allowance and Hedera
against that same contract, records the result as a checked-in decision
record plus a mechanical, test-pinned adapter capability classification, and
recommends exactly one next step: **`DEFER_EXTERNAL_PAYMENT`**, with explicit,
testable re-entry criteria. It also defines the rail-independent external
receipt / reconciliation envelope that any later rail must populate. It
changes no runtime behaviour: no route, no table, no adapter, no env var.

## User stories

- AS a platform owner I WANT one documented, evidence-backed decision on the
  first external payment rail SO THAT no rail is wired in that bypasses
  canonical authorization, policy, budget or approval.
- AS a commerce maintainer I WANT each rail's lifecycle classified against
  the existing `PaymentAuthorizer` feature vocabulary SO THAT no adapter fakes
  authorize/capture/void/refund it does not support.
- AS a reconciler / operator I WANT a rail-independent receipt envelope SO
  THAT any future external payment can be reconciled without blind
  re-execution and without conflating customer charge currency with the
  settlement asset.
- AS a reviewer of a later rail proposal I WANT explicit re-entry criteria SO
  THAT I can tell when deferral ends and which proof to build first.

## Acceptance criteria (EARS)

- WHEN the decision record is published THE SYSTEM SHALL contain a
  comparison matrix for x402, MPP, account-funded allowance and Hedera, each
  row evaluated against the same contract: `PaymentAuthorizer`
  (`Authorize`/`Capture`/`Void`/`Status`), the `mctl-pay/v1:<invocation_id>:<operation>`
  key, the reserve/dispatch/finalize/release phase machine and the
  approval/budget gates of `docs/commerce-ledger.md`.
- WHEN the matrix records a rail THE SYSTEM SHALL record, per rail: pinned
  protocol/SDK/scheme/network/facilitator versions (or "not pinned -- not
  verified in this evaluation"), quote/challenge binding, supported lifecycle
  operations, signer custody, replay/idempotency, lost-response behaviour,
  execution-uncertainty reconciliation, settlement asset vs accounting
  currency, fee/latency/minimum charge, MCP error semantics,
  streaming/long-running support, generic-client compatibility,
  secrets/merchant/KYC constraints, and ledger mapping.
- WHEN a rail's lifecycle is classified THE SYSTEM SHALL express it as an
  `AdapterInfo` feature profile using only the existing feature constants
  (`auth_capture`, `void`, `status_lookup`, `partial_capture`, `refund`,
  `async_settlement`, `simulation`), and a unit test SHALL pin whether
  `checkAdapter` accepts or refuses that profile.
- IF a rail does not natively support a required feature THEN THE SYSTEM
  SHALL classify it as unsupported and SHALL NOT model it as emulated by MCTL
  bookkeeping.
- WHEN the x402 row is written THE SYSTEM SHALL cite mctl-api#616/#617 as
  in-progress pilot evidence only and SHALL NOT claim a live or testnet proof
  that has not been observed.
- WHEN non-custodial signing is assessed THE SYSTEM SHALL state, per rail,
  either that the payer's key stays outside MCTL (proved by naming who signs
  what) or that the rail is rejected for requiring MCTL custody.
- WHILE any external rail is evaluated THE SYSTEM SHALL treat payment proof
  as an input to `Authorize` only (`PaymentRequest` comment in
  `internal/commerce/budget.go`) and never as capability authority.
- WHEN ambiguity is defined THE SYSTEM SHALL show, per rail, that a retry
  (client, gateway, concurrent) resolves through `Status` on the same
  operation key and cannot create a second economic charge, or SHALL mark
  the rail as unable to give that guarantee.
- WHEN streaming and long-running calls are assessed THE SYSTEM SHALL
  explicitly reject them for the first external proof, consistent with the
  60 s `dispatch_deadline` fence in `docs/commerce-ledger.md`.
- WHEN the receipt envelope is recommended THE SYSTEM SHALL list, at
  minimum: `invocation_id`, `quote_digest`, payer principal, tenant, payer
  account, rail, network, settlement asset, accounting currency and amount
  (authorized and captured), settlement amount (authorized and settled),
  external payment reference, payment status, execution status, and
  reconciliation status -- with accounting money and settlement money as
  separate fields and no FX field.
- WHEN the recommendation is stated THE SYSTEM SHALL name exactly one of
  `ADOPT_X402`, `ADOPT_MPP`, `ADOPT_ACCOUNT_FUNDED`, `ADOPT_HEDERA`,
  `MULTI_RAIL_FOUNDATION`, `DEFER_EXTERNAL_PAYMENT`; this proposal names
  `DEFER_EXTERNAL_PAYMENT` and lists the re-entry criteria that would allow a
  later `ADOPT_*` proposal.
- WHILE this change is deployed THE SYSTEM SHALL behave exactly as before:
  `funds_mode: live` refused, only `SimulatedAuthorizer` installable, no new
  route, table, migration or env var.

## Out of scope

- Any adapter implementation, live or testnet funds, mainnet, wallets or
  facilitator credentials.
- MCTL custody of private keys; stored card data; stored-value products.
- Changes to `checkAdapter`, `requiredFeatures`, `checkFundsMode`,
  `PaymentAuthorizer` or the phase machine (these are recorded as re-entry
  prerequisites, not changed here).
- Provider marketplace/onboarding, payouts, revenue share, tax/VAT/FX.
- Redefining canonical authorization or approval semantics.
- Closing mctl-api#616; that needs its own live testnet acceptance.

## Open questions

- x402 pilot evidence: PR #617 is not in this clone (no `x402` symbol exists
  in the repo). The decision record must be reconciled with whatever #617
  actually proved at implementation time; if #617 has passed live testnet
  acceptance by then, the x402 row is updated but the recommendation stays
  `DEFER_EXTERNAL_PAYMENT` until the re-entry criteria (design.md) are met.
- Exact protocol/SDK versions for x402, MPP and Hedera (Agent Kit, Payments
  MCP, Network MCP) were not verified from primary sources in this run; the
  matrix marks unpinned versions explicitly and task 1 pins them from the
  vendors' published specs. Claims about these protocols in design.md are
  the investigator's understanding and must be checked, not trusted.
- Whether account-funded allowance would be "stored value" is a policy
  question for the platform owner; this proposal treats it as not authorized
  (issue body) and therefore not adoptable now, noting that invoice-backed
  entitlements (mctl-api#614) already cover the non-stored-value part.
- The upstream ADR 020 (mctlhq/mctl-agents `docs/adr/020-capability-commerce-contract.md`)
  and `docs/plans/agent-commerce.md` live outside this repo and were not
  read; the decision record cites them by path only.
- The deployed mctl-api configuration (whether `COMMERCE_*` env vars are set
  in production) could not be observed in this run; it does not affect a
  docs/test-only change.
