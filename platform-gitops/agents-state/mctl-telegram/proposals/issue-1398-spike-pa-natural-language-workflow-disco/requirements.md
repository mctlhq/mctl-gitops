# Spike: natural-language workflow discovery and governed personal automations for the Personal Assistant

## Context

Issue mctlhq/mctl-telegram#1398 asks for a research-only P1 spike. The question is whether the MCTL Personal Assistant (PA, epic #1312, ADR 0011) can grow from "chat with an agent that calls my MCP tools" into "describe a recurring job once, inspect and approve its plan, then reuse it safely". It must do this without a second assistant runtime, scheduler, policy engine, MCP auth layer or privilege boundary. The candidate first journey is an evening "Daily Brief" of questions waiting for the principal in chats they permitted, sent only to the principal through the PA's own bot.

The deliverable is a research package, not code. It contains:

- a pinned, evidence-labelled baseline;
- a product model and Telegram storyboard;
- an options matrix with a recommendation;
- a proposed (non-production) versioned workflow and authority contract;
- a safety and negative-test matrix in which every scenario is UNTESTED;
- a staged experiment with go/no-go gates.

It matters because ADR 0011 already reserves the `scheduled` and `event` triggers on `ExecutionContext` (`internal/pa/context.go`) but defers routines to Phase 4 (HOLD). A careless routine design would bypass consent, taint, budgets or the per-dispatch revalidation that Phase 1 builds.

## User stories

