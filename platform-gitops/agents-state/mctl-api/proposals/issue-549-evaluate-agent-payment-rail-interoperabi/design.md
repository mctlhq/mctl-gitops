# Design: issue-549-evaluate-agent-payment-rail-interoperabi

Revision 3. It supersedes the 2026-11-22 revision 2 (REQUEST_CHANGES) and
changes only documentation and test-only fixtures. Every verdict below is
**proposed**: the owner decision is not issued here.

## Current state

### Commerce core in this clone (HEAD `80f7a01`, 2026-11-22)

The reviewer's pinned blobs match this clone exactly:

- `internal/commerce/budget.go`: `git hash-object` = `8aac93f17c07b6d9afeb7341778bd05e2aafa1f7`
- `internal/commerce/dispatch.go`: `git hash-object` = `51649687a1d81acb386089b5437b34e879fde8f8`

**Adapter contract (`budget.go` ~222-300).** `PaymentAuthorizer` has four
methods: `Adapter`, `Authorize(ctx, q querier, PaymentRequest)`,
`Capture(ctx, q, key, authorizationID, Money)`, `Void(ctx, q, key,
authorizationID)` and `Status(ctx, q, key)`.

- `Status` takes only the MCTL key. It has no slot for a protocol identifier
  (tx hash, nonce, `paymentInfoHash`).
- `PaymentRequest` carries `Key`, `InvocationID`, `TenantID`,
  `PayerAccountID`, `Money`, `FundsMode` and `QuoteDigest`. It does not carry
  payee, network, asset or `args_digest`.
- `checkAdapter` (~273) requires `AdapterID`, `AdapterVersion` and
  `requiredFeatures = {auth_capture, void, status_lookup}` (~92). It also
  requires `FundsModeSimulated` in `FundsModes`.
- `SimulatedAuthorizer` writes `commerce_payment_operations` through the
  passed `querier`, which is the ledger transaction.

**Keys (`types.go:525-532`).** `ProviderOperationKey = "mctl-op/v1:" + invocation_id`;
`PaymentOperationKey = "mctl-pay/v1:" + invocation_id + ":" + operation`.

**Transaction shape (`store.go:361`).** `withTx` begins a transaction, takes
`pg_advisory_xact_lock(hashtext(lockKey))`, runs `fn`, then commits. The
following paths all call the adapter inside `fn`:

- `Reserve` (`budget.go:784`): `s.auth.Authorize(ctx, tx, ...)` at ~869, then
  `INSERT INTO commerce_reservations` and `applyTransition`.
- `resolveUnknownHold`.
- `Finalize` (~1007) through `settlePayment` (~1152, `Status` then
  `Capture`/`Void`).
- `Release` (~1205).

A `PaymentResultUnknown` answer from authorize is committed as
`payment_status: unknown` (~895). An `err` from the adapter, or any later
SQL failure, or a failed commit rolls everything back.

**Money (`types.go:178`).** `Money{Currency, AmountMinor}` with
`currencyExponents`, ISO 4217 only. USDC and HBAR are refused.
`checkFundsMode` (~320) refuses `live`.

**Windows.** `DefaultReservationWindow = 15m` (`budget.go:44`),
`DefaultDispatchWindow = 60s`, `MaxClockSkew = 60s` (`dispatch.go:45,51`),
`DefaultReconciliationWindow = 24h` (`store.go:37`). The phase graph
(`types.go:606-615`) allows dispatching/dispatched -> `outcome_unknown` ->
finalized.

**Receipt (`receipt.go:43-79`).** The receipt already carries
`invocation_id`, `quote_digest`, tenant/payer/principal, `price`, and the
separate `execution_outcome`, `charge_status`, `payment_status` and
`settlement_status`. It has no rail, network, asset or external reference.

**Existing tests.** `budget_test.go:662` `TestAdapterNegotiation` and
`fakeAdapter` refuse "no void", "no status", "no simulation" and "no id".
`unknownOnce` (~612) exercises the unknown path.

### Evidence inventory (gh, 2026-11-22)

