# Design: issue-549-evaluate-agent-payment-rail-interoperabi

## Current state

The commerce core is `internal/commerce` (Go, pgx), exposed by
`internal/api/handlers_commerce.go`, `internal/api/handlers_commerce_budget.go`
and the read-only MCP tools in `internal/mcp/commerce.go`
(`mctl_get_commerce_budget`, `mctl_list_commerce_invocations`,
`mctl_get_commerce_receipt`). `docs/commerce-ledger.md` documents it.

Facts that constrain any external rail, all read in the clone:

1. **One authorizer interface.** `PaymentAuthorizer` in
   `internal/commerce/budget.go` is `Adapter()`, `Authorize`, `Capture`,
   `Void`, `Status`. Every operation is idempotent on
   `PaymentOperationKey(invocationID, op)` (`mctl-pay/v1:<invocation_id>:<operation>`);
   same key with different parameters is `ErrPaymentConflict`.
   `PaymentRequest` carries `Key`, `InvocationID`, `TenantID`,
   `PayerAccountID`, `Money`, `FundsMode`, `QuoteDigest`; its comment says a
   payment proof "is an input here and nowhere else".
2. **Feature negotiation is strict.** `requiredFeatures =
   {auth_capture, void, status_lookup}`; `checkAdapter` refuses an adapter
   missing any, or one whose `FundsModes` lacks `simulated`.
   `UseAuthorizer` applies it at configuration time. Optional features exist
   as constants: `partial_capture`, `refund`, `async_settlement`,
   `simulation`.
3. **Authorize runs inside the ledger transaction.** `Store.Reserve` calls
   `s.auth.Authorize(ctx, tx, ...)` under the tenant-budget advisory lock and
   row locks, between the budget check / `holdEntitlementUnit` and the
   reservation insert. A `Denied` result commits no reservation; `Unknown`
   keeps the hold with `payment_status: unknown`.
4. **Unknown is never denied.** `resolveUnknownHold` and
   `resolveAuthorization` resolve an unknown authorization only through
   `Status` on the same key; `settlePayment` calls `Status` before issuing
   `Capture`/`Void`, so a lost response is replayed, not reissued.
   `reserved -> dispatching` is refused while payment is unknown.
5. **Execution fence.** `…/dispatch` writes a 60 s `dispatch_deadline` once
   and returns an Ed25519 authorization bound to `provider_operation_key`,
   `args_digest`, `tenant_id`, etc. (`internal/commerce/dispatch.go`).
   Providers dedupe on `provider_operation_key`. A `dispatched` row cannot be
   released; only an observed outcome finalizes it; `outcome_unknown` is
   resolved by `…/finalize`, never by time.
6. **Money.** `Money` is ISO 4217 minor units, checked against the
   `currencyExponents` table in `internal/commerce/types.go`; there is no
   token/crypto asset and no FX. Budgets are a limit, never a balance
   (`budget.go` header comment); `funds_mode` is `simulated` by CHECK
   constraint; `checkFundsMode` refuses `live`.
7. **Receipt.** `internal/commerce/receipt.go` projects an allowlist:
   ids, `quote_digest`, `price`, `funds_mode`, `phase`, the five facts
   (`execution_outcome`, `usage_quantity`, `charge_status`, `payment_status`,
   `settlement_status`), timestamps and `policy_decision`. It deliberately
   omits payment proofs, `external_ref`, `authorization_id`, `capture_id`.
   There is no rail, network, settlement asset or external reference field.
8. **Invoice-backed entitlements already exist** (mctl-api#614,
   `commerce_entitlements`, `holdEntitlementUnit` / `captureEntitlementUnit`
   / `releaseEntitlementUnit` in `budget.go`): finite unit packages granted
   by an admin against an `invoice_ref`, consumed FIFO in `Reserve`. This is
   the account-funded shape in unit form, with external payment entirely
   out of band.
