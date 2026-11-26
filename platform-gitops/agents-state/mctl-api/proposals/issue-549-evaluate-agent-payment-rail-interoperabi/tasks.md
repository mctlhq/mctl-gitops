# Tasks: issue-549-evaluate-agent-payment-rail-interoperabi

Revision 3 boundary:

- Change only documentation and test-only fixtures.
- No real funds, credentials, wallets, purchases, live or testnet calls,
  merchant registration or production change.
- Do not touch PR #617, #616 or #346.
- Do not approve the DevLoop or edit `.status.yaml`.

- [ ] 1. Evidence inventory and source matrix: write `docs/payment-rail-interop-sources.md` with S1-S13 and the evidence inventory table from design.md "Current state", re-verified at write time. Re-run `gh pr view 617`, the issue states, and the x402/mpp-specs HEAD SHAs. Any changed pin is updated, and its effect on the decision is noted. — DoD:
  - Every material claim in design sections 2-9 has a pinned row.
  - Vendor and third-party rows are labelled self-report.
  - Each item is classified as simulated credit proof, offline test, external testnet settlement or production availability.
  - The deployed-state gap (mctl-api config not observable) is recorded.
- [ ] 2. Negative classification fixtures and crash-gap characterization (depends on 1): add `internal/commerce/rail_classification_test.go` (package `commerce`, test-only), reusing `fakeAdapter`, `newTestStore`, `setBudget`, `publish`, `acceptOne` from the existing tests. — DoD:
  - T1-T3 pass with `go test -p 1 ./internal/commerce/...`.
  - `go vet` and `golangci-lint` are clean.
  - No non-test file changes.
- [ ] 3. Decision report (depends on 1, 2): write `docs/payment-rail-interop.md` with the design sections 1-12. — DoD:
  - It contains: the finding->change table; the classification table with `checkAdapter` result and `eligible_for_mctl` matching T1 exactly; the identifier-domain table; the section 3 design; the deadline invariant and asset boundary; the merchant/buyer sections; the host matrix; the envelope; the synthetic scenario; P1/P2/P3 risks; and the future test plan N/F/D/A below.
  - It states that no exactly-once guarantee across external systems is promised.
- [ ] 4. Proposed ADR (depends on 3): write `docs/adr/0002-payment-rail-interop.md` with `Status: proposed`. — DoD:
  - It states the proposed merchant outcome (`EXTEND_X402_PILOT`, offline only), evaluated against conditions C1-C3 using the actual results of tasks 1-2. If a condition fails, the ADR records the fallback (`KEEP_SIMULATED` or `DEFER`) instead.
  - It states the proposed buyer outcome `KEEP_SIMULATED` and the proposed original token `DEFER_EXTERNAL_PAYMENT`, with leading candidate and re-entry criteria R1-R5.
  - It records owner gates G0-G3.
  - It contains the line "Owner decision: not issued". There is no auto-adopt and no pilot approval.
- [ ] 5. Handoff (depends on 4): post a summary comment on mctlhq/mctl-api#549 linking the docs. It requests a new independent review. It does not approve the DevLoop or change status. — DoD: the comment exists and contains no credentials and no purchase instructions.

## Tests

Implemented in task 2 (offline, test-only):

- [ ] T1. `TestRailClassificationFixtures`: a table of `AdapterInfo` fixtures, one per design section 2 row, using an **honest** declaration. Each row holds `wantCheckAdapter` and `eligibleForMCTL`.
  - x402 exact EVM (no void, live only) -> `ErrAdapterIneligible`.
  - x402 exact Hedera -> refused.
  - MPP charge -> refused (no void).
  - auth-capture with honest `FundsModes: [live]` -> refused.
  - auth-capture collect-only (no capture/void relayed) -> refused.
  - Every row asserts `eligibleForMCTL == false`.
