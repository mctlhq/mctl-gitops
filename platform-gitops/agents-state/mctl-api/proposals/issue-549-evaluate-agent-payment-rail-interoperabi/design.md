# Design: issue-549-evaluate-agent-payment-rail-interoperabi

Revision 2 (2026-11-22). Supersedes the proposed revision of 2026-10-25,
which nobody approved. This revision authorizes no funds, wallets, purchases,
testnet transfers, merchant registration, account linking, production
changes or implementer run.

## Current state

### Commerce core in this clone (HEAD `5062295`, 2026-11-22)

- **Adapter contract.** `internal/commerce/budget.go`: `PaymentAuthorizer` is
  `Adapter() AdapterInfo`, `Authorize(ctx, q, PaymentRequest)`,
  `Capture(ctx, q, key, authorizationID, Money)`, `Void(ctx, q, key,
  authorizationID)` and `Status(ctx, q, key)`. Keys are
  `mctl-pay/v1:<invocation_id>:<operation>`; the same key with different
  parameters is `ErrPaymentConflict`. `PaymentRequest` is the only place a
  payment proof may enter. The interface comment already anticipates an
  external rail whose answer "the core treats as unknown until status
  confirms it".
- **Feature negotiation.** `requiredFeatures = {auth_capture, void,
  status_lookup}`. The optional features are `partial_capture`, `refund`,
  `async_settlement` and `simulation`. `checkAdapter` refuses an adapter that
  lacks a required feature **or does not list `FundsModeSimulated`**.
  `Store.UseAuthorizer` runs it at install. The only adapter is
  `SimulatedAuthorizer` (`adapter_id: simulated`), which writes
  `commerce_payment_operations` inside the ledger transaction and refuses
  `funds_mode: live`.
- **Money edges.** `Store.Reserve` (budget.go:784) reserves under an advisory
  budget lock and calls `Authorize`. `Store.Finalize` (:1007) captures or
  voids exactly once from `dispatched`/`outcome_unknown`. `Store.Release`
  (:1205) voids from `reserved`/`dispatching`. "Unknown is never denied": an
  unclassifiable adapter answer leaves `payment_status: unknown` (409
  `payment-unknown`) and is resolved only through `Status` on the same key.
  The ledger never issues a fresh authorization.
- **Dispatch fence.** `internal/commerce/dispatch.go` `Store.Dispatch` (:211)
  writes `dispatch_deadline` (now + 60 s) and returns an Ed25519
  `mctl-commerce-dispatch/v1` authorization over the invocation,
  `provider_operation_key`, capability, input schema hash, `args_digest`,
  tenant and deadline. Providers dedupe on `provider_operation_key`.
- **Currency.** `internal/commerce/types.go` `Money{Currency, AmountMinor}`.
  `currencyExponents` holds ISO 4217 codes only (EUR, USD, GBP, ... KWD).
  There is no USDC or HBAR, and a budget's currency is fixed once used.
- **Account-funded today.** `commerce_entitlements` (#614, merge
  `87256896`) holds finite units granted by an admin against `invoice_ref`.
  Units are held on reserve and captured or released on finalize. Budgets are
  limits, never balances (`docs/commerce-ledger.md`).
- **Receipt.** `internal/commerce/receipt.go` `Receipt` is an allowlist (ids,
  quote digest, terms, tenant, payer account, principals, price, five facts,
  phase, policy decision). It has no rail, network, asset, settlement amount
  or external reference fields, and it never carries proofs.
- **Routes and MCP.** `internal/api/router.go` mounts `/commerce` under
  `Commerce *commerce.Store`. `internal/mcp/commerce.go` exposes the read
  tools `mctl_get_commerce_budget`, `mctl_list_commerce_invocations` and
  `mctl_get_commerce_receipt`. ADRs in this repo live in `docs/adr/`
  (`0001-queue-execution-request-while-active.md`). The commerce contract
  itself is ADR 020 in mctl-agents.

### Evidence inventory (gh, 2026-11-22)

