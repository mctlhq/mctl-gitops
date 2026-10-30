# Tasks: issue-549-evaluate-agent-payment-rail-interoperabi

- [ ] 1. Capture the contract under test: write the first section of
  `docs/payment-rail-interop.md` quoting `PaymentAuthorizer`, `AdapterInfo`,
  `requiredFeatures`, `checkAdapter`, the phase machine and the
  unknown-is-never-denied rule from `internal/commerce/budget.go` and
  `docs/commerce-ledger.md`, plus a header stating the record authorizes no
  funds, wallets, payouts or production rails. — DoD: section exists, every
  quoted symbol exists in the tree.
- [ ] 2. Collect pinned x402 evidence (depends on 1): read the current state of
  #616 and draft PR #617 (`experiments/x402-mcp-check`), the x402 spec at
  commit `6c470a80c6145b27fcbb4f6359c47a6a8cfe5887`
  (`specs/transports-v2/mcp.md`, `specs/schemes/exact/scheme_exact_evm.md`),
  EIP-3009, and the current x402 SDK/facilitator release; record whether any
  auth/capture-style scheme exists for the selected tuple. — DoD: source-pin
  table rows for x402; explicit statement of what #616/#617 have and have not
  proven live.
- [ ] 3. Collect pinned MPP evidence (depends on 1): read
  github.com/tempoxyz/mpp-specs at a commit SHA and the IETF
  `draft-ryan-httpauth-payment` revision; map `charge` and `session` intents to
  `Authorize`/`Capture`/`Void`/`Status` without inventing features. — DoD:
  pinned rows; each operation classified or marked `unpinned`.
- [ ] 4. Collect pinned Hedera evidence (depends on 1): Hedera Agent Accounts,
  Payments MCP / Network MCP docs and availability (partner vs public
  testnet); evaluate delegated spend, owner signing/limits, payee/tool scope,
  revocation, status/reconciliation, audit. — DoD: pinned rows with access
  dates; testnet availability stated as observed.
- [ ] 5. Account-funded analysis (depends on 1): map top-up/invoice/chargeback
  onto existing `commerce_entitlements` (`invoice_ref`) and budgets, without
  proposing stored value or stored cards. — DoD: matrix column complete,
  citing entitlement hold/capture/release code paths.
- [ ] 6. Fill the comparison matrix and adapter capability classification
  (depends on 2-5): every field from the issue, every cell `native` /
  `emulated-with-evidence` / `unsupported` / `unpinned` with a citation;
  custody, ambiguity/retry, currency, fee/latency/minimum charge, MCP error
  semantics, streaming/long-running (support or explicit rejection), generic
  vs binding-aware buyer, eligibility/KYC/secrets. — DoD: no empty cell; no
  rail marked `Void`-capable if it settles at authorize time.
- [ ] 7. Add `internal/commerce/rail.go` (depends on 6): inert
  `ExternalPaymentEnvelope`, `RailCapability` constants, a classification
  table mirroring task 6, and `RequiredFeaturesSatisfied` reusing
  `requiredFeatures`. Not wired into `Store`, routes or MCP. — DoD: `go fmt`,
  `go vet`, `golangci-lint` clean; no change to `checkAdapter` or
  `SimulatedAuthorizer`.
- [ ] 8. Define the envelope section of the record (depends on 7): field
  list matching `ExternalPaymentEnvelope`, with accounting amount (ISO 4217
  minor units) and settlement amount (asset atomic units) distinct and no FX.
  — DoD: section and type agree field-for-field.
- [ ] 9. Apply the decision rubric and record exactly one token (depends on 6,
  8): explain why it beats each rejected alternative; if adopting, draft the
  bounded testnet proof scope (identity -> authorization -> policy -> budget
  -> approval -> payment -> execution -> ledger/reconciliation); if
  deferring, write measurable re-entry criteria and the leading retest
  candidate. — DoD: one token; each material claim pinned; no claim of live
  proof not recorded in #616.
- [ ] 10. Link the record from `docs/commerce-ledger.md` ("Adapter contract"
  section) and post a summary comment reference for #549 in the PR body
  (depends on 9). — DoD: link present; PR body states #616 remains open and no
  production rail is authorized.

## Tests

- [ ] T1. `TestRailClassificationAgainstRequiredFeatures` in
  `internal/commerce/rail_test.go`: for each classified rail,
  `RequiredFeaturesSatisfied` matches the record (for example x402 `exact`
  returns false because `void` is `unsupported`); `simulated` returns true.
- [ ] T2. `TestCheckAdapterRefusesExactSettleOnly`: an `AdapterInfo` declaring
  only `status_lookup` and `async_settlement` is refused by `checkAdapter`
  with `ErrAdapterIneligible`; one declaring only `FundsModeLive` is refused.
  Confirms the decision did not relax the contract.
- [ ] T3. `TestExternalPaymentEnvelopeHasNoSecrets`: reflect over
  `ExternalPaymentEnvelope` fields and assert no field named like proof,
  signature, idempotency key or private key, mirroring the `Receipt`
  allowlist rule.
- [ ] T4. `TestEnvelopeKeepsCurrencyAndAssetDistinct`: an envelope with
  `AccountingAmount{EUR, 1}` and `SettlementAmount "10000"` / asset USDC
  validates without any conversion; an `AccountingAmount` with a non-ISO code
  (`USDC`) is refused by the existing `Money` validation.
- [ ] T5. Existing `go test ./internal/commerce/...` (including
  `TestAdapterNegotiation` and `TestUnknownAuthorizationIsNeverDenied`) and
  `internal/mcp` `server_test.go` tool count pass unchanged.

## Rollback

The change is a new document, one inert Go file and its tests, and a doc
link. Revert the PR; no data, route, env var or deployment depends on it. The
decision token can be superseded by a later record without code changes.
