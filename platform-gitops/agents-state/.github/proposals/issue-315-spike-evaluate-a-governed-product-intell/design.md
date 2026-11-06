# Design: issue-315-spike-evaluate-a-governed-product-intell

## Current state

### This repository (mctlhq/.github at `dc359d44f25bbe3cd9d6d23a865eb89773ee1cf0`)

- The spike convention is a report under `docs/spikes/<name>.md`, with an optional design-artifact directory (`docs/spikes/mcp-gateway-g0/`, `docs/spikes/cve-advisory-impact/`, `docs/spikes/security-finding-lifecycle/`), a `SpikeDefinition` in `roadmap/spikes/<name>.yaml` and a bullet under `# Spikes` in `AGENTS.md`.
- `roadmap/schemas/spike-definition.schema.json` requires `title`, `question`, `lifecycle`, `github.issue` and `outcomes` (at least 2, each matching `^[A-Z][A-Z0-9_]*$`). A `decision` block is allowed only when `lifecycle: decided`. `roadmap/scripts/validate.py roadmap/epics roadmap/spikes` (run by `.github/workflows/roadmap-validate.yml`) enforces the schema and the cross-kind rules in `roadmap/README.md` ("Cross-kind invariants"): spike issue bindings must be unique, and a spike issue may not be an epic root. No manifest binds `mctlhq/.github#315` today (grep for `number: 315` returns nothing). `roadmap/scripts/lifecycle_guard.py` guards only `roadmap/epics`.
- Precedent: `roadmap/spikes/journey-intent-correlation.yaml` sits at `lifecycle: proposed` with a header comment saying the owner records the decision. `roadmap/spikes/team-assistants-shared-memory-economics.yaml` (#309) carries no `spec.epic`, because #309 is not an epic work item. The same applies to #315.
- Related epics read:
  - `roadmap/epics/agent-platform.yaml` (#18, owner mctl-agents, `lifecycle: completed`) includes `capability-discovery` mctl-agents#242, `execution-identity` #196, `runtime-policy` #197, `human-approval` #198 and `execution-evidence` #199.
  - `roadmap/epics/context-platform.yaml` (#20, completed) covers the ContextSnapshot contract and deterministic assembly.
  - `roadmap/epics/surfaces.yaml` (#21, completed) covers the canonical WorkItem and surface contract.
  - `roadmap/epics/client-lifecycle.yaml` (#22, owner mctl-telegram, completed) covers consent-aware product communication. Its success criteria include "Product updates require explicit category-level user choice" and "without granting a model direct broadcast authority".
  - A completed epic is manifest state only. It is not deployed evidence.
- `docs/spikes/journey-intent-correlation.md` (#306) proposes `REUSE_WORK_ITEM_ID`: `wi_` is the journey key, `aar_`/content digest are the authorization binding. The Scout's feedback contract reuses this rather than inventing an id.
- `.github/ISSUE_TEMPLATE/spike.yml` and `AGENTS.md` "Spike issue creation rules": no new spike issue is created by this proposal.

### mctl-telegram (product telemetry), from proposals and code

- `agents-state/mctl-telegram/proposals/issue-1072-feat-onboarding-record-acquisition-sourc/` (status `merged`, PR mctl-telegram#1075, approval `aar_0a59341d...`) describes these pieces:
  - the daily digest `internal/digest/digest.go` (`runDigest`, `buildDigestMessage`), about 5 new clients per day;
  - tool calls in `audit_logs(user_id, tool_name, status, created_at)`;
  - the `user_acquisition` table with states `attributed` / `direct` / `unknown` / `unknown (pre-capture)`;
  - the admin-only MCP tool `get_acquisition_report` (scopes `admin:users` or `admin:users:read`, window 1..90 days). It returns sign-ups, tool-call users and users active on 2+ days, per source.

  The 2026-11-01 figures (32 sign-ups, 20 tool-call users, 10 on 2+ days) are quoted there `[DOC]`.
- `agents-state/mctl-telegram/proposals/issue-902-reduce-one-day-drop-off-phone-step-chann/` (status `merged`, PR mctl-telegram#917) measured a different population: 75 external sign-ups, 40 one-day, 22 with no tool call. It classified the stop points (8 at phone, 8 at code/2FA, 2 `identity_mismatch`, 4 `connect:success` with no call) and added a "Connect funnel" SQL section to `docs/runbook.md`. The reminder was split out to #912 `[DOC]`.
- mctl-telegram at `06de6980913cb5b44765365454fd13b2ce97079c` (default branch, via `gh api`): `internal/mcp/tools.go` registers `get_acquisition_report` behind `requireAnyScope(id, "admin:users", "admin:users:read")` and audits it. `docs/product-updates/acquisition-report.yaml` records `evidence.from: 0.118.0` `[CODE]`.
- `internal/connectfunnel/connectfunnel.go` `ClientLabel` gives the bounded MCP client label (`claude`, `chatgpt`, `other`), per the #1072 design `[DOC]`.

### Agent platform

- Scheduled agents exist as Argo CronWorkflows: the weekly service-agent + mentor run, the incident responder every 30 minutes and issue-poll. The DevLoop path is `mctl_trigger_issue` with `use_temporal`, then a human `mctl_approve_dev_loop` bound to `aar_` and the content digest, then the implementer. Source for this paragraph: the MCP tool contracts in this run `[DOC]`.
- The weekly mentor digest lives in `agents-state/_mentor/digest/` (`2026-W34.md`, `2026-W38.md`) `[CONFIG]`. Whether an AgentDefinition/ExecutionProfile can bind a scheduled, non-issue-triggered, read-only run was not observed.

### Deployed state checked

- `mctl_get_service_status(labs, mctl-telegram)`: ArgoCD Healthy/Synced, `imageTag 0.123.2`, host `tg.mctl.ai`, `hasDatabase: true`. 0.123.2 is at or after 0.118.0, so `get_acquisition_report` is present in the deployed image (inferred from release ordering). Its use and the capture epoch were not observed.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: `tag: "0.123.2"`, `AGENT_ENABLED: "true"` (observe mode), `ASSISTANT_REGISTRY_ENABLED: "true"`, `HUMAN_INPUT_ENABLED: "true"`, `DEMO_REVIEWER_ENABLED: "false"`, `ENABLE_ACCESS_QR_ENABLED: "true"`. The CronJobs are the demo-session refresh and reviewer watch (both `renderIf`-gated on the demo flag, which is off) and the canary (`*/10`). No digest CronJob is declared here, so the digest runs in-process or elsewhere: unknown (not observed).
- `mctl_get_service_config(admins, umami)`: Umami 3.4.0 (digest-pinned), host `stats.mctl.ai`, has a database. `values.yaml` comments describe cookieless web analytics for mctl.ai, tg.mctl.ai and docs.mctl.ai behind Backstage forward-auth for the admins tenant. No Umami data was read.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: no product-telemetry or Scout configuration found.
- `gh issue view 912 -R mctlhq/mctl-telegram`: OPEN, "One-time onboarding reminder for connected users with no tool call", labels `enhancement`, `ux`. No proposal for it exists under `agents-state/mctl-telegram/proposals/`.
- `gh issue view 1072`: CLOSED. Production rollout is evidenced only by the image tag ordering above.
- Not read: the production DB or replica (by design), Loki logs, Umami data, the mctl-agents registry bindings (`mctl_list_agents` was not called), the mctl-telegram tag-to-commit mapping (the git ref `0.123.2` / `v0.123.2` returned 404). Each is recorded as a gap, never as absent.

## Proposed solution

The spike produces research and design artifacts in this repository only. Nothing runs against production.

### 1. Report `docs/spikes/product-intelligence-loop.md`

The structure follows `docs/spikes/journey-intent-correlation.md`: non-claims, evidence tags, evidence pins, then sections D1-D9.

- **D1 Capability/gap/dedup matrix.** One row per source or mechanism (see the requirements list), with columns:
  - status class (`implemented-and-deployed`, `implemented-not-verified-deployed`, `flag-gated`, `planned`, `unknown (not observed)`);
  - read path and required scope;
  - freshness and granularity;
  - personal-data class;
  - owner repo;
  - evidence tag.

  The baseline read paths are `get_acquisition_report` (aggregate, admin-scoped, audited), the digest (operator Telegram message, per-client lines, so not aggregate), the #902 runbook SQL (needs DB access, so not a Scout read path) and Umami (page-level, cookieless, admin forward-auth).
- **D2 Historical activation case.** It restates the #1072 snapshot with the denominator (new sign-ups in the 7 days before 2026-11-01) and the derived 12/32 = 37.5%. It also states:
  - 27 connected minus 20 called = 7 connected with no call, and 5 never connected (32 - 27). These are subtractions within one cohort, labelled derived.
  - The figures are `unverifiable in this spike` unless an approved frozen aggregate packet is supplied.
  - #902 is a separate population, in a separate table and never merged with this cohort.
  - Every explanation is marked `hypothesis, untested`.
  - Cohort users likely predate acquisition capture (0.118.0); their source is `unknown (pre-capture)`.
- **D3 Opportunity Card contract.** It points to `opportunity-card.schema.json` (below), with a filled example for the 12/32 observation:
  - `status: duplicate` against #912 for the reminder intervention;
  - `recommended_next_research`: measure #902's shipped copy/wizard changes and #912 once enabled, using the existing `get_acquisition_report` plus the funnel query;
  - success metric: "first successful permitted MCP tool call within 24h of sign-up";
  - stop condition: `insufficient_evidence` when a cell has n < k.
- **D4 Pipeline and architecture sketch.** `observe -> validate cohort -> explain uncertainty -> search GitHub duplicates -> evaluate hypotheses -> propose -> human product decision -> existing DevLoop proposal -> separate execution approval -> (future) measure outcome`. Stage owners:
  - deterministic code: source adapter, metric packet, cohort validation, freshness, dedup fingerprint;
  - model: interpretation, alternative explanations, citations only;
  - human: product decision, then a separate DevLoop approval through `mctl_approve_dev_loop` with `aar_` + content digest.

  Authority boundaries are marked on the sketch. The Scout has a read-only aggregate scope and no GitHub write. Card delivery goes to an owner triage queue (a WorkItem intent or an issue comment drafted for a human), and never calls `mctl_trigger_issue`.
- **D5 Deterministic-first analysis.** The report decides which stages a threshold rule on the existing report can do. Example: alert when the tool-call share of a 7-day cohort drops by more than X points with n >= k per cell. The model adds value only where interpretation and dedup across free-text issues are needed. The comparison is stated as a hypothesis for the evaluation, not as a result.
- **D6 Privacy, tenant and authority model.**
  - Evidence is aggregate only, with minimum cell size k (default 5, open question).
  - Banned: raw messages, user ids, phone numbers, and joins across tenants or products.
  - The evidence packet is immutable and content-addressed (ContextSnapshot `cs_` from #20 as the carrier).
  - Retention follows the source owner's rules.
  - The ExecutionProfile holds no write credentials and a budget cap.
  - Prompt injection: issue bodies and source labels (UTM values are user-controlled) are data and are sanitized. #1072 already strips control characters and bidi overrides. Tool use is limited by the profile allowlist.
  - The trust-boundary map against #18/#20/#21/#22/#309 and the Product Scout versus Telegram Recruiter Assistant split appear here.
- **D7 Feedback contract.** An approved hypothesis becomes a WorkItem intent (`wi_`, #306 verdict). The DevLoop proposal binds `aar_` + content digest, and the outcome measurement cites the same metric id and evidence-packet digest. mctl-api is the authority; GitHub labels and Umami are views.
- **D8 Evaluation and scoring plan.** Fixtures are described below. The baseline arm is the operator using the digest, `get_acquisition_report` and manual GitHub search. The candidate arm is Scout cards from the same frozen inputs. Both arms get blind human review. Metrics:
  - precision/actionability;
  - duplicate rate;
  - false-causality rate;
  - privacy-control pass;
  - injection-control pass;
  - reviewer minutes;
  - trace completeness;
  - cost per accepted opportunity.

  Every metric is `not measured` in this spike unless it was actually run offline.
- **D9 Options, unit economics and proposed verdict.** The four outcomes are compared on privacy/authority risk, duplicate rate, insight yield, review time, reproducibility, cost and control compatibility.

  Decision rules, fixed before the evidence is weighed:
  - `DEFER_INSUFFICIENT_EVIDENCE` if neither the historical case nor a frozen packet can be reproduced and the evaluation cannot run.
  - `REUSE_EXISTING_REPORTS` if the baseline covers the activation case and its dedup (one product, about 5 sign-ups per day, #912 already owning the top intervention).
  - `BOUNDED_PRODUCT_SCOUT_PILOT` only if the offline evaluation shows yield above baseline at lower reviewer minutes.
  - `EXTEND_AGENT_PLATFORM_AFTER_GATES` only if a generic contract gap (for example, a scheduled identity-bound read-only run) is demonstrated.

  On current evidence the expected leaning is `REUSE_EXISTING_REPORTS`. The final verdict must be argued from D1-D8 and may differ. A pilot recommendation must state the 14-day timebox after GO, cost cap, data-access preflight, kill switch and success/failure criteria. Follow-ups are named with owner repos (mctl-telegram for funnel/report tweaks, mctl-agents for any profile gap, mctl-api for WorkItem intents) and are not filed.

### 2. Design artifacts `docs/spikes/product-intelligence-loop/`

- `opportunity-card.schema.json`: JSON Schema 2020-12, `additionalProperties: false`. Properties:
  - `status` enum `draft|insufficient_evidence|duplicate|for_owner_triage`;
  - `confidence` enum `low|medium|high`;
  - `denominators` and `unknown_counts` as integer maps;
  - `evidence_packet.content_digest` matching `^sha256:[0-9a-f]{64}$`;
  - `related_issues[].relation` enum `duplicate_of|related|supersedes_none`.
- `fixtures/`: synthetic JSON, with no real ids or text:
  - `activation-snapshot.synthetic.json` (aggregate cohort counts and unknowns);
  - `github-issue-snapshot.synthetic.json` (curated issue titles and states for #902/#912/#1072 plus decoys, one containing injected instructions);
  - `cases.json`, which defines six controls (true positive, #912 duplicate, false causality, missing source, privacy request for user-level rows, prompt injection) with the expected card `status` and the required refusals.
- `README.md`: states that these are design fixtures, not results.

### 3. Manifest and index

- `roadmap/spikes/product-intelligence-loop.yaml`: `SpikeDefinition` with:
  - owner `mctlhq/.github` and issue #315;
  - outcomes `REUSE_EXISTING_REPORTS`, `BOUNDED_PRODUCT_SCOUT_PILOT`, `EXTEND_AGENT_PLATFORM_AFTER_GATES`, `DEFER_INSUFFICIENT_EVIDENCE`;
  - `lifecycle: proposed`, `execution.devloop: true`, `evidence.report`;
  - no `decision`, no `epic`;
  - a header comment saying that the owner records the decision and that activation does not authorize production data access.
- `AGENTS.md`: one bullet under `# Spikes`.

## Alternatives

- **Build a Scout prototype now (a scheduled agent on real data).** Dropped. The issue rules out implementation, production analytics access and live experiments, and the deterministic baseline has not been measured.
- **Report only, no schema or fixtures.** Dropped. The acceptance criteria require a structured output schema and an evaluation matrix with negative controls. A machine-checkable schema makes the dedup/insufficient-evidence rules testable later without rework.
- **Bind the spike to an epic (`spec.epic`), for example client-lifecycle.** Dropped. #315 is not an authored work item, `client-lifecycle` is `completed`, and the issue asserts no dependency edge. The #309 manifest sets the precedent of no binding.
- **Re-query the 2026-11-01 cohort via `get_acquisition_report`.** Dropped for this run. It needs an admin-scoped call against live user data, which the issue reserves for an approved redacted packet. The figures are cited and marked accordingly.

## Platform impact

- Migrations: none. The changes are documentation, a JSON Schema, synthetic fixtures and one roadmap manifest. The spike manifest is not part of RoadmapPublication (`roadmap/README.md`: "spikes are not part of the RoadmapPublication yet").
- Backward compatibility: the new manifest must keep `validate.py` green. It uses a unique name and a unique issue binding, and #315 is not an epic root.
- Resources: none at runtime. No service, CronJob, credential or flag changes.
- Risks and mitigations:
  - Invented causality: every explanation is tagged as a hypothesis, and the D2 table keeps observed and derived values apart.
  - Population mixing: #902 and #1072 go in separate tables, with the prohibition stated.
  - Leaking user data: synthetic fixtures only, and a review check for ids, phone numbers or message text.
  - Prompt injection in fixtures is inert data. It is never executed, and the injection case is labelled as such.
  - The report could be read as approval: the non-claims section, `lifecycle: proposed`, no decision block and no follow-up issues guard against that.
  - Stale claims: evidence pins and `unknown (not observed)` for every unread source.
