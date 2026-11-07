# Spike: MCTL Automation Control Plane (Temporal-backed Automation MCP across surfaces)

## Context

Issue mctlhq/.github#318 is a research spike. It asks whether MCTL can offer
durable, user-owned automations: a one-shot time (`at`), a recurring schedule,
or an authenticated external event or dependency trigger. Each automation is
created from Claude, ChatGPT or Telegram (and, in a narrow form, from MCTL
Assistant and mctl-support). The same automation can then be seen, edited,
paused and revoked from any authorized surface. Runs would use the Temporal and
agent execution primitives MCTL already has, with no second scheduler and no
way around tenant or agent authority. The spike has to pick exactly one
outcome: `COMPOSE_EXISTING_ONLY`, `EXTEND_MCTL_API`,
`DEDICATED_AUTOMATION_SERVICE` or `DEFER_WITH_GAPS`. That choice must rest on
an inventory, a contract, a threat model and an inert, non-production harness.
The owner records the decision. The spike does not implement anything.

This matters for three reasons. Some of the needed pieces are already
deployed: a Temporal worker that owns system schedules
(`admins/mctl-agents-worker`, namespace `mctl-agents`), canonical WorkItems
from the `surfaces` epic, the events envelope v1 in this repo, and the
tenant-bound support agent over A2A. A naive automation feature would
duplicate these stores and authorities: a second scheduler, a second identity
key, or a second approval path. The spike follows the repo's existing pattern
for spikes. The report goes under `docs/spikes/`, a `SpikeDefinition` with
`lifecycle: proposed` goes under `roadmap/spikes/`, and the reference model
runs in CI from `.github/workflows/workflow-tests.yml`, as
`docs/spikes/mcp-gateway-g0/` does.

## User stories

- AS a tenant user on Claude, ChatGPT or Telegram I WANT to say "remind me tomorrow at 09:00", "check prices every Friday" or "when CI fails, investigate and notify me" SO THAT the work happens durably after the chat session ends.
- AS a tenant user I WANT to see, edit, pause, resume and delete the same automation from any surface I am authorized on SO THAT the automation is not tied to the chat that created it.
- AS the platform owner I WANT one evidence-backed verdict among the four declared outcomes SO THAT implementation ownership and any epic are chosen from evidence, not assumed.
- AS a security reviewer I WANT a threat model and negative fixtures (forged and replayed events, cross-tenant access, revoked installs, budget exceeded, raw Temporal workflow requests) SO THAT any later implementation inherits tested refusal semantics.
- AS the mctl-support operator I WANT support-created follow-ups to be tenant-bound, read-only by default, bounded in lifetime and budget, and explicitly authorized SO THAT support can never schedule privileged mutations or reach another tenant.
- AS a FinOps reviewer I WANT per-execution budgets, per-owner ceilings and no double spend on duplicate delivery SO THAT recurring and event-driven automations cannot run away on cost.

## Acceptance criteria (EARS)

Deliverables and repository artifacts

- WHEN the spike is delivered THE SYSTEM SHALL add the report `docs/spikes/automation-control-plane.md` containing D1 to D5 as defined in the issue, with an evidence-pins table of 40-hex commits per repository read and evidence tags (`[CODE]`, `[CONFIG]`, `[LIVE]`, `[DOC]`, `[GIT]`), following `docs/spikes/journey-intent-correlation.md`.
- WHEN the spike is delivered THE SYSTEM SHALL add `roadmap/spikes/automation-control-plane.yaml`, a `SpikeDefinition` valid against `roadmap/schemas/spike-definition.schema.json` with `lifecycle: proposed`, `github.issue` = mctlhq/.github#318, the four outcomes from the issue, `execution.devloop: true`, `evidence.report` pointing at the report, and no `decision` and no `epic` block.
- WHEN the spike is delivered THE SYSTEM SHALL add an entry for the report under the `# Spikes` heading of `AGENTS.md`.
- WHEN the reference model is added under `docs/spikes/automation-control-plane/` THE SYSTEM SHALL run it in `.github/workflows/workflow-tests.yml` as a separate Go step (`go vet ./... && go test ./...`), with no network, no Temporal server, no credentials and no third-party module dependencies.

D1 inventory

