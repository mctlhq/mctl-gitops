# Spike: Finance Assistant, read-only personal finance intelligence for the Assistant Catalog (mctlhq/.github#325)

## Context

Issue mctlhq/.github#325 asks a P3 discovery question. Can MCTL offer a safe, useful,
tenant-isolated Finance Assistant inside the existing Telegram Assistant Catalog
(mctl-telegram#1002), starting with read-only analytics, without a parallel agent
runtime and without exposing financial data through conversation auto-replies? The
external trigger is Anthropic's Personal Finance in Claude beta (2026-11-05: US paid
plans, Plaid-linked read-only accounts). That is a product benchmark. It does not show
that MCTL works with any bank, and it gives no permission to process real customer data.

The deliverable is research only, in the shape of earlier spikes in this repo
(`docs/spikes/cve-advisory-impact/`, `docs/spikes/automation-control-plane/`):
- a report under `docs/spikes/`;
- a `SpikeDefinition` manifest under `roadmap/spikes/` with `lifecycle: proposed`;
- a stdlib-only, offline reference model with a synthetic fixture and reproducible tests;
- one proposed verdict from `REUSE_CATALOG_CSV_MVP | EXTEND_AFTER_CONNECTOR_GATES |
  RESEARCH_ONLY_DEFER | NO_ADOPTION`.

Only the owner selects the verdict. Nothing is built, deployed or approved.

## User stories

- AS the platform owner I WANT an evidence-backed decision record on a Finance Assistant SO THAT I can select one outcome without first building a finance runtime.
- AS a security reviewer I WANT an identity/consent/data-flow diagram, a threat model and runnable negative-control tests SO THAT I can verify the owner-only and no-leak claims independently.
- AS a future mctl-telegram implementer I WANT a deterministic normalization and calculation model with oracle values SO THAT money arithmetic is never delegated to an LLM.
- AS a tenant owner (future user) I WANT only me to see my financial answers, through a private destination I approved SO THAT no peer, group or other tenant can read or receive them.

## Acceptance criteria (EARS)

- WHEN the report is written THE SYSTEM SHALL tag every claim with its evidence class (`[CODE]` at a 40-hex pin, `[CONFIG]`, `[LIVE]`, `[DOC]`, `[PRIMARY]` for external primary sources, `[MODEL]` for reference-model results). Implemented, feature-flagged, proposed, missing and `unknown (not observed)` SHALL be separate states.
- WHEN the dedup/capability map is produced THE SYSTEM SHALL cover mctl-telegram#1002, #1048, #1088, #1046, mctlhq/.github#309, #181, #322 and any finance-related issue found. Each row SHALL give owner repo, canonical store, state and evidence.
- WHEN the product-surface matrix is produced THE SYSTEM SHALL compare options A (catalog assistant, private owner chat), B (owner workspace plus catalog launcher) and C (external read-only finance MCP connector), and the data paths CSV/OFX/QIF import, statement upload, Open Banking/Plaid-like API and no-ingestion mode.
- WHEN a provider-by-country claim is made for Montenegro, the EEA or the UK THE SYSTEM SHALL cite a primary source, or SHALL mark it `unknown`.
- THE SYSTEM SHALL ship a synthetic fixture with:
  - at least 2 accounts and 2 currencies;
  - 1 duplicated import, 1 transfer, 1 refund, 1 pending payment and 1 recurring subscription;
  - 1 conflicting merchant category;
  - adversarial statement text, such as a merchant description that tries to start a tool call or change policy.
