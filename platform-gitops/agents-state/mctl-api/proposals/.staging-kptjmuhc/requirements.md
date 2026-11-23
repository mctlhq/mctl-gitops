# Payment rail interoperability decision, revision 3 (x402, MPP, account-funded, Hedera, MCP Payments / SEP-2007)

## Context

Issue mctlhq/mctl-api#549 (roadmap `payment-interop`, optional item of the closed
Agent Commerce epic mctlhq/.github#173) asks which external payment rail shape
could plug into the existing commerce core in `internal/commerce` without
creating a second authorization path. The MCTL invariant stays: `has funds` AND
`authorized` AND `within policy` AND `within budget` AND `approved when
required` -> execute. Payment proof never grants capability authority. The
2026-11-22 owner refresh adds MCP Payments (SEP-2007) and merchant/buyer
separation. It also requires a source-pinned matrix and an ADR with one of
`KEEP_SIMULATED | EXTEND_X402_PILOT | EVALUATE_MPP | ACCOUNT_FUNDED_FIRST | DEFER`.
Spending, wallets, onboarding, production changes and the implementer are not
authorized.

The independent review of revision 2 (REQUEST_CHANGES, 2 P1 / 3 P2) found five
problems:

- P1-PAY-01: the crash gap between an external money side effect and the
  Postgres commit in `Store.Reserve`/`Store.Finalize`.
- P1-PAY-02: the MCTL payment key was conflated with the payer-signed nonce.
- P2-PAY-03: the verdict was hard-coded before verification.
- P2-PAY-04: a fixture that declares simulated funds was a false-positive
  eligibility.
- P2-PAY-05: the static capture-deadline rule and the asset boundary were not
  executable checks.

Revision 3 changes only documentation and test-only negative classification
fixtures. It keeps the isolated #616/PR #617 testnet boundary unchanged. Every
outcome is a **proposed** recommendation with measured conditions. The owner
decision is left unissued.

## User stories

- AS the platform owner I WANT one evidence-based proposed recommendation, with separate merchant and buyer answers and pinned sources, SO THAT I can make a digest-bound decision without trusting vendor marketing.
- AS a commerce-core maintainer I WANT the external-side-effect/DB-commit gap and the identifier separation specified before any live adapter is designed, SO THAT no future rail can move funds without a committed, recoverable operation record.
- AS a reviewer I WANT executable negative fixtures that show which rail shapes `checkAdapter` refuses and which pass only on contract shape, SO THAT a fixture can never be read as live-rail eligibility.
- AS a tenant owner I WANT accounting currency and settlement asset kept distinct, with deadlines checked at every step, SO THAT no implicit FX or payer reclaim can desynchronize my budget.

## Acceptance criteria (EARS)

- WHEN a protocol claim is material to the recommendation THE SYSTEM SHALL cite a pinned source (commit SHA or blob SHA, draft name and revision, or vendor URL with access date). It SHALL label vendor pages and third-party comments (including Screwtape) as self-report.
- WHEN the comparison is written THE SYSTEM SHALL compare x402, MPP, account-funded and Hedera against the same `PaymentAuthorizer` (`Authorize`/`Capture`/`Void`/`Status`), ledger and governance contract in `internal/commerce/budget.go`. It SHALL classify each adapter capability as native, emulated-with-evidence, unsupported or unknown.
- WHEN a rail-shape fixture is evaluated THE SYSTEM SHALL record two separate results: the `checkAdapter` outcome, and an `eligible_for_mctl` verdict. The verdict SHALL be `false` for every external rail in this revision. A fixture that passes `checkAdapter` only by declaring `FundsModeSimulated` without a proven real simulator SHALL be labelled `contract-shape only`.
- WHEN the design describes any future external adapter THE SYSTEM SHALL require a durable pre-call payment intent. The intent SHALL be committed before the external call, and the result SHALL be recorded in a separate transaction, with a recovery reconciler. No external call SHALL be made from inside the `withTx` transaction that records its result.
- IF an external call succeeds and the recording transaction then rolls back, the process dies or the response is lost THEN THE SYSTEM SHALL resolve the operation only through status lookup on persisted protocol identifiers. It SHALL never issue a second external authorize, settle or capture for the same invocation.
- WHEN identifiers are specified THE SYSTEM SHALL keep separate, domain-bound values:
  - the internal invocation id and `mctl-pay/v1` operation key;
  - the protocol payment identifier (x402 `payment-identifier` id, MPP challenge `id`);
  - the payer-signed nonce or commitment (EIP-3009 `nonce`, auth-capture `signatureNonce`/`salt`/`saltNonce`/`paymentInfoHash`);
  - the binding tuple (chain, asset, payee, amount, expiry, quote digest, args digest).

  The server SHALL never derive or dictate a payer-signed nonce for a generic client.