| Item | State | Evidence class |
|---|---|---|
| .github#173 Agent Commerce | CLOSED 2026-10-12; roadmap lifecycle `completed` (manifest sha256 `c284c95f…`) | simulated-proof |
| mctl-api#546 contract | CLOSED; ADR 020 lives in mctl-agents | design |
| mctl-api#547 ledger | PR #550 merge `362df561` | offline-tests (Postgres) |
| mctl-api#548 budgets/simulated authorizer | PR #557 merge `d8158679` | simulated-proof |
| mctl-api#569/#570 receipts, accept kill switch | PR #573 `757797ab`, PR #580 `fefeef11` | offline-tests |
| mctl-api#614 entitlements | merged `87256896` | offline-tests |
| mctl-agents#619 governed paid invocation | PR #624 `472f1ca3` | simulated-proof |
| mctl-agents#620 paid capabilities proof | PR #634 `1904c810` | simulated-proof |
| mctl-agents#631 shared tenants | OPEN, roadmap `ready` | not production-available on shared tenants |
| mctl-api#616 x402 MCP Check | OPEN | open |
| mctl-api PR #617 | OPEN draft, single commit `e3bf0293` (2026-10-13); x402 v2 `exact`/EIP-3009, Base Sepolia, 0.01 test USDC, 42 offline tests. Body: "No live testnet transfer, external wallet signature, hosted-facilitator conformance proof or real public target proof has been performed." Own SQLite store; binding-aware buyer only | offline-tests |
| .github#346 ChatGPT Wallet spike | OPEN, P2 discovery. Explicitly must not decide #549's rail comparison | open |
| roadmap `governed-external-payment-proof` | `unbound`, depends on `payment-interop` | unknown |

No item has `external-testnet-settlement` evidence. Nothing external is
`production-available`.

### Pinned external sources (read 2026-11-22)

| Id | Source | Pin |
|---|---|---|
| S1 | SEP-2007 text `seps/2007-payment-support-for-mcp-servers.md` | PR #2007 head `09b9d1d8`; PR CLOSED unmerged 2026-06-24 ("dormant", no sponsor); file says `Status: Draft`; revival comment 2026-11-20 |
| S2 | x402 MCP transport `specs/transports-v2/mcp.md` | x402-foundation/x402 `e35bf884` (file last changed `b74dd052`, 2026-02-03) |
| S3 | x402 `auth-capture` scheme and EVM binding | `e35bf884`; SDK "auth capture sdk v1.1" `28376d64` (2026-10-06); last spec change `a8bd9a38` (2026-10-27); builds on base/commerce-payments `AuthCaptureEscrow` |
| S4 | x402 `exact` EVM / Hedera, `upto`, `batch-settlement` (`cloudflare:402`), `payment-identifier`, `offer-and-receipt` | `e35bf884` |
| S5 | MPP core `draft-httpauth-payment-01`, MCP transport `draft-payment-transport-mcp-00`, `tempo-session-00`, `hedera-session-00`, `stripe-charge-00` | tempoxyz/mpp-specs `7bb99c85` (MCP transport last changed `2565c6f5`, 2026-04-16) |
| S6 | Cloudflare Agents payments page | developers.cloudflare.com/agents/tools/payments/, accessed 2026-11-22, vendor page, no versions |
| S7 | Hedera Agent Accounts / Payments MCP / Network MCP | secondary press and hedera.com/mcp-servers, accessed 2026-11-22, unpinned |
| S8 | #617 spec pins | x402-foundation/x402 `6c470a80` (older than S2/S3) |

Facts that matter for the decision:

- **Three incompatible MCP wire formats.**
  - SEP-2007 (S1): JSON-RPC error `-32402`, `params.payment.paymentInput`, `result.payment.paymentOutput`, optional `payment` capability.
  - x402 MCP (S2): tool result `isError: true` with `structuredContent` PaymentRequired, `_meta["x402/payment"]`, `_meta["x402/payment-response"]`.
  - MPP MCP (S5): JSON-RPC error `-32042` with `data.challenges`, `_meta["org.paymentauth/credential"]`, `_meta["org.paymentauth/receipt"]`.

  Cloudflare's statement that MPP is "backwards-compatible with x402" (S6) is vendor marketing. It is unverified at the MCP layer, where the codes and keys differ.