- AS the platform owner I WANT an evidence-labelled map of what the PA, the Assistant Catalog, the managed runtime and automation actually are today SO THAT I decide on facts rather than on closed issues.
- AS a PA principal I WANT to describe a recurring job in plain language and get back a human-readable workflow draft SO THAT I can see exactly which chats, tools, schedule and delivery target it would use before anything runs.
- AS a PA principal I WANT a dry run on synthetic data and an explicit activation step SO THAT natural-language consent is never treated as authorization.
- AS a PA principal I WANT to pause, edit, revoke and delete a workflow and see its execution receipts SO THAT I stay in control and can trust what ran.
- AS the security owner (#1048) I WANT every workflow run to pass the same consent, pin, scope-ceiling, taint, budget and revision checks as an interactive run SO THAT routines add no new privilege boundary.
- AS the product owner I WANT ranked alternative jobs and falsifiable hypotheses with defined metrics SO THAT the next owner decision is bounded.

## Acceptance criteria (EARS)

Baseline and evidence:

- WHEN the spike report is produced THE SYSTEM SHALL pin the mctl-telegram commit (`9877b1d68ef7d2d969992023bd5fb49fe7835db6`) and the mctl-gitops commit (`876a44144760e4bf9ca181b6f104cec06dc3fc7a`) it was measured against.
- WHEN the report states a capability THE SYSTEM SHALL label it VERIFIED_CODE, VERIFIED_DEPLOYMENT, DESIGNED_ONLY or UNKNOWN, and cite the file, test, gitops path or tool call behind the label.
- IF a source could not be read THEN THE SYSTEM SHALL label the claim UNKNOWN, never absent or disabled.
- THE SYSTEM SHALL include a relationship diagram covering four surfaces: the PA (`internal/pa`), the Assistant Catalog / `AssistantInstall` (`internal/assistant`, `internal/assistantinstall`), the automation control plane (mctlhq/.github#318) and `mctl-agents`.

Product model:

- THE SYSTEM SHALL define a conversational discovery flow:
  - capture intent, selected chats, frequency and time zone, delivery target and success checks;
  - ask clarifying questions;
  - show a human-editable workflow draft with provenance per field.
- THE SYSTEM SHALL define a storyboard: request -> draft -> permission and data-flow preview -> synthetic dry run -> explicit activation -> execution receipts -> feedback -> edit, pause or revoke.
- WHEN a principal answers in free text THE SYSTEM SHALL treat the answer as input to the draft only. Activation SHALL require a verified `callback_query` on a card bound to the exact draft digest, following the ADR 0011 pattern that grants standing permissions outside the model.

Architecture and contract:

- THE SYSTEM SHALL compare PA_EXTENSION, CATALOG_COMPOSER, BOUNDED_HYBRID and DEFER. For each it SHALL give dependency owners, build-vs-reuse evidence and a recommendation.
- THE SYSTEM SHALL propose a versioned workflow spec and authority contract, marked "proposed, not production". It SHALL bind to:
  - the principal;
  - the consent version;
  - connection ids and `authority_revision`;
  - the pinned tool names, schema hashes and description hashes;
  - the selected peers;
  - the schedule and time zone;
  - the delivery recipient (the principal only);
  - the budget ceilings;
  - the spec digest.
- WHILE a workflow is active THE SYSTEM SHALL revalidate, before every execution and every dispatch, everything an interactive run revalidates today:
  - the `PA_*` switches;
  - the per-principal disable and consent;
  - the connection state and revision;
  - the catalog pin and a fresh `tools/list`;
  - the budget reservation;
  - the audit append.
- IF any binding no longer matches THEN THE SYSTEM SHALL refuse the run, record a refusal receipt and notify the principal. It SHALL NOT run with the current values.
- WHEN a trigger fires more than once for the same occurrence THE SYSTEM SHALL produce at most one execution for that occurrence, using an idempotency key derived from the workflow id, the version and the occurrence instant.
- IF a retrieval fails THEN THE SYSTEM SHALL report the brief as incomplete. A failed read SHALL NOT be counted as "no matching messages".
- IF the outcome of a delivery is unknown THEN THE SYSTEM SHALL record `outcome_unknown` and SHALL NOT resend automatically.
- WHILE any tool output is in a run THE SYSTEM SHALL treat the run as tainted (threat model T5). A tainted workflow run SHALL have no write path, and the scheduler-facing contract SHALL carry no write tool.
- THE SYSTEM SHALL map scheduling to the canonical trigger authority of mctlhq/.github#318 (Temporal). It SHALL NOT propose an in-process scheduler in mctl-telegram, a new agent runtime, a new MCP auth layer or a memory database separate from the #1325 design.

Experiment and handoff:

- THE SYSTEM SHALL design a synthetic Daily Brief test. Its only data sources SHALL be the pinned `tg` read tools of `internal/pa/catalog/pin.json`, and its only delivery SHALL be a PA bot message to the same principal. Its negative-case matrix SHALL cover at least the cases listed in issue #1398, each marked UNTESTED.
- THE SYSTEM SHALL rank 2-4 alternative jobs by five criteria: evidence, activation friction, repeat usage, safety and cost.
- THE SYSTEM SHALL define these metrics without numeric thresholds:
  - D1 first useful task;
  - D7 repeat;
  - completion per eligible run;
  - cost per successful job;
  - pause, revoke, trust and denial rates.
- THE SYSTEM SHALL state falsifiable hypotheses and one bounded next owner decision.
- THE SYSTEM SHALL NOT claim Telegram access, recurring delivery or production activation unless evidence shows it.

## Out of scope

- Any code, migration, flag change, preview or production deployment, image, Vault or credential access.
- Real user data and real Telegram messages, outreach, Telegram delegated writes, checkout and payment.
- Enabling PA Phases 2-4, or any approval of this proposal by the investigator or implementer.
- Designing a scheduler (owned by mctlhq/.github#318), PA routines and memory implementation and Glovo (#1325), custom connector security and egress (#1048), the managed runtime (#1088), Townie/Grok benchmarking (#1379), or Assistant Catalog UX (#1002/#1280). This spike only maps interfaces to them.
- Changing `AssistantInstall` or the auto-reply assistants.

## Open questions

- Matt Pocock "VECTOR": the primary material (https://x.com/mattpocockuk/status/2123810087361810663) was not fetched in this run. Its claims and the acronym's meaning are UNKNOWN and must be verified from the original source before the report cites them.
- "Unanswered" semantics: `telegram.Message` (`internal/telegram/messages.go`) exposes `id`, `peer`, `from`, `text`, `date` and media. It has no outgoing flag and no reply-to id, and `get_unread_messages` is not in the PA pin. Unread is not the same as unanswered. Should the pilot redefine the job as "messages addressed to me since my last message in each selected chat", or does it need a pin change for a reply-to field, which requires a reviewed catalog PR and a tg change?
- The trigger authority contract of mctlhq/.github#318 (Temporal schedule ownership, delivery semantics, cross-repo signal into mctl-telegram) was not readable from this clone. It is UNKNOWN.
- Phase 1 evidence (refreshed 2026-11-23): production GitOps has no PA variables; preview HAS configured PA variables but PA_ENABLED=false, PA_EXTERNAL_TOOLS_ENABLED=false, PA_SERVER_TG_ENABLED=false and PA_WRITES_ENABLED=false. Dedicated agent-worker-pa-preview has replicaCount 0. S1 manifest does not currently show gap entries, but #1317 and R1-R6 #1319 are open; no user-exercised PA run is verified.
- Whether the Assistant Catalog `Definition` / `Install` split (`internal/assistant/assistant.go`) should host PA workflow definitions needs a #1002/#1280 owner view. This spike only recommends a narrow adapter.
- The delivery identity for the brief is the PA bot (Bot API). Can the brief be sent outside the 24-hour conversation context, given that Bot API private chats need a prior `/start`? Answer: yes, once the principal has started the bot. Note, though, that the PA output path (`internal/pa/output`) is today only reached from a reply to a job.

## Revision 2: personal agent skills, routines and product benchmark (2026-11-23)

- WHEN evaluating the user journey THE SYSTEM SHALL compare Grok Bot, Hermes Agent, dots, Gemini and MCTL PA, separating source-backed vendor capabilities from VERIFIED_CODE and deployed/flagged status. Grok Bot product reference: https://docs.x.ai/grok-bot/skills-routines-and-automations ; Hermes: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md . Reference existing benchmark owner #1379; do not duplicate it.
- THE SYSTEM SHALL distinguish three artifacts: (1) reusable **skill/template** with instructions, digest, provenance and safe success checks but NO OAuth authority; (2) **workflow instance** with selected read-only source IDs, approved schedule, delivery bound to principal, consent and pinned authorities; (3) **personal memory** with inspect/edit/delete, provenance and retention, owned by Phase 4 #1325. A user correction can SUGGEST a new skill version but cannot self-activate, acquire scopes or bypass PA approval.
- THE SYSTEM SHALL design two simulated journeys: interactive read-only Telegram question with one successful tool call; and Daily Brief draft -> explicit source selection -> versioned skill/spec -> synthetic dry-run -> activation confirmation -> deterministic occurrence -> receipts -> pause/edit/revoke. Scheduled execution remains DESIGNED_ONLY and HOLD.
- THE SYSTEM SHALL prohibit treating unread messages as unanswered; tool errors MUST be incomplete/error, not empty result. Negative tests include stale client authority_revision, revoked consent, tainted source prompt injection, changing catalog pin, duplicate schedule event, wrong recipient, DST, budget exhaustion and disconnect during a run.
- THE SYSTEM SHALL distinguish third-party **Grok (grok.com)** E2E already OWNER_OBSERVED_WORKS on 2026-11-22 (#1381/#1393) from distinct Grok Bot product attribution UNKNOWN. These are MCP distribution facts, NOT evidence of a deployed MCTL PA or working scheduled workflows. An earlier test using an MCTL admin account inherited admin scopes and does not prove a read-only safety gate.
- The owner decision remains BOUNDED_HYBRID for research / DEFER for implementation until Phase 1 exit and #318 trigger-contract evidence. Metrics: D1 first useful task, activation opt-in, D7 successful repeat, task success/eligible occurrence, costs, denial/approval and revocation, with non-invented measurement definitions. All Phase 2-4 HOLDs remain.
