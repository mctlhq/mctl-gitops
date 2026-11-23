# Design: issue-1398-spike-pa-natural-language-workflow-disco

Revision 3 (2026-11-23): research-only design for `docs/spikes/pa-workflow-discovery.md`. This supersedes the former PA-owned authority/store sketch with the owner-decided mctl-api Automation Control Plane. No adapter here exists in production.

## Current state

Historical baseline: mctl-telegram `9877b1d`, gitops `876a441` (2026-11-22). Revision-3 current pinned baseline and live checks are documented at the end; historical observations below are not current.

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
- **Data semantics for "unanswered".** `telegram.Message` in `internal/telegram/messages.go` has `id`, `peer`, `peer_title`, `from` (a display string from `resolveSender`), `text`, `date` and media. It has no outgoing flag and no reply-to id. `list_dialogs` returns `unread_count` and `last_message_date` (`internal/mcp/tools.go`). Unread is not unanswered. "Unanswered" is at best a heuristic: compare `from` against `get_my_identity`, then take the messages after the principal's last message. That is not reliable in groups, with edits, or with replies sent from another device. VERIFIED_CODE, and the heuristic itself is NOT_EXECUTED.
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
- VERIFIED_CODE. Production sets `ASSISTANT_REGISTRY_ENABLED: "true"` (VERIFIED_GITOPS_DESIRED, config only).

### Scheduling precedent in this repo

- `internal/digest/digest.go` is an in-process `time`-based daily or weekly digest to configured admin recipients via the login bot. It is a precedent for Bot API delivery. It is also exactly the kind of independent scheduler the issue forbids for user workflows.
- `internal/sweeper` runs background sweeps.
- No Temporal client exists in mctl-telegram: a grep for `temporal` under `internal` hits only a Glovo test import check.

### Historical deployment observations (2026-11-22; superseded below)

- `mctl_get_service_status(labs, mctl-telegram)`: ArgoCD Healthy and Synced, image `0.142.0`, host `tg.mctl.ai`, has a database.
- `mctl_get_service_status(labs, mctl-telegram-preview)`: Healthy and Synced, image `main-9877b1d` (the pinned SHA), host `tg-preview.mctl.ai`.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`: no `PA_*` variable appears. Since every switch fails closed, the PA is not enabled in production (VERIFIED_GITOPS_DESIRED of config; runtime env was not observed directly). The file sets `AGENT_ENABLED: "true"`, `AGENT_KILL_SWITCH: "false"` and `ASSISTANT_REGISTRY_ENABLED: "true"`, plus digest settings.
- [HISTORICAL] Preview previously had PA flags disabled and the PA worker at zero replicas. Revision 3's pinned GitOps and live Argo evidence below supersedes it.
- `$MCTL_GITOPS_ROOT/tenants/labs`: no PA reference found by grep.
- Not observed:
  - live pod env;
  - PA bot registration;
  - Vault paths;
  - any PA usage metrics;
  - the mctlhq/.github#318 and mctl-agents Temporal configuration.

  All are UNKNOWN and listed in Open questions. Exercise by a real user: UNKNOWN, with no evidence found.

## Proposed solution — revision 3 canonical adapter

### Implementation mapping (illustrative; normative requirements are in requirements.md)

This documents, but does not implement, the **already owner-decided EXTEND_MCTL_API** boundary of .github#318/#322. `mctl-api` owns `AutomationDefinition au_`, schedule and principal policy; WorkItems `wi_ → xr_ → we_` and a query-only `AutomationRun` VIEW are canonical. PA owns only draft/consent/source-bound adapter and the principal-only notification channel. The automation/v1 source contract is currently contract-only. It is **not** a deployed scheduling service. These aren't alternative stores.

```text
Telegram VerifiedUpdate → PAWorkflowDraft (peer picker, consent, tool pins)
      → explicit verified callback bound to draft digest
      → [future gated authenticated bridge / SurfaceIdentityLink]
      → mctl-api automation/v1 (canonical au_, owner/tenant/trigger)
      → Temporal → durable occurrence claim (wi_→xr_→we_)
      → [future server-verified PA scheduled principal context]
      → current read-only PA connector checks per tool call
      → PA private outbox → original verified principal only
