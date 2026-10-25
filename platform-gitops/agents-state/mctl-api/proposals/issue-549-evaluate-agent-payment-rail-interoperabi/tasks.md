# Tasks: issue-549-evaluate-agent-payment-rail-interoperabi

- [ ] 1. Gather and pin evidence — read the current state of mctl-api#616 and PR #617 (merged or not, what testnet run if any was observed), and the published specs of x402, MPP, Hedera Agent Kit / Payments MCP / Network MCP and HIP-336 allowances. Record exact versions and the date read; anything not verifiable is written "not pinned". — DoD: an evidence list with URLs, versions and "evaluated as of" date, ready to paste into the record; no claim of live proof that was not observed.
- [ ] 2. Write `docs/payment-rail-evaluation.md` (depends on 1) — sections per design.md: contract under test (citing `PaymentAuthorizer`, `requiredFeatures`, `checkAdapter`, `Store.Reserve`, `resolveAuthorization`, `settlePayment`, `checkFundsMode`, `receipt.go`), comparison matrix with every dimension the issue lists, capability classification table, non-custodial verdict per rail, ambiguity/no-double-charge analysis, streaming/long-running rejection, eligibility/secrets/fee constraints, external receipt envelope (accounting money and settlement money as separate fields, no FX field), recommendation `DEFER_EXTERNAL_PAYMENT`, re-entry criteria 1-4. — DoD: file exists, English, no emoji, every matrix cell filled or "not pinned"/"unverified", exactly one recommendation token present.
- [ ] 3. Link the record from `docs/commerce-ledger.md` (depends on 2) — one sentence at the end of "### Adapter contract": external rails were evaluated in `payment-rail-evaluation.md` and deferred; `SimulatedAuthorizer` remains the only adapter. — DoD: link resolves; no other text in the ledger doc changes.
- [ ] 4. Add `internal/commerce/rail_profiles_test.go` (independent of 2) — table-driven `TestRailProfilesAgainstAdapterContract` with `AdapterInfo` profiles `x402-exact`, `mpp`, `hedera-allowance`, `account-funded` built only from existing `Feature*` and `FundsMode*` constants; comment points to `docs/payment-rail-evaluation.md`. — DoD: `go test ./internal/commerce -run TestRailProfiles` passes without `TEST_DATABASE_URL`; no production file changed.
- [ ] 5. Lint and verify (depends on 2, 3, 4) — `go fmt ./...`, `go vet ./...`, `golangci-lint run`, `go test ./...`. — DoD: all clean; `git diff --stat` shows only the two docs files and the one test file.
- [ ] 6. Post the decision on mctl-api#549 (depends on 5) — PR description states `DEFER_EXTERNAL_PAYMENT`, the re-entry criteria, and that #616 stays open pending its own acceptance. — DoD: PR opened referencing #549 and mctlhq/.github#173; #616 not closed.

## Tests

- [ ] T1. `x402-exact` profile (`Features: [status_lookup]`, `FundsModes: [live]`) is refused by `checkAdapter` with `errors.Is(err, ErrAdapterIneligible)` and the message names `auth_capture`.
- [ ] T2. `mpp` profile (`[status_lookup]`) is refused, naming `auth_capture`.
- [ ] T3. `hedera-allowance` profile (`[status_lookup, async_settlement]`) is refused, naming `auth_capture`.
- [ ] T4. A hypothetical external profile declaring all three required features but only `FundsModes: [live]` is refused for lacking simulated funds (pins that live-only rails cannot install today).
- [ ] T5. `account-funded` profile (`[auth_capture, void, status_lookup, refund, simulation]`, `FundsModes: [simulated]`) is accepted (`err == nil`).
- [ ] T6. Existing suites unchanged: `go test ./internal/commerce/... ./internal/api/... ./internal/mcp/...` pass, MCP tool count in `internal/mcp/server_test.go` unchanged.
- [ ] T7. Doc check: `grep -c` for each of `ADOPT_X402|ADOPT_MPP|ADOPT_ACCOUNT_FUNDED|ADOPT_HEDERA|MULTI_RAIL_FOUNDATION` appears only in the alternatives section; `DEFER_EXTERNAL_PAYMENT` is the stated recommendation.

## Rollback

Docs and a test file only; no runtime, schema or configuration change.
Revert the PR (`git revert <merge-sha>`). Nothing to drain, migrate or
redeploy, and commerce behaviour (`funds_mode: live` refused,
`SimulatedAuthorizer` only) is identical before and after.