| Item | State | Evidence class |
|---|---|---|
| mctlhq/.github#173 Agent Commerce | closed 2026-10-12 | epic |
| mctl-api#546 terms, #547 ledger, #548 budgets | closed 2026-10-11 | merged code, simulated funds only. Merge PRs include #550 `362df561fe36` (ledger) and #557 `d81586790beb` (atomic budgets with simulated authorization) |
| mctl-api#614 entitlements | merged `87256896af00` | account-funded units, simulated |
| mctl-agents#619 governed invocation, #620 Paid Capabilities proof | closed 2026-10-11/12 | **simulated credit proof** |
| mctl-agents#631 shared tenants | open | not available |
| mctl-api#616 x402 MCP Check pilot | open | - |
| mctl-api PR #617 | open, head `e3bf0293bef6`, one commit, CI `offline-tests`/`test`/`lint` success, 0 comments | **offline tests only** against fake facilitator. No external testnet settlement recorded. No production availability |
| mctl-api#346 | merged PR (human-input read model) | scope preserved, untouched |

PR #617 facts, from `experiments/x402-mcp-check/README.md` at `e3bf029`:

- x402 v2, `exact`, EIP-3009, Base Sepolia `eip155:84532`, test USDC
  `0x036C...CF7e`, 10000 atomic units, facilitator `https://x402.org/facilitator`.
- SQLite claims committed before I/O. Restart in settling -> `settlement_unknown`.
- `reconcile.mjs` verifies finalized `AuthorizationUsed` + `Transfer`.
- The pilot **supplies the nonce** to a binding-aware buyer. Generic random-nonce
  signers are explicitly not supported.
- Streaming, long-running, MPP and refunds are absent.

The pilot nonce is therefore a pilot-only binding, not a pattern for the core
(see P1-PAY-02).

### Pinned external sources (read 2026-11-22)

| Id | Source | Pin | Material facts used |
|---|---|---|---|
| S1 | x402 `specs/transports-v2/mcp.md` | x402-foundation/x402 `e35bf8846f3e` (2026-11-20), blob `0dbd9e76` | Payment required = tool result `isError: true` + `structuredContent` PaymentRequired. Payment in `_meta["x402/payment"]`. Receipt in `_meta["x402/payment-response"]`. On settle failure after execution, the content is withheld |
| S2 | x402 `schemes/exact/scheme_exact_evm.md` | same commit, blob `cda2ed42` | EIP-3009 `authorization.nonce` + `validBefore` are inside the payer-signed authorization |
| S3 | x402 `schemes/auth-capture/scheme_auth_capture_evm.md` | same commit, blob `6ef2fb1b` | See below |
| S4 | x402 `extensions/payment_identifier.md` | same commit, blob `e85f0d53` | Client-supplied `id` (16-128 chars) used as an idempotency key at the server and/or facilitator |
| S5 | x402 `schemes/exact/scheme_exact_hedera.md` | same commit, blob `46d654c9` | x402 `exact` exists for Hedera (lifecycle as exact) |
| S6 | SEP-2007 `seps/2007-payment-support-for-mcp-servers.md` | modelcontextprotocol PR #2007 head `09b9d1d8c321`, **closed unmerged 2026-06-24**; issue #2008 closed | `Status: Draft`. `payment` capability, tool `payment` field, error `-32402`, request `params.payment.paymentInput`, result `payment.paymentOutput`. x402 v2 is recommended. No reserve/refund/streaming semantics |
| S7 | MPP `specs/extensions/transports/draft-payment-transport-mcp-00.md` | tempoxyz/mpp-specs `7bb99c854225` (2026-11-11), blob `f55bee17` | See below |
| S8 | MPP `specs/core/draft-httpauth-payment-01.md` | same, blob `bbd8fd65` | HMAC-SHA256 binding over `realm|method|intent|request|expires|digest|opaque`. `digest` binds the request body. Retries use `Idempotency-Key` |
| S9 | MPP `methods/hedera/draft-hedera-charge-00.md` / `-session-00.md` | same, blobs `414b52a8` / `c3a4937c` | See below |
| S10 | MPP method/intent inventory | same commit tree | See below |
| S11 | MPP SDKs | `mpp-go` release `v0.9.1`, `mppx@0.21.1` | Version pins only, not exercised |
| S12 | Cloudflare Agents payments page | https://developers.cloudflare.com/agents/tools/payments/, `dateModified` 2026-08-05, accessed 2026-11-22. **Vendor self-report** | x402 (`withX402`, `paidTool`, `withX402Client`) and MPP. No refund, auth-capture or streaming claims |
| S13 | `hashgraph/hedera-agent-kit-js` | `81bd43a8e10e` (2026-11-04) | SDK context only. No official "Hedera Agent Accounts" / "Payments MCP" spec found |

