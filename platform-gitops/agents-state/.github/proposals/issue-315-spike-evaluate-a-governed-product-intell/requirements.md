# Spike: evaluate MCTL InsightLoop — governed Product Scout discovery

## Context

mctlhq/.github#315 asks whether MCTL can turn the product telemetry, user-journey evidence and GitHub backlog it already has into a non-duplicative, evidence-backed product opportunity. The opportunity would go to a human as a `proposed` DevLoop research/experiment proposal, with no second agent runtime and no authority to implement. The first bounded case is tg.mctl.ai activation. In the 2026-11-01 cohort snapshot from mctlhq/mctl-telegram#1072, 32 people signed up and 20 made a tool call, so 12/32 had not made a tool call. That is a descriptive observation. It is not a known cause.

This is a research-only spike in the form of the earlier `.github` spikes (`docs/spikes/journey-intent-correlation.md`, `roadmap/spikes/journey-intent-correlation.yaml`). The deliverables are a report at `docs/spikes/product-intelligence-loop.md`, design-only artifacts (an Opportunity Card JSON Schema and synthetic evaluation fixtures under `docs/spikes/product-intelligence-loop/`), a `SpikeDefinition` manifest `roadmap/spikes/product-intelligence-loop.yaml` at `lifecycle: proposed` with exactly the four declared outcomes, and an `AGENTS.md` index bullet. It matters because much of the pipeline already exists: a deterministic daily digest (`internal/digest/digest.go`), the admin-only `get_acquisition_report` tool (mctl-telegram 0.118.0+), the `audit_logs` connect funnel from #902 and an open #912. A Product Scout that does not first measure itself against these sources would add noise, duplicates or invented causality.

## Owner amendments (2026-11-05): name, triggers, neutral discovery verdict

- **Canonical research/product name:** MCTL **InsightLoop**; **agent role:** Product Scout. Retain the historical issue source, proposal slug, and `docs/spikes/product-intelligence-loop*` artifact paths for stable identity; use InsightLoop in conceptual headings and diagrams.
- **Trigger-agnostic Scout:** investigate three entry points into the same bounded discovery pipeline: `scheduled` (periodic), `event-driven` (validated anomaly, feedback, release outcome), and `on-demand` (an authorized human request). All must use deterministic cohort validation, dedup/idempotency, evidence freshness, principal/tenant scope, read-only capabilities, limits and audit. No trigger grants authority to start implementation.
- **MVP sequencing:** a future pilot may support scheduled execution first, but the design must not hardwire the general InsightLoop contract to a CronWorkflow. Existing Argo/Temporal primitives should be reused where proven; mark unsupported modes unknown, not implemented.
- **Fair comparison:** independently score the best deterministic digest/report + manual GitHub triage baseline and the Scout on identical frozen data. Measure *novel actionable opportunities*, recall or missed opportunities, duplicate/false-causality rate, reviewer minutes, evidence quality, and cost. Do not infer that known issue #912 is a novel Scout success. Do not pre-select `REUSE_EXISTING_REPORTS` or any other outcome before evidence.
- **Decision boundary:** no new epic until a cross-product reusable need is proven. No production data access or follow-up implementation without a separate owner decision.

## User stories

- AS the product owner I WANT a source-linked inventory of the telemetry, digests, agent mechanisms and issues that exist today SO THAT I decide on a Scout against real capabilities, not assumed ones.
- AS the product owner I WANT the 12/32 activation observation reconstructed, or explicitly marked unverifiable, with denominators and unknowns SO THAT no hypothesis is mistaken for a finding.
- AS a reviewer I WANT a fixed Opportunity Card schema with provenance, confidence, alternatives, related issues, success metric and stop condition SO THAT every Scout output can be triaged the same way.
- AS a reviewer I WANT a deterministic dedup and freshness protocol SO THAT #912, #902 and #1072 are reused, not duplicated, and unobserved data stays `unknown`.
- AS a platform owner I WANT the Scout role mapped onto the existing AgentDefinition, ExecutionProfile, DevLoop and approval controls SO THAT no second policy or approval plane appears.
- AS an operator I WANT scheduled, event-driven and on-demand observations to converge on one identity-bound, idempotent read-only Scout contract SO THAT the runtime behavior and governance do not depend on the trigger source.
- AS a privacy owner I WANT the evidence restricted to aggregate, minimum-cohort, tenant-scoped data with no raw messages SO THAT discovery does not become user profiling.
- AS the decision owner I WANT one verdict from the four declared outcomes, with a baseline-versus-candidate scoring plan SO THAT any pilot is justified by measured utility over reviewer burden.

