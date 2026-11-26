# Spike: natural-language workflow discovery and governed personal automations for the Personal Assistant

## Context

Issue mctlhq/mctl-telegram#1398 asks for a research-only P1 spike. The question is whether the MCTL Personal Assistant (PA, epic #1312, ADR 0011) can grow from "chat with an agent that calls my MCP tools" into "describe a recurring job once, inspect and approve its plan, then reuse it safely". It must do this without a second assistant runtime, scheduler, policy engine, MCP auth layer or privilege boundary. The candidate first journey is an evening "Daily Brief" of questions waiting for the principal in chats they permitted, sent only to the principal through the PA's own bot.

The deliverable is a research package, not code. It contains:

- a pinned, evidence-labelled baseline;
- a product model and Telegram storyboard;
- an options matrix with a recommendation;
- a proposed (non-production) versioned workflow and authority contract;
- a safety and negative-test matrix in which every scenario is NOT_EXECUTED;
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

- WHEN the report is produced THE SYSTEM SHALL cite the current 2026-11-23 pinned evidence from design.md, explicitly preserving historical 2026-11-22 pins and separating GitOps desired, live Argo and R1–R6 user results.
- WHEN the report states a capability THE SYSTEM SHALL label it VERIFIED_CODE, VERIFIED_GITOPS_DESIRED, LIVE_ARGO_OBSERVED, VENDOR_DOCUMENTED, DESIGNED_ONLY or UNKNOWN, and cite a precise SHA/path, live tool observation or checked vendor source. Argo Healthy/Synced is not proof of R1–R6 user success.
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

