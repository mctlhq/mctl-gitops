# Spike F1: verify seller eligibility, hosted checkout and payout for first MCTL revenue

## Revision 2026-11-27

Revised per the review amendment register
(https://github.com/mctlhq/.github/issues/429#issuecomment-7229397137). Research only: no
outreach, charging, signup or KYC; approval only via the DevLoop decide page.

- Eligibility uses four states (confirmed / conditional / ineligible / unknown) keyed to legal
  entity, registration jurisdiction, payout and product category; anything short of confirmed on
  a mandatory item blocks launch. The checklist stays owner-private.
- The synthetic order/entitlement model covers partial refunds, repeated disputes, conflicting and
  out-of-order events and SKU/amount/currency mismatch, with per-provider order identity,
  manual/webhook conflict handling, monotonic transitions and an owner-review hold for ambiguous
  records (no automatic grant or revocation).
- The synthetic HMAC verifier is stated to prove model invariants only, not Creem/Paddle webhook
  compatibility; provider-specific official evidence and unresolved fields are documented.
- New fixtures and tests for event permutation/replay, partial refund, dispute recurrence,
  manual/webhook conflict, wrong SKU/amount/currency and invalid signature.
- The cost example uses the #428 SKU when available, otherwise it is labeled illustrative.

## Context

mctlhq/.github#429 (child of #427, P0 business priority, proposed / research only) asks for an
evidence-backed decision on how MCTL can lawfully collect its first real revenue. It compares two
Merchant-of-Record (MoR) providers, Creem and Paddle, with a lawful invoicing / bank-acquiring
fallback, evaluated against the actual seller jurisdiction and legal entity, not the owner's
residence. For each option it must verify, from current official sources, supported seller
countries, identity/entity and bank/payout eligibility, acceptance of digital services / SaaS,
tax/VAT/MoR boundaries, fees (percentage, fixed and FX), refunds and chargebacks, subscription
cancellation, payout cadence and the webhook sandbox. It must also define a minimal hosted checkout
and entitlement/reconciliation flow (signed, idempotent webhooks plus a manual-fulfillment path),
a cost example for the first SKU, a checklist and the owner-only steps.

This matters because every existing commerce artifact in this repo is explicitly simulated:
`docs/plans/agent-commerce.md` (root #173) ships simulated, non-redeemable credits, and
`docs/plans/agent-commerce-payment-rails.md` lists "merchant onboarding, provider payouts, tax/VAT/FX"
as non-goals. Nothing today tells the owner whether, where and at what cost MCTL can be paid.
The spike delivers a research package only: report, synthetic reference model, tests and a
`SpikeDefinition` manifest. It authorizes no provider signup, KYC, transaction, sandbox execution,
external publication, implementation or production change.

## User stories

- AS the MCTL owner I WANT a per-provider eligibility verdict against my actual seller entity and
  jurisdiction SO THAT I do not sign up for a provider that will later refuse or freeze payouts.
- AS the MCTL owner I WANT a worked cost example for the first SKU (fees, fixed fees, FX, VAT
  treatment, payout cost) SO THAT I can price it and compare net revenue across options.
- AS the MCTL owner I WANT an ordered owner-only checklist SO THAT the steps requiring my identity,
  bank or KYC data stay with me and never pass through agents or the repository.
- AS a future implementer I WANT a minimal checkout -> webhook -> entitlement -> reconciliation
  contract with a manual-fulfillment fallback SO THAT a later, separately approved build starts
  from a verified design.
- AS an Agent Commerce maintainer I WANT revenue checkout kept separate from simulated credits
  (#173) SO THAT real money never enters the simulated ledger or acts as capability authorization.

## Acceptance criteria (EARS)

- WHEN the spike PR is opened THE SYSTEM SHALL contain `docs/spikes/commercial-f1-seller-payments.md`,
  `roadmap/spikes/commercial-f1-seller-payments.yaml` (`lifecycle: proposed`, issue mctlhq/.github#429),
  a stdlib-only reference model with tests under `docs/spikes/commercial-f1-seller-payments/`, and an
  AGENTS.md `# Spikes` index entry.
- WHEN the report states a provider fact (supported seller country, entity type, payout method,
  prohibited product category, fee, payout cadence, refund/chargeback rule, cancellation rule,
  sandbox/webhook capability) THE SYSTEM SHALL tag it `[PRIMARY]` with the official URL and access
  date, or mark it `unknown (not observed)`.
- IF an official source cannot be fetched or is ambiguous THEN THE SYSTEM SHALL record the attempt
  and the value as `unknown (not observed)` and SHALL NOT fill it from memory, third-party blogs or
  the provider's marketing claims alone.
- WHILE evaluating eligibility THE SYSTEM SHALL key each verdict to the seller's actual legal
  entity type, registration jurisdiction, payout (bank account jurisdiction and currency) and
  product category, and SHALL NOT infer eligible-seller status from personal residence.
- WHEN an eligibility item is assessed THE SYSTEM SHALL assign exactly one state: `confirmed`,
  `conditional`, `ineligible` or `unknown`.
- IF any mandatory eligibility item for an option is not `confirmed` THEN THE SYSTEM SHALL mark
  that option blocked for launch and SHALL NOT propose it as an adopted rail.
- WHILE recording eligibility THE SYSTEM SHALL keep the per-entity checklist owner-private; the
  repository SHALL carry only the published rules, the state vocabulary and placeholders, never
  identity, address, banking or KYC data.
- WHILE writing any file THE SYSTEM SHALL contain no personal identity, address, tax ID, bank
  account, IBAN, KYC document or entity registration number; such values SHALL appear only as named
  owner-private placeholders (for example `<OWNER_PRIVATE:seller_jurisdiction>`).
- WHEN the report compares options THE SYSTEM SHALL include, per option, a row for each of:
  supported countries, entity/identity eligibility, bank/payout eligibility, digital-service
  acceptance, tax/VAT/MoR boundary, percentage fee, fixed fee, FX/currency conversion, payout fee and
  cadence, refunds, chargebacks/disputes, subscription cancellation, webhook signing and sandbox.
- WHEN the cost example is computed THE SYSTEM SHALL derive it from the reference model with Decimal
  arithmetic from fee parameters cited in the report with source dates, for at least one EU and one
  non-EU buyer. It SHALL use the SKU proposed by the #428 spike when available, and otherwise SHALL
  label the SKU and price as illustrative. An unknown cost input SHALL make the result not
  computable, never zero.
- WHEN the reference model receives a webhook event THE SYSTEM SHALL verify its signature over the
  raw body with a synthetic secret, reject an invalid signature or a stale timestamp, and apply
  each provider event id at most once.
- WHEN the report describes the synthetic verifier THE SYSTEM SHALL state that it proves model
  invariants only, not compatibility with the actual Creem or Paddle webhook format, and SHALL
  document each provider's official webhook evidence and the fields that remain unresolved.
- WHILE identifying orders THE SYSTEM SHALL key each order by `(provider, provider_order_id)` and
  each event by `(provider, event_id)`.
- IF events are duplicated, replayed, delivered in any order or conflict with each other THEN THE
  SYSTEM SHALL either converge to the same entitlement state as a single in-order delivery or place
  the order in an explicit reconciliation hold; order state transitions SHALL be monotonic, and a
  terminal state SHALL NOT be re-granted by a late event.
- WHEN a partial refund, a repeated dispute, or an SKU, amount or currency that does not match the
  order is received THE SYSTEM SHALL record it on the order and SHALL route any case whose
  entitlement effect is ambiguous to owner review.
- IF a manual grant and a webhook event disagree about the same order THEN THE SYSTEM SHALL keep a
  single entitlement for that order and SHALL hold the conflict for owner review.
- IF webhook delivery is unavailable THEN THE SYSTEM SHALL support a manual-fulfillment path in
  which the owner records a verified order reference and the entitlement is granted with
  `source: manual`, reconcilable against the provider's order export.
- WHEN reconciliation runs THE SYSTEM SHALL classify every order as matched, missing-entitlement,
  orphan-entitlement, amount-mismatch, sku-mismatch, currency-mismatch or owner-review, and SHALL
  never automatically grant or revoke on an ambiguous record.
- WHILE defining the flow THE SYSTEM SHALL keep revenue entitlements separate from the Agent
  Commerce simulated credits, ledger, `PaymentAuthorizer`, budgets and authorization (#173); a
  payment SHALL NOT grant capability authorization.
- WHEN the report concludes THE SYSTEM SHALL propose exactly one verdict from the manifest outcomes
  and SHALL list the owner-only steps that must precede any signup, together with the open
  eligibility facts that would change the verdict.
- WHEN `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` and the model tests run
  THE SYSTEM SHALL pass.

## Out of scope

- Provider account creation, KYC/KYB submission, bank connection, live or sandbox transactions,
  webhook sandbox execution, publishing checkout links or pricing pages.
- Any change to mctl-api, mctl-web, mctl-portal, mctl-gitops, tenants or Agent Commerce code.
- Integrating real money into Agent Commerce credits, x402/MPP rails (#549, #616) or budgets.
- Tax or legal advice beyond citing official provider boundaries; a professional review is an
  owner-only step.
- Choosing the first SKU's product scope (owned by the #428 spike under #427).

## Open questions

- The seller entity and jurisdiction are not stated (rightly, as they are private). The report
  evaluates the providers' published country/entity rules generically and gives a decision table
  the owner completes privately. May the country (not the identity) be named in the public report?
  Default: no.
- The first SKU and its price are not stated in #429; they come from the #428 spike, which may not
  be decided when this spike runs. Default: an illustrative EUR-denominated monthly subscription
  and a one-off variant, labeled illustrative.
- Whether a parent epic manifest for #427 should exist; no `roadmap/epics/*` file references it.
  Default: the spike manifest carries no `epic` binding.
- Whether "Creem" pages are reachable and authoritative enough; if not, its rows stay
  `unknown (not observed)` and the verdict cannot select it.