9. **No x402 code.** `grep -ri x402` over the clone finds nothing; the
   mctl-api#616 pilot / PR #617 is not merged into this main
   (HEAD `53c1fc6`). Its evidence is therefore "in progress" for this
   evaluation.

Deployed state checked:
- `mctl_get_service_config(team=admins, service=mctl-api)`: error
  "service not found: admins/mctl-api" -- mctl-api is not a catalogue
  service under that tenant; deployed config not observed.
- `$MCTL_GITOPS_ROOT/services/` listing: tenants `admins`, `karabu`, `labs`;
  no `mctl-api` directory; `grep -ri "commerce\|x402"` over `services/`
  found nothing. Whether `COMMERCE_*` env vars are set in production is
  therefore unobserved (recorded under Open questions in requirements.md).
  This change is docs and tests only, so the gap does not affect it.

## Proposed solution

Deliver the evaluation as two repo artifacts, change no runtime code, and
recommend **`DEFER_EXTERNAL_PAYMENT`**.

### Artifact A: `docs/payment-rail-evaluation.md` (decision record)

Sections: contract under test (facts 1-7 above), comparison matrix,
adapter capability classification, non-custodial verdicts,
ambiguity/reconciliation analysis, streaming/long-running verdict,
eligibility/secrets/fee constraints, external receipt envelope,
recommendation, re-entry criteria. Linked from `docs/commerce-ledger.md`
("Adapter contract" section) with one sentence. Versions not verified
against vendor specs during writing are marked "not pinned" -- never guessed.

Comparison matrix (content of the record; the investigator's current
understanding, to be verified and version-pinned in task 1):

| Dimension | x402 (`exact`) | MPP | Account-funded allowance | Hedera (Agent Accounts / Payments MCP / allowances) |
|---|---|---|---|---|
| Versions | x402 spec + SDK + facilitator + network as used by #617: not pinned until #617 evidence is read | not pinned | n/a (internal) | Hedera SDK / Agent Kit / MCP servers: not pinned |
| Quote binding | Server-issued payment requirements (amount, asset, payTo, resource, expiry); MCTL must embed `quote_digest` in the resource/extra field and verify on receipt -- binding is MCTL's, not the rail's | Challenge/credential; binding to MCTL `quote_digest` likewise MCTL-side | `quote_digest` already bound by the ledger | Transfer memo / scheduled tx can carry `quote_digest`; binding MCTL-side |
| exact payment | yes | yes | n/a | yes (transfer) |
| spend cap | not in `exact` | session/limit model claimed; unverified | yes (budget limit, existing) | yes: owner-approved allowance (HIP-336 style), revocable |
| reserve/authorize -> capture | no: verify+settle, no hold | unverified; do not assume | yes (ledger hold = existing simulated adapter semantics) | partial: allowance approval is a cap, not a per-invocation hold |
| void | no (nothing held; settled payment can only be refunded) | unverified | yes | allowance can be reduced; settled transfer cannot be voided |
| refund | not a protocol operation (merchant-initiated transfer) | unverified | yes (credit back to allowance) | new reverse transfer only |
| status/reconcile | facilitator settle response + chain lookup by tx hash | unverified | yes (ledger) | mirror node lookup by transaction id |
| Signer custody | buyer signs a transfer authorization; MCTL need not hold buyer key; MCTL as merchant needs only a receive address | buyer-side wallet/credential; MCTL custody not required as far as known | none (no keys) | owner signs allowance; spender (agent) key is held by whoever runs the agent -- non-custodial for MCTL only if the agent runtime, not mctl-api, holds it |
| Replay/idempotency | per-authorization nonce prevents double settlement of the same signature; a client retry with a fresh signature is a second payment unless MCTL keys on `invocation_id` | unverified | `mctl-pay/v1` key (existing) | transaction id (payer + valid-start) is unique; a fresh tx id is a second payment |
| Lost response | settle may have happened with no response; recover only by chain lookup | unverified | n/a (same DB tx) | mirror-node query of the deterministic tx id |
| Execution uncertainty | payment settles at request time, before/with execution: a settled payment with `outcome_unknown` has no void, only refund | unverified | handled by existing finalize/release | as x402 |
| Settlement asset vs accounting | stablecoin token (e.g. USDC) on a chain network vs ISO 4217 `Money`; no FX allowed | unverified | same currency (ISO 4217) | HBAR or HTS token vs ISO 4217; no FX allowed |
| Fee / latency / min charge | network + facilitator fee, seconds; unmeasured | unmeasured | zero marginal | network fee small, finality seconds; unmeasured |
| MCP error semantics | HTTP 402 challenge; MCP transport needs a binding-aware client to surface it | 402-based; same | existing 422 codes (`budget-exhausted`, `payment-denied`) | tool-level errors from Payments MCP; unverified |
| Streaming / long-running | rejected for first proof | rejected | rejected | rejected |
| Generic client | requires x402-aware buyer | requires MPP-aware buyer | any MCP client | requires Hedera-aware agent |
| Secrets / KYC | merchant receive address; facilitator account; possible KYC/geo for fiat off-ramp | merchant onboarding with provider; unverified | invoicing only | Hedera account for MCTL as recipient; operator key custody for any MCTL-run account |
| Ledger mapping | cannot satisfy `requiredFeatures` honestly; would need a prepaid/settle-first shape the ledger does not have | unknown until pinned | maps 1:1 onto existing entitlements / budget | allowance-as-cap does not map to per-invocation `Authorize`/`Void` |