- **Ordering.** SEP-2007 and x402 `exact` run verify -> execute -> settle. If the server executes and settlement then fails, x402 returns the payment error and withholds the content (S2). x402 `auth-capture` `escrow` runs settle(authorize) -> resource -> settle(capture or void), with a `captureDeadline` and a payer-side `reclaim` once it passes (S3).
- **Idempotency.** x402 `payment-identifier` (S4) offers a client-chosen id of 16-128 characters for dedupe at the server and facilitator. MPP binds challenges statelessly with HMAC-SHA256 over `realm|method|intent|request|expires|digest|opaque` and recommends `Idempotency-Key` (S5).
- **Hedera.** x402 `exact_hedera` (`hedera:testnet`, facilitator as fee payer, client-signed `TransferTransaction`) and MPP `hedera-charge`/`hedera-session` drafts exist in the specs. Agent Accounts are limited-partner only; Payments MCP is "coming soon". Network MCP (testnet, wallet-approval gated) builds transactions and is not a payment rail (S7).

Deployed state checked:

- `mctl_get_service_config(team=admins, service=mctl-api)`: error "service not found: admins/mctl-api". mctl-api is not a catalogue service under that name, so its deployed config was not observed.
- `$MCTL_GITOPS_ROOT/services/` listing: tenants `admins, karabu, labs, namax66, redloop`, with no `mctl-api` directory. `grep -ri "COMMERCE_\|x402"` over `services/` and `tenants/` found nothing. This is a gap, not evidence that commerce is disabled.
- `mctl_get_commerce_budget(tenant=admins)`: 403 `agent_scope_denied` (outside investigate scope). Ledger liveness was not observed.
- `mctl_get_epic_status(mctlhq/.github#173)`: epic `completed`; `payment-interop`, `x402-mcp-check-pilot` and `paid-capabilities-shared-tenant` are `ready`; `governed-external-payment-proof` is `unbound`; drift diagnostics on #616 (missing parent/dependency link). Publication captured 2026-11-22T00:26:07Z, state revision `2e81263f`.
- `gh` reads of PR #617, issues #616, #346, #631 and the closing PRs above (see inventory).
- Previous proposal `agents-state/mctl-api/proposals/issue-549-…/` (status `proposed`, 2026-10-25) read for refresh. Its `.status.yaml` was not edited.

## Proposed solution

Deliver three docs artifacts and one test-only file. Nothing else changes.

1. `docs/payment-rail-interop.md`: decision record, matrix, envelope, scenario, backlog.
2. `docs/adr/0002-payment-rail-interop.md`: short ADR with the outcome.
3. `docs/payment-rail-interop-sources.md`: the source/pinned-code matrix above, extended with section-level anchors.
4. `internal/commerce/rail_classification_test.go`: `AdapterInfo` fixtures per rail shape, asserting `checkAdapter` outcomes.

### 1. Adapter capability classification (core of the record)

Legend: N native, E emulated-with-evidence, U unsupported, ? unknown or unpinned.

