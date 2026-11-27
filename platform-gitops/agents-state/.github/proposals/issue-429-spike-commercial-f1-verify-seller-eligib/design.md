# Design: issue-429-spike-commercial-f1-verify-seller-eligib

## Current state

`mctlhq/.github` is the org-level repo for plans, spikes and the declarative roadmap. It holds no
service code. What it has that is relevant here:

- Spike convention: a report in `docs/spikes/<name>.md`, an optional stdlib reference model in
  `docs/spikes/<name>/` (for example `docs/spikes/finance-assistant/model.py`,
  `fixtures/`, `tests/test_finance.py`), a `SpikeDefinition` manifest in
  `roadmap/spikes/<name>.yaml` validated against `roadmap/schemas/spike-definition.schema.json`
  (required `title`, `question`, `lifecycle`, `github.issue`, `outcomes` with at least 2 entries;
  optional `epic`, `evidence.report`, `decision`), and an index entry under `# Spikes` in
  `AGENTS.md`. `docs/spikes/finance-assistant.md` sets the house style: a "D0 Non-claims and
  evidence tags" section (`[CODE]`, `[CONFIG]`, `[LIVE]`, `[DOC]`, `[PRIMARY]` with access date,
  `[MODEL]`), an L0-L4 evidence ladder, pinned 40-hex revisions, and the rule that
  `unknown (not observed)` is never read as absent.
- CI: `.github/workflows/roadmap-validate.yml` runs
  `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` and
  `roadmap/scripts/lifecycle_guard.py` (owner decisions move `lifecycle` to `decided`, not agents).