S3 details (auth-capture):

- Built on base/commerce-payments `AuthCaptureEscrow`: v1.1 `0xf968...B19c`,
  v1.0 `0xBdEA...0cff`.
- `capture`/`void`/`refund` are relayed only for `delegated` with a non-zero
  `receiverAuthorizer`. `custom` and authorize-only routes are collect-only
  and MUST use `captureMode: "deferred"`.
- `signatureNonce = keccak256(chainId, escrow, payerAgnosticHash(paymentInfo))`
  and `paymentInfoHash = escrow.getHash(paymentInfo)`. The client's random
  `salt`/`saltNonce` keeps the nonce fresh.
- Async servers MUST persist `saltNonce` with `paymentInfo`.
- `captureDeadline` = `authorizationExpiry`, after which the payer may
  `reclaim`. `refundDeadline` = `refundExpiry`.

S7 details (MPP MCP transport):

- Error `-32042` with `data.challenges[]`. The challenge `id` MUST be
  cryptographically bound to `realm`, `method`, `intent`, the JCS
  `request` hash and `expires`, and SHOULD be bound to the operation.
- Credential in `_meta["org.paymentauth/credential"]`, receipt in
  `_meta["org.paymentauth/receipt"]`.
- Unknown, expired or used challenge ids are rejected. Atomic check-and-mark
  is required under concurrency.
- Notifications cannot carry payment.

S9 details (MPP Hedera): `charge` is an HTS transfer in push mode (client
submits, server verifies on Mirror Node) or pull mode (client signs, server
submits). It carries a 32-byte challenge-bound memo, with stated finality of
3-5 s. `session` is an escrow contract (`HederaStreamChannel`) with EIP-712
vouchers and close.

S10 details (MPP inventory): `charge`, `session` and `subscription` intents.
Methods are card, evm, hedera, lightning, nearintents, solana, stellar,
stripe, tempo, usdc and xrpl.

Third-party comments on the issue (including Screwtape) are treated as
untrusted vendor self-report and are not used as evidence.

### Deployed state checked

- `mctl_list_services(team=admins)` answered `complete: true` with 8 catalogue
  services (mctl-agents-worker*, mctl-design, mctl-docs, mctl-support,
  mctl-web, umami). **mctl-api is not among them.**
- `mctl_get_service_config(admins, mctl-api)` answered
  `service not found: admins/mctl-api`.
- `$MCTL_GITOPS_ROOT/services/{admins,karabu,labs,namax66,redloop}`: no
  `mctl-api/values.yaml`. `grep -ri "commerce|x402"` over `services/` found
  nothing.
- **Conclusion:** mctl-api's deployed commerce env (for example
  `COMMERCE_ACCEPT_DISABLED`, the adapter in use) could not be observed. This
  is a gap and does not mean the setting is absent (see Open questions in
  requirements.md). The design relies only on code: `checkFundsMode` refuses
  `live` regardless of deployment.

## Proposed solution

Deliver four artifacts. No production code, migration, route, tool or Helm
change.

1. `docs/payment-rail-interop.md`: the decision report, with the sections
   below.
2. `docs/payment-rail-interop-sources.md`: the S1-S13 matrix with
   section-level anchors, plus the evidence inventory.
3. `docs/adr/0002-payment-rail-interop.md`: ADR, `Status: proposed`. It names
   the proposed merchant and buyer outcomes and their conditions, and records
   "owner decision: not issued".
4. `internal/commerce/rail_classification_test.go`: test-only negative
   classification fixtures plus a crash-gap characterization test (task 2).
   The file is in package `commerce` and reuses `fakeAdapter`/`Store`
   patterns from `budget_test.go`.

