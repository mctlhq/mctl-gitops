# Design: issue-1398-spike-pa-natural-language-workflow-disco

This is the design of a research deliverable. The spike produces one report, `docs/spikes/pa-workflow-discovery.md`, with appendices, and changes no runtime code. Every contract below is **proposed, not production**.

## Current state

Pinned at mctl-telegram `9877b1d68ef7d2d969992023bd5fb49fe7835db6` (main, merge of #1396) and mctl-gitops `876a44144760e4bf9ca181b6f104cec06dc3fc7a`.

### PA (epic #1312, ADR 0011)

- **ADR status.** `docs/adr/0011-personal-assistant.md` is `Status: Proposed`. It defines:
  - Phases 0-4;
  - the `pa-data-flow/v1` consent;
  - the `ExecutionContext`;
  - the server-side connector executor;
  - the catalog pin;
  - tiers, the approval binding, taint, egress, limits, audit and switches.

  Routines and memory are Phase 4, and each needs an addendum (DESIGNED_ONLY).
- **Execution context.** `internal/pa/context.go` declares `TriggerInteractive`, `TriggerScheduled` and `TriggerEvent`, but only `NewInteractive` and `restoreInteractive` construct a context. `Policy` deliberately has no trigger accessor, and `TestPolicyHasNoTrigger` enforces that. Interactive is VERIFIED_CODE; scheduled and event are DESIGNED_ONLY. This is the key reuse point: a routine run can be a new constructor that yields the same `ExecutionContext` and `Policy`.
- **Run loop and jobs.** In `internal/pa/runloop.go`, claim, turn and reply re-check consent, the conversation, budget (the managed ledger reservation), the context size and the turn and tool caps. Every read failure is a refusal (I9). `AdmitPAToolCall` gates each tool call. `internal/pa/jobs/jobs.go`:
  - `Job` is keyed by `UpdateID` (an interactive Bot API update) and carries `ContextDigest` and the signed `ToolSet`;
  - `EnqueueRequest` has no trigger or occurrence field.

  VERIFIED_CODE. For routines this is a true gap: a job has no non-update origin.
- **Connector.** `internal/pa/connector/dispatch.go` and `execute.go` hold the executor pin check, the fresh `tools/list` (cached at most `catalog.ReadListingTTL`), the `ok` / `fenced` / `outcome_unknown` outcomes and the fail-closed audit sink (`storesink.go`). VERIFIED_CODE.
- **Catalog pin.** `internal/pa/catalog/pin.json` (schema `mctl-telegram.pa-catalog-pin/v1`) pins:
  - for `tg`: `get_messages`, `get_my_identity`, `list_dialogs`, `list_folders`, `list_topics`, `search_messages`;
  - for `alice`: four read tools.

  All are `tier: auto`, `class: read`. `get_unread_messages` is NOT pinned. `pin_phase2.json` exists for Phase 2. VERIFIED_CODE.
- **Data semantics for "unanswered".** `telegram.Message` in `internal/telegram/messages.go` has `id`, `peer`, `peer_title`, `from` (a display string from `resolveSender`), `text`, `date` and media. It has no outgoing flag and no reply-to id. `list_dialogs` returns `unread_count` and `last_message_date` (`internal/mcp/tools.go`). Unread is not unanswered. "Unanswered" is at best a heuristic: compare `from` against `get_my_identity`, then take the messages after the principal's last message. That is not reliable in groups, with edits, or with replies sent from another device. VERIFIED_CODE, and the heuristic itself is UNTESTED.
- **Connections, linking and gate.** `internal/pa/connection` (`state.go`, `scope.go`, `kek.go`) holds the state machine, the `authority_revision` and `token_generation` counters, and scope-ceiling verification. `internal/pa/linking` holds the Mini App `initData` flow, and `internal/pa/gate/decide.go` the tier decision. VERIFIED_CODE.
- **Memory.** `internal/pa/memory.go` has a `MemoryStore` interface and only `NoopMemoryStore`. DESIGNED_ONLY for real memory.
- **Gates.**
  - Current `docs/agent-runtime/pa-s1-manifest.yaml` has no gap rows in its manifest body; #1317 is still open and a gate-closing CI pass and #1319 R1-R6 exit have not been attested. No readiness inferred from a zero-gap grep.
  - `docs/agent-runtime/pa-s2-manifest.yaml` has 27 `pending` and 5 `green` rows, and states `PA_WRITES_ENABLED` stays off everywhere until it is clean.
- **Switches.** `PA_ENABLED`, `PA_EXTERNAL_TOOLS_ENABLED`, `PA_WRITES_ENABLED`, `PA_SERVER_<NAME>_ENABLED`, `PA_ALLOWED_PRINCIPALS` and `PA_BUDGET_USD_{JOB,DAY,MONTH}` are read in `cmd/server` (`pa_state.go`, `main.go`). Everything is inert unless `PA_ENABLED` is true.

### Assistant Catalog (#1002/#1280)

- `internal/assistant` has `Definition` (versioned, digest-pinned `Materialized` form), `Install`, `Resolve` and `resolveSchedule` (an `outside_hours` reply window, not a cron trigger). It also has fork and publish.
- `internal/assistantinstall` and `internal/assistantregistry` hold installs and the registry client. `assistants/hr-recruiter` is the one catalog entry. The schemas live in `assistants/schemas`.
- It runs as the user's MTProto account through the communication-agent worker (closed tool set, `internal/agentapi/toolgate.go`). ADR 0011 explicitly rejects extending `AssistantInstall` for the PA.
- VERIFIED_CODE. Production sets `ASSISTANT_REGISTRY_ENABLED: "true"` (VERIFIED_DEPLOYMENT, config only).

### Scheduling precedent in this repo

- `internal/digest/digest.go` is an in-process `time`-based daily or weekly digest to configured admin recipients via the login bot. It is a precedent for Bot API delivery. It is also exactly the kind of independent scheduler the issue forbids for user workflows.
- `internal/sweeper` runs background sweeps.
- No Temporal client exists in mctl-telegram: a grep for `temporal` under `internal` hits only a Glovo test import check.

### Deployed state checked

- `mctl_get_service_status(labs, mctl-telegram)`: ArgoCD Healthy and Synced, image `0.142.0`, host `tg.mctl.ai`, has a database.
- `mctl_get_service_status(labs, mctl-telegram-preview)`: Healthy and Synced, image `main-9877b1d` (the pinned SHA), host `tg-preview.mctl.ai`.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: no `PA_*` variable appears. Since every switch fails closed, the PA is not enabled in production (VERIFIED_DEPLOYMENT of config; runtime env was not observed directly). The file sets `AGENT_ENABLED: "true"`, `AGENT_KILL_SWITCH: "false"` and `ASSISTANT_REGISTRY_ENABLED: "true"`, plus digest settings.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: PA variables ARE present in the current GitOps main, but `PA_ENABLED=false`, `PA_EXTERNAL_TOOLS_ENABLED=false`, `PA_SERVER_TG_ENABLED=false`, `PA_WRITES_ENABLED=false`; the separate PA worker (`services/labs/agent-worker-pa-preview/values.yaml`) is scaled to zero. This is desired state, not live operation.
- `$MCTL_GITOPS_ROOT/tenants/labs`: no PA reference found by grep.
- Not observed:
  - live pod env;
  - PA bot registration;
  - Vault paths;
  - any PA usage metrics;
  - the mctlhq/.github#318 and mctl-agents Temporal configuration.

  All are UNKNOWN and listed in Open questions. Exercise by a real user: UNKNOWN, with no evidence found.

## Proposed solution

### Deliverable

The deliverable is `docs/spikes/pa-workflow-discovery.md` plus appendices (an inventory table, a diagram, the contract schema and the test matrix), delivered as a docs-only PR for independent review.

### Relationship diagram (to be rendered in the report)

```
               mctlhq/.github#318 trigger authority (Temporal schedules) [UNKNOWN contract]
                         | occurrence signal (workflow_id, version, occurrence_at, idem key)
                         v
Telegram user <-> PA bot (internal/pa: ingress, convo, runloop, jobs)
                         |  ExecutionContext{trigger=scheduled} -> same Policy, gates
                         v
                 managed runtime worker (ADR 0008, #1088) --pa-job token--> connector executor
                         |                                                   (pin, ceiling, revision,
                         v                                                    audit, egress)
                 tg / alice MCP servers (read tools only)

Assistant Catalog (internal/assistant Definition/Install) -- optional narrow adapter: definition
   template only, never install/authority; separate MTProto auto-reply runtime stays separate.
mctl-agents: DevLoop / platform agents; not on the PA data path.
```

### Recommendation: BOUNDED_HYBRID, leaning PA_EXTENSION

- **The PA owns** the workflow *instances* and their authority: the spec, its activation, the consent binding, the receipts, and pause, revoke and delete. Everything runs through the existing `ExecutionContext`, run loop, connector and audit.
- **Scheduling** is delegated to the #318 trigger authority. It only emits occurrence signals, and it holds no credentials or policy.
- **The Assistant Catalog** may later supply versioned *templates* (for example "daily-brief/v1") through a narrow, read-only adapter that copies a template into a PA draft. It never shares the install, tool set or runtime.

Until #318 publishes a contract and the PA Phase 1 gate closes, the build recommendation is DEFER. The research recommendation is BOUNDED_HYBRID.

### Proposed workflow spec (`pa-workflow/v1alpha1`, not production)

Fields:

- identity and versioning: `workflow_id`, `version` (a monotone integer), `principal`, `created_from` (conversation id and draft provenance per field: `user` or `model_suggested`);
- the job: `intent_text` (user provenance only), `sources` (connection id, `authority_revision`, server, and peer ids chosen by the principal from `list_dialogs` output, never inferred), `tools` (pinned name, schema hash, description hash);
- when to run: `schedule` (local time, IANA time zone, DST policy `skip|shift`);
- delivery: `delivery` (`pa_bot_private`, recipient equal to the principal, enforced, not a free field);
- limits and checks: `budget` (per run, per day), `success_checks`, `window` (lookback);
- consent and lifecycle: `consent_version`, `state` (`draft|active|paused|revoked|deleted`);
- `spec_digest`: SHA-256 of the canonical JSON, using the `internal/pa/catalog/canonical.go` style.

Rules:

- **Activation receipt.** It binds `spec_digest`, `authority_revision` per connection, `consent_version` and the pin hashes. It is created only by a verified `callback_query` on a server-rendered card. The model cannot create, widen or renew it, as with standing permissions in ADR 0011.
- **Edits.** An edit creates `version+1` and needs a new activation. The card shows a diff against the active version.
- **Revalidation per occurrence.** On every occurrence: switches, allowlist, principal disable, consent, connection state and revision equality, pin and fresh `tools/list` equality, budget reservation, and the audit append. Any mismatch produces a `refused:<reason>` receipt and one notice to the principal. Three consecutive refusals auto-pause the workflow (proposed; the count is an owner decision).
- **Idempotency.** The key is `H(workflow_id, version, occurrence_at)`, unique in a proposed `pa_workflow_runs` table. A duplicate trigger gives no second execution.
- **Retries.** A retrieval error is retried within the run's budget only for idempotent reads. The final error marks the brief `incomplete` with a named failing source. Delivery uses `output.Sender`, and `ErrOutcomeUnknown` is recorded `outcome_unknown` with no resend.
- **Taint.** Every tool output is external, so every workflow run is tainted from its first read. The contract carries no write tools. The brief is rendered through `safetext.Render` (T14: URL neutralisation, plain text).
- **Kill switch and isolation.** `PA_ENABLED=false` or a proposed `PA_ROUTINES_ENABLED=false` fails every occurrence closed. Owner pause is a state flip, checked at claim. All rows are keyed by principal, as `jobs.Ref` lookups are today.
- **Revocation and deletion.** `/disconnect` bumps `authority_revision`, so activations fail. `/consent withdraw` and delete cancel queued runs and erase specs and receipts beyond the retained audit digests.

### Product model and storyboard

1. The user writes "Each evening, brief me on questions waiting for me in my work chats."
2. The PA asks clarifying questions: which chats (a picker from `list_dialogs`, chosen by the user), what time and time zone, and what counts as a question.
3. The PA shows the draft card: sources, tools, schedule, recipient "you only", data flow ("these messages go to the model provider under pa-data-flow/v1"), cost ceiling.
4. A synthetic dry run on a fixture (personas Alice, Bob, Carol, Dana), labelled SYNTHETIC.
5. The user taps Activate (a verified callback).
6. Each evening the PA sends a brief with a receipt line: run id, sources read, sources failed, cost.
7. Feedback buttons: useful, not useful, wrong.
8. `/workflows` lists the workflows and offers edit, pause, revoke and delete.

The report compares this with a form or builder (the #1280 reference in `docs/spikes/assistant-builder-ui-reference.md`) and keeps Telegram first.

### Experiment, metrics and handoff

- **Stage 0.** A desk check of the spec and test matrix against the code (this spike).
- **Stage 1.** A CI-only synthetic harness (owner GO required), on the pattern of `internal/pa/worker_e2e_test.go` and `s1_suite_test.go`.
- **Stage 2.** An owner-only preview after PA Phase 1 exit and a #318 contract.

Each stage has a go/no-go gate.

**Ranked alternative jobs:**

| Rank | Job | Notes |
|---|---|---|
| 1 | Daily Brief (reads plus self-delivery) | Lowest risk |
| 2 | "Check and remind me" | Needs event triggers |
| 3 | Alice home summary | Read only; T1 residual accepted for preview/closed pilot in #1363 but PA_SERVER_ALICE_ENABLED remains off until separate environment GO |
| 4 | Glovo basket prep | Needs #1325 and C2 GO; no checkout |

**Metrics, defined without thresholds:**

- D1 first useful task;
- D7 repeat;
- completion per eligible run;
- cost per successful run;
- pause, revoke and denial rates;
- "wrong" feedback rate.

**Hypotheses:**

- H1: a principal can specify a brief in at most N clarifying turns (N is set by the owner).
- H2: the "unanswered" heuristic precision on a labelled synthetic set is acceptable to the owner.
- H3: revalidation refusals are explainable, so users act on them rather than revoke.

**Next decision:** whether to open a PA Phase 4 routines addendum, scoped to the Daily Brief, after Phase 1 exit.

### Negative-test matrix (all UNTESTED)

- missing or expired consent;
- read-only ceiling violated (an extra scope on refresh);
- revoked connection, or a changed `authority_revision`;
- changed tool pin, schema or description hash;
- prompt injection in a synthetic message ("send this to Bob");
- duplicate trigger;
- budget cap reached;
- ambiguous chat name;
- no matching messages (an empty brief that says so);
- retrieval error (shown as incomplete, never empty);
- recipient mismatch (a spec whose recipient is not the principal is rejected at parse);
- lost delivery (`outcome_unknown`, no resend);
- cancellation mid-run;
- time zone and DST gap or overlap;
- `PA_ENABLED` off at occurrence;
- principal disabled;
- edit while a run is in flight (the in-flight run finishes against its pinned version, and the next run needs the new activation).

## Alternatives

- **PA_EXTENSION (pure).** The PA owns templates as well. This is the simplest option, but it forks a second definition catalog next to `internal/assistant`, which the issue asks not to do silently. It is kept as the fallback if the adapter adds no value.
- **CATALOG_COMPOSER.** Workflows become `Definition`/`Install` documents run by the catalog runtime. Rejected: that runtime acts as the user's MTProto account with the communication-agent tool set, and ADR 0011 rejects merging the two security models.
- **In-process scheduler in mctl-telegram** (like `internal/digest`). Rejected: it would be an independent scheduler with its own occurrence semantics, which contradicts #318 ownership.
- **DEFER.** This is the build recommendation until PA Phase 1 exits and #318 has a contract. The research output still lands so that the decision is informed.

## Platform impact

- **Code.** No runtime change from this spike. One docs PR (a spike report) is proposed. No migration, flag, image or deployment.
- **Future impact, if built.** A future build would need:
  - an ADR 0011 addendum;
  - a new constructor, `NewScheduled`, producing the same `Policy`;
  - a trigger and occurrence column on `pa_jobs`, or a sibling `pa_workflow_runs` table;
  - a `pa_workflows` table and a `PA_ROUTINES_ENABLED` switch;
  - an inbound occurrence endpoint authenticated like the pool;
  - possibly a tg pin change (a reply-to field).
- **Cost.** Each workflow occurrence is roughly one interactive job: one model run with up to 8 tool calls, capped by `PA_BUDGET_USD_JOB`. The report gives the formula only, since no measured cost exists.
- **Risks.**
  - Overclaiming readiness. Mitigation: the evidence labels; UNKNOWN is never read as absent.
  - The "unanswered" heuristic is unreliable. Mitigation: frame the brief as "messages since your last message", and measure H2 on synthetic data.
  - A scope collision with #318, #1325 or #1048. Mitigation: map interfaces to those issues only, and include no design of their internals.
  - Natural-language consent mistaken for authorization. Mitigation: callback-only activation bound to the digest.

## Revision 2: source-pinned competitive product model and security reuse (2026-11-23)

### Competitive evidence ledger

| Competitor / pattern | Primary source | Evidence class | MCTL implication |
| --- | --- | --- | --- |
| Grok Bot: successful one-off job -> saved skill -> scheduled/event routine | https://docs.x.ai/grok-bot/skills-routines-and-automations | VENDOR_DOCUMENTED | Reusable user-visible recipe + independently approved occurrence; no auto-permission |
| Grok Bot: custom Remote HTTPS MCP and OAuth Client ID UX | https://docs.x.ai/grok-bot/computer-and-apps | VENDOR_DOCUMENTED | Simplify connector onboarding, never derive OAuth authority from UI |
| Hermes: agent-managed procedural skill knowledge | https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md | PROJECT_DOCUMENTED | Explicit review/version/digest/provenance for user-requested saved skills |
| dots: proactive and continued agent work | https://openai.com/index/introducing-dots/ | VENDOR_DOCUMENTED | Separate persistent job lifecycle from interactive chat; do not infer backend parity |
| Gemini scheduled task behavior | https://support.google.com/gemini/answer/17094710 | VENDOR_DOCUMENTED / verify eligibility | Capture user intent into a schedule with explicit limits and edit/revoke |
| Grok (grok.com) -> MCTL tg MCP | https://github.com/mctlhq/mctl-telegram/pull/1393 , #1381 | OWNER_OBSERVED_WORKS (2026-11-22) | External MCTL distribution works; product attribution to separately named Grok Bot still UNKNOWN |

### Authority model: skill != workflow != memory

1. **SkillDefinition** (proposed non-authoritative content): version, provenance, immutable digest, required inputs/tool references, checkable expected output; no executable code by default, no OAuth tokens, no scheduled triggers, no self-grant. A proposed auto-learned skill remains DRAFT until user review.
2. **WorkflowInstance** (proposed authority): principal, source peer IDs selected by user, connection IDs + authority_revision, pinned schema/description hashes, consent version, budget, a schedule/occurrence binding, explicit activation receipt. Every modification creates a new version/digest and requires renewed approval.
3. **MemoryItem** (future #1325): user facts/preferences with explicit source and confidence, TTL/retention, inspect/correct/delete operations; external taint is preserved. No memory entry can authorize a tool or change a scope ceiling.

Both interactive and scheduled runs must reuse the existing PA ExecutionContext, connector executor and audit. Scheduling is only a signal from existing #318 authority; no new cron, shadow memory database or agent runtime. A task may fail incomplete, fenced or outcome_unknown and must not silently retry a write or interpret a tool failure as an empty result.

### Minimum synthetic product journey

User: 'Every workday at 09:00, summarize the selected Telegram chats for me.' -> draft (choose chats, timezone, principal-only private Bot delivery, budget) -> synthetic dry-run -> immutable digest/authority preview -> explicit activation callback -> schedule occurrence id H(workflow_id, version, occurrence_at) -> revalidate flags, consent, allowlist, revision, pin, budget and recipient -> audited read-only execution -> safe answer / actionable incomplete receipt -> pause/edit/revoke. All steps after draft are DESIGNED_ONLY pending approvals; no real chat data or sends.

### Corrected current baseline

Current GitOps: production mctl-telegram image tag 0.143.0 with no PA variables, preview main-3aab3cb with PA feature flags false, PA worker at replicaCount 0. This supersedes the 2026-11-22 historical 'preview has no PA variables' line, which was accurate only at its older pin. R1-R6 #1319 and the S1 gate still require direct evidence. The external Grok Web connection is not a test of the MCTL PA.

**Recommendation:** BOUNDED_HYBRID for research (PA owns instances and authority; optional Catalog template adapter; #318 provides trigger occurrences), DEFER implementation. Do not submit a second assistant, grant, scheduler, or memory subsystem.