- WHEN the reference model computes month spend by category, deduplicated totals, FX conversion, duplicate-charge detection and recurring detection THE SYSTEM SHALL use `decimal.Decimal` with explicit rounding. Every FX conversion SHALL record the pinned rate's source and timestamp. Results SHALL equal the oracle values committed in the fixture.
- IF the same transaction arrives twice through overlapping imports THEN THE SYSTEM SHALL suppress it as a repeated import, not report it as a duplicate charge. Two distinct same-amount charges SHALL be reported as a possible duplicate charge.
- IF a transaction is pending THEN THE SYSTEM SHALL leave it out of posted totals and report it separately. Transfers between the owner's own accounts SHALL be excluded from spend. Refunds SHALL net against their category.
- IF an FX rate is missing or older than its allowed age THEN THE SYSTEM SHALL return an explicit uncertainty or error result, never a guessed conversion.
- WHILE the authorization model runs THE SYSTEM SHALL return financial results only to the authenticated owner of the source, through an owner-approved private destination. All of these SHALL be denied: another user, another tenant, an unauthorized Telegram peer, a group chat, and any auto-reply path.
- WHEN a source is revoked or deleted while a job is in flight THE SYSTEM SHALL fence that job, so it neither delivers nor persists any derived result. The test SHALL prove this.
- IF statement or merchant text contains instructions THEN THE SYSTEM SHALL treat them as inert data. The tool allowlist SHALL stay read-only (no payment, transfer, trade, credit, outbound share or credential access). The test SHALL prove this.
- WHEN the rules-only baseline digest and the assistant explanation are compared THE SYSTEM SHALL use exactly the same fixture. Any run that needs a model or live service SHALL be reported `not-run` with a reason, never as a fabricated PASS.
- WHEN the report concludes THE SYSTEM SHALL propose exactly one of the four outcomes. It SHALL also give the rejected alternatives, the decision rules used, the smallest follow-up, the responsible repository, the kill/exit criteria and the explicit statement that an owner decision is required.
- THE SYSTEM SHALL keep `roadmap/spikes/<name>.yaml` at `lifecycle: proposed` with no `decision` block. The file SHALL pass `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes`.
- THE SYSTEM SHALL run the reference-model tests in CI from `.github/workflows/workflow-tests.yml`, using stdlib `unittest`, with no network access.

## Out of scope

- Live bank linking, real financial records, banking credentials, brokerage accounts, trades, money movement, credit decisions, and regulated investment or tax advice.
- Production connector setup or financial provider accounts.
- Outbound finance data to groups, auto-replies, and real notifications.
- Any change to mctl-telegram, mctl-api, mctl-agents or mctl-gitops code or flags.
- Enabling the managed runtime in production, or bypassing the #1048 connector gates.
- A new runtime, orchestrator, identity, policy, approval or audit system. A new finance service or epic.
- Changing any active EpicDefinition, or adding a required work item to one.
- Creating implementation child issues before the owner decides.
- Approving or accepting this spike. The investigator only proposes.

## Open questions

- Plaid and other Open Banking provider coverage for Montenegro (a non-EU, non-EEA country) is unknown. PSD2 does not apply there directly. The report must establish this from primary sources or leave it `unknown`. The proposed verdict must not depend on a guess.
- Can the current AssistantInstall audience scope plus the observe-mode profile express "owner-invoked only, no auto-reply, owner Saved Messages / private DM only"? This needs a `[CODE]` read of mctl-telegram at a pinned SHA (`internal/assistant/catalog.go`, `assistants/schemas/assistant-install.schema.json`). It is not observable from this repository. Until it is read it stays `unknown (not observed)`, and it decides between REUSE_CATALOG_CSV_MVP and EXTEND_AFTER_CONNECTOR_GATES.
- The #309 report path named in `roadmap/spikes/team-assistants-shared-memory-economics.yaml` (`docs/spikes/team-assistants-shared-skills-memory-economics.md`) is not present at this clone's head (`ace500c`). The shared-memory exclusion for finance data must be checked against whatever #309 actually lands.
- I did not fetch the primary sources for the Claude Personal Finance product (claude.com article, support article) during investigation. They must be read and quoted with an access date during the spike.
- Data residency and model-provider data flow for managed runtime jobs (Nebius/OpenAI-compatible through the Cloudflare AI gateway, per `agent-worker-managed-preview` values) are not yet assessed against finance data. The report must state them explicitly.
- Spike manifest name: assumed `finance-assistant`. The owner may rename it.