### 1. Finding -> change mapping (revision 3)

| Finding | Source it rests on | Change in this revision |
|---|---|---|
| P1-PAY-01 commit gap | `store.go:361` `withTx`; `budget.go` ~869 `Authorize(ctx, tx, ...)` then INSERT; ~1152 `settlePayment` inside `Finalize` tx | Section 3: the durable-intent + out-of-tx external call + recording tx + reconciler design is required before any live adapter. Characterization test T3 proves the gap exists today. Fault-injection test plan F1-F6 is for the future adapter |
| P1-PAY-02 nonce conflation | S2, S3 Payment identity, S4; `types.go:530` | Section 4 key table: four separate identifier domains. The "rail nonce derived from invocation" text is removed. The #617 server-supplied nonce is labelled a pilot-only binding-aware-buyer mode. Negative tests N1-N8 |
| P2-PAY-03 hard-coded verdict | revision 2 requirements/tasks | The ADR is `proposed`. Outcomes are conditional (section 7) with fallbacks. The ADR task depends on the classification and inventory tasks |
| P2-PAY-04 simulated false positive | `budget.go:273-300` | Section 2: `checkAdapter` result and `eligible_for_mctl` are separate. Rows that pass only by declaring simulated are labelled `contract-shape only`. Fixture T1 asserts `eligible_for_mctl=false` for every external row, including the false-positive row |
| P2-PAY-05 deadline/asset | `budget.go:44`, `dispatch.go:45,51`, `store.go:37`, `types.go:178-190`; S3 deadlines | Section 5: invariant evaluated at reserve/capture/reconcile, with abort paths. Section 6: asset boundary. Test plan D1-D5 and A1-A3 |

### 2. Adapter capability classification

Legend: N native, E emulated-with-evidence, U unsupported, ? unknown/unpinned.
`checkAdapter` is evaluated on an **honest** declaration: `FundsModes` contains
`simulated` only if a real simulator exists for that rail.