| Rail shape | authorize | capture | void | status | partial | refund | async | passes `checkAdapter`? |
|---|---|---|---|---|---|---|---|---|
| x402 `exact` (EVM/EIP-3009) | E (verify only, no hold) | N (settle) | U (signed auth settleable by any holder until `validBefore`; payer-side cancellation only) | E (facilitator settle replay + chain `AuthorizationUsed` by nonce, as #617 `reconcile.mjs`) | U | U | U | No: void |
| x402 `auth-capture` `escrow` (EVM) | N (escrow hold) | N (repeatable up to held) | N | E (escrow `paymentState` by `paymentInfoHash`; no facilitator status endpoint in S3) | N | N (until `refundDeadline`) | N (async finalize allowed) | Yes on paper; hosted-facilitator support ? |
| x402 `auth-capture` `authorization` flow | E | N (`charge`) | U | E | U | N | ? | No: void |
| x402 `upto` / `batch-settlement` | ? | ? | ? | ? | ? | ? | ? | Not assessed for first proof (metered/batched) |
| MPP `charge` (tempo/evm/usdc) | E | N | U | E (receipt + chain) | U | U in protocol | U | No: void |
| MPP `session` (tempo, hedera) | N (escrow deposit) | N (cumulative voucher close) | E (close at 0 returns deposit) | E | N | E (unused deposit) | N | Plausible; channel model does not map one-to-one to one invocation |
| MPP Stripe `charge` (SPT) | ? (PaymentIntent manual capture is Stripe-side, not in S5) | N | ? | ? | ? | outside MPP | ? | Unknown; requires a Stripe merchant account (KYC) |
| Account-funded entitlements (#614) | N (ledger hold) | N | N (release) | N (ledger-local) | U | U (no money moved) | N/A | Not an external rail; already in core |
| Hedera Agent Accounts / Payments MCP | ? | ? | ? | ? | ? | ? | ? | Unassessable: no public spec or testnet |
| x402 `exact` on Hedera | E | N | U | E (mirror node) | U | U | U | No: void |

`checkAdapter` also requires `FundsModeSimulated` in `FundsModes`. Any
external adapter must therefore keep a simulated mode, or ADR 020 must be
amended. This is recorded as a constraint and not changed here.

### 2. Per-rail dimensions (record subsections, one row each)

- **Binding.** The MCTL quote binds payer account, canonical principal, tenant, capability and expiry through `quote_digest` (`mctl-commerce-quote/v1`). The action binds through the dispatch `args_digest`. A rail challenge must carry `quote_digest` as its opaque or resource field. x402 `resource.url` and `extra`, MPP `opaque` and `digest`, and the auth-capture `salt`/`paymentInfo` can carry it. The rail never replaces the digest.
- **Custody.**
  - x402 and MPP: the payer wallet signs (EIP-3009/Permit2/EIP-712 vouchers), so MCTL as merchant stays non-custodial. As buyer, MCTL must use an external signer (wallet or delegated smart account) and never hold a raw key.
  - auth-capture `delegated` operator: the **facilitator** controls `captureAuthorizer`. If MCTL self-facilitates, MCTL holds an operator key that can move held funds to the configured receiver only. This is custody of an operator credential, not of payer funds. It is a P1 risk and needs its own owner gate.
  - Hedera: owner-set on-chain caps (per press). Unverified.
  - Account-funded: no key.
- **Replay, idempotency and concurrency.** The MCTL key `mctl-pay/v1:<invocation_id>:authorize` maps to the x402 `payment-identifier` id (16-128 chars: use `invocation_id`) or to the MPP challenge `id`. Concurrent reserves are already serialized by the budget advisory lock. The rail nonce must be derived from the invocation so that a gateway retry re-presents the same authorization.
- **Lost response.** In every rail, a missing answer becomes `payment_status: unknown`, and only `Status` on the same key may resolve it:
  - x402 exact: chain nonce lookup.
  - auth-capture: escrow `paymentState`.
  - MPP: receipt replay plus chain.
  - Hedera: mirror node.
  - Account-funded: ledger-local.

  Execution uncertainty stays on `outcome_unknown`, with provider dedupe on `provider_operation_key`. No rail permits blind re-execution.
- **Deadlines.** For auth-capture, `captureDeadline` must exceed reservation window (15 min) + `dispatch_deadline` (60 s) + `reconciliation_deadline` (24 h). Otherwise the payer can `reclaim` a hold the ledger still counts as `reserved`/`outcome_unknown`. The rule is `captureDeadline >= reserve_time + 24h15m + margin`.
- **Currency.** The settlement asset (for example `eip155:84532` + USDC `0x036C…CF7e`, 6 decimals; `hedera:testnet` + HBAR/HTS) is not in `currencyExponents`. An external rail needs either asset-denominated terms (a separate ADR 020 amendment) or a separately designed FX layer. Neither is in scope, so this is a blocker for every on-chain rail.
- **Fees, latency, minimum charge** (labelled assumptions, not measurements):
  - auth-capture declares `minFeeBps`/`maxFeeBps` in-protocol.
  - On-chain gas on L2s is facilitator-sponsored in `exact`.
  - Assumption A1: two on-chain operations per call (authorize + capture) make charges below roughly USD 0.01 uneconomic.
  - Assumption A2: MCP Check utilization is low (tens of calls a month), so unit economics do not justify production merchant setup.

  Both must be replaced by testnet measurements at gate G1.
- **MCP errors.** For the merchant, the first proof uses the x402 MCP shape (S2) only, because that is what #617 implements. SEP-2007 `-32402` and MPP `-32042` are not served on any public endpoint until the formats stabilize.
- **Streaming and long-running.** Rejected for the first proof. x402 MCP (S2) and #617 are JSON-response only; the 60 s dispatch fence does not cover long tasks. MPP `session` is the only design built for streaming, and it is deferred.
- **Generic client versus binding-aware buyer.** #617 requires a nonce-binding-aware buyer, so generic-client interoperability is not established.
- **Eligibility.**
  - x402 testnet: no KYC for test USDC; mainnet merchant terms are not assessed.
  - MPP Stripe: a Stripe account (KYC, merchant of record, tax, refunds/chargebacks) is required.
  - Hedera: early-access form.
  - Account-funded: invoicing, tax and refund handling are already a business process outside the API.

### 3. Host/client matrix (buyer clients of an MCTL merchant tool)

| Client | x402 MCP | MPP MCP | SEP-2007 | Fallback |
|---|---|---|---|---|
| ChatGPT | not observed | not observed | not observed | entitlement/simulated budget via governed tool; refuse with payment-required text |
| Claude (desktop/code) | not observed | not observed | not observed | same |
| Antigravity | not observed | not observed | not observed | same |
| Grok bot | not observed | not observed | not observed | same |
| Cloudflare `withX402Client` (S6) | vendor-claimed | n/a | n/a | n/a |
| Headless reference buyer (#617 `buyer.mjs`) | offline-tests only | none | none | n/a |

Catalog or SDK support is never extrapolated to native host payments.

### 4. Merchant and buyer recommendations

- **MCTL as merchant** (selling its own capability, MCP Check): `EXTEND_X402_PILOT`, offline fixtures only. Keep #617's `exact` path. Add an `auth-capture` `escrow` fixture path that maps onto `Authorize`/`Capture`/`Void`/`Status`. Route quote, budget, approval and ledger state through the existing `internal/commerce` contract instead of a second store. This is a follow-up scope with design only in this revision.
- **MCTL as buyer** (paying external capabilities): `KEEP_SIMULATED`. No rail lets MCTL pay without holding a key or a delegated spend credential. Hedera Agent Accounts, the most relevant delegated-spend design, is not publicly available. Revisit with #346's outcome.

### 5. ADR outcome

- Refresh outcome: **`EXTEND_X402_PILOT`**.
- Original issue token: **`DEFER_EXTERNAL_PAYMENT`**, with x402 `auth-capture` `escrow` on Base Sepolia as the leading retest candidate.

The two agree. No rail is adopted into the commerce core because no
external-testnet settlement exists, the facilitator support is unconfirmed,
and the currency/asset blocker remains. The pilot is the evidence-gathering
step toward re-entry.

Why `EXTEND_X402_PILOT` beats each alternative:

- `KEEP_SIMULATED`: it would ignore new, material evidence. `auth-capture` is the first pinned rail shape that passes `checkAdapter` on paper, and it extends an existing isolated pilot at zero spend.
- `EVALUATE_MPP`: MPP `charge` fails `void`. MPP `session` is a channel model that does not map one-to-one to invocations. Stripe needs merchant KYC. No MPP evidence exists in-house.
- `ACCOUNT_FUNDED_FIRST`: already shipped as entitlements (#614). It is the fallback for unsupported clients, not an external rail to evaluate.
- `DEFER` with no pilot work: it wastes the #617 investment and leaves the auth-capture mapping unproven.
- Original-token view: `ADOPT_X402` and `MULTI_RAIL_FOUNDATION` need live evidence and an asset-pricing decision. `ADOPT_MPP` and `ADOPT_HEDERA` fail as above. `ADOPT_ACCOUNT_FUNDED` adds nothing beyond #614.

Re-entry criteria (all measurable):

- R1. A hosted or self-run facilitator returns `auth-capture` for `eip155:84532` from `/supported`, pinned by version.
- R2. With G1 approved, one Base Sepolia authorize -> capture and one authorize -> void, each with an external-wallet signature and chain reconciliation of a deliberately dropped response.
- R3. An accepted ADR 020 amendment for asset-denominated terms, or a separate FX design.
- R4. The deadline rule in section 2 is verified on-chain.
- R5. The MCP wire format choice is re-checked against SEP-2007 status (adopted, experimental extension, or still dormant).

Owner gates, each separate:

- G0: offline fixtures (this backlog).
- G1: testnet transfers with a dedicated test wallet the owner provisions.
- G2: merchant registration, facilitator or Stripe account, terms.
- G3: production/mainnet.

### 6. Rail-independent receipt/reconciliation envelope (documented only)

Fields:

- `schema_version`, `invocation_id`, `quote_digest`, `action_digest` (dispatch `args_digest`)
- `payer_principal_id`, `tenant_id`, `payer_account_id`
- `rail` (`x402|mpp|account|hedera|simulated`), `scheme` (`exact|auth-capture|charge|session|entitlement`)
- `network` (CAIP-2 or empty), `asset` (CAIP-19, or ISO code for account)
- `accounting_amount` (`Money`), `settlement_amount` (decimal string, atomic units)
- `external_payment_ref` (opaque tx hash, escrow `paymentInfoHash` or receipt id)
- `payment_state` (ledger `payment_status` vocabulary), `execution_state` (`execution_outcome` vocabulary)
- `reconciliation_state` (`pending|matched|mismatch|unresolved`)

It never carries proofs, signatures or idempotency keys, which is the
`Receipt` allowlist rule. It is not added to `Receipt` or to the MCP tools in
this revision.

### 7. Composed reference scenario (synthetic)

1. A GitHub event (mctlhq/.github#377 Events) creates a governed task (#41 Tasks).
2. The MCP App (#376) shows status and a quote with `quote_digest`.
3. The owner approves when policy requires it (existing action approval, `approval_id`).
4. The gateway runs `…/reserve`, which calls the adapter `Authorize`. The x402 challenge and receipt happen here.
5. `…/dispatch` fence, then execution.
6. `…/finalize` (`Capture`/`Void`), then a durable result plus the envelope.

Event delivery and payment receipt are inputs to nothing in the
authorization path. Identity, tenant, policy, budget and approval decide.
None of this is implemented in this revision.

### 8. Risks

- **P1.** Operator-key custody under self-facilitated auth-capture. P1. Capture after `captureDeadline` or payer `reclaim` while the ledger holds `reserved`/`outcome_unknown` (mitigated by the deadline rule). P1. An unstable MCP wire field exposed on a public endpoint.
- **P2.** Asset/currency mismatch leading to implicit FX. P2. Hosted facilitator behaviour that cannot be pinned. P2. Vendor claims (Cloudflare compatibility, Hedera timelines, third-party comments) mistaken for protocol facts.
- **P3.** Unit economics (assumptions A1 and A2). P3. Spec churn making the pins stale. Mitigation: re-pin at each gate.

## Alternatives

- **Adopt x402 `auth-capture` into the core now (`ADOPT_X402`).** Rejected. There is no testnet evidence, hosted support is unconfirmed, and terms cannot be priced in USDC without an ADR 020 amendment. It would require relaxing the simulated-mode check.
- **Relax `requiredFeatures` so that `exact`/`charge` rails install.** Rejected. "Void" would leave settled money moved, contradicting the release/finalize rules in `docs/commerce-ledger.md`.
- **Add an inert `ExternalPaymentEnvelope` Go type now (previous revision).** Dropped. The owner refresh forbids unstable fields and integration in this revision. Docs plus a test-only classification check deliver the same verifiability without production code.

## Platform impact

- No migrations, routes, MCP tools, env vars or Helm changes. The `server_test.go` tool count is unchanged.
- One new `_test.go` file in `internal/commerce`. It calls the unexported `checkAdapter` only, needs no database, and runs under `go test -p 1 ./...` without `TEST_DATABASE_URL`.
- Backward compatible. Fully revertible by deleting the four files.
- Risk: the docs are read as authorization to spend. Mitigation: a header in each doc stating that no funds, wallets, testnet transfers or production rails are authorized, and that gates G1 to G3 need separate owner approval.