- Commerce today is simulated only. `docs/plans/agent-commerce.md` (root #173) delivers
  "simulated credits, visibly distinguished from real money"; its non-goals include provider
  onboarding, payouts, tax/VAT engine, subscriptions engine and FX. Its protocol table notes for
  Stripe "Business eligibility remains a real-integration gate."
  `docs/plans/agent-commerce-payment-rails.md` states it "does not authorize ... merchant
  onboarding, provider payouts" and keeps tax/VAT/FX out of the governed external-payment proof.
  `roadmap/epics/agent-commerce.yaml` owns that graph. Nothing in the repo mentions Creem, Paddle,
  invoicing or #427.

Deployed state checked:

- `mctl_get_tenant commerce-proof` [LIVE]: tenant exists, owner `mashkovd`, no services,
  `allowInternetEgress: false`, description "simulated funds only, EUR 1.00 budget, no workloads".
  Confirms the only commerce tenant is the simulated #620 proof; no revenue workload exists.
- `$MCTL_GITOPS_ROOT/tenants/commerce-proof/values.yaml` [CONFIG]: same description, PVC quota 0.
- Grep of `$MCTL_GITOPS_ROOT/services` and `tenants` for `creem|paddle|stripe`: no matches. No
  payment-provider configuration is deployed as far as GitOps shows (GitOps only, not runtime).
- Parent issue #427 and the provider websites were not read in this run (no fetch performed);
  their content is an open question, not assumed.

## Proposed solution

A research-only spike package in this repo, following the finance-assistant layout. No runtime,
no other repository touched.

1. `docs/spikes/commercial-f1-seller-payments.md` (report), sections:
   - D0 Non-claims, evidence tags and ladder (L0 docs read, L1 synthetic model; L2 sandbox, L3 live
     test payment and L4 production all `not-run`, explicitly not authorized by #429). Privacy rule:
     no personal identity, bank or KYC data; seller facts appear as `<OWNER_PRIVATE:...>`
     placeholders.
   - D1 Seller-eligibility frame: eligibility is a function of (legal entity type, registration
     jurisdiction, bank account jurisdiction/currency, product category), not residence. A decision
     table the owner fills privately: for each option, the published rule and the question the owner
     answers yes/no/unknown for their entity.
   - D2 Provider comparison matrix, one column each for Creem, Paddle, and invoicing / bank
     acquiring fallback (direct invoice with bank transfer, optionally a card acquirer or payment
     link under the seller's own entity). Rows: supported seller countries; entity and identity
     (individual vs company, KYB); bank/payout eligibility and methods; digital service / SaaS /
     AI-service acceptance and prohibited lists; tax/VAT/MoR boundary (who is seller of record, who
     files EU OSS / other VAT, what the seller still owes in its own jurisdiction); percentage fee;
     fixed fee; FX and currency-conversion spread; payout fee, minimum and cadence; refunds;
     chargebacks/disputes and fees; subscription cancellation and dunning; webhook signing scheme,
     retries and sandbox availability. Each cell `[PRIMARY]` URL + access date or
     `unknown (not observed)`. For the fallback the MoR boundary inverts: the seller owns VAT
     registration/OSS, invoicing law and consumer-refund duties; the report states this as a
     boundary and defers the legal check to the owner's accountant.
   - D3 Minimal flow (below), D4 cost example, D5 separation from Agent Commerce, D6 checklist,
     D7 owner-only steps, D8 model results, D9 proposed verdict with what would change it.
2. Minimal checkout and entitlement flow (design only, provider-neutral):
   ```text
   buyer -> provider hosted checkout (no card data at MCTL)
         -> provider webhook (raw body, signature header, event id, timestamp)
         -> verify signature + timestamp window -> dedupe on (provider, event_id)
         -> apply to Order(provider_order_id) state machine
              pending -> paid -> refunded | disputed -> (won -> paid | lost -> revoked)
              subscription: active -> past_due -> canceled (entitlement until period end)
         -> Entitlement(subject, sku, source: webhook|manual, valid_until)
   manual path: owner verifies order in provider dashboard / bank statement
         -> records order ref -> Entitlement(source: manual)
   reconciliation (daily or on demand): provider order export vs entitlements
         -> matched | missing-entitlement | orphan-entitlement | amount-mismatch
         -> ambiguous => flag for owner, never auto-revoke
   ```
   Monotonic event application uses the provider's event/occurred-at ordering plus a terminal-state
   rule, so a late `paid` after `refunded` does not re-grant.
3. Reference model `docs/spikes/commercial-f1-seller-payments/model.py` (stdlib, Decimal): fee
   calculator (percentage + fixed + FX spread + payout fee, rounding per currency minor unit),
   HMAC-SHA256 webhook verifier with a synthetic secret and timestamp tolerance, idempotent event
   store, order/entitlement state machine, manual grant, and reconciler. Fixtures in `fixtures/`
   (synthetic events, a synthetic order export, `fee-params.json` copied from D2 with source URL and
   access date per value, `oracle.json`). Tests in `tests/test_seller_payments.py`. The model does
   not imitate any provider's exact signature format; it states that the real format is per
   provider docs (D2).
4. D4 cost example: illustrative first SKU (EUR monthly subscription and a one-off variant unless
   #427 fixes a price), buyers in an EU country and a non-EU country, net-to-seller per option,
   computed by the model; rows with `unknown` fee inputs are reported as not computable rather than
   estimated.
5. D5 separation from #173: revenue entitlements live outside `PaymentAuthorizer`, simulated
   ledger and tenant budgets; a paid order never sets a budget or authorizes a capability; any
   later link (for example a paid plan raising quota) is a separate, owner-approved design.
6. `roadmap/spikes/commercial-f1-seller-payments.yaml`: `lifecycle: proposed`,
   `github.issue: mctlhq/.github#429`, `evidence.report` pointing at the report, outcomes
   `ADOPT_PADDLE`, `ADOPT_CREEM`, `INVOICE_FALLBACK_FIRST`, `DEFER_NO_ELIGIBLE_RAIL`. No `decision`
   block (owner-only). No `epic` binding until #427 has a manifest.
7. AGENTS.md: one bullet under `# Spikes`.

Recommendation logic for D9 (conditional, to be filled with evidence): prefer an MoR whose
published rules accept the owner's entity type and jurisdiction and AI/SaaS products, because it
removes per-country VAT collection from a one-person operation; between MoRs, prefer the lower
all-in cost at the first SKU's price and the stronger documented payout/sandbox story; if neither
MoR is confirmed eligible, propose `INVOICE_FALLBACK_FIRST` for B2B with manual fulfillment; if
the fallback also needs an unresolved legal check, propose `DEFER_NO_ELIGIBLE_RAIL`.

## Alternatives

- Build a Stripe (non-MoR) integration now. Dropped: #429 limits scope to research; Stripe is
  already noted in `docs/plans/agent-commerce.md` with an open business-eligibility gate, and a
  non-MoR leaves all VAT duties with the seller. It can be listed in D2 as context only.
- Route first revenue through Agent Commerce (convert simulated credits to real top-ups).
  Dropped: #173 and the payment-rails plan explicitly forbid real stored value and payouts in that
  path, and #429 requires separation.
- Report without a reference model. Dropped: idempotency, out-of-order delivery and fee/FX
  rounding are exactly where prose designs fail; the finance-assistant spike shows a small stdlib
  model with an oracle is cheap and reviewable.

## Platform impact

- No migrations, no deployed change, no new tenant or secret. Files are additive in `.github`;
  CI cost is one more manifest in `roadmap-validate.yml` and a stdlib unittest run.
- Risk: leaking private seller data into a public repo. Mitigation: placeholders only, a test that
  greps the package for IBAN-shaped strings that pass mod-97 and for email/phone patterns, and an
  explicit reviewer check.
- Risk: stale or memory-sourced provider facts. Mitigation: every fact carries URL + access date or
  `unknown (not observed)`; the verdict lists which unknowns would flip it.
- Risk: report read as authorization to sign up. Mitigation: D0 non-claims, `lifecycle: proposed`,
  owner-only steps gated behind an explicit owner decision.