### Canonical automation authority (P1-01 — required)
The approved research decision [mctlhq/.github#318](https://github.com/mctlhq/.github/issues/318) is **EXTEND_MCTL_API**; planning epic [#322](https://github.com/mctlhq/.github/issues/322) and [mctl-api automation/v1](https://github.com/mctlhq/mctl-api/blob/3233f6c0a00437f73021570d8a16253d2bcd524b/docs/automation-contract.md) fix ownership. mctl-api alone owns standing **AutomationDefinition `au_`**, owner/tenant, trigger, lifecycle and Temporal reconciliation; every occurrence maps to one `wi_ → xr_ → we_`. **AutomationRun is a query VIEW**, not a new PA-owned `pa_workflow_runs` table. PA owns Telegram-verified draft UX, `pa-data-flow/v1` consent, selected peers, PA connection revisions and executor/outbox adapter. No second PA `pa_workflows` standing-intent authority, scheduler, memory DB or independent run ledger. The automation contract is **contract-only**, not deployed implementation; #322 and its owner gates remain required.

A proposed `PAWorkflowDraft/v1alpha1` contains user-originated intent, selected read-only peers, PA connection IDs/`authority_revision`, consent, pinned tool schema/description hashes, budget, schedule/time zone suggestion, principal-only PA-bot delivery and immutable draft digest; a skill is only non-authoritative instructions. A verified Telegram callback authorizes *requesting* canonical activation. The future authenticated mctl-api bridge uses a registered server-side automation template and verified `SurfaceIdentityLink`/PA principal proof; neither model nor client controls `au_`, owner/tenant, credentials or Temporal workflow type. No PA token/raw private chat may leak into Temporal histories.

### Canonical occurrence / replay (P1-02 — required)
Use [mctl-api occurrence.go:74–101](https://github.com/mctlhq/mctl-api/blob/3233f6c0a00437f73021570d8a16253d2bcd524b/internal/automation/contract/occurrence.go#L74-L101): domain-separated length-prefixed `OccurrenceKey(au_id, trigger_kind, source)`; source is scheduled UTC RFC3339Nano instant or authenticated event producer/type/stable event ID. **Definition version MUST NOT be in the deduplication key** (otherwise same fire replayed across edits executes twice). Snapshot admitted version separately. Claim `(tenant,au_id,occurrence_key)` durably; retain a tombstone after WorkItem cleanup; duplicate yields original `wi_` and `replayed:true`, with no second reservation, model execution or delivery, while conflicting reuse fails with typed 409. Durable claim is a future `automation-api-store` gate, not proof of live behavior.

### Scheduled identity, authority and in-flight semantics (P2)
`internal/pa/context.go` currently accepts **only NewInteractive(VerifiedUpdate)** and requires a conversation ID/budget; `pa_jobs` keys interactive Bot `UpdateID`; conversations have 24h TTL. An authenticated future canonical occurrence **cannot impersonate** an interactive update or reuse its expired conversation. Specify a server-verified principal bridge, per-occurrence bounded scheduled context, fresh ledger hold and principal-only PA Bot API outbox with `outcome_unknown` no-blind-resend handling; all are DESIGNED_ONLY.

At fire time **mctl-api** rechecks owner/tenant identity, automation state/version, policy, usage authority and budget. At every PA tool dispatch and outbound delivery **mctl-telegram** independently rechecks consent, principal disable, `PA_*` flags, connection `authority_revision`, token scopes, tool pin/catalog drift, taint, budget and audit, failing closed. Editing a definition makes a new version; an already admitted old-version read-only run may finish only while its unchanged grants remain valid. **Pause, revoke, withdraw consent, disconnect, principal disable, schema drift or authority-revision change must fence the NEXT DISPATCH AND SEND even mid-run**. Neither a schedule, skill nor memory item grants tool authority. Failed read is `incomplete`, not a successful empty result.

**Recommendation:** BOUNDED_HYBRID means PA drafting/consent/delivery adapter over the **already decided** mctl-api control plane; **DEFER** Phase-4 runtime implementation. No new scheduler, OAuth layer, PA execution store or alternate assistant.

### Additional normative safeguards (Claude P2; research-only, not production)

- WHEN comparing architecture alternatives THE SYSTEM SHALL evaluate `PA_EXTENSION`, `CATALOG_COMPOSER`, `BOUNDED_HYBRID` and `DEFER` against control-plane ownership, consent, safety, cost and reuse. It SHALL show why a PA-owned scheduler/store and Catalog-owned MTProto authority are rejected, choose **BOUNDED_HYBRID as PA adapter over already-decided EXTEND_MCTL_API** for design, and **DEFER** implementation pending owner GO and the #322 gates.
- WHEN a draft or scheduled execution is compiled THE SYSTEM SHALL allow **only pinned read-only `tg` tools** in its scheduler-facing tool contract. No Telegram send/forward/pin/delete, Alice control/Quasar, arbitrary MCP tool or generic `write` tool may be included; a model's suggestion, a saved skill, a memory item or an external result cannot create or widen grants. All external tool/model content remains **tainted (T5/I6)** and is rendered via the existing safe-text/URL-neutralization boundary (`safetext.Render` where applicable); tainted content has **no write path** or destination override in this first slice.
- WHEN the platform refuses admission, a tool dispatch or a result delivery THE SYSTEM SHALL **audit a typed refusal receipt** with verified principal, `au_` and `occurrence_key` where admitted, stage, reason, source-status and cost metadata, without tokens or private message content. It SHALL notify **only the original verified principal** via the PA bot when notification is still authorized; otherwise it SHALL retain an inspectable sanitized refusal for that principal's next verified session and MUST NOT bypass a delivery fence to send the notice.
- WHEN a workflow is **edited to narrow** selected peers, tools, allowed delivery identity/channel, model/data-flow consent or run budget THE SYSTEM SHALL treat the edit as an immediate authority reduction for *all admitted in-flight runs*: the next tool dispatch and outbound send MUST be fenced if they exceed the new policy, even if the run holds a previously admitted definition version and valid old consent. Remove-peer and lower-budget examples MUST appear in the negative-test matrix. Expanded rights require separate user approval and fresh digest; either edit changes version but MUST NOT alter the already claimed occurrence key.
- WHEN an occurrence is claimed THE SYSTEM SHALL retain a durable tombstone for **at least the authenticated source's replay horizon** after WorkItem cleanup. The pinned mctl-api `automation/v1` contract currently proposes `DefaultTombstoneHorizon=30 days`, but the real webhook/source horizon is **UNKNOWN** and must be confirmed; any longer horizon requires longer retention and an owner-approved limit. A missing claim store or unknown unsafe replay horizon MUST fail closed; a redelivery within retention returns the same `wi_`, without new budget reservation, tool call or notification.
- WHEN testing this proposal THE SYSTEM SHALL include simulated prompt injection, tainted write attempts, refusal-receipt/notice handling, edit-narrowing during execution and send, cross-version retry, tombstone/claim-crash and all Phase-1 gates, each initially **NOT_EXECUTED**. No live user content, runtime change or implementer is authorized.

Experiment and handoff:

- THE SYSTEM SHALL design a synthetic Daily Brief test. Its only data sources SHALL be the pinned `tg` read tools of `internal/pa/catalog/pin.json`, and its only delivery SHALL be a PA bot message to the same principal. Its negative-case matrix SHALL cover at least the cases listed in issue #1398, each marked NOT_EXECUTED.
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
- The #318 decision and mctl-api automation/v1 contract ARE AVAILABLE; only automation store/Temporal runtime/PA identity bridge implementation and live outcomes remain UNKNOWN. #322 owns this work, not PA.
- Phase 1 evidence is updated below: read-only PA preview flags and worker now on in GitOps, three services Healthy/Synced in Argo, but user R1–R6 results and Phase-4 automation execution are unverified.
- Whether the Assistant Catalog `Definition` / `Install` split (`internal/assistant/assistant.go`) should host PA workflow definitions needs a #1002/#1280 owner view. This spike only recommends a narrow adapter.
- The delivery identity for the brief is the PA bot (Bot API). Can the brief be sent outside the 24-hour conversation context, given that Bot API private chats need a prior `/start`? Answer: yes, once the principal has started the bot. Note, though, that the PA output path (`internal/pa/output`) is today only reached from a reply to a job.

## Revision 3: research evidence and decisions (2026-11-23)

**Current pinned evidence (2026-11-23):** mctl-telegram `ecbce7732fc2915a2a72dc21f1d1d2e9f8713d73`, mctl-gitops `869582d33b66f5eb36de29ff9b52c487f2631ed4`, mctl-api `3233f6c0a00437f73021570d8a16253d2bcd524b`, .github `60e9db522f18299e73dac23fffedfe5b4ce81930`. GitOps preview: image `main-6623542`, `PA_ENABLED=true`, `PA_EXTERNAL_TOOLS_ENABLED=true`, `PA_SERVER_TG_ENABLED=true`, `PA_WRITES_ENABLED=false`, `PA_SERVER_ALICE_ENABLED=false`, PA worker `replicaCount=1`; production `0.145.0`, no PA flags. Read-only live Argo checks 18:01–18:03Z were Healthy/Synced for these three services; this does not prove PA R1–R6 user success. #1317/#1319 remain open; S1 manifest body has no gaps. Older `9877b1d/876a441` and preview-disabled states are HISTORICAL, not current.

A Grok (grok.com) owner-observed OAuth+MCP connection on 2026-11-22 (#1381/#1393) is NOT a Grok Bot build attribution or MCTL PA workflow success. Grok Bot's saved skill→routine UX, Hermes skill management, dots proactive work and Gemini scheduling are vendor/product patterns (sources and dated quotes in #1379), not existing PA permissions or deployments. Separate non-authoritative skill/template and future inspectable memory from PAWorkflowDraft and canonical mctl-api `au_`. Keep #1325 Phase-4 and #1048 connector security gates. Synthetic Daily Brief must test cross-version replay, event-source identity, claim crash/tombstones, wrong/expired principal link, 24h conversation expiry, revoked consent mid-run, tool pin drift, prompt injection, unknown send outcome, budget failure, DST and cross-tenant authority. Research-only, no implementer or rollout.