Adapter capability classification (encoded in Artifact B):

| Profile | Features declared | `checkAdapter` |
|---|---|---|
| `x402-exact` | `status_lookup` | refused (no `auth_capture`, no `void`, no `simulated`) |
| `mpp` | `status_lookup` (only what is verified) | refused |
| `hedera-allowance` | `status_lookup`, `async_settlement` | refused |
| `account-funded` | `auth_capture`, `void`, `status_lookup`, `refund`, `simulation` | accepted, but it is an internal ledger mode, not an external rail |

Non-custodial verdict: x402 and MPP -- MCTL can stay non-custodial (buyer
signs; MCTL only receives). Hedera -- non-custodial only if the spender key
lives in the agent runtime/owner wallet, never in mctl-api; any MCTL-run
spender account is custody and is rejected. Account-funded -- no keys.

Ambiguity/no-double-charge: for every external rail the only safe retry is
`Status` on a reference MCTL recorded *before* the external call. Today
`Authorize` runs inside the DB transaction (fact 3), so the external
reference cannot be durably recorded before the network call and a crash
between rail settle and commit loses it. Retries therefore cannot be proven
single-charge for any external rail on the current contract. This is the
main structural reason for deferral.

### External receipt / reconciliation envelope (recommended, not built)

Rail-independent fields any future adapter must persist (new table, later
proposal), keyed by `invocation_id`:

- `invocation_id`, `quote_digest`, `payment_op_key` (`mctl-pay/v1:…`)
- `principal_id`, `subject_principal_id`, `delegation_grant_id`,
  `tenant_id`, `payer_account_id`
- `rail` (`simulated|x402|mpp|hedera|account_funded`), `rail_version`,
  `network`, `facilitator_id`
- accounting money: `accounting_currency`, `authorized_minor`,
  `captured_minor` (ISO 4217, from `Money`)
- settlement money: `settlement_asset` (asset id, not ISO 4217),
  `settlement_asset_decimals`, `settlement_authorized_units`,
  `settlement_settled_units` -- never derived from accounting money; no FX
  rate field exists until a separate FX design
- `external_payment_ref` (tx hash / tx id / provider id), stored but never
  exposed on the tenant receipt (fact 7 allowlist stays)
- `payment_status` (existing vocabulary), `execution_status`
  (`execution_outcome`), `reconciliation_status`
  (`not_required|pending|matched|mismatch|unresolved`)
