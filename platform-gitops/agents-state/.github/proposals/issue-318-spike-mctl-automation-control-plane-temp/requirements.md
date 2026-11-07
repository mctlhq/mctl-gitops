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

- WHEN D2 is written THE SYSTEM SHALL define `AutomationDefinition v0` with: an opaque `automation_id` (prefix `au_`), tenant, owner principal, delegated actor and creating surface; a registered template reference (never a raw `workflow_type`, `task_queue`, namespace or signal name); a pinned agent/profile/install revision or a named resolution policy; trigger; inputs; delivery policy; policy snapshot reference; budget and limits; lifecycle `enabled | paused | deleted`; TTL and retention; provenance; and last and next execution. Each fire SHALL create or idempotently reuse a **distinct WorkItem (`wi_`)** keyed by `(automation_id, occurrence/event_id)` and routed through the existing `ExecutionRequest` (`xr_`) / `WorkItemExecution` (`we_`) contract. `AutomationRun` SHALL be a derived view of the per-fire `wi_`/`we_`, not a second execution store. A recurring automation SHALL NOT attach all fires to one standing WorkItem: `workitem/v1` allows at most one non-terminal execution per WorkItem, while Temporal overlap policies may permit multiple concurrent fires. The canonical `au_` stays stable across surfaces.
- WHEN an `at` trigger is specified THE SYSTEM SHALL require a well-defined instant (offset-aware timestamp, or local timestamp plus IANA timezone and explicit ambiguity policy), and SHALL define DST gap/overlap handling based on **observed Temporal behavior**, with any product-specific shift/first-occurrence normalization implemented and proved explicitly rather than assumed.
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
- WHILE an automation fires THE SYSTEM SHALL re-evaluate owner, tenant membership, install revision and policy on every fire, not only at creation. BEFORE **each consequential external action** (including Telegram send and deployment/mutation tools) it SHALL also perform an action-time policy/revocation checkpoint using the existing server-side authority, with a negative fixture where permissions are revoked mid-run.
- IF the same trigger is delivered more than once THEN THE SYSTEM SHALL start at most one run and SHALL reserve and settle budget at most once for it.
- IF an automation is deleted or its install is revoked while a run is in flight THEN THE SYSTEM SHALL stop future fires and SHALL NOT silently terminate the in-flight run. The documented semantics SHALL say how that run finishes or is cancelled explicitly.
- WHEN measured evidence is reported THE SYSTEM SHALL distinguish **fake-clock reference-model results** from **real non-production Temporal dev-server integration results**. At least one integration test SHALL create a real Temporal Schedule through a pinned Temporal SDK, execute a registered inert workflow with a real worker, and assert the actual workflow result and Schedule state. An unavailable, skipped or failed Temporal integration test SHALL block the research PR from claiming D4 complete; no production Temporal endpoint is permitted.

D5 verdict

Additional blocking research requirements (owner review, 2026-11-07)

- WHEN overlapping fires are possible THE SYSTEM SHALL materialize **different** `wi_` records per occurrence and permit at most one active `we_` within each `wi_`; it SHALL prove deterministic per-fire idempotency, a stable parent `au_`, and no parallel run-state DB. A test SHALL create two simultaneous fires for the same `au_`, each with a different `wi_`.
- WHEN schedule creation, update, pause, resume or delete spans Postgres and Temporal THE SYSTEM SHALL define a crash-safe desired/observed reconciliation protocol (intent persisted first, idempotent apply, owner/tenant auth checked, safe orphan detection, retry and repair), with a failure-injection test for the crash after Temporal accepted a Schedule but before the API recorded success.
- WHEN an external event is used THE SYSTEM SHALL verify webhook authenticity at the ingress producer, enforce tenant binding during hydration, and distinguish **supported event types now** (existing Telegram and GitHub PR/review envelopes) from proposed CI `check_run`/`workflow_run` producers, which require separate tested ingestion and are not available merely because a GitHub event is desired.
- WHEN identity is resolved across ChatGPT, Claude and Telegram THE SYSTEM SHALL prove canonical principal linkage (`SurfaceIdentityLink`) or refuse cross-surface ownership/modification; an unverified identity may not be accepted as equivalent.
- WHEN temporal integration is run THE SYSTEM SHALL record CLI/server version, SDK version, the command/check name, Schedule id, workflow id, observed outcome and any divergences from the model; a model-only success SHALL NOT satisfy D4.

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
- A real isolated Temporal dev server (`temporal server start-dev`) is **required** for at least one automated, non-skipped SDK integration test in CI (or an equally enforced, reproducible required check). It MUST use synthetic data, localhost, a disposable namespace, a pinned CLI/server + SDK version, explicit cleanup and no production credentials. The stdlib Go fake-clock model remains a separate fast test suite; real and simulated evidence are never conflated.
- The deployed state of mctl-api and mctl-telegram could not be observed. `mctl_list_services(admins)` lists neither, matching the gap recorded in `docs/spikes/journey-intent-correlation.md`. D1 must pin their source revisions and mark the runtime state `unknown (not observed)` unless an operator read is obtained.
- Which Temporal namespace should user automations use: the existing `mctl-agents` namespace (system schedules) or a separate least-privilege namespace? The spike evaluates both. The default recommendation to test is a separate namespace or, at minimum, a separate task queue and Search Attribute tenant filter.
- Consent mapping between ChatGPT, Claude and Telegram principals relies on the `unified-identity` linked external identities. Whether a Telegram AssistantInstall principal resolves to the same canonical principal as the MCP OAuth subject is unverified.
- The timebox `decisionBy` is not given in the issue. Assumption: 2026-12-15, aligned with #41, because MCP Tasks overlap is a core comparison.
