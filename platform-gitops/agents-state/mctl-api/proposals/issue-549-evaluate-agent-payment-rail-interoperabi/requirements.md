# Payment rail interoperability decision, refreshed 2026-11-22 (x402, MPP, account-funded, Hedera, MCP Payments / SEP-2007)

## Context

Issue mctlhq/mctl-api#549 (roadmap item `payment-interop`, optional child of
the completed Agent Commerce epic mctlhq/.github#173) asks for an
evidence-driven choice of the first external payment rail shape that can plug
into the existing commerce core in `internal/commerce` without creating a
second authorization path. The MCTL invariant stays: `has funds` AND
`authorized` AND `within policy` AND `within budget` AND `approved when
required` -> execute. Payment proof never grants capability authority. The
2026-11-22 owner refresh adds MCP Payments (SEP-2007) as a fourth research
pillar. It also asks for a merchant/buyer split, a client/host matrix, an
inventory of the evidence gathered so far, a single isolated merchant
experiment (offline first), a synthetic composed scenario, and an ADR with an
outcome from `KEEP_SIMULATED | EXTEND_X402_PILOT | EVALUATE_MPP |
ACCOUNT_FUNDED_FIRST | DEFER`.

The 2026-10-25 proposal is stale in three material ways. (1) x402 now
publishes an `auth-capture` scheme with authorize/capture/void/refund/reclaim
(x402-foundation/x402 `e35bf884`, SDK "auth capture sdk v1.1" `28376d64`,
2026-10-06). The earlier finding "x402 cannot void" therefore holds for
`exact` only. (2) SEP-2007's PR #2007 was closed as dormant and unmerged on
2026-06-24. The SEP file at its head still reads `Status: Draft`, which
contradicts the issue's "stage proposal". (3) The three MCP payment wire
formats are mutually incompatible. This revision delivers documentation, an
ADR and test-only classification checks. It changes no runtime behaviour.

## User stories

