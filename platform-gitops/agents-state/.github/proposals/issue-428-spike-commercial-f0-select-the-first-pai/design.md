# Design: issue-428-spike-commercial-f0-select-the-first-pai

## Current state
- Spike convention. Spikes in `mctlhq/.github` are a Markdown report in `docs/spikes/<name>.md`, an optional offline reference model in `docs/spikes/<name>/`, a `SpikeDefinition` manifest in `roadmap/spikes/<name>.yaml`, and an index line in `AGENTS.md` under "Spikes". The worked precedent is `docs/spikes/finance-assistant.md` with `roadmap/spikes/finance-assistant.yaml`. That report uses evidence tags (`[CODE]`, `[CONFIG]`, `[LIVE]`, `[DOC]`, `[PRIMARY]`, `[MODEL]`), an L0-L4 evidence ladder, an evidence-pin table and "unknown (not observed) is never absent". The manifest moves from `lifecycle: proposed` to `decided` with `decision.verdict`, `decidedBy` and `followUps` only after the owner decides.
- Schema. `roadmap/schemas/spike-definition.schema.json` requires `title`, `question`, `lifecycle`, `github.issue` and at least 2 `outcomes`, each matching `^[A-Z][A-Z0-9_]*$`. Optional fields are `epic`, `activation`, `timebox`, `evidence`, `execution` and `decision`. The `roadmap-validate.yml` workflow validates it with `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes`, and `roadmap/tests/test_validate_spike.py` covers it.
- Related plans. `docs/plans/agent-commerce.md` and `docs/plans/agent-commerce-payment-rails.md` cover the commerce foundation and the #616 isolated x402 MCP Check testnet pilot. The payment-rails plan explicitly forbids real money, merchant onboarding and payouts. `roadmap/epics/organic-discovery-growth.yaml` (#349) is the acquisition baseline. It is `lifecycle: proposed`, covers `academy.mctl.ai` and `tg.mctl.ai`, and its work items are unbound.
- No artifact for #427 or #428 exists in `roadmap/` or `docs/`. (`agent-commerce.yaml` references mctl-api#428, which is a different issue.)

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-academy/values.yaml`: image tag `0.1.101`, hosts `academy.mctl.ai` and `labs-mctl-academy.mctl.ai`, a database secret, and no payment or billing env keys. That is `[CONFIG]` only; the effective runtime was not observed.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: tag `b773df01`, `MCP_APPS_ENABLED: "true"`, `AGENT_ENABLED: "true"`, `ASSISTANT_REGISTRY_ENABLED: "true"`, and an OAuth implicit-host allowlist for the claude.ai, chatgpt.com, cursor.com and town.com hosts. grep found no billing or pricing keys. `[CONFIG]`.
- `$MCTL_GITOPS_ROOT/tenants/`: the tenant `commerce-proof` exists, which matches the testnet commerce proof. Its values were not read in depth.
- mctl MCP live tools were not called in this investigation. The live health of these services is unknown (not observed), and the report must record that gap.

## Proposed solution
A research-only PR in `mctlhq/.github`:

1. `docs/spikes/commercial-f0-first-offer.md` has these sections:
   - D0: non-claims, evidence tags and evidence ladder, reusing the finance-assistant wording.
   - D1: evidence pins (40-hex `main` heads of .github, mctl-telegram, mctl-academy, mctl-api and mctl-gitops at write time).
   - D2: the candidate inventory and readiness map. It covers the nine candidates in requirements.md, each with owner repo, actual state (`[CONFIG]`/`[CODE]`/`[DOC]`), and the gates it needs (#429, #1197, merchant of record, #616 kept testnet).
   - D3: the competitor table (the eleven named alternatives), with offering, fee, license and access date, or `unknown (not observed)`. Basic connectivity checks are recorded as commoditized and a candidate for a free tier.
   - D4: the ranked matrix with the eight columns from the issue, plus a weighted score. Weights favor low engineering effort and short time to first sale, as the issue directs. The weights and the arithmetic are explicit so the ranking can be reproduced.
   - D5: unit economics. Each candidate gets incremental infra, LLM and support cost per fulfillment and per month, a contribution margin at the hypothesized price, and a hard cost ceiling.
   - D6: the conversation protocol. It covers screening for 5 qualified voluntary conversations, a script, consent text, and an anonymized record template, with every record `not-run`. The protocol says plainly that the owner runs every conversation and nothing is sent automatically.
   - D7: the ONE proposed SKU, its price hypothesis, scope, refund policy, cost ceiling, the direct alternatives it competes with on total cost and time saved, and the GO / PIVOT / STOP criteria. The criteria are measurable, for example ">=2 of 5 state WTP at or above price; fulfillment cost <= ceiling".
   - D8: the proposed verdict and follow-ups, deferred until the owner decides: live competitor reverification, a bounded comparison run, and a separate pricing and outreach decision.

   Working hypothesis, which the matrix must confirm or reject: a fixed-scope manual or semi-automated "MCP Assurance report" for one server. It would check host-specific compatibility (Claude, ChatGPT, Cursor), OAuth flow, MCP Apps rendering, security evidence and a CI release-gate recommendation, at a one-time price in the $19-29 range, with a $19/month monitoring upsell evaluated later and not built. The reasons for that hypothesis: it reuses the existing OAuth host matrix and the MCP Apps capability seen in the mctl-telegram config, it needs the least new engineering, and it avoids competing on commoditized basic checks. The report may still rank another candidate first if the evidence points there.
2. `roadmap/spikes/commercial-f0-first-offer.yaml`: a `SpikeDefinition` with `owner: mctlhq/.github`, `lifecycle: proposed`, `github.issue` set to `{repository: mctlhq/.github, number: 428}`, `outcomes: [GO, PIVOT, STOP]`, `evidence.report` pointing at the report, and `execution.devloop` matching the precedent. It has no `decision` block.
3. Optional: `docs/spikes/commercial-f0-first-offer/score.py`, a stdlib-only script that recomputes the D4 ranking and D5 margins from a JSON fixture, with a test. This makes the ranking deterministic, the same way the finance-assistant model did.
4. `AGENTS.md`: one line under "Spikes".

## Alternatives
- A new `EpicDefinition` for #427 with F0 as a work item. Dropped for now: the issue is planning-only, and the epic graph is the owner's call. Binding later through `spec.epic` is cheap.
- A report only, with no manifest. Dropped: it breaks the repo convention and roadmap visibility, and `validate.py` would no longer track the spike's lifecycle.
- Several SKUs evaluated in parallel builds. Dropped: the issue explicitly asks for ONE first SKU and no simultaneous builds.

## Platform impact
- Documentation and manifest only. No migrations, no runtime or gitops change, no resource impact.
- Risk: the report could be read as a pricing commitment or a demand claim. Mitigation: a non-claims section, `lifecycle: proposed`, every conversation record `not-run`, and the owner-decision gates restated in D7 and D8.
- Risk: competitor facts become stale. Mitigation: access dates on every entry, `unknown` where a fact was not fetched, and a reverification step after GO.
- Risk: privacy. Mitigation: the template stores only anonymized aggregate fields, never names, emails or handles.
- Backward compatible. Existing manifests and tests are untouched.