- IF a presented proof's binding tuple differs from the persisted intent (other payer, network, asset, payee, amount, quote, args or rail) THEN THE SYSTEM SHALL reject it without an external call. The test plan SHALL contain a negative case for each of these.
- WHILE an escrowed or deadline-bound payment is reserved, dispatched or `outcome_unknown` THE SYSTEM SHALL check a deadline invariant at reserve, capture and reconcile. The invariant covers the capture deadline, clock skew, finality, pause margin and the remaining ledger deadlines. IF the invariant cannot be met THEN THE SYSTEM SHALL refuse the reserve, void before capture, or move the row to manual reconciliation, and SHALL never count a reclaimable hold as captured.
- WHILE `Money` accepts only ISO 4217 codes (`currencyExponents` in `internal/commerce/types.go`) THE SYSTEM SHALL record settlement asset (CAIP-2 network + CAIP-19 asset + atomic amount string) separately from accounting `Money`. No conversion SHALL be applied without a separately designed FX layer.
- WHEN the ADR is written THE SYSTEM SHALL mark it `proposed`. It SHALL state the proposed merchant outcome and the proposed buyer outcome, each with the measurable conditions under which it falls back to `KEEP_SIMULATED` or `DEFER`. It SHALL map to exactly one original-issue token. It SHALL explain why the proposal beats each rejected alternative. It SHALL be written only after the classification fixtures (task 2) and the evidence inventory (task 1) are complete.
- WHEN the merchant experiment is described THE SYSTEM SHALL bound it to MCP Check (#616/PR #617), offline fixtures first. It SHALL use separate owner gates for testnet (G1), merchant registration (G2) and production (G3). It SHALL make no purchases or live financial calls, and SHALL not promise exactly-once across external systems.
- WHEN MCP wire formats are compared THE SYSTEM SHALL distinguish:
  - SEP-2007 `-32402` + `params.payment`, a draft whose PR was closed without merging;
  - x402 MCP transport `isError` + `_meta["x402/payment"]`;
  - MPP MCP transport `-32042` + `_meta["org.paymentauth/credential"]`.

  It SHALL expose none of them on a public production endpoint in this revision.
- WHEN streaming or long-running calls are assessed THE SYSTEM SHALL reject them for the first proof, with the reason recorded.
- WHERE a rail-independent receipt/reconciliation envelope is recommended THE SYSTEM SHALL document it only. It SHALL not change `Receipt` in `internal/commerce/receipt.go` or any MCP tool.
- WHEN the revision is delivered THE SYSTEM SHALL include a finding-to-change table for P1-PAY-01..P2-PAY-05, citing the source lines each change rests on.

## Out of scope

- Any live, testnet or mainnet transfer, purchase, wallet, private key, facilitator account, Stripe or Hedera account, merchant registration or KYC.
- Any production code change in `internal/commerce` (only a new `_test.go` file and docs are added), any migration, route, MCP tool or Helm change.
- Changing `checkAdapter`, `requiredFeatures`, `FundsMode*` semantics or ADR 020 (amendments are named as future scope only).
- Changes to PR #617 or closing #616; changes to #346 scope.
- Approving the existing DevLoop, editing `.status.yaml`, restarting the completed Temporal execution, or running the implementer before a new independent review and an owner digest-bound approval.
- FX, tax/VAT, payouts, revenue share, marketplace, a new commerce epic, or invoking third-party purchase tools.

## Open questions

- mctl-api's deployed commerce configuration (for example `COMMERCE_ACCEPT_DISABLED`, whether a non-simulated adapter could be configured) could not be observed. `mctl_get_service_config admins/mctl-api` answered "service not found", and no mctl-api values file exists under the gitops `services/` checkout. This is recorded as a gap, not as absence.
- No official public spec or repository named "Hedera Agent Accounts" or "Hedera Payments MCP" was found. Hedera is assessed through the pinned x402 `exact` Hedera scheme and the MPP Hedera charge/session methods, plus `hashgraph/hedera-agent-kit-js` as SDK context. Delegated-spend claims remain unverified.
- The official SEP tracker stage ("proposal", according to the issue) was not re-fetched. PR #2007 is closed and unmerged (2026-06-24), and its text says `Status: Draft`. Whether a successor SEP exists is unknown.
- It is unknown whether any hosted facilitator advertises x402 `auth-capture` for `eip155:84532` in `/supported`. This is condition C2 of the proposed merchant outcome.
- It is an owner decision whether ADR 020 will later admit asset-denominated terms or an FX layer. Until then every on-chain rail stays blocked for the ledger.