- WHEN D1 is written THE SYSTEM SHALL list, for each of mctl-agents system Temporal schedules, the mctl-api Temporal client and MCP surface, AgentDefinition/ExecutionProfile/ReleaseBinding, the WorkItem API (`surfaces` epic), MCP Tasks (#41, mctl-api#284), attention routing (mctl-agents#757), events envelope v1 (`events/`), Assistant Catalog (mctl-telegram#1002), Managed Runtime (mctl-telegram#1088), the support A2A task store (#243), and the usage ledger (`agent-finops`): its owner repository, its canonical store, and whether it is deployed, flagged or planned, with a source link or an explicit `unknown (not observed)`.
- IF a component's deployed state could not be read THEN THE SYSTEM SHALL record it as `unknown (not observed)` and SHALL NOT report it as absent or off.

D2 contract and threat model

- WHEN D2 is written THE SYSTEM SHALL define `AutomationDefinition v0` with: an opaque `automation_id` (prefix `au_`), tenant, owner principal, delegated actor and creating surface; a registered template reference (never a raw `workflow_type`, `task_queue`, namespace or signal name); a pinned agent/profile/install revision or a named resolution policy; trigger; inputs; delivery policy; policy snapshot reference; budget and limits; lifecycle `enabled | paused | deleted`; TTL and retention; provenance; and last and next execution. Individual executions SHALL be a separate `AutomationRun` record that references a WorkItem execution (`we_`) rather than a parallel execution store.
- WHEN an `at` trigger is specified THE SYSTEM SHALL require an absolute local timestamp plus an IANA timezone, and SHALL define how a nonexistent local time (DST spring-forward) and an ambiguous one (fall-back) resolve.
- WHEN a `schedule` trigger is specified THE SYSTEM SHALL define interval and cron forms with timezone, start/end, a catch-up window for misfires, and an overlap policy chosen from a closed set that maps to Temporal Schedule overlap policies (skip, buffer-one, cancel-other, allow-all), with skip as the default.
- WHEN an `event` trigger is specified THE SYSTEM SHALL accept only events from the closed set of verified ingress streams in `events/README.md`, filtered by an allowlisted `type` and `subject` match, and deduplicated by envelope `id`. A `dependency` trigger SHALL be modelled as an event trigger on an observed state transition, not as a new trigger mechanism.
- WHEN D2 defines ingress handling THE SYSTEM SHALL state the rule for starting a new workflow versus Signal/Update-with-Start on an existing one, keyed on automation id plus event dedupe key.
- WHEN D2 defines the MCP/REST contract THE SYSTEM SHALL specify `mctl_create_automation`, `mctl_list_automations`, `mctl_get_automation`, `mctl_update_automation`, `mctl_pause_automation`, `mctl_resume_automation`, `mctl_delete_automation`, `mctl_run_automation` and a bounded run-history read. Each SHALL have a JSON schema, a required idempotency key on mutations, an `expected_version` optimistic precondition on updates, cursor pagination and a closed error vocabulary. The contract SHALL state how it differs from MCP Tasks: a task is one execution, an automation is a standing intent.
- WHEN D2 includes the threat model THE SYSTEM SHALL cover forged and replayed ingress, cross-tenant read/create, confused-deputy delegation from support and assistants, revoked install or revision, schedule storms, event loops and fanout, budget exhaustion, secret exposure in inputs, and LLM-supplied raw Temporal parameters.

D3 diagrams and matrices

- WHEN D3 is written THE SYSTEM SHALL include sequence diagrams (Mermaid) for create, update/pause, trigger (`at`, `schedule`, `event`), revoke, recover, inspect and deliver across Claude, ChatGPT and Telegram, and SHALL show that the same `automation_id` survives every surface.
- WHEN D3 is written THE SYSTEM SHALL include a permission matrix (owner, delegated assistant, mctl-support, platform admin, system schedule) and a cost matrix (per-run budget, per-owner and per-tenant ceilings, concurrency and fanout caps).

D4 reference model and fixtures

- WHEN the reference model runs THE SYSTEM SHALL demonstrate, under an injected fake clock and mocked agent execution: (1) an `at` one-shot firing exactly once, including across a DST transition; (2) a recurring schedule with overlap and catch-up behaviour; (3) a signed webhook to envelope to new-run or signal decision; (4) a support diagnostic follow-up that is tenant-bound, read-only and TTL-bounded.
- WHEN a forged event (bad signature), a replayed event (outside the replay window or a duplicate `id`), an overlapping or burst fire, a cross-tenant inspect or create, a revoked install/revision, an exceeded budget, a worker crash mid-run, a delivery failure or a raw-Temporal-workflow request is presented THE SYSTEM SHALL refuse it, or recover from it, with a named, asserted outcome in a negative fixture.
- WHILE an automation fires THE SYSTEM SHALL re-evaluate owner, tenant membership, install revision and policy on every fire, not only at creation.
- IF the same trigger is delivered more than once THEN THE SYSTEM SHALL start at most one run and SHALL reserve and settle budget at most once for it.
- IF an automation is deleted or its install is revoked while a run is in flight THEN THE SYSTEM SHALL stop future fires and SHALL NOT silently terminate the in-flight run. The documented semantics SHALL say how that run finishes or is cancelled explicitly.
- WHEN measured evidence is reported THE SYSTEM SHALL state that it comes from the reference model, not from Temporal or production, and SHALL list what a Temporal dev-server proof would still need to confirm.

D5 verdict

- WHEN D5 is written THE SYSTEM SHALL propose exactly one of the four outcomes, with an A/B/C/D comparison, a technology comparison (mctl-api Go SDK plus existing MCP, mctl-agents Python schedule utilities, official read-only temporalio temporal-mcp, a community Python SDK MCP, a TypeScript HTTP MCP), a repository ownership map, rollout and rollback proposals, and measurable operational and cost targets.
- WHEN D5 is written THE SYSTEM SHALL state Telegram as the first delivery proof and SHALL mark ChatGPT same-chat push as `unknown`, referenced to mctlhq/.github#300, and not an acceptance dependency.
- IF the owner has not recorded a decision THEN THE SYSTEM SHALL keep the manifest at `lifecycle: proposed` and SHALL list follow-up issues as unfiled candidates only.

## Out of scope

- Implementing, deploying or flag-enabling any production endpoint, worker, Temporal schedule or GitOps change; creating real user automations.
- Replacing Temporal or Argo, rebuilding ChatGPT Scheduled Tasks, or introducing a second scheduler or approval authority.
- Arbitrary recurring user shell or LLM code, cross-tenant support operations, broad outbound Telegram messaging, production credentials, and paid inference.
- Claiming that a message can be injected into an existing ChatGPT chat (that is #300's question).
- Changing the assistant or managed-runtime rollout gates.
- Filing follow-up issues, creating an epic or binding the spike to an epic, and approving any implementation.
- Exposing raw cluster-admin Temporal tools to agents.

## Open questions

- Which repository owns the reference model and report? Assumption: `mctlhq/.github`, as the issue states, with the reference model under `docs/spikes/automation-control-plane/` like `mcp-gateway-g0`.
- Is a real Temporal dev server (`temporal server start-dev`) allowed in the harness? Assumption: no. The CI model stays stdlib Go with a fake clock. An optional local Temporal proof is listed as a follow-up the reviewer can request, so semantics such as Schedule catch-up and overlap are modelled from the Temporal documentation and remain unproven against a server.
- The deployed state of mctl-api and mctl-telegram could not be observed. `mctl_list_services(admins)` lists neither, matching the gap recorded in `docs/spikes/journey-intent-correlation.md`. D1 must pin their source revisions and mark the runtime state `unknown (not observed)` unless an operator read is obtained.
- Which Temporal namespace should user automations use: the existing `mctl-agents` namespace (system schedules) or a separate least-privilege namespace? The spike evaluates both. The default recommendation to test is a separate namespace or, at minimum, a separate task queue and Search Attribute tenant filter.
- Consent mapping between ChatGPT, Claude and Telegram principals relies on the `unified-identity` linked external identities. Whether a Telegram AssistantInstall principal resolves to the same canonical principal as the MCP OAuth subject is unverified.
- The timebox `decisionBy` is not given in the issue. Assumption: 2026-12-15, aligned with #41, because MCP Tasks overlap is a core comparison.