## Acceptance criteria (EARS)

Report and inventory
- WHEN the spike is delivered THE SYSTEM SHALL contain `docs/spikes/product-intelligence-loop.md` with an evidence-pins table: 40-hex commits for every repository read, and the deployed image tag of `labs/mctl-telegram`.
- THE SYSTEM SHALL tag every factual claim in the report `[CODE]`, `[CONFIG]`, `[LIVE]`, `[DOC]` or `[ISSUE]`, the same tag vocabulary as `docs/spikes/journey-intent-correlation.md`.
- THE SYSTEM SHALL include a capability/gap/dedup matrix that classifies each of #18, #20, #21, #22, #309, mctl-agents#242, mctl-telegram#902, #912 and #1072, the daily digest, `get_acquisition_report`, Umami (`admins/umami`), the weekly mentor digest and the scheduled agent crons as `implemented-and-deployed`, `implemented-not-verified-deployed`, `flag-gated`, `planned` or `unknown (not observed)`.
- IF an issue is closed or a proposal is `merged` but no deployed evidence was read THEN THE SYSTEM SHALL classify it as `implemented-not-verified-deployed`, never as rolled out.

Historical activation case
- WHEN the report presents the tg.mctl.ai activation case THE SYSTEM SHALL state the #1072 figures (32 / 27 / 20 / 10 / 4, snapshot 2026-11-01), their denominator, their source and the fact that this run did not re-query them.
- IF the figures cannot be reproduced from a frozen, approved evidence packet THEN THE SYSTEM SHALL mark them `unverifiable in this spike` and SHALL NOT present derived rates as current metrics.
- THE SYSTEM SHALL keep the #902 population (75 external sign-ups, different window and stage classification) separate from the #1072 cohort and SHALL NOT sum, merge or compare their counts as one population.
- THE SYSTEM SHALL list every candidate explanation for the 12/32 (post-auth client setup friction, phone/code/2FA step, misconfigured MCP client, lack of intent, reporting gaps, late activation, users who predate acquisition capture) as `hypothesis, untested`.

Opportunity Card contract
- THE SYSTEM SHALL include trigger provenance (mode: scheduled/event-driven/on-demand, origin reference, dedup/idempotency key and actor or service-principal scope) without storing sensitive event payloads or treating an event as authorization.
- THE SYSTEM SHALL define a JSON Schema (draft 2020-12) `docs/spikes/product-intelligence-loop/opportunity-card.schema.json`. Its required fields: `observation`, `evidence_packet` (snapshot id, captured_at, source refs, content digest), `denominators`, `unknown_counts`, `freshness`, `confidence` (enum), `limitations`, `alternative_explanations`, `related_issues` (with a dedup relation), `dedup_fingerprint`, `recommended_next_research`, `success_metric`, `stop_condition`, `status`.
- THE SYSTEM SHALL restrict Opportunity Card `status` to values that grant no authority (`draft`, `insufficient_evidence`, `duplicate`, `for_owner_triage`) and SHALL NOT include an `approved` or `accepted` value.
- WHEN a card's evidence has a sample below the minimum cohort threshold, or a required source is missing or stale THE SYSTEM SHALL require `status: insufficient_evidence` and SHALL forbid a numeric uplift claim.