| Rail shape (pin) | authorize | capture | void | status | refund | async | honest `checkAdapter` | eligible_for_mctl |
|---|---|---|---|---|---|---|---|---|
| x402 `exact` EVM EIP-3009 (S2) | E (verify, no hold) | N (settle) | U (payer-signed auth is settleable until `validBefore`) | E (chain `AuthorizationUsed` by payer nonce, as #617 `reconcile.mjs`) | U | U | refused: void; no simulated mode | false |
| x402 `auth-capture` `escrow`, `delegated` + receiverAuthorizer (S3) | N (escrow hold) | N | N | E (escrow `paymentState[paymentInfoHash]`, no facilitator status endpoint) | N until `refundDeadline` | N (`deferred`) | refused: no real simulated mode (testnet is live funds on a test chain, not `FundsModeSimulated`) | false |
| same, declared `simulated` without a simulator | - | - | - | - | - | - | **accepted: false positive** | false (`contract-shape only`) |
| x402 `auth-capture` collect-only (`custom` / authorize-only) | N | out-of-band operator | out-of-band | E | out-of-band | deferred only | refused: features not relayed | false |
| x402 `exact` Hedera (S5) | E | N | U | E (Mirror Node) | U | U | refused: void | false |
| MPP `charge` (evm/tempo/usdc/hedera, S7-S10) | E (credential verify) | N | U | E (receipt + chain/Mirror Node) | U in protocol | U | refused: void | false |
| MPP `session` (tempo/evm/hedera) | N (escrow deposit) | N (voucher close) | E (close at 0) | E | E (unused deposit) | N | channel per payer, not per invocation: not mappable 1:1 | false |
| MPP `stripe` charge | ? | N | ? | ? | outside MPP | ? | unknown; needs Stripe merchant (KYC) | false |
| SEP-2007 (S6) | transport only, delegates to the protocol | - | - | - | - | - | not a rail | n/a |
| Account-funded entitlements (#614) | N (ledger hold) | N | N (release) | N (ledger) | U (no money moved) | n/a | in core already (simulated) | already used, not external |
| Hedera "Agent Accounts / Payments MCP" | ? | ? | ? | ? | ? | ? | unassessable (no official spec found, S13) | false |

Rules recorded in the report:

- `checkAdapter` passing is necessary and never sufficient.
- A live adapter verdict needs: a real simulator or an ADR 020 amendment for
  `FundsModeLive`; a status path on persisted protocol identifiers; the
  section 3 commit-gap design; and the section 6 asset decision.
- No row gets a legal live-adapter verdict here.

### 3. External side effect vs DB commit (P1-PAY-01)

**The gap today.** Everything below happens in one `withTx`: the advisory
lock, `Authorize` or `Capture`, the ledger INSERT/UPDATE, and the commit. For
the simulated adapter this is atomic because its writes share `tx`. An
external call cannot join that transaction. The following failures after
external success leave money held or moved with **no committed row**:

- the INSERT into `commerce_reservations` fails;
- `applyTransition` fails;
- `tx.Commit` fails;
- the lock or ctx times out;
- the process dies.

The existing unknown path (`payment_status: unknown`, ~895) covers only the
case where the adapter *returned* unknown and the transaction committed. The
retry then calls `Authorize` again on the same key, and only a key-idempotent
rail dedupes that call.

**Required design before any live adapter (specified, not implemented):**

1. **Tx A, intent.** Under the budget lock, insert a
   `commerce_payment_intents`-style row and commit it. The row holds:
   - the operation key and state `intent`;
   - the full binding tuple (section 4);
   - the presented proof fingerprint and the protocol identifiers already
     known (EIP-3009 nonce; auth-capture `paymentInfo` + `saltNonce` +
     `paymentInfoHash`; MPP challenge id);
   - a deadline and an owner/fencing epoch.

   The ledger hold is committed in the same Tx A, in phase `reserved`,
   `payment_status: pending_external`. That status is new and needs an ADR
   020 amendment, so it is recorded as future scope.
2. **External call, outside any DB transaction.** The call presents the same
   proof bytes. Exactly one in-flight attempt per intent is allowed, enforced
   by a CAS `intent -> in_flight` with the epoch.
3. **Tx B, record.** CAS `in_flight -> authorized|captured|denied|unknown`,
   storing the external reference (tx hash / `paymentInfoHash` / receipt id).
4. **Reconciler.** It sweeps `in_flight`/`unknown` intents past a bound. It
   calls `Status` on the **persisted protocol identifiers** and never calls
   `Authorize`/`settle`/`Capture` again unless one of these is proven:
   - for exact: the payer-signed authorization is expired (`validBefore`
     passed) **and** the chain shows it unused;
   - for auth-capture: `paymentState` is absent and the `preApprovalExpiry`
     has passed.

   Otherwise the intent goes to manual reconciliation. The `Status`
   signature therefore needs the intent, not just the key. This is recorded
   as the interface delta for the follow-up ADR.
5. **Dead owner.** An `in_flight` intent whose epoch owner is gone is taken
   over only by fencing (new epoch) and only through step 4, never by
   re-sending.

**Why a retry avoids a second economic charge:**

- x402 exact: the payer-signed EIP-3009 nonce is single-use on-chain (S2). A
  second settle of the same proof fails.
- auth-capture: `signatureNonce` is derived from `paymentInfo` (S3), so the
  same proof cannot collect twice.
- MPP: challenge ids are single-use under atomic check-and-mark (S7).

The residual risk is a client that signs a **second** proof for the same
invocation. MCTL prevents that by accepting one proof fingerprint per intent
and rejecting others (N7). Exactly-once across external systems is not
promised; the guarantee is at most one accepted proof per invocation, plus
reconciliation.

### 4. Identifier domains (P1-PAY-02)

| Domain | Owner | Value | Use | Never |
|---|---|---|---|---|
| Invocation / operation | MCTL | `invocation_id`; `mctl-pay/v1:<inv>:<op>` (`types.go:530`); `mctl-op/v1:<inv>` | ledger idempotency, intent primary key | never sent as, or used to derive, a payer-signed nonce |
| Protocol payment identifier | client (x402 S4) or server (MPP challenge `id`, S7/S8) | x402 `payment-identifier.id` (16-128 chars); MPP HMAC-bound challenge id | protocol-level dedupe and replay set | not authority; not equal to the nonce |
| Payer-signed nonce / commitment | payer wallet | EIP-3009 `nonce`; auth-capture `salt`, `saltNonce`, `signatureNonce`, `paymentInfoHash`; Hedera tx id + memo | on-chain replay protection, status lookup | never dictated by MCTL for a generic client. The #617 supplied-nonce mode is a pilot-only binding-aware buyer and is labelled as such |
| Binding tuple | MCTL intent | CAIP-2 chain, CAIP-19 asset, payee, atomic amount, expiry, `quote_digest`, dispatch `args_digest`, rail+scheme, payer address -> `payer_account_id` mapping | verify the proof against the intent before any external call | a payer address never grants tenant authority |

**Binding strategy for generic clients.** The challenge carries
`quote_digest` in a server-bound field: the x402 `resource.url`/`extra`, or
the MPP `opaque`/`digest` inside the HMAC. MCTL verifies the proof's
terms against the intent. It does not try to put the digest into the payer's
nonce.

### 5. Deadline invariant (P2-PAY-05)

The invariant is checked at reserve (before Tx A), before capture, and at
every reconcile:

`external_deadline - now - MaxClockSkew(60s) - finality_bound - pause_margin >= remaining_ledger_obligation`

- `external_deadline` is the auth-capture `captureDeadline` or the exact
  `validBefore`.
- `finality_bound` is per network and must be measured at G1. Hedera's stated
  3-5 s is a spec claim, not a measurement.
- `pause_margin` covers a facilitator, chain or token pause. It is an owner
  parameter.
- `remaining_ledger_obligation` at reserve = reservation window (15m) +
  dispatch window (60s) + reconciliation window (24h). After dispatch, it is
  the remaining `reconciliation_deadline`.

| Step | Invariant fails | Action |
|---|---|---|
| reserve | cannot be met | refuse (future reason code `payment-deadline-unmeetable`) with no external call |
| capture | cannot be met | void if still possible, else manual reconciliation; never mark captured |
| reconcile `outcome_unknown` | deadline passed | treat as reclaimable: ledger state `unresolved`, budget not counted as committed, owner alert |

Long-running execution cannot outlive the deadline, which is one reason
long-running calls are rejected for the first proof.

### 6. Asset boundary

Accounting stays `Money` (ISO 4217, `currencyExponents`). Settlement is
recorded separately as `{network: CAIP-2, asset: CAIP-19, amount_atomic:
decimal string, decimals}`.

- A rail is usable only with terms that explicitly declare the
  (accounting `Money`, settlement asset+amount) pair. That needs an ADR 020
  amendment and is future scope.
- No conversion and no implicit EUR/USD/USDC/HBAR equivalence.
- Tests A1-A3 (in the follow-up) refuse a USDC `Money`, a mismatched declared
  pair, and a settlement amount different from the quote.

### 7. Proposed recommendations (ADR `proposed`, owner decision not issued)

**MCTL as merchant** (selling its own MCP Check, #616/#617). Proposed:
`EXTEND_X402_PILOT`, limited to offline fixtures, **iff** all of the following
hold at task 4:

- C1: T1/T2 pass.
- C2: S3 auth-capture relayed lifecycle remains pinned.
- C3: the section 3 design reviews clean.

If C2 fails (spec changed or withdrawn) or C3 fails -> `KEEP_SIMULATED`. If
#617 is abandoned -> `DEFER`.

The extension means adding offline fake-facilitator fixtures to the pilot
for: auth-capture escrow mapping, durable intent, reconciler, and the
negative tests N/F/D. The pilot's `exact` path and testnet boundaries stay
unchanged. Nothing is connected to `internal/commerce` until G1+ review.

**MCTL as buyer** (paying external capabilities). Proposed: `KEEP_SIMULATED`.

- Every rail requires MCTL to hold a signing key or a delegated spend
  credential. Hedera delegated-spend is not officially specified (S13).
- Re-entry requires a non-custodial delegated signer with owner-set limits,
  pinned by a public spec.

**Original-issue token.** Proposed `DEFER_EXTERNAL_PAYMENT`. The leading
retest candidate is x402 `auth-capture` `escrow` (`delegated` +
receiverAuthorizer) on Base Sepolia. Re-entry criteria:

- R1: a facilitator `/supported` advertises auth-capture on `eip155:84532`,
  version-pinned.
- R2 (G1 approved): authorize->capture, authorize->void, and a deliberately
  dropped response reconciled from the chain, each with an external-wallet
  signature.
- R3: an ADR 020 amendment for asset-denominated terms and
  `pending_external`.
- R4: the section 3 fault-injection suite F1-F6 passes.
- R5: SEP-2007 / MCP wire format status re-checked.

**Why this beats each alternative:**

- `EVALUATE_MPP`: MPP `charge` fails void (refused by `checkAdapter`), and
  `session` is per-channel, not per-invocation. There is no in-house MPP
  evidence, and Stripe needs KYC. MPP is the second candidate if R1 fails.
- `ACCOUNT_FUNDED_FIRST`: already shipped (#614, simulated). It is the
  fallback for unsupported clients, not a new step.
- `DEFER` with no pilot work: it leaves P1-PAY-01/02 unproven where it is
  cheapest to prove them (an isolated pilot, zero spend).
- `KEEP_SIMULATED` for the merchant: correct only if C2/C3 fail, which is
  why it is the fallback.
- Original tokens:
  - `ADOPT_X402` and `MULTI_RAIL_FOUNDATION` lack live evidence (R2) and the
    asset decision (R3).
  - `ADOPT_HEDERA` has no official delegated-spend spec.
  - `ADOPT_MPP` fails as above.
  - `ADOPT_ACCOUNT_FUNDED` adds nothing beyond #614.

**Owner gates (separate):** G0 offline fixtures; G1 testnet with an
owner-provisioned test wallet; G2 merchant/facilitator/Stripe registration;
G3 production/mainnet.

### 8. MCP wire formats and clients

There are three incompatible formats (S1, S6, S7):

- x402: `isError` + `_meta["x402/payment"]`;
- SEP-2007: `-32402` + `params.payment`;
- MPP: `-32042` + `_meta["org.paymentauth/credential"]`.

The first proof uses only the x402 MCP shape #617 already implements, on
loopback. None of the three is served on a public production endpoint.

| Client | x402 MCP | MPP MCP | SEP-2007 | Fallback |
|---|---|---|---|---|
| ChatGPT | not observed | not observed | not observed | entitlement/simulated budget through the governed tool; payment-required text |
| Claude | not observed | not observed | not observed | same |
| Antigravity | not observed | not observed | not observed | same |
| Grok bot | not observed | not observed | not observed | same |
| Cloudflare `withX402Client` (S12) | vendor-claimed | vendor-claimed (MPP-aware clients) | n/a | n/a |
| #617 `buyer.mjs` | offline only, binding-aware | none | none | n/a |

Catalog or SDK support is never extrapolated to native host payments.
Streaming and long-running calls are rejected for the first proof:

- S1 and #617 are JSON-response only.
- The 60 s dispatch window and the section 5 deadline bound execution.
- MPP notifications cannot carry payment (S7).
- MPP `session` is deferred.

### 9. Per-rail dimensions (recorded in the report)

**Fees, latency, minimum charge.** These are labelled assumptions, to be
replaced at G1:

- A1: two on-chain operations per auth-capture call make charges below
  roughly USD 0.01 uneconomic.
- A2: MCP Check utilization is tens of calls a month, so production merchant
  setup is not justified.
- auth-capture declares `minFeeBps`/`maxFeeBps` in protocol.

**Custody.**

- Payer-signed proofs keep MCTL non-custodial as a merchant.
- auth-capture `delegated`: the facilitator holds `captureAuthorizer`. If
  MCTL self-facilitates, it holds an operator/receiverAuthorizer key, which
  is custody of a credential that can move held funds to the payee. This is
  P1 and gated by G2.
- MPP pull mode has MCTL submit a payer-signed tx (no key).
- Account-funded needs no key.

**Eligibility.**

- x402 testnet: no KYC.
- MPP Stripe: merchant of record, tax, chargebacks.
- Hedera: account association for HTS tokens.
- Mainnet terms are not assessed.

**Merchant vs buyer obligations** (tax/refund/chargeback, data rights,
subscriptions/invoices vs pay-per-call) are listed per side. All of them are
gated by G2/G3.

### 10. Rail-independent envelope (documented only)

Fields:

- `schema_version`, `invocation_id`, `quote_digest`, `action_digest` (dispatch
  `args_digest`);
- `payer_principal_id`, `tenant_id`, `payer_account_id`;
- `rail`, `scheme`, `network` (CAIP-2), `asset` (CAIP-19 or ISO code);
- `accounting_amount` (`Money`), `settlement_amount_atomic`;
- `protocol_payment_id`, `external_payment_ref` (tx hash /
  `paymentInfoHash` / receipt id);
- `payment_state`, `execution_state`, and `reconciliation_state`
  (`pending|matched|mismatch|unresolved`).

It never carries proofs, signatures, nonces' preimages or idempotency keys,
following the `Receipt` allowlist rule. It is not added to `Receipt` in this
revision.

### 11. Composed reference scenario (synthetic only)

1. An event (mctlhq/.github#377) creates an existing governed task (#41).
2. The MCP App (#376) shows status and a quote (`quote_digest`).
3. The owner approves when policy requires it (`approval_id`).
4. `reserve` writes intent Tx A, then the x402 challenge and proof are
   exchanged, then the external call, then Tx B.
5. Dispatch fence, then execution.
6. `finalize` with capture/void through the same intent pattern, giving a
   durable result plus the envelope.

Payment and event delivery are inputs to nothing in the authorization
decision. Nothing in this scenario is implemented.

### 12. Risks

- **P1.** An external success with no committed row (section 3). Mitigation:
  no live adapter until R4.
- **P1.** Operator-key custody under self-facilitated auth-capture.
  Mitigation: G2.
- **P1.** Payer `reclaim` while the ledger holds `reserved`/`outcome_unknown`.
  Mitigation: section 5.
- **P2.** Implicit FX. Mitigation: section 6.
- **P2.** An unstable MCP wire field on a public endpoint. Mitigation:
  loopback only.
- **P2.** A fixture misread as eligibility. Mitigation: the
  `eligible_for_mctl` column.
- **P2.** An unpinnable hosted facilitator.
- **P3.** Vendor claims (S12, Hedera press, Screwtape) mistaken for protocol
  facts.
- **P3.** SDK churn (`mppx` 0.x, `mpp-go` 0.x).

## Alternatives

- **Keep revision 2 and patch the wording.** Dropped: the review needs an
  executable negative fixture and a specified commit-gap design, not wording.
- **Prototype the durable intent in `internal/commerce` now.** Dropped:
  that is production code and a migration, outside the "docs + negative
  fixtures" revision 3 boundary. It also requires an ADR 020 amendment
  (`pending_external`, asset terms) first.
- **Make `checkAdapter` reject non-simulated external adapters harder.**
  Dropped for now: changing negotiation semantics is ADR 020 scope. The
  fixture documents the false positive instead.
- **Choose MPP as the leading candidate.** Dropped: MPP `charge` lacks void,
  and there is no in-house evidence. It is kept as the second candidate.

## Platform impact

- **Migrations:** none.
- **API/MCP/Helm:** none.
- **Runtime:** none.
- **New files:** three docs and one `_test.go` file. The Postgres-backed test
  T3 uses the existing `TEST_DATABASE_URL` and the `-p 1` convention in
  CLAUDE.md, and skips like sibling tests when the variable is unset.
- **Backward compatibility:** unaffected. The MCP tool count in
  `server_test.go` is unchanged.
- **Main risk:** reviewers reading T3 (which *asserts the gap exists*) as
  desired behaviour. Mitigation: the test name and comment say
  "characterization: must be inverted when the durable-intent design lands".
- **Approval:** no implementer run before a new independent review and an
  owner digest-bound approval.
