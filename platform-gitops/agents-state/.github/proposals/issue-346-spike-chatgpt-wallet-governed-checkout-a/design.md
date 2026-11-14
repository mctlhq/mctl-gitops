# Design: issue-346-spike-chatgpt-wallet-governed-checkout-a

## Current state

`mctlhq/.github` is the roadmap and research home. This spike produces documentation only, and it
follows the existing spike conventions.

- `AGENTS.md` has a "Spikes" index with one bullet per report, and an "Active plans" list. The
  list includes `docs/plans/agent-commerce.md`.
- `roadmap/spikes/*.yaml` hold the `SpikeDefinition` manifests, for example
  `journey-intent-correlation.yaml` (`lifecycle: proposed`, verdict only in the report) and
  `finance-assistant.yaml` (`decided` by the owner, with a `decision` block). The schema is
  `roadmap/schemas/spike-definition.schema.json`. The rules are in `roadmap/README.md`
  ("SpikeDefinition v1alpha1"):
  - outcomes are UPPER_SNAKE values;
  - `decision` is allowed only when `lifecycle: decided`;
  - a spike issue may not be an epic root;
  - `spec.epic` is required only if the issue is bound as an epic work item.

  Validation runs through `roadmap/scripts/validate.py` and `roadmap/tests/test_validate_spike.py`,
  and CI enforces it in `.github/workflows/roadmap-validate.yml`.
- Report style precedent: `docs/spikes/finance-assistant.md`. It has a D0 non-claims section,
  evidence tags (`[CODE] [CONFIG] [LIVE] [DOC] [PRIMARY] [MODEL]`), an L0 to L4 evidence ladder,
  40-hex evidence pins, and `unknown (not observed)` never read as absent.
- Commerce baseline in this repo:
  - `roadmap/epics/agent-commerce.yaml` has `lifecycle: completed`. Its required items are C1 #546,
    C2 #547, C3 #548, C4 mctl-agents#619 and C5 mctl-agents#620. Its optional items are #631, the
    x402 pilot #616, `payment-interop` #549, and an unbound `governed-external-payment-proof`.
  - `docs/plans/agent-commerce.md` defines the execution order: identity, authz, policy, quote,
    `aar_` approval, revalidate, reserve, authorize, dispatch, capture or release. It also defines
    the failure and charging contract (`outcome_unknown`, no blind re-execution) and the
    `PaymentAuthorizer` authorize/capture/void/status contract. Its protocol table already names
    AP2 mandates and Stripe MPP/SPT. Its non-goals include a "wallet product" and card storage.
  - `docs/plans/agent-commerce-payment-rails.md` scopes #549 to a rail comparison (enterprise,
    account-funded, autonomous wallet). Its non-goals include card storage and PCI-sensitive data,
    and it states that "payment proof is never an authorization grant".
- Related spikes: `docs/spikes/journey-intent-correlation.md` proposes reusing `work_item_id` as the
  journey key, and `docs/spikes/agent-governance-decision-assurance.md` covers #181. The #308 Web
  Bot Auth spike exists as an agents-state proposal; it has no report in this repo yet.

Deployed state checked:

- `mctl_whoami`: `agent:issue-investigator`, not admin, no teams, no namespaces.
- `mctl_get_commerce_budget(tenant=labs)`: HTTP 403 `agent_scope_denied` ("outside the investigate
  scope of this agent run"). The live Commerce budget and `funds_mode` were NOT observed. This is
  not evidence that Commerce is absent or disabled.
- `mctl_get_service_config(labs, mctl-telegram)`: image `0.138.1`, host `tg.mctl.ai`, port 8080,
  has a database. This is the Assistant Catalog and Managed Runtime surface. No payment config was
  observed there.
- `$MCTL_GITOPS_ROOT/tenants/commerce-proof/values.yaml`: an isolated tenant for the C5 proof,
  "simulated funds only, EUR 1.00 budget, no workloads", with owner `mashkovd`. This is config,
  not runtime.
- `$MCTL_GITOPS_ROOT/services/labs/payment-llm-pipelines/values.yaml`: an unrelated base-service
  (image `0.1.0-r2`). It is not a payment rail, and the spike must not cite it as one.
- `grep -i commerce|payment|wallet|stripe` over the mctl-telegram and mctl-agents-worker values
  returned no hits.
- Proposal-reported state from agents-state, not verified against GitHub:
  - mctl-api #549 is `proposed` (2026-10-25). Its design describes `internal/commerce` with
    `PaymentAuthorizer` implemented only by `SimulatedAuthorizer`, and `checkAdapter` requiring
    `auth_capture`, `void` and `status_lookup`. It refuses `funds_mode: live`.
  - #569 (commerce receipt read plus MCP tools) is `merged`, PR #573.
  - #570 (accept-only kill switch) was implemented by hand in mctl-api#580.
  - #989 (Glovo single authoritative `aar_` approval with basket fingerprint) is `accepted`.
  - #1004 (wiring the Glovo approval ledger behind the closed gate) is `proposed`. It states that
    the gates `glovoWriteFenceHoldLifted` and `glovo.ControlDefault.Open` are const false.
  - The `_mentor/digest/2026-W46.md` digest lists the Glovo M1 canary as dark-launched behind
    holds.
- Not read: GitHub issue or PR state for #1012, #1002, #1088, #546, #548 and #181, and every
  OpenAI page named in the issue. These are recorded under Open questions in requirements.md.

## Proposed solution

Add one research package to `mctlhq/.github` with three file changes and no runtime change.

1. `docs/spikes/chatgpt-wallet-agentic-checkout.md`, structured on the finance-assistant report.
   - D0, non-claims and evidence tags: the same tag set and L0 to L4 ladder. This spike reaches L0
     (pinned sources) and L1 (synthetic table-top traces) only. L2 to L4 are `not-run`.
   - Evidence pins: 40-hex `main` heads for .github, mctl-api, mctl-agents, mctl-telegram and
     mctl-gitops, read on the run date.
   - D1, baseline and dedup map. Each row has a feature, a status
     (`implemented | feature-flagged | proposed | unavailable | unknown`), a source, and what the
     checkout use case can reuse. Rows:
     - ADR 020 ledger phases;
     - `PaymentAuthorizer` and `checkAdapter`;
     - `funds_mode`;
     - receipt read (#569);
     - kill switch (#570);
     - `aar_` single-use approval (#366 and #989 bindings);
     - Glovo exact basket fingerprint and receipt lifecycle (#989, #1004, #1012);
     - WorkItem and `work_item_id` correlation;
     - decision assurance (#181);
     - Web Bot Auth operator identity (#308);
     - Assistant Catalog and Managed Runtime surfaces.

     A separate table, "covered by #549, not decided here", lists rail selection, custody,
     settlement, the external receipt envelope and fee constraints.
   - D2, vendor facts matrix. Columns: fact, source URL, access date, version or date, tag
     (`documented | tested | proposed | unknown`). Rows:
     - Wallet eligibility (US, Pro, adult);
     - approval security check;
     - substitute network credentials;
     - bounded mandates (future);
     - a third-party developer API (expected `unknown` or `unsupported`);
     - Commerce Partner Playbook integration surfaces;
     - MCP or browser handoff and `continue_url`;
     - Web Bot Auth;
     - PSP risk and SCA;
     - PCI scope of substitute credentials.
   - D3, option comparison. Options A to D are scored on one shared set of criteria: authority,
     identity, budget, approval, merchant confirmation, idempotency, privacy and cost. Each option
     lists its failure reasons. Distinction kept explicit:
     - A is the human paying at the merchant, with MCTL reconciling the confirmed order only;
     - B adds a rail-neutral Payment Intent and Consent artifact;
     - C changes no MCTL abstraction.
   - D4, an actor and sequence diagram (ASCII), plus three field tables. Each field maps to an
     existing artifact, or is marked `DELTA`:
     - **Checkout Intent / Payment Intent**: `work_item_id`, the commerce `invocation_id` and
       `quote_digest`, canonical `principal_id`, `tenant`, `agent`, `merchant` (payee identity and
       origin), line items, quantity, subtotal, tax, shipping, `max_total_minor`, `currency`,
       fulfillment constraints, `expires_at`, `purpose`.
     - **Consent**: an `aar_` approval with action kind and version, `intent_digest` (the Glovo
       basket fingerprint pattern), single use, decider, decided at, revocation reference.
     - **Merchant-confirmation evidence**: merchant order reference (a hash, not raw PII), the
       evidence source (merchant API, signed receipt or user attestation), observed total and
       currency, PSP payment state as a separate field, `observed_at`, verification method, and a
       redaction rule. No credential or token fields, by design.

     State diagram: `prepared -> approved -> submitted -> merchant_confirmed | declined | unknown`,
     with `unknown -> reconciling -> merchant_confirmed | declined | manual_review`. Finance states
     (PSP authorized, captured, settled, refunded, disputed) are a separate column that is never
     merged with order state. The report states which existing ledger phase each order state maps
     to. The working assumption is evidence attached to `finalized` or `outcome_unknown`, with no
     new phase.
   - D5, threat and failure matrix. Each row has the case, the detection signal, the required
     outcome, and the existing control or `DELTA`. It covers every case listed in the requirements.
     Five or more synthetic table-top traces cover: changed basket, lost merchant receipt after the
     handoff, duplicate submit under concurrency, a fraud decline after approval, and a refund after
     a confirmed order. "No blind retry" and "fail closed on unverifiable merchant state" are
     explicit outcomes.
   - Section 6, eligibility, security and compliance: region and PSP onboarding, PCI exposure,
     PSD2 SCA versus US rules, consumer protection, permitted categories, data minimization,
     retention. Unverified cells say `unsupported`.
   - D6, an ownership map:
     - mctl-api Commerce: ledger and approval evidence fields;
     - mctl-agents: governed runtime and refusal of a generic "approve and pay" tool;
     - mctl-telegram and assistants: the handoff UX;
     - merchant or provider integrations: the Glovo bridge;
     - mctl-docs: user-facing docs.

     It names one smallest next step, for example "document the checkout-handoff evidence envelope
     as an ADR 020 amendment, owned by mctl-api, with no code", or an explicit DEFER with a re-entry
     trigger such as "a documented third-party Wallet or mandate API, plus a #549 verdict other than
     DEFER". It states that a pilot needs a separate approval.
   - Falsifiable assertions: each assertion is paired with its refuting evidence. Example: "No
     ChatGPT Wallet surface lets a third party initiate a payment on behalf of a user", refuted by a
     documented developer API.
   - Proposed verdict: one token, explicitly not decided.
2. `roadmap/spikes/chatgpt-wallet-agentic-checkout.yaml` with these fields:
   - `metadata.name: chatgpt-wallet-agentic-checkout` and `owner: mctlhq/.github`;
   - `title` and `question` taken from the issue;
   - `lifecycle: proposed`;
   - `github.issue: mctlhq/.github#346`;
   - the five outcomes;
   - `execution.devloop: true`;
   - `evidence.report` set to the report path.

   It has no `spec.epic`, because #346 is a logical child of #173 and not a work item, and no
   `decision`. A header comment states that the proposed verdict lives only in the report.
3. `AGENTS.md`: one "Spikes" bullet linking the report, "spike report for mctlhq/.github#346,
   proposed verdict <TOKEN>".

Why this shape: it reuses the repository's spike pipeline unchanged. It keeps rail decisions in
#549, and it anchors any checkout delta on contracts that already exist or are already in flight
(ADR 020 ledger, `aar_` with basket fingerprint, `work_item_id`). The result is a delta list, not a
new service or a second ledger.

## Alternatives

- **Add a synthetic reference model (Python or Go) under `docs/spikes/chatgpt-wallet-agentic-checkout/`,**
  as finance-assistant and mcp-gateway-g0 did. Dropped for now. The issue asks for table-top traces
  and a field table, and an executable state machine would look like an implementation of a
  contract the owner has not chosen. It can follow if the owner picks B.
- **Add the spike as an optional work item in `roadmap/epics/agent-commerce.yaml`.** Rejected. The
  issue says this is not a new required child and that the closed epic manifest and lifecycle must
  not change. A spike-only manifest also satisfies the cross-kind rules.
- **Fold the analysis into #549's decision record.** Rejected. The issue explicitly separates
  checkout, consent and order evidence from rail selection, and #549 has its own owner and outcome
  set.

## Platform impact

- Migrations: none. Backward compatibility: there is no runtime or API surface. The manifest adds
  one new spike name and one new issue binding, and the validator checks that both are unique.
- Resource impact: none. No service, tenant, flag or GitOps value changes.
- Risks and mitigations:
  - Vendor facts may be stale or unverifiable. Mitigation: every fact is URL- and date-pinned, and
    unread facts are tagged `unknown`. The verdict must not depend on any `unknown` cell being
    favourable.
  - Duplicating or contradicting #549. Mitigation: a dedicated "covered by #549" table, no rail
    scoring, and a cross-link to #549.
  - The report could be read as authorizing payments. Mitigation: D0 non-claims, a proposed-only
    verdict, no `decision` block, and `Refs #346` without a closing keyword.
  - Sensitive data. Mitigation: synthetic traces only. Fixture card-like strings, if any, must fail
    the Luhn check, as finance-assistant did with IBAN mod-97.
  - Glovo and agents-state status could be misreported. Mitigation: every row is re-read from GitHub
    at the run date, and agents-state-only rows are labelled proposal-reported.