Dedup and freshness protocol
- THE SYSTEM SHALL specify a deterministic dedup fingerprint over normalized product, journey stage, metric id and intervention class, matched against a frozen GitHub issue snapshot before any model reasoning.
- WHEN a candidate matches an open issue on product, stage and intervention class (the #912 reminder case) THE SYSTEM SHALL emit `status: duplicate` with a link and SHALL recommend measuring the existing work, never a new issue.
- WHILE a source has not been read in the current evidence packet THE SYSTEM SHALL record its value as `unknown (not observed)` and SHALL NOT treat it as zero or absent.

Evaluation design
- THE SYSTEM SHALL include synthetic trigger cases for all three initiation modes, duplicate event delivery and unauthorized on-demand invocation, each with a deterministic expected safe result.
- THE SYSTEM SHALL evaluate actionable **new** findings, reviewer time and missed opportunities against a comparable best-effort deterministic baseline; no option is treated as the expected outcome before scoring.
- THE SYSTEM SHALL provide synthetic or frozen-redacted fixtures with at least these cases: one true positive, one known duplicate (#912), one false-causality signal, one missing source, one privacy-boundary case (a request for user-level data) and one prompt-injection case (untrusted text in an issue body or source field).
- THE SYSTEM SHALL contain no real user identifiers, message bodies, phone numbers, tokens or secrets in any fixture or in the report.
- THE SYSTEM SHALL define a baseline (existing digest + `get_acquisition_report` + manual GitHub search) versus candidate scoring plan with precision/actionability (human-reviewed), duplicate rate, false-positive rate, reviewer minutes, trace completeness and cost per accepted opportunity, and SHALL report `not measured` for any metric it did not measure.

Authority and governance
- THE SYSTEM SHALL include a role/trust-boundary map against AgentDefinition/ExecutionProfile (#18), ContextSnapshot (#20), WorkItem (#21), Temporal DevLoop approval (`aar_`, content digest binding), product telemetry and #309. It SHALL show that the Scout holds no write credentials and cannot approve, implement, message users or change flags.
- THE SYSTEM SHALL distinguish the Product Scout (trigger-agnostic, read-only discovery) from the Telegram Recruiter Assistant (communication, delegated identity) role.
- THE SYSTEM SHALL specify a feedback contract that links an approved hypothesis to its WorkItem (`wi_`), the DevLoop proposal and its outcome measurement by reference, and keeps mctl-api as the authority. GitHub and analytics UIs SHALL NOT become a competing authority.

Verdict and manifest
- WHEN the report concludes THE SYSTEM SHALL propose exactly one of `REUSE_EXISTING_REPORTS`, `BOUNDED_PRODUCT_SCOUT_PILOT`, `EXTEND_AGENT_PLATFORM_AFTER_GATES` or `DEFER_INSUFFICIENT_EVIDENCE`, with the alternatives, owning repositories and the evidence for each.
- IF the proposed verdict is `BOUNDED_PRODUCT_SCOUT_PILOT` THEN THE SYSTEM SHALL state a timebox (14 days after explicit GO), a cost cap, a data-access preflight, a kill switch and success/failure criteria, as a proposal only.
- THE SYSTEM SHALL use the name InsightLoop in report headings and decision framing while leaving existing stable file paths and proposal slug unchanged.
- THE SYSTEM SHALL add `roadmap/spikes/product-intelligence-loop.yaml` (owner `mctlhq/.github`, issue `mctlhq/.github#315`, the four outcomes, `lifecycle: proposed`, `execution.devloop: true`, `evidence.report`) with no `decision` block and no `epic` binding, and it SHALL pass `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes`.
- THE SYSTEM SHALL NOT open follow-up issues, modify any EpicDefinition, or record the owner decision.

## Out of scope

- Implementing a Product Scout, scheduler, AgentDefinition/ExecutionProfile, MCP server, connector, analytics warehouse, dashboard or database.
- Running any query against production or the production replica, accessing Umami data, or reading Telegram messages, user-level records, logs with personal data or secrets.
- Opening issues or PRs, approving or triggering DevLoop, sending Telegram messages or reminders, running a live A/B experiment, changing production flags.
- Changing #912 or the #902/#1072 implementations, and any EpicDefinition manifest.
- Claiming a cause for the 12/32 drop-off or treating small-cohort results as statistically decisive.
- Replacing #18, #20, #21, #22, #309 or mctl-telegram#1002.

## Open questions

- The "existing daily digest" in the issue is read here as the mctl-telegram operator digest (`internal/digest/digest.go`, cited in the #1072 proposal). Whether another product digest exists was not observed. The weekly mctl-agents mentor digest (`agents-state/_mentor/digest/`) is a backlog digest, not product telemetry.
- Reproducing the 2026-11-01 figures needs an approved, redacted aggregate export. This proposal assumes no such export is authorized, so the case will most likely be marked `unverifiable in this spike`. The owner may supply a frozen aggregate packet; that is information, not approval to query production.
- The 2026-11-01 cohort probably predates acquisition capture (`get_acquisition_report` ships from mctl-telegram 0.118.0). Its users would then report `unknown (pre-capture)`, and source segmentation of this cohort would be impossible. This is to be confirmed from the capture epoch, not assumed.
- Minimum cohort threshold for aggregates: the proposal uses k >= 5 per reported cell as a design default, pending the owner's privacy decision.
- Whether the current AgentDefinition/ExecutionProfile contract supports a scheduled, identity-bound, read-only run without a DevLoop issue trigger is not verified. The scheduled agents observed (service-agent weekly cron, mentor, incident responder every 30 minutes) are Argo CronWorkflows, and their registry binding was not read.
- #912 is OPEN (observed via `gh issue view`), but it has no proposal under `agents-state/mctl-telegram/proposals/`. Its owner decision on default category and enablement is not recorded.
