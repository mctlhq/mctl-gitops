# Spike report: shared team assistants with governed skills, approved shared memory, tenancy and unit economics (mctlhq/.github#309)

## Context

Issue mctlhq/.github#309 is a P3 discovery spike, marked PROPOSED / NOT ACTIVATED. Its question: what is the smallest additive, governed and economically sustainable change to the existing MCTL Assistant Catalog (mctlhq/mctl-telegram#1002) and Managed Runtime (mctlhq/mctl-telegram#1088, `roadmap/epics/telegram-managed-runtime.yaml`) that would let many authorized users and channels share one expert-maintained team assistant? That assistant would need a versioned skill set, approved shared memory, per-user access context and auditable costs. The external trigger (the xAI Data Bot announcement and press reports of high Grok Bot costs) only illustrates a product experience. It is not an architecture or a cost benchmark.

The deliverable is evidence, not runtime code. It is a spike report at `docs/spikes/team-assistants-shared-skills-memory-economics.md` (the canonical target the issue names), plus a `SpikeDefinition` manifest under `roadmap/spikes/` that records the question and allowed outcomes in Git before the verdict is known. The report also includes synthetic acceptance fixtures written as specifications. The report proposes one verdict from `EXTEND_EXISTING`, `EXTEND_AFTER_GATES`, `DEFER_UNIT_ECONOMICS` and `REJECT_FOR_MCTL`. The owner records the decision, never the agent. Nothing in this proposal changes GitOps, flags, production traffic, paid inference or the managed-runtime gates (mctl-telegram#889, #334).

## User stories

- AS the product owner of the Assistant Catalog I WANT a grounded capability-vs-gap matrix and an A/B/C decision matrix SO THAT I can decide whether shared team assistants extend #1002/#1088 or need a separate owner.
- AS a security reviewer I WANT explicit identity, memory-approval and connector invariants plus a threat-model delta against mctl-telegram#1048 SO THAT a shared assistant cannot leak one member's data to another or grant itself tools.
- AS a FinOps owner I WANT cost per successful answer, weekly report and complex investigation built only from measured MCTL usage or labelled assumptions SO THAT pricing decisions are not based on invented margins.
- AS a later implementer I WANT executable acceptance fixtures (specifications, not code) for the team-analytics weekly-report workflow SO THAT any follow-up slice has a fixed definition of done.
- AS the roadmap maintainer I WANT the spike recorded as a valid `SpikeDefinition` with no `decision` block SO THAT roadmap validation passes and no implementation starts automatically.

## Acceptance criteria (EARS)

- WHEN the spike is delivered THE SYSTEM SHALL add `docs/spikes/team-assistants-shared-skills-memory-economics.md` containing the six deliverables named in #309: the capability/gap matrix, the A/B/C decision matrix with a recommended smallest extension, the lifecycle diagrams and invariants with the #1048 threat-model delta, the quantitative model, the synthetic acceptance/eval matrix, and the proposed follow-up issue map.
- WHEN the spike is delivered THE SYSTEM SHALL add `roadmap/spikes/team-assistants-shared-skills-memory-economics.yaml` (`kind: SpikeDefinition`) bound to `mctlhq/.github#309`, with outcomes exactly `EXTEND_EXISTING`, `EXTEND_AFTER_GATES`, `DEFER_UNIT_ECONOMICS` and `REJECT_FOR_MCTL`, `evidence.report` pointing at the report, and no `decision` block.
- WHEN `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` runs on the change THE SYSTEM SHALL exit 0.
- WHEN the report is added THE SYSTEM SHALL add one index line under `# Spikes` in `AGENTS.md` that links the report and names the proposed verdict.
- WHILE the owner has not recorded a decision THE SYSTEM SHALL keep the manifest at `lifecycle: proposed` (or `active` with a `timebox.decisionBy` date only if the owner has explicitly activated #309), and the report SHALL label its verdict "proposed".
- THE SYSTEM SHALL tag every factual claim in the report with an evidence class (`[CODE]`, `[CONFIG]`, `[LIVE]`, `[DOC]`, `[ASSUMPTION]`). Every capability row SHALL also carry one status from implemented, flag-gated, planned, missing or unverified, with the exact repo/issue/path it rests on.
- IF a source could not be read (repo not cloned, MCP call refused, value not observed) THEN THE SYSTEM SHALL record it as `unknown (not observed)` and never as absent or off.
- THE SYSTEM SHALL evaluate options A (immutable definition plus per-member installs plus explicit team binding), B (organization-owned install with per-user delegated session) and C (team chat surface wrapping per-account installs). For each option it SHALL state who owns, grants, edits skills, revokes, pauses, receives notifications, pays and can see audit history, with Telegram as the primary surface and Slack as a paper-only portability test.
- THE SYSTEM SHALL NOT treat a Telegram account as an organization, and SHALL NOT infer actor authority from channel membership. Authority SHALL be traced to the canonical principal / tenant membership contract from the completed `unified-identity` epic (`roadmap/epics/unified-identity.yaml`, issues #373, #376, #377).
- THE SYSTEM SHALL specify a shared-memory lifecycle (proposal, classification, human reviewer approval bound to content digest + source + tenant + visibility scope + expiry, immutable publish, audit/revoke/forget). That lifecycle SHALL state as an invariant that a model cannot approve its own memory publication.
- THE SYSTEM SHALL state as an invariant that a skill or prompt revision can never widen the tool set or permission ceiling of an install. The permission ceiling SHALL remain owned by the existing AgentDefinition / ExecutionProfile / registry contracts (`roadmap/epics/agent-platform.yaml`).
- WHEN computing unit economics THE SYSTEM SHALL use only measured MCTL usage (agent-finops ledger, managed-runtime usage ledger mctl-telegram#1092, preview soak results) or `[ASSUMPTION]`-labelled inputs. It SHALL separate model COGS, cloud infrastructure and customer price, and SHALL report p50/p95 per workload class, or name the missing measurement that prevents them.
- IF the managed-runtime preview soak (#1088 success criterion: at least 30 managed jobs) has not produced p50/p95 cost-per-job data THEN THE SYSTEM SHALL bound costs only by the configured caps it observed (for example `MANAGED_MAX_JOB_COST_USD`) and SHALL list the soak as a measurement gate.
- THE SYSTEM SHALL include at least the eight acceptance scenarios listed under T6 of #309 as fixtures for a synthetic tenant (3 users: expert manager, authorized colleague, unauthorized colleague; 2 channels; mocked analytics tool). Negative and fault cases SHALL be included, and each fixture SHALL name its expected observable outcome.
- THE SYSTEM SHALL present the follow-up issue map as proposals only (owning repo, dependency, priority, product-UX vs runtime-architecture class) and SHALL NOT create any GitHub issue, epic work item or implementation PR.
- IF the evidence shows an option needs a second agent registry, definition format, orchestration engine or billing system THEN THE SYSTEM SHALL rate that option as conflicting with #18 / #173 scope.

## Out of scope

- Any runtime code, schema migration, GitOps change, flag flip, provisioning of paid inference or production traffic.
- Building a Slack connector or any MCP connector. Authorizing warehouse/CRM access (owned by mctl-telegram#1048 and its gates).
- Changing the scope of #1002 P4/P5, the #1088 work items, or the managed-runtime gates #889 / #334.
- Billing, pricing or entitlement implementation (Agent Commerce, `docs/plans/agent-commerce.md`).
- Creating follow-up issues or epic work items, and recording the spike `decision` block.
- Starting DevLoop/intake for any follow-up.

## Open questions

- Activation conflict: #309 says "do not start DevLoop/intake ... without an explicit owner decision", yet this proposal was produced by a DevLoop investigation. This proposal assumes the reviewer's approval of this proposal counts as the explicit activation of the spike. Reviewers who disagree should reject or hold it. In that case the manifest should land as `proposed` with no report, or not land at all.
- Timebox date: the issue gives "5 working days after explicit activation". If activated, `timebox.decisionBy` must be set from the activation date, which is unknown here.
- Access to sibling repositories: grounding the gap matrix needs pinned reads of mctl-telegram (AssistantInstall, assistant registry, managed runtime, ledger), mctl-api (assistant catalog, WorkItem, approvals, usage ledger) and mctl-agents (#989 memory tiers). This clone contains only `mctlhq/.github`. Rows the implementer cannot read must be marked unverified.
- Preview soak data: whether the #1088 preview soak has produced cost-per-job p50/p95 by the time the report is written. At investigation time `agent-worker-managed-preview` runs 1 replica, but the GitOps comment says no account was yet on the managed runtime.
- Whether MCTL already has an organization/team grouping above `tenant` that maps to "team" in the Telegram assistant sense. The completed unified-identity epic provides principals and tenant membership. Whether a Telegram account is linked to a canonical principal for assistant installs is not verified here.
