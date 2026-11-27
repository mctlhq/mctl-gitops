# Spike F1: verify seller eligibility, hosted checkout and payout for first MCTL revenue

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
- WHILE evaluating eligibility THE SYSTEM SHALL key each verdict to the seller's legal entity type
  and registration jurisdiction and SHALL NOT infer eligible-seller status from personal residence.
- WHILE writing any file THE SYSTEM SHALL contain no personal identity, address, tax ID, bank
  account, IBAN, KYC document or entity registration number; such values SHALL appear only as named
  owner-private placeholders (for example `<OWNER_PRIVATE:seller_jurisdiction>`).
- WHEN the report compares options THE SYSTEM SHALL include, per option, a row for each of:
  supported countries, entity/identity eligibility, bank/payout eligibility, digital-service
  acceptance, tax/VAT/MoR boundary, percentage fee, fixed fee, FX/currency conversion, payout fee and
  cadence, refunds, chargebacks/disputes, subscription cancellation, webhook signing and sandbox.
- WHEN the cost example is computed THE SYSTEM SHALL derive it from the reference model with Decimal
  arithmetic from fee parameters cited in the report, for at least one EU and one non-EU buyer, and
  SHALL label the SKU price as illustrative if the owner has not fixed it.
- WHEN the reference model receives a webhook event THE SYSTEM SHALL verify its signature over the
  raw body with a synthetic secret, reject a stale timestamp, and apply each provider event id at
  most once.
- IF the same event is delivered twice or out of order THEN THE SYSTEM SHALL leave the entitlement
  in the same state as a single in-order delivery.
- IF webhook delivery is unavailable THEN THE SYSTEM SHALL support a manual-fulfillment path in
  which the owner records a verified order reference and the entitlement is granted with
  `source: manual`, reconcilable against the provider's order export.
- WHEN reconciliation runs THE SYSTEM SHALL classify every order as matched, missing-entitlement,
  orphan-entitlement or amount-mismatch and SHALL never auto-revoke on an ambiguous record.
- WHILE defining the flow THE SYSTEM SHALL keep revenue entitlements separate from the Agent
  Commerce simulated ledger, `PaymentAuthorizer` and budgets (#173); a payment SHALL NOT grant
  capability authorization.
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
- Choosing the first SKU's product scope (owned by #427).

## Open questions

- The seller entity and jurisdiction are not stated (rightly, as they are private). The report
  evaluates the providers' published country/entity rules generically and gives a decision table
  the owner completes privately. May the country (not the identity) be named in the public report?
  Default: no.
- The first SKU and its price are not stated in #429; #427 is not readable from this clone. Default:
  an illustrative EUR-denominated monthly subscription and a one-off variant, labeled illustrative.
- Whether a parent epic manifest for #427 should exist; no `roadmap/epics/*` file references it.
  Default: the spike manifest carries no `epic` binding.
- Whether "Creem" pages are reachable and authoritative enough; if not, its rows stay
  `unknown (not observed)` and the verdict cannot select it.
