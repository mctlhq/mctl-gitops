# Tasks: issue-429-spike-commercial-f1-verify-seller-eligib

- [ ] 1. Read the parent issue mctlhq/.github#427 and the #428 spike and pin the `.github` main
  head; record the #428 SKU if available (otherwise mark it illustrative) and confirm no existing spike with the same `Source:` exists — DoD:
  report "Evidence pins" table and a D4 SKU statement.
- [ ] 2. Gather official sources for Creem, Paddle and the invoicing / bank-acquiring fallback
  (supported countries, entity/identity, payout, prohibited products, MoR/tax boundary, pricing,
  payout cadence, refunds, disputes, cancellation, webhooks, sandbox, documented order/event
  identifiers and signature fields), read-only, no signup — DoD: every D2 cell is `[PRIMARY]` URL
  + access date or `unknown (not observed)`, failed fetches and unresolved webhook fields listed.
- [ ] 3. Write `docs/spikes/commercial-f1-seller-payments.md` sections D0-D2 and D5-D7 (non-claims,
  privacy rule, eligibility frame with the confirmed / conditional / ineligible / unknown states,
  mandatory items and `<OWNER_PRIVATE:...>` placeholders, comparison matrix, separation from #173,
  owner-private checklist, owner-only steps) (depends on 2) — DoD: no personal data, every row from
  requirements present, and the rule that any mandatory item not `confirmed` blocks launch is
  stated.
- [ ] 4. Implement `docs/spikes/commercial-f1-seller-payments/model.py` (stdlib, Decimal): fee
  calculator, HMAC webhook verifier with timestamp window, idempotent event store keyed by
  `(provider, event_id)`, order and subscription state machine keyed by
  `(provider, provider_order_id)` with partial refund, repeated disputes, monotonic transitions and
  a hold state, manual grant with manual/webhook conflict handling, reconciler, and a launch-gate
  check over the eligibility states (synthetic placeholder inputs only); plus synthetic
  `fixtures/` including event sets for permutation/replay, partial refund, dispute recurrence,
  manual/webhook conflict, wrong SKU/amount/currency and invalid signature, `fee-params.json`
  (values from task 2 with source and date) and `oracle.json` (depends on 2) — DoD: runs with
  `python3 -I`, no third-party imports.
- [ ] 5. Write `docs/spikes/commercial-f1-seller-payments/tests/test_seller_payments.py` covering
  T1-T13 (depends on 4) — DoD: `python3 -I -m unittest discover docs/spikes/commercial-f1-seller-payments/tests` passes.
- [ ] 6. Fill report D3 (flow), D4 (cost example from the model), D8 (model results, with the
  statement that the synthetic HMAC proves model invariants only, not provider webhook
  compatibility) and D9 (proposed verdict and flip conditions) (depends on 3, 5) — DoD: numbers
  match `oracle.json`; unknown costs not computable, never zero; exactly one proposed outcome, and
  no launch-blocked option proposed for adoption.
- [ ] 7. Add `roadmap/spikes/commercial-f1-seller-payments.yaml` (`lifecycle: proposed`, issue
  #429, four outcomes, `evidence.report`) and the AGENTS.md `# Spikes` entry (depends on 6) — DoD:
  `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes; commit carries the
  `Agent:` trailer per AGENTS.md.

## Tests

- [ ] T1. Fee calculator reproduces `oracle.json` net-to-seller for each option, buyer region and
  SKU variant, with per-currency minor-unit rounding; an `unknown` fee input yields "not computable",
  never zero.
- [ ] T2. Valid signature over the raw body is accepted; an invalid signature (one-byte body
  change, wrong secret, malformed signature), missing header or timestamp outside the window is
  rejected and changes no state.
- [ ] T3. Duplicate delivery of the same event id is applied once.
- [ ] T4. Out-of-order delivery (`refunded` before `paid`, late `paid` after `refunded`) ends in the
  same state as in-order delivery; terminal states are not re-granted. Every permutation and replay
  of each fixture event set either converges to the in-order state or ends in an explicit
  reconciliation hold.
- [ ] T5. Subscription cancel keeps the entitlement until period end, then expires it.
- [ ] T6. Manual fulfillment creates `source: manual` and reconciles as matched against the order
  export; a manual grant with no export row is `orphan-entitlement`.
- [ ] T7. Reconciler classifies matched, missing-entitlement, orphan-entitlement, amount-mismatch,
  sku-mismatch, currency-mismatch and owner-review, and never grants or revokes automatically on
  an ambiguous row.
- [ ] T8. Privacy scan: no string in the package passes the ISO 13616 mod-97 IBAN check, and no
  email/phone-shaped values exist outside placeholder syntax.
- [ ] T9. The model imports nothing from Agent Commerce and has no budget or capability-grant
  symbol (separation from #173).
- [ ] T10. Partial refund records the refunded amount, keeps the entitlement and flags owner
  review; cumulative refunds reaching the order amount end in `refunded`.
- [ ] T11. Dispute recurrence: a second dispute (new dispute id) after a won dispute opens again and
  a lost one revokes; replaying the first dispute's events is a no-op.
- [ ] T12. Manual/webhook conflict: a webhook for an order already granted manually with matching
  data reuses the single entitlement; with conflicting data the order is held and the entitlement
  is unchanged. An event whose SKU, amount or currency does not match the order is held, not
  applied.
- [ ] T13. Eligibility: an option with any mandatory item `conditional`, `ineligible` or `unknown` is
  reported blocked for launch and cannot be the proposed adopted rail.
- [ ] T14. `roadmap/scripts/validate.py` and `lifecycle_guard.py` pass on the new manifest.

## Rollback

Everything is additive documentation, a synthetic model and a manifest in `mctlhq/.github`. Roll
back by reverting the spike PR (or deleting the manifest, report directory and AGENTS.md line).
No provider account, tenant, secret or deployment exists to unwind.