```

**Claim/replay reference:** [mctl-api occurrence.go:74–101](https://github.com/mctlhq/mctl-api/blob/3233f6c0a00437f73021570d8a16253d2bcd524b/internal/automation/contract/occurrence.go#L74-L101) excludes definition version from `OccurrenceKey(au_id,trigger_kind,source)`; the admitted version is a separate snapshot. The [contract's durable-claim section](https://github.com/mctlhq/mctl-api/blob/3233f6c0a00437f73021570d8a16253d2bcd524b/docs/automation-contract.md) proposes a 30-day default tombstone but leaves the producer replay horizon to confirm. The first implementation slice must not assume the 30 days cover every source. Claim failure, unknown replay bounds and duplicate budget use fail closed.

**Edit/action fencing:** `NewInteractive(VerifiedUpdate)` and an interactive `conversationID` with 24-hour TTL are not a scheduled identity. A signed server-to-server occurrence must be bound to the existing, *currently verified* PA principal and a fresh per-occurrence context. At each dispatch and before bot send, compare the old admitted read set against **current** selected peer IDs, approved tool set, connection `authority_revision`, consent/data-flow, recipient and budget. A narrowing edit (e.g., remove Alice's peer from the allowed list, restrict model egress, lower cost ceiling, or change recipient) must fence the next read or send exactly like revoke/pause; an expanding edit is not activated without a new callback. Retaining a prior definition snapshot never preserves withdrawn authority.

**No-write / untrusted output:** the scheduler-facing `PAWorkflowDraft/v1alpha1` exposes pinned **read-only** `tg` tools, no write tool or forwarding destination, and cannot import an `AssistantInstall` MTProto write permission. Treat MCP responses as tainted and reject any model-inferred tool change or out-of-policy action; render the response through the existing `safetext.Render`/safe URL suppression boundary. A denied admission/read/send produces a content-free audit refusal receipt; if notification is blocked, store a safe receipt for the next principal-verified visit instead of sending past a revoke.

**Comparison:** `PA_EXTENSION` (standing PA store) is rejected; `CATALOG_COMPOSER` (MTProto authority) is rejected; `BOUNDED_HYBRID` is a PA draft/consent/delivery adapter over canonical mctl-api; `DEFER` remains the runtime recommendation until #322 and PA gates are separately authorized.

### Product model and storyboard

1. The user writes "Each evening, brief me on questions waiting for me in my work chats."
2. The PA asks clarifying questions: which chats (a picker from `list_dialogs`, chosen by the user), what time and time zone, and what counts as a question.
3. The PA shows the draft card: sources, tools, schedule, recipient "you only", data flow ("these messages go to the model provider under pa-data-flow/v1"), cost ceiling.
4. A synthetic dry run on a fixture (personas Alice, Bob, Carol, Dana), labelled SYNTHETIC.
5. The user taps a verified request-activation callback. This remains a synthetic storyboard until separately approved canonical automation implementation and PA bridge exist.
6. In a future separately approved rollout, mctl-api admits each occurrence and PA sends the principal-only receipt with canonical `au_`/`wi_`, sources, errors and cost; not a current live capability.
7. Feedback buttons: useful, not useful, wrong.
8. `/workflows` lists the workflows and offers edit, pause, revoke and delete.

The report compares this with a form or builder (the #1280 reference in `docs/spikes/assistant-builder-ui-reference.md`) and keeps Telegram first.

### Experiment, metrics and handoff

- **Stage 0.** A desk check of the spec and test matrix against the code (this spike).
- **Stage 1.** A CI-only synthetic harness (owner GO required), on the pattern of `internal/pa/worker_e2e_test.go` and `s1_suite_test.go`.
- **Stage 2.** A separately approved owner-only scheduled preview AFTER PA Phase 1 exit AND #322 canonical store/Temporal/verified-principal bridge, not merely the existence of #318's research contract.

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

### Negative-test matrix (all NOT_EXECUTED)

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
- edit while a run is in flight (synthetic): after a peer is removed, delivery recipient changed, consent narrowed or budget reduced, the old-version run is fenced at its NEXT read and outbound send, records a typed refusal and never reuses its old grant; an expanded grant requires fresh owner callback. Tombstone survives WorkItem cleanup for source replay horizon (default proposed 30d, actual source TBD).

## Alternatives

- **PA_EXTENSION (pure).** REJECTED as standing authority: would contradict owner-decided `.github#318/#322` and fork `automation/v1` in mctl-api. PA may still implement read-only proposal/draft UI and own PA-specific connection records.
- **CATALOG_COMPOSER.** Workflows become `Definition`/`Install` documents run by the catalog runtime. Rejected: that runtime acts as the user's MTProto account with the communication-agent tool set, and ADR 0011 rejects merging the two security models.
- **In-process scheduler in mctl-telegram** (like `internal/digest`). Rejected: it would be an independent scheduler with its own occurrence semantics, which contradicts #318 ownership.
- **DEFER.** This is the build recommendation until evidence closes PA Phase 1 exit, canonical `automation-api-store` and Temporal adapter (#322), a verified cross-surface/PA-principal bridge and action-time consent gates. The `automation/v1` contract itself already exists and is contract-only.

## Platform impact

- **Code.** No runtime change from this spike. One docs PR (a spike report) is proposed. No migration, flag, image or deployment.
- **Future impact, if built.** A future build would need:
  - an ADR 0011 addendum;
  - a new constructor, `NewScheduled`, producing the same `Policy`;
  - a future PA scheduled-job adapter with a fresh per-occurrence bounded context, using canonical `au_`/`occurrence_key`/`wi_` rather than any competing `pa_workflow_runs` ledger;
  - canonical mctl-api `AutomationDefinition au_`, durable claim/tombstones and Temporal adapter under the separately gated `.github#322` roadmap; a PA routine kill switch may be proposed but never owns standing automation authority;
  - a signed, verified principal-bound occurrence bridge from mctl-api to PA, independently checking the current PA connection/consent/flags on each dispatch and send;
  - possibly a tg pin change (a reply-to field).
- **Cost.** Each workflow occurrence is roughly one interactive job: one model run with up to 8 tool calls, capped by `PA_BUDGET_USD_JOB`. The report gives the formula only, since no measured cost exists.
- **Risks.**
  - Overclaiming readiness. Mitigation: the evidence labels; UNKNOWN is never read as absent.
  - The "unanswered" heuristic is unreliable. Mitigation: frame the brief as "messages since your last message", and measure H2 on synthetic data.
  - A scope collision with #318, #1325 or #1048. Mitigation: map interfaces to those issues only, and include no design of their internals.
  - Natural-language consent mistaken for authorization. Mitigation: callback-only activation bound to the digest.

## Revision 3 current evidence, source ledger and cross-issue architecture (2026-11-23)

**Current pinned evidence (2026-11-23):** mctl-telegram `ecbce7732fc2915a2a72dc21f1d1d2e9f8713d73`, mctl-gitops `869582d33b66f5eb36de29ff9b52c487f2631ed4`, mctl-api `3233f6c0a00437f73021570d8a16253d2bcd524b`, .github `60e9db522f18299e73dac23fffedfe5b4ce81930`. GitOps preview: image `main-6623542`, `PA_ENABLED=true`, `PA_EXTERNAL_TOOLS_ENABLED=true`, `PA_SERVER_TG_ENABLED=true`, `PA_WRITES_ENABLED=false`, `PA_SERVER_ALICE_ENABLED=false`, PA worker `replicaCount=1`; production `0.145.0`, no PA flags. Read-only live Argo checks 18:01–18:03Z were Healthy/Synced for these three services; this does not prove PA R1–R6 user success. #1317/#1319 remain open; S1 manifest body has no gaps. Older `9877b1d/876a441` and preview-disabled states are HISTORICAL, not current.

Grok Bot skills/routines: https://docs.x.ai/grok-bot/skills-routines-and-automations (checked 2026-11-23, VENDOR_DOCUMENTED); custom Remote HTTPS MCP: https://docs.x.ai/grok-bot/computer-and-apps (checked 2026-11-23, VENDOR_DOCUMENTED); Hermes `skill_manage`: https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md (checked 2026-11-23, PROJECT_DOCUMENTED); dots: https://openai.com/index/introducing-dots/ (checked 2026-11-23, VENDOR_DOCUMENTED); Gemini schedules: https://support.google.com/gemini/answer/17094710 (checked 2026-11-23, VENDOR_DOCUMENTED). No vendor feature implies MCTL deployment. For product detail and direct Grok/Town interop use #1379; durable PA memory/routines and Glovo remain HOLD in #1325.

**Review disposition:** PR #2937 initial 2 P1 findings addressed at the proposal-architecture level through the canonical adapter and version-independent occurrence key. Remaining PA prototype/contract is DESIGNED_ONLY; retain independent external review before owner approval. No new automation WorkItem is created.
