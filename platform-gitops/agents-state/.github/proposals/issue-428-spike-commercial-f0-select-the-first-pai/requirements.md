# Spike F0: select the first paid MCTL offer and validate demand (research only)

## Context
mctlhq/.github#428 is the F0 spike under the Commercialization & First Revenue parent (#427). It asks for an evidence-backed comparison of candidate first paid offers: Academy, managed MCP/hosting, Telegram MCP, a fixed-scope MCP diagnostic/audit, a manual paid MCP compatibility report, and the 2026-11-27 expansion: an automated diagnostic pack, a paid MCP Assurance report or monitoring, a one-time MCP App export, and a managed MCP App overlay (#430). The output is a ranked matrix, exactly ONE proposed SKU, a price hypothesis, a scope and refund policy, a cost ceiling and a GO / PIVOT / STOP recommendation. Everything is research. Publishing prices, contacting prospects, charging money and building anything each need a separate owner decision.

It matters because it is the P0 business priority, and the platform has been built (agent commerce foundation, x402 testnet pilot #616, Telegram MCP Apps, Academy) without a validated revenue path. The spike follows the existing spike convention in this repo: a report in `docs/spikes/`, a `SpikeDefinition` manifest in `roadmap/spikes/`, and an entry in `AGENTS.md`. That convention is how `docs/spikes/finance-assistant.md` and `roadmap/spikes/finance-assistant.yaml` were done.

## User stories
- AS the platform owner I WANT a ranked, evidence-tagged matrix of candidate first offers SO THAT I can choose one SKU to build on facts rather than intuition.
- AS the platform owner I WANT one proposed SKU with price hypothesis, scope, refund policy and cost ceiling SO THAT a later build or sell decision has bounded risk.
- AS the platform owner I WANT a protocol for 5 voluntary, owner-run customer conversations with anonymized recording SO THAT willingness to pay is checked without automated outreach or private data collection.
- AS a reviewer I WANT every claim about competitors, readiness and cost tagged with its source and access date SO THAT unknowns are never read as favorable.

## Acceptance criteria (EARS)
- WHEN the spike PR is opened THE SYSTEM SHALL add `docs/spikes/commercial-f0-first-offer.md`, `roadmap/spikes/commercial-f0-first-offer.yaml` and a one-entry `AGENTS.md` "Spikes" line, and nothing else outside `docs/spikes/commercial-f0-first-offer/` (optional fixtures or a stdlib scoring model).
- WHEN `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` runs THE SYSTEM SHALL accept the new manifest with `kind: SpikeDefinition`, `lifecycle: proposed`, `github.issue` set to mctlhq/.github#428, and outcomes `GO`, `PIVOT` and `STOP`.
- THE SYSTEM SHALL compare at least these candidates in one matrix: Academy; managed MCP/hosting; Telegram MCP (paid tier); fixed-scope MCP diagnostic/audit; manual paid MCP compatibility report; automated diagnostic pack; MCP Assurance report or monitoring; one-time MCP App export; managed MCP App overlay (#430).
- THE SYSTEM SHALL score each candidate on these columns: actual readiness, licenses/terms, customer value, time to first fulfillment, incremental infra/LLM/support cost, expected contribution margin, distribution channel, blockers. Each cell SHALL carry an evidence tag (`[CODE]`, `[CONFIG]`, `[LIVE]`, `[DOC]`, `[PRIMARY]` with access date, `[MODEL]`) or `unknown (not observed)`.
- THE SYSTEM SHALL list the competitors named in the issue (MCPJam, CheckMCP, MCPTest.io, MCPComp, MCPServerStatus, Supercompatible, AgentStatus, Agent Check, x402 Doctor, the official ext-apps add-app-to-server skill, MCPG) with offering, published fee, license and access date. Any entry it could not fetch from a primary source SHALL be `unknown (not observed)`.
- THE SYSTEM SHALL treat basic connectivity, `initialize` and `tools/list` checks as commoditized. It SHALL NOT claim competitive uniqueness or customer demand.
- THE SYSTEM SHALL reuse the #349 acquisition baseline (`roadmap/epics/organic-discovery-growth.yaml`) and the mctl-telegram#1379 meetup interviews as inputs by reference only, and SHALL NOT duplicate their technical work.
- THE SYSTEM SHALL propose exactly ONE first SKU, with a price hypothesis in the range the issue gives ($9-29 per export, $9-29/month overlay, $19/month assurance, or a justified alternative), a written scope, a refund policy, a per-sale and per-month cost ceiling, and a GO, PIVOT or STOP recommendation.
- THE SYSTEM SHALL include a conversation protocol for 5 qualified voluntary conversations: a screening rubric, a question script, an anonymized record template (segment, current workaround, willingness-to-pay band, objections), and a consent statement. The records SHALL be left empty or marked `not-run` until the owner runs the conversations.
- WHILE the spike is `lifecycle: proposed` THE SYSTEM SHALL record no decision: the verdict is "proposed", and owner approval is a separate step.
- IF a candidate depends on #429 eligibility, the #1197 marketplace gates or a merchant of record THEN THE SYSTEM SHALL list that gate as a blocker and SHALL NOT assume it is satisfied. Manual consultancy through a merchant of record is excluded unless the owner approves it.
- IF a live competitor reverification or a bounded comparison run would need to happen THEN THE SYSTEM SHALL defer it until after an owner GO and record it as a follow-up.

## Out of scope
- Publishing pricing, landing pages or checkout.
- Contacting any prospect, sending automated outreach, or collecting personal data.
- Charging money, merchant-of-record onboarding, mainnet funds or payouts.
- Product code, agent intake (`agents:intake`), DevLoop implementation, paid API or LLM calls, and any change to production or gitops.
- Changes to the #616 x402 testnet pilot, which stays testnet commerce proof.
- Building more than one SKU.

## Open questions
- Is #427 meant to get its own `EpicDefinition` with F0 as a work item? Assumption: no. The manifest is a standalone `SpikeDefinition` without `spec.epic`, and binding it can come later.
- The data from mctl-telegram#1379 (meetup interviews) and from the #349 baseline could not be read from this clone. The report cites them by reference and marks their figures `unknown (not observed)` until someone reads them.
- Merchant-of-record and tax setup (who invoices, which jurisdiction) is not stated anywhere. Every candidate gets it as a blocker.
- Competitor pricing and licenses were not fetched in this investigation. The issue says to reverify them only after GO. The report's competitor table is therefore L0, documentation-level only.
- The Academy license and terms, and whether course content can be sold, are not visible in this repo.
