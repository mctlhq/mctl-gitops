# Spike: ChatGPT Wallet, governed merchant checkout and delegated spending for MCTL

## Context

Issue mctlhq/.github#346 is a P2, discovery-only spike. It asks whether MCTL can support
agent-initiated merchant checkout with a human approval bound to one transaction, and later a
bounded delegated-spend policy. MCTL identity, tenant policy, budget, approval, execution and
audit must stay the only authority. MCTL must not become a card wallet, hold payment credentials
or money, or create a second authorization plane. The external signal is OpenAI's ChatGPT Wallet
announcement, dated 2026-11-13 in the issue. As the issue describes it, eligible US Pro adults
approve a purchase with a security check, and the merchant receives network-provided substitute
credentials. Bounded purchase mandates are only discussed as future work. There is no announced
third-party MCTL wallet API.

The deliverable is research only. It is a report at `docs/spikes/chatgpt-wallet-agentic-checkout.md`
with deliverables D1 to D7 from the issue, a `SpikeDefinition` manifest at
`roadmap/spikes/chatgpt-wallet-agentic-checkout.yaml` with `lifecycle: proposed`, and an index
entry in `AGENTS.md`. The report proposes exactly one verdict from
`REUSE_CHECKOUT_HANDOFF | EXTEND_GOVERNED_PAYMENT_INTENT | MERCHANT_INTEGRATION_ONLY | DEFER | REJECT`.
Only the owner records the decision. This matters for three reasons. A real checkout adds a
merchant, a PSP and an order lifecycle that the simulated-credit Commerce foundation (#173, closed)
never had to model. Rail selection already belongs to mctl-api#549 and must not be duplicated.
The Glovo real-cart work (mctl-api#1012 and the M1 `aar_` approval slices) is already building one
concrete checkout surface, so this spike should reuse its contracts instead of inventing new ones.

## User stories

- AS the platform owner I WANT a source-pinned comparison of checkout handoff, governed Payment
  Intent and merchant-integration-only options, scored on the same criteria, SO THAT I can record
  one verdict without approving any payment execution.
- AS an mctl-api Commerce maintainer I WANT a mapping of checkout states onto the existing ledger
  phases, the `PaymentAuthorizer` contract and the `aar_` action approval SO THAT any later delta
  extends ADR 020 commerce instead of adding a parallel payment ledger or wallet service.
- AS a security reviewer I WANT a threat and failure matrix covering replay, changed baskets,
  ambiguous payments, lost receipts and no-blind-retry outcomes SO THAT a later pilot cannot charge
  twice or treat browser completion as a confirmed order.
- AS the mctl-api#549 owner I WANT this spike to consume my rail evidence without re-deciding it
  SO THAT the two spikes do not reach conflicting conclusions.
- AS an Assistant Catalog or Glovo surface owner I WANT ownership of each proposed delta assigned to
  an existing repository SO THAT no surface derives a runtime permission from a PSP success.

## Acceptance criteria (EARS)

Deliverables and placement

- WHEN the research PR is opened THE SYSTEM SHALL add exactly
  `docs/spikes/chatgpt-wallet-agentic-checkout.md`,
  `roadmap/spikes/chatgpt-wallet-agentic-checkout.yaml` and one `AGENTS.md` "Spikes" index entry, and
  no other file.
- WHEN the manifest is added THE SYSTEM SHALL bind it to `mctlhq/.github#346`, list the five
  outcomes of the issue verbatim, set `lifecycle: proposed`, set `execution.devloop: true`, set
  `evidence.report` to the report path, omit `decision` and `spec.epic`, and pass
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes`.
- THE SYSTEM SHALL state exactly one proposed verdict in the report, labelled as proposed and not
  decided, and SHALL NOT write a `decision` block or change any epic manifest, including
  `roadmap/epics/agent-commerce.yaml`.

D1 baseline and dedup

- WHEN the report describes an existing MCTL contract THE SYSTEM SHALL tag it
  `implemented | feature-flagged | proposed | unavailable | unknown` and cite an issue, PR, commit or
  file path for it. At minimum this covers #173 C1 to C5, mctl-api#546, #548, #549, #569, #570,
  .github#181, .github#308, mctl-api#1012 and the Glovo M1 approval slices (#989, #1004),
  mctl-telegram#1002 and #1088.
- THE SYSTEM SHALL include a "what #549 already covers" table and SHALL NOT compare or decide
  between x402, MPP, account-funded or Hedera rails.
- IF a status was read only from an agents-state `.status.yaml` or a proposal, THEN THE SYSTEM SHALL
  label it as proposal-reported and not as verified code.
- THE SYSTEM SHALL NOT claim that simulated credits or the `commerce-proof` tenant prove production
  payments.

D2 vendor facts

- WHEN the report states a vendor fact (ChatGPT Wallet eligibility, region, developer surface,
  bounded mandates, the Commerce Partner Playbook, Web Bot Auth, MCP or browser checkout, PSP
  constraints) THE SYSTEM SHALL tag it `documented | tested | proposed | unknown` with a URL and an
  access date.
- IF a vendor page cannot be fetched or does not state the fact, THEN THE SYSTEM SHALL record
  `unknown` or `unsupported`, and SHALL NOT fill the cell from memory or from the issue text alone.
- THE SYSTEM SHALL keep "merchant compatibility with ChatGPT Wallet" and "a hypothetical MCTL
  wallet API" as separate rows.

D3 option comparison

- THE SYSTEM SHALL score options A (REUSE_CHECKOUT_HANDOFF), B (EXTEND_GOVERNED_PAYMENT_INTENT),
  C (MERCHANT_INTEGRATION_ONLY) and D (DEFER/REJECT) against one shared set of criteria: authority,
  identity, budget, approval, merchant confirmation, idempotency, privacy and cost. It SHALL list
  the failure reasons of each option.

D4 sequence and schema

- THE SYSTEM SHALL provide an actor and sequence diagram (principal, agent, MCTL governed runtime,
  mctl-api Commerce and approvals, merchant, PSP or wallet), and field tables for a bounded Payment
  Intent, a Consent and a merchant-confirmation evidence envelope.
- THE SYSTEM SHALL map every new field to an existing ADR 020 commerce, `aar_` approval or
  WorkItem field where one exists, and SHALL mark a field as a delta only where none exists.
- WHILE defining the consent digest THE SYSTEM SHALL bind canonical principal, tenant, agent,
  merchant or payee identity, line items and quantity, total and maximum including tax and
  shipping, currency, fulfillment constraints, expiry, purpose, approval kind and version,
  single-use flag, limits and revocation.
- IF the price, merchant, address, basket or currency drifts after approval, THEN THE SYSTEM SHALL
  require a new approval and SHALL NOT reuse the consumed one.
- THE SYSTEM SHALL keep MCTL policy, budget and approval, PSP authorization, settlement,
  refund or dispute, and merchant order or fulfillment as separate states. The state diagram SHALL
  include at least prepared, approved, submitted, merchant-confirmed, declined and unknown, plus
  reconciliation, and SHALL NOT treat browser completion or a payment token as order confirmation.

D5 threats and failures

- THE SYSTEM SHALL include a threat and failure matrix covering denial, replay, TTL expiry,
  concurrent requests, idempotency, changed basket, prompt-injected product data, redirect or
  phishing, merchant spoofing, partial inventory, cross-tenant leakage, duplicate charge, fraud
  decline, ambiguous payment, lost merchant receipt, network partition, cancellation, refund or
  dispute, and non-confirmation by the merchant.
- IF an action may already have charged, THEN the documented outcome SHALL be reconcile and SHALL
  NOT be a retry. IF merchant state cannot be verified, THEN the documented outcome SHALL fail closed.
- THE SYSTEM SHALL use synthetic table-top traces only, and SHALL NOT run a live payment, merchant
  call, PSP sandbox enrolment or wallet enrolment.

D6 and D7 ownership and next step

- THE SYSTEM SHALL assign every proposed delta to an existing owner: mctl-api Commerce and
  approvals, the mctl-agents governed runtime, mctl-telegram or assistant surfaces,
  merchant or provider integrations, or mctl-docs. It SHALL NOT propose a new Wallet service.
- THE SYSTEM SHALL name one smallest next step, or an explicit defer with a re-entry trigger, and
  SHALL state that any pilot needs a separate owner-approved issue, an independent security review
  and PSP or merchant eligibility verification.
- THE SYSTEM SHALL state falsifiable assertions, each with the evidence that would refute it.

Governance

- WHILE this spike is open THE SYSTEM SHALL NOT store, log or transmit PAN, network tokens,
  substitute credentials or payment proofs, and SHALL NOT treat a payment token or PSP success as an
  authorization grant.
- WHEN the research PR is opened THE SYSTEM SHALL reference #346 without a closing keyword.

## Out of scope

- Any code, migration, API route, MCP tool, flag or GitOps change in mctl-api, mctl-agents,
  mctl-telegram, mctl-gitops or mctl-docs.
- Choosing a payment rail, or any change to mctl-api#549's comparison or decision.
- Real money, card or network-token handling, stored value, payouts, merchant onboarding, PSP
  account creation, ChatGPT Wallet enrolment, merchant pilots, live payment or merchant tests.
- Autonomous or pre-approved delegated spending. Bounded mandates are analysed as research only.
- Changes to the closed Agent Commerce epic manifest, its lifecycle, or to Glovo,
  Assistant Catalog or Managed Runtime rollout gates.
- Recording the owner verdict, approving or accepting this proposal, or closing #346.

## Open questions

- Vendor facts are not verified. This proposal could not read the OpenAI announcement, the
  release notes, the Wallet terms or the Commerce Partner Playbook. The 2026-11-13 date and every
  capability claim come from the issue text only. The spike run must fetch them and mark any it
  cannot read `unknown`.
- Deployed Commerce state was not observed. `mctl_get_commerce_budget` for tenant `labs` was
  refused with 403 `agent_scope_denied` for this agent run, so the live `funds_mode` and budget
  state is unknown. The report must rely on code or proposal citations, or on a run that has read
  scope.
- The real status of mctl-api#1012, #989 and #1004 was not read from GitHub. Only agents-state
  shows #989 `accepted` and #1004 `proposed`, and #1004 says #989 and #985 are merged but dark. The
  spike must re-read issue and PR state before it tags D1 rows.
- #549 is still `proposed` in agents-state (2026-10-25). If its verdict is
  `DEFER_EXTERNAL_PAYMENT`, option B has no rail to attach to. The report should then say whether B
  can still be designed rail-neutrally or must collapse into DEFER.
- Should "merchant-confirmed order" be a new commerce ledger phase, or an evidence record attached
  to the existing `finalized` or `outcome_unknown` phases? The working assumption is an evidence
  record, so the ledger phase machine is unchanged. The report must justify any deviation.
- Leading hypothesis (falsifiable, not a verdict): REUSE_CHECKOUT_HANDOFF is the smallest safe
  step, because the Glovo real-cart work already provides an exact-basket `aar_` approval. Option B
  stays gated on #549. The report may reach a different verdict.