- [ ] T2. `TestSimulatedDeclarationIsContractShapeOnly`: an auth-capture fixture that falsely declares `FundsModeSimulated` plus all required features.
  - Asserts `UseAuthorizer` **accepts** it, which documents the false positive.
  - Asserts the fixture table labels it `contract-shape only` with `eligibleForMCTL == false`.
  - A second fixture (Postgres; skips without `TEST_DATABASE_URL`) declares `status_lookup` but has no status path. `Authorize` returns `unknown`, so no authorization id is recorded, and `Status` always returns `not_found`. The test asserts:
    - a retry `Reserve` (through `resolveUnknownHold` -> `resolveAuthorization`) returns `ErrPaymentUnknown` and rolls back, leaving the hold `reserved` with `payment_status: unknown`;
    - the unknown is never denied or released;
    - balance `ReservedMinor` still counts the hold.

    This shows a declared-but-unimplemented status path leaves a hold that can never resolve, so the declaration alone is not eligibility. (When `AuthorizationID` is recorded, `resolveAuthorization` at `budget.go:1124` skips `Status`, so this negative must use the unknown path.)
- [ ] T3. `TestCharacterizeExternalSuccessBeforeCommitGap` (Postgres; skips when `TEST_DATABASE_URL` is unset). The fake adapter records each `Authorize` call in memory (simulating an external side effect outside `tx`), returns `authorized`, and cancels the request context, so the following reservation INSERT fails and `withTx` rolls back.
  - The first `Reserve` returns an error. The invocation stays `accepted`, and `GetReservation` finds no reservation.
  - The fake recorded exactly one external authorization: the gap is real.
  - A retry `Reserve` with a fresh context calls `Authorize` a second time with the **same** `mctl-pay/v1:<inv>:authorize` key. Only a key-idempotent rail would dedupe it.
  - The test comment says it must be inverted (no second external call, recovery via persisted intent) when the design section 3 lands.

Specified only (future follow-up scope, gated, not implemented in this revision):

- [ ] N1-N8. Identifier and binding negatives. Each is rejected before any external call:
  - N1 wrong payer;
  - N2 wrong network/chain id;
  - N3 wrong asset;
  - N4 wrong payee;
  - N5 changed amount or quote digest;
  - N6 changed `args_digest`;
  - N7 a second, different proof for the same invocation;
  - N8 cross-rail replay (an x402 proof presented on an MPP challenge, and the reverse).

  Plus: a revoked delegation or identity at the time of reserve; a wrong tenant scope; an unusable or malformed receipt.
- [ ] F1-F6. Fault injection on the durable intent, all with fake facilitator/chain:
  - F1 crash between external success and Tx B;
  - F2 Tx B commit failure;
  - F3 lost response;
  - F4 concurrent retry of the same invocation (one in-flight attempt only);
  - F5 dead owner, fenced takeover;
  - F6 recovery via `Status` on persisted identifiers with no second charge.
- [ ] D1-D5. Deadline invariant with a fake clock:
  - D1 reserve refused when it cannot be met;
  - D2 capture converted to void near the deadline;
  - D3 `outcome_unknown` past the deadline goes to `unresolved`, not captured;
  - D4 clock skew at the `MaxClockSkew` edge;
  - D5 long-running execution exceeding the deadline is rejected.
- [ ] A1-A3. Asset boundary:
  - A1 USDC as `Money.Currency` refused;
  - A2 undeclared accounting/settlement pair refused;
  - A3 settlement amount different from the quoted atomic amount refused.
- [ ] Failed execution with a settled payment: content withheld per S1, and ledger plus envelope consistent.

## Rollback

Revert the single docs/test commit: `git revert <sha>`, then reopen the
proposal for revision. Nothing runtime, schema, route, tool or deployment
changes, so no data or service rollback exists. If T3 is flaky in CI, delete
only `rail_classification_test.go`'s T3 case and keep the docs; the gap stays
documented in `docs/payment-rail-interop.md`.