- `recorded_intent_at`, `external_observed_at`, `reconciled_at`

### Recommendation: `DEFER_EXTERNAL_PAYMENT`

Reasons, each grounded above: (a) no external rail satisfies
`requiredFeatures` without faking `auth_capture`/`void`; (b) `Authorize`
inside the ledger transaction cannot record an external reference before an
external call, so single-charge under retry is unprovable; (c) `Money` has no
settlement-asset concept and FX is a non-goal; (d) #616/#617 has no observed
live testnet proof; (e) account-funded is not an external rail and its
non-stored-value form already exists as entitlements (#614); adopting a
funded balance is stored value, which the issue does not authorize.

Re-entry criteria (all required before an `ADOPT_*` proposal):

1. mctl-api#616 passes its own live testnet acceptance (for x402), or an
   equivalent pinned testnet run for the candidate rail.
2. An approved design for an out-of-transaction adapter call: commit an
   intent row with the external idempotency reference first, call the rail,
   then record the result in a second transaction; `Status` on the intent
   resolves every crash window.
3. The envelope above exists with settlement money separate from `Money`.
4. A settle-first lifecycle is modelled explicitly (e.g. a new declared
   feature such as `settle_on_authorize` with refund-only compensation) via
   an ADR 020 amendment, rather than relaxing `requiredFeatures`.

First candidate on re-entry: x402 `exact` on a testnet, restricted to
`per_call` terms with no execution-dependent capture, because its evidence
track (#616) is furthest along. That is a later, separately reviewed scope.

### Artifact B: `internal/commerce/rail_profiles_test.go`

A table-driven test in package `commerce` declaring the four `AdapterInfo`
profiles above and asserting `checkAdapter` refuses the three external ones
with `ErrAdapterIneligible` and names the first missing required feature,
and accepts `account-funded`. It changes no production code and pins the
classification so a future relaxation of `requiredFeatures` breaks a test
that points at the decision record.

## Alternatives

- **`ADOPT_X402`**: furthest evidence track, non-custodial buyer signing.
  Dropped: `exact` has no hold/void, so it either fails `checkAdapter` or
  requires faking `auth_capture`; settle-before-execution conflicts with
  `per_successful_call`; #617 has no live proof in this clone.
- **`MULTI_RAIL_FOUNDATION`** (build the envelope, out-of-transaction call
  and settle-first feature now): the right eventual shape, but it builds
  money-moving infrastructure with no rail proven to need its exact shape;
  kept as re-entry criteria 2-4 instead.
- **`ADOPT_ACCOUNT_FUNDED`**: cleanest fit (already accepted by
  `checkAdapter` semantics, no keys). Dropped: it is not an external payment
  rail, its invoice-backed unit form already exists (#614), and a funded
  monetary balance is a stored-value product the issue does not authorize.
- **`ADOPT_HEDERA` / `ADOPT_MPP`**: allowance model is attractive for owner
  control and revocation, but neither maps to per-invocation
  authorize/void, versions are unpinned, and Hedera non-custody depends on
  where the spender key runs.

## Platform impact

- Migrations: none. Backward compatibility: unaffected; no route, MCP tool,
  env var or table changes, so the MCP tool count in
  `internal/mcp/server_test.go` is unchanged.
- Resources: none at runtime. The new test uses no database
  (`checkAdapter` is pure), so it runs without `TEST_DATABASE_URL`.
- Risks: (1) external protocol facts in the record go stale or are wrong --
  mitigated by version pinning, "not pinned" markers, and a dated
  "evaluated as of" header; (2) the record is read as authorization to
  build a rail -- mitigated by the explicit `DEFER_EXTERNAL_PAYMENT`
  verdict and re-entry criteria; (3) #617 lands with a different conclusion
  -- the record has an evidence section to update, the verdict holds until
  criteria 2-4 are met.
