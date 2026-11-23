# Tasks: issue-549-evaluate-agent-payment-rail-interoperabi

Scope: docs plus one test-only file. No purchases, transfers (testnet
included), wallets, keys, merchant registration, account linking, production
changes, routes, MCP tools or migrations. Gates G1 (testnet), G2 (merchant
registration) and G3 (production) each need separate owner approval and are
not part of these tasks.

- [ ] 1. Write `docs/payment-rail-interop-sources.md`: the pinned source matrix S1-S8 from design.md (repo, path, commit SHA or access date, which claim each supports, and a `vendor-self-report` flag for S6/S7 and for third-party issue comments). Also the evidence inventory table (#173, #546, #547/PR #550, #548/PR #557, #569/#570, #614, mctl-agents#619/PR #624, #620/PR #634, #631, #616, PR #617 `e3bf0293`, .github#346) with an evidence class per row. — DoD: every material protocol claim in tasks 2-3 resolves to a row here. No row says `external-testnet-settlement` or `production-available` without a link to that evidence.
- [ ] 2. (depends on 1) Write `docs/payment-rail-interop.md`, starting with a no-funds header, with these sections:
  - the contract under test (quoting `PaymentAuthorizer`, `requiredFeatures`, `checkAdapter` including the simulated-mode requirement, and the phase machine);
  - the adapter classification table;
  - the per-rail dimensions: binding, custody, replay/concurrency, lost response, the deadline rule `captureDeadline >= reserve + 24h15m + margin`, currency/asset blocker, fees with labelled assumptions A1/A2, MCP error shapes for SEP-2007 `-32402`, x402 `isError`+`_meta` and MPP `-32042`, the streaming/long-running rejection, generic versus binding-aware client, eligibility/KYC;
  - the host/client matrix with `not observed` cells;
  - merchant versus buyer recommendations;
  - the envelope (docs only);
  - the synthetic composed scenario;
  - the P1/P2/P3 risks.

  — DoD: the record compares all four rails against the same contract, and each cell is `N/E/U/?` with a source id.
- [ ] 3. (depends on 2) Write `docs/adr/0002-payment-rail-interop.md`, following the format of `docs/adr/0001-queue-execution-request-while-active.md`. It records:
  - refresh outcome `EXTEND_X402_PILOT` and original token `DEFER_EXTERNAL_PAYMENT`, with the explicit mapping between them;
  - why each beats every rejected alternative (`KEEP_SIMULATED`, `EVALUATE_MPP`, `ACCOUNT_FUNDED_FIRST`, `DEFER`; `ADOPT_X402`, `ADOPT_MPP`, `ADOPT_ACCOUNT_FUNDED`, `ADOPT_HEDERA`, `MULTI_RAIL_FOUNDATION`);
  - re-entry criteria R1-R5, with x402 `auth-capture` `escrow` on Base Sepolia as the leading candidate;
  - gates G0-G3.

  — DoD: exactly one outcome per vocabulary, and no statement that live proof occurred.
- [ ] 4. (depends on 2) Add `internal/commerce/rail_classification_test.go` (package `commerce`, no database). It holds a table of `AdapterInfo` fixtures, one per rail shape in the classification, with `FundsModes` and `Features` exactly as classified, and asserts `checkAdapter`:
  - x402 `exact`, x402 auth-capture `authorization` flow, MPP `charge` and x402 `exact` on Hedera are refused (missing `void`);
  - x402 auth-capture `escrow` is accepted only when `simulated` is also listed, and refused otherwise;
  - the entitlement shape is not modelled as an adapter.

  — DoD: `go test -p 1 ./internal/commerce -run TestRailClassification` passes without `TEST_DATABASE_URL`. `go vet` and `golangci-lint` are clean. No non-test file changes.
- [ ] 5. (depends on 2, 3) Write the bounded G0 backlog section in `docs/payment-rail-interop.md` for the follow-up MCP Check merchant experiment (offline only, separate issue and PR, not implemented here). It covers:
  - the x402 auth-capture `escrow` fixture path in `experiments/x402-mcp-check`;
  - mapping its authorize/capture/void/escrow-status onto the `PaymentAuthorizer` semantics;
  - quote binding of payee, amount, asset, network, payer, `quote_digest`/action digest and expiry;
  - `payment-identifier` = `invocation_id`;
  - the required negative tests (identity unresolved, wrong tenant/scope, revoked approval, wrong payee, changed quote, expired quote, unusable or mismatched receipt, failed execution then void, retry after a lost authorize or capture response, replay of a consumed authorization, concurrent reserve on one invocation, `captureDeadline` too short);
  - an explicit "no exactly-once across external systems" statement;
  - use of the existing commerce ledger and correlation ids instead of a second store.

  — DoD: every item names its file or test, and its gate is G0.
- [ ] 6. (depends on 1-5) Independent review: a reviewer other than the author checks each pinned claim against its SHA and confirms that no doc authorizes spend. — DoD: review comment recorded on the PR. Proposal stays `proposed` until a human approves.

## Tests

- [ ] T1. `TestRailClassification`: each rail fixture's `checkAdapter` result matches the classification table in `docs/payment-rail-interop.md`, including `ErrAdapterIneligible` for the missing-`void` shapes.
- [ ] T2. `TestRailClassificationRequiresSimulatedMode`: an auth-capture fixture with only `live` in `FundsModes` is refused, which pins the current simulated-mode rule.
- [ ] T3. The existing `budget_test.go` adapter tests (`UseAuthorizer` with `fakeAdapter`, `SimulatedAuthorizer`) and `digest_test.go` golden vectors still pass unchanged.
- [ ] T4. `go test -p 1 ./...` and the `server_test.go` MCP tool count are unchanged.
- [ ] T5. Docs check (manual, in review): every `N`/`E` cell cites a source id from `docs/payment-rail-interop-sources.md`. No public endpoint, `Receipt` field or MCP tool response gains SEP-2007, x402 or MPP fields.

## Rollback

Revert the single PR, which deletes the three docs and
`internal/commerce/rail_classification_test.go`. No data, schema,
configuration or runtime behaviour depends on them, so a revert needs no
migration or redeploy coordination.