- AS the platform owner I WANT one evidence-backed recommendation with pinned sources SO THAT I can decide the next payment step without re-reading every vendor page.
- AS a commerce-core maintainer I WANT every rail classified against the existing `PaymentAuthorizer` contract (`Authorize`, `Capture`, `Void`, `Status`, `requiredFeatures`) SO THAT no adapter fakes an operation the rail cannot do.
- AS a security reviewer I WANT custody, replay, ambiguity and reconciliation analysed per rail SO THAT no rail introduces MCTL key custody or duplicate economic charges.
- AS the owner of MCP Check (#616/#617) I WANT a bounded offline-fixture backlog for the merchant experiment SO THAT the pilot can advance without live funds or a second ledger.
- AS a buyer-side integrator I WANT a host/client compatibility matrix with explicit "not observed" cells SO THAT catalog support is never mistaken for native host payment support.

## Acceptance criteria (EARS)

- WHEN the decision record is written THE SYSTEM SHALL compare x402 (`exact` and `auth-capture`), MPP (`charge`, `session`, Stripe `charge`), account-funded entitlements and Hedera (Agent Accounts, Payments MCP, Network MCP, x402 `exact` on Hedera, MPP `hedera` methods) against the same contract: `PaymentAuthorizer`, `requiredFeatures`, the phase machine and the receipt in `internal/commerce`.
- WHEN a protocol claim is material to the decision THE SYSTEM SHALL cite a pinned source (commit SHA, draft revision, or vendor URL with access date) and label vendor pages and third-party comments as vendor self-report.
- WHEN a rail is classified THE SYSTEM SHALL mark each of `authorize`, `capture`, `void`, `status_lookup`, `partial_capture`, `refund` and `async_settlement` as `native`, `emulated-with-evidence` or `unsupported`, and SHALL state whether the rail could pass `checkAdapter` as written.
- WHEN the classification is encoded THE SYSTEM SHALL include test-only `AdapterInfo` fixtures in `internal/commerce` that assert the result of `checkAdapter` per rail, without changing `requiredFeatures`, `checkAdapter`, `SimulatedAuthorizer` or the live-funds refusal.
- WHEN evidence is inventoried THE SYSTEM SHALL classify each of #173, #546, #547, #548, #614, mctl-agents#619/#620/#631, #616/PR #617 and .github#346 as `simulated-proof`, `offline-tests`, `external-testnet-settlement`, `production-available`, `open` or `unknown`, with commit or PR references.
- WHILE no separate owner approval exists THE SYSTEM SHALL NOT perform or plan inside this scope any purchase, testnet or mainnet transfer, wallet or private-key creation, merchant registration, account linking or production configuration change.
- WHILE any rail is described THE SYSTEM SHALL keep accounting currency (ISO 4217 `Money`) separate from the settlement asset (CAIP-2 network plus asset id plus atomic amount), and SHALL NOT introduce implicit EUR/USD/USDC/HBAR conversion.
- IF a rail's lost-response or settlement ambiguity cannot be resolved by a status or reconciliation lookup keyed by the existing `mctl-pay/v1:<invocation_id>:<operation>` key THEN THE SYSTEM SHALL classify that rail as unable to avoid duplicate economic charge under retry.
- IF a rail requires MCTL to hold a payer signing key THEN THE SYSTEM SHALL reject that rail shape for buyer-side use.
- WHEN streaming or long-running calls are evaluated THE SYSTEM SHALL explicitly reject them for the first proof, with the reason tied to `dispatch_deadline` (60 s), `reconciliation_deadline` (24 h) and the rail's capture or settlement deadlines.
- WHEN the ADR is written THE SYSTEM SHALL record exactly one refresh outcome (`EXTEND_X402_PILOT`) and exactly one original-issue token (`DEFER_EXTERNAL_PAYMENT`). It SHALL explain why each beats every rejected alternative and SHALL make separate merchant-side and buyer-side recommendations.
- WHEN deferral is recorded THE SYSTEM SHALL define measurable re-entry criteria, name the leading retest candidate (x402 `auth-capture` with `escrow` flow on Base Sepolia), and define separate owner gates for testnet, merchant registration and production.
- WHEN the merchant experiment backlog is drafted THE SYSTEM SHALL scope it to offline fixtures on MCP Check. It SHALL include negative tests for identity, scope, revocation, wrong payee, changed quote, unusable receipt, failed execution, retry, replay and concurrent reserve, and SHALL NOT promise exactly-once behaviour across external systems.
- WHEN the composed reference scenario is described THE SYSTEM SHALL mark it synthetic, and SHALL show that event delivery and payment receipt are never authorization inputs.
- WHERE a rail-independent receipt envelope is recommended THE SYSTEM SHALL document it only. It SHALL NOT add fields to the public `Receipt` or to the MCP tool responses in this revision.

## Out of scope

- Mainnet or production funds, and any testnet transfer (separate explicit approval needed).
- MCTL custody of wallet private keys; stored card data; stored-value or top-up products.
- Provider marketplace, merchant onboarding or KYC, payouts or revenue share, a tax/VAT/FX engine.
- Changing canonical identity, authorization, policy, approval or budget semantics, `requiredFeatures` or `checkAdapter`.
- Any new route, MCP tool, migration, env var or persisted envelope type.
- Merging or closing #616/PR #617; changing #346 scope (ChatGPT Wallet checkout spike).
- Invoking third-party purchase endpoints named in issue comments (for example Screwtape).
- A new commerce epic.

## Open questions

- Is `auth-capture` (EVM) offered by the hosted facilitator `https://x402.org/facilitator` on Base Sepolia? Only spec, SDK and e2e/example code (`examples/go/facilitator/auth-capture`) were observed, not a hosted `/supported` answer. A live probe is a network call against an external service and was not made.
- SEP-2007 status conflict: the issue cites the SEP tracker as `proposal`; PR #2007 is closed as dormant (2026-06-24) and its text says `Status: Draft`. A 2026-11-20 comment proposes reviving it as an experimental extension. Treated here as "not adopted, wire format unstable".
- Hedera Agent Accounts / Payments MCP availability is known only from secondary press (limited partner testnet Q4 2026, public testnet Q1 2027, Payments MCP "coming soon"). No pinned developer specification was found.
- The deployed mctl-api commerce configuration (`COMMERCE_DB_URL`, `COMMERCE_ACCEPT_DISABLED`, dispatch key) could not be observed (see design.md "Deployed state checked"). Production availability of paid capabilities is therefore recorded as `unknown`, apart from the fact that #631 (shared tenants) is open.
- Native payment support in ChatGPT, Claude, Antigravity and Grok hosts was not observed for any of the three MCP wire formats. The matrix records `not observed`, not `unsupported`.
- Whether the owner wants the refresh outcome and the original token in one ADR, or the original token retired. This proposal records both, mapped explicitly.
