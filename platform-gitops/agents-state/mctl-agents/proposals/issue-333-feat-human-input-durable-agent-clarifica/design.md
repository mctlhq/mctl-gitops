# Design: issue-333-feat-human-input-durable-agent-clarifica

## Current state

### The approval primitive that exists

`DevLoopWorkflow` (`orchestrator/temporal/workflows/dev_loop.py:713`) is the only
durable human-in-the-loop today. Its shape:

- one signal, `approve(self, *args: object)` (`dev_loop.py:788`), with **no
  payload dataclass** — it parses `{"approver": ...}` or a bare string
  defensively and sets `self._approved = True` (`dev_loop.py:800`);
- one unbounded durable wait, `await workflow.wait_condition(lambda:
  self._approved)` (`dev_loop.py:827`) — the file's only `wait_condition`, with
  no timeout;
- two queries, `shepherd_in_loop` (`:754`) and `lifecycle_claim` (`:767`);
- state carried as plain `__init__` fields (`:714-751`), never an enum.

There is **no workflow-phase vocabulary at all**. Phase is implicit in the
program counter. The only state strings in the module are
`WorkflowResult.phase` (`"Succeeded" | "Failed" | "Error"`,
`activities/argo.py:71`), `DeployObservation.outcome`, `PRState.state`, and the
lifecycle verdicts imported from `orchestrator/lifecycle/contract.py:231-234`.
So "`WAITING_FOR_INPUT` must be distinguishable from `WAITING_FOR_APPROVAL`" is
not a matter of splitting an enum — both names have to be introduced.

Every model step goes through one funnel, `_run_cwft(operation, params, *,
step_timeout)` (`dev_loop.py:483`), which executes the `submit_and_wait`
activity (`activities/argo.py:93`). Four operations use it:
`mctl-agents-investigate` (`:817`), `mctl-agents-approve` (`:897`),
`mctl-agents-implement` (`:957`), `mctl-agents-shepherd` (`:1268`). The
activity returns `WorkflowResult` — `workflow_name`, `phase`, `started_at`,
`finished_at` and nothing else. **There is no channel for a typed step outcome
from the Argo pod back to Temporal**, and adding one is an mctl-api change,
outside this DevLoop's boundary.

Every behavioural change to this workflow is gated by `workflow.patched`;
twelve markers exist (`exec-queue` `:499`, `registry-required` `:646,677`,
`atomic-approve` `:864`, `slug-scoped-implement` `:869`, `merge-detection`
`:966`, `deploy-observation` `:980`, `incident-watch` `:991`,
`lifecycle-refusal-backoff` `:1572`, `fast-shepherd-cadence` `:2245`,
`shepherd-in-loop` `:2247`, `concurrent-shepherd-tick` `:2281`,
`lifecycle-ownership` `:2286`). `deprecate_patch` is never called; migration is
by attrition (`dev_loop.py:491-498`, pinned by
`tests/test_patch_memoization.py`).

### Reading gitops from the workflow

`find_proposal_slug` (`activities/proposals.py:61`) is the precedent for the
workflow learning something the Argo step wrote: the Temporal worker pod mounts
no gitops clone, so the activity reads `mctl-gitops` main through the GitHub
contents API with a token resolved per-call by `_resolve_token`
(`proposals.py:41`), raising the retryable `ProposalListingError` (`:37`) rather
than mistaking an outage for absence.

### Contract modules

`orchestrator/context_snapshot.py` is the house pattern for a versioned,
content-addressed, stdlib-only contract: `API_VERSION =
"context.mctl.ai/v1alpha1"` (`:38`), the `SUPPORTED_API_VERSIONS` allow-list
(`:44`), `_hash_bytes` (`:79`, `"sha256:" + sha256(...)`), `_canonical_json`
(`:83`, sorted keys, no NaN), `_reject_unknown_keys` (`:92`), frozen dataclasses
with `to_dict`/`from_dict`, a single keyword-only `seal()` constructor (`:885`)
computing `content_hash` then `snapshot_id = "cs-" + content_hash[7:23]`, and
`to_log_dict()` (`:807`) which deliberately omits `locator`/`selector`. Trust
tiers (`:49`) are `authoritative | corroborated | reported | untrusted`; source
kinds (`:50-60`) are a closed set; `EvidenceRef` (`:583`) is `{evidence_id,
kind}` and nothing else. The module has **no production caller yet** — only
`tests/test_context_snapshot.py:20` — and ADR 009's follow-up table names
`run_issue_investigator.py` as its intended first producer.

### Eligibility plumbing

`issue-investigator` is the one v1alpha2 agent
(`agents/_manifests/issue-investigator/agent.yaml:22-23`); its execution shape
lives in the mctl-gitops catalog profile `issue-investigator-default`.
`resolver.execute` (`resolver.py:788`) materialises an immutable `ExecutionPlan`
(`:226`) whose `tools: tuple[str, ...]` (`:247`) comes straight from
`profile.tools` (`:896`). At run time `_run_agent`
(`run_issue_investigator.py:1285`) branches on `_resolver_mode()` (`:108`,
env `ISSUE_INVESTIGATOR_RESOLVER_MODE`, default `legacy`) and, in
`declarative` mode, builds options via
`build_issue_investigator_options_from_plan` (`options.py:422`). That builder
treats `plan.tools` as the authoritative allow-list and special-cases exactly
one entry:

```
allowed_tools = [t for t in plan.tools if t != "mcp__mctl__*"]
if "mcp__mctl__*" in plan.tools:
    allowed_tools += _mctl_tool_globs()
```

(`options.py:459-461`). Everything else passes through verbatim.
`validate_manifest.py` then enforces **set equality** between a manifest's
declared tools and what the real builder returns (`:351-357`) and between the
catalog profile's `spec.tools` and the builder's `allowed_tools`
(`check_catalog_profiles_match_builders`, `:610-615`). There are no in-process
SDK MCP servers anywhere (`create_sdk_mcp_server` has zero hits);
`orchestrator/mcp_guard.py` guards MCP *connectivity*, not permissions.

### The blocker in the prompt

`_build_prompt` (`run_issue_investigator.py:1127`) currently emits, verbatim:

> **No human is present. Do not ask for input. Work with what you have.**

That line is the exact opposite of this issue's capability and must become
conditional. Note that `spec.prompt.sources` for this agent is
`inline: orchestrator/run_issue_investigator.py:_build_prompt`
(`agent.yaml:30`), so editing it changes the prompt hash
(`resolver._hash_prompt_source`, `resolver.py:744`) but not `agent.yaml`'s
bytes, so the release binding's `sourceManifest.contentHash` pin does not need
re-pinning.

## Proposed solution

Five in-repo pieces plus an ADR. Nothing outside `mctlhq/mctl-agents` changes.

### 1. ADR-011, `docs/adr/011-human-input-contract.md`

The issue asks for ADR-009; that number and 010 are taken
(`docs/adr/009-context-snapshot-contract.md`,
`docs/adr/010-lifecycle-ownership-contract.md`), so this ships as **ADR 011**.
House style, copied from 009/010: H1 `# ADR 011 — \`HumanInputRequest\`,
\`HumanInputResponse\` and \`WAITING_FOR_INPUT\``, a blockquote metadata block
(`**Status:** proposed`, `**Date:**`, `**Issue:** mctlhq/mctl-agents#333 (child
of mctlhq/.github#42)`, `**Supersedes:** nothing — it adds a primitive
alongside #198's approval, and says why they are not the same gate`), then
`## Context`, `## Decision` with numbered `###` sections, `## Alternatives`
(numbered, each "**X.** Rejected: why"), `## Non-goals`, `## Platform impact`,
`## Follow-ups and sequencing`, `## Implementation map`, `## Testable
invariants`. Contracts stated as `| Field | Type | Owner | Meaning |` tables
and ` ```text ` state machines, matching 009 and 010 respectively. This ADR is
the schema of record that `mctl-api#261` and `mctl-telegram#571` consume.

### 2. `orchestrator/human_input.py` — the contract module

Stdlib-only, no I/O, no production dependency on the SDK — modelled line for
line on `context_snapshot.py`, so the two validate and hash the same way.

| Symbol | Shape |
| --- | --- |
| `API_VERSION` | `"humaninput.mctl.ai/v1alpha1"` |
| `REQUEST_KIND` / `RESPONSE_KIND` | `"HumanInputRequest"` / `"HumanInputResponse"` |
| `SUPPORTED_API_VERSIONS` | `{API_VERSION: (REQUEST_KIND, RESPONSE_KIND)}` |
| `RESPONSE_TYPES` | `frozenset({"free_text","single_choice","multi_choice","structured"})` |
| `AUDIENCES` | `frozenset({"work_item_owner","repo_operators","tenant_operators"})` |
| `CONTEXT_REF_PREFIXES` | `("github:","gitops-file:","context_snapshot:","evidence:")` |
| `DEFAULT_REQUEST_TTL_SECONDS` | `86400` |
| `MAX_REQUEST_TTL_SECONDS` | `604800` |
| `MAX_CLARIFICATION_ROUNDS` | `3` |
| `MAX_OUTSTANDING_REQUESTS_PER_EXECUTION` | `1` |
| `HumanInputError(ValueError)` | the only raised type |
| `ResponseSpec` | `type: str`, `options: tuple[str, ...] = ()`, `schema_ref: str \| None = None` |
| `RequestedFrom` | `audience: str`, `actor_refs: tuple[str, ...] = ()` |
| `Respondent` | `actor_type: str`, `actor_id: str` |
| `HumanInputRequest` | `api_version`, `kind`, `request_id`, `request_hash`, `question_hash`, `request_version: int`, `created_at`, `expires_at`, `work_item_id`, `execution: ExecutionCorrelation`, `question`, `reason`, `response: ResponseSpec`, `requested_from: RequestedFrom`, `context_refs: tuple[str, ...] = ()`, `round: int = 1` |
| `HumanInputResponse` | `api_version`, `kind`, `request_id`, `request_hash`, `respondent: Respondent`, `surface`, `value: Any`, `received_at` |

`execution` reuses `context_snapshot.ExecutionCorrelation` (`:406`) directly
rather than re-declaring correlation fields — it already carries
`temporal_workflow_id`, `temporal_run_id`, `argo_workflow_name`, `agent`,
`environment`, `target_repository_sha` and the four version/hash pins.

Functions:

- `seal_request(*, work_item_id, execution, question, reason, response,
  requested_from, created_at, expires_at, context_refs=(), round=1) ->
  HumanInputRequest` — the only constructor. Computes
  `request_hash = _hash_bytes(_canonical_json(payload))` over every field except
  `request_id`, `request_hash` and `created_at`, then
  `request_id = "hir-" + request_hash[7:23]`. Same rule as `seal()`
  (`context_snapshot.py:915-916`), so sealing identical inputs twice at
  different wall-clock times yields the same identity — that is what makes a
  retried Argo step idempotent instead of duplicative.
- `question_hash_for(question, response) -> str` — `sha256` over the
  whitespace-collapsed, case-folded question plus the canonical JSON of the
  response spec. The dedupe key. Deliberately *not* the `request_hash`:
  `request_hash` includes `created_at`-independent but round- and
  correlation-specific fields, so two retries of the same ambiguity share a
  `question_hash` even when `round` differs.
- `validate_response(request, response, *, now) -> None` — raises
  `HumanInputError` on id mismatch, hash mismatch, `now >= expires_at`,
  respondent outside `requested_from.actor_refs`, or a value that does not
  satisfy `request.response` (non-listed option, wrong cardinality, empty
  free text).
- `to_dict`/`from_dict` on every dataclass, with `_reject_unknown_keys` and the
  `SUPPORTED_API_VERSIONS` gate.
- `request_log_dict(request) -> dict` / `response_log_dict(...)` — the safe
  telemetry projection, mirroring `ContextSnapshot.to_log_dict`
  (`context_snapshot.py:807`). It emits ids, hashes, versions, correlation,
  audience, surface, respondent reference, `round`, `expires_at`, outcome —
  and **never `question`, `reason` or `value`**.

### 3. Producer side — `run_issue_investigator.py` and `options.py`

**Eligibility is a capability entry in `plan.tools`, not an SDK tool name.**
`options.py` gains `HUMAN_INPUT_CAPABILITY = "human.request_input"` and
`plan_grants_human_input(plan: ExecutionPlan) -> bool`, and
`build_issue_investigator_options_from_plan` filters the capability out of
`allowed_tools` the same way `mcp__mctl__*` is special-cased today
(`options.py:459-461`) — a capability is not a tool the CLI can call, and
leaking it into `allowed_tools` would produce a dead allow-list entry.
`validate_manifest.py` subtracts the same `_CAPABILITY_TOOLS` frozenset before
its two set-equality comparisons (`:351-357`, `:610-615`), so
`mctl-gitops#1277` adding `human.request_input` to the profile's `spec.tools`
does not turn CI red. In `legacy` resolver mode there is no plan, so the
capability is never granted — the no-eligibility branch.

**The agent emits a file; it does not call a synchronous tool.** With no
in-process SDK MCP server in this repo and the durable boundary explicitly at
Temporal, the capability is realised as a *write contract*: when granted,
`_build_prompt` (`:1127`) replaces the "No human is present" paragraph with an
instruction to write a single JSON document to
`$PROPOSAL_DIR/human-input/request.json` when — and only when — retrieval,
code and docs are exhausted and the ambiguity is consequential, then finish the
proposal on its best current interpretation and stop. `PROPOSAL_DIR` is already
exported into the child env and `add_dirs` (`options.py:407,416,459-472`), so
no new capability surface is needed. The model never waits, never polls, and the
process exits normally.

**The proposal triplet is still written.** This is the load-bearing decision.
`_landed_triplet_defects` (`:439`) fails a publish that lacks
requirements/design/tasks, and `WorkflowResult` has no outcome field, so a step
that "yielded" would surface as a plain failure. Instead the step **succeeds**,
publishing a complete best-effort triplet *plus* the request; the request is the
durable signal that the proposal rests on an unresolved ambiguity. The pod exits
either way. This is what makes the no-eligibility branch trivially correct: no
grant, no request file, byte-identical behaviour to today.

`investigate()` (`:1457`) gains a post-publish step,
`collect_human_input_request(proposal_dir, *, granted, execution, now)`:
if not `granted` it deletes any `human-input/` directory the model wrote and
returns `None`; if granted it parses the document, re-seals it through
`seal_request` (the model supplies question/reason/response/context_refs; the
wrapper supplies every correlation, id, hash and timestamp field, so the model
cannot forge identity), enforces
`MAX_OUTSTANDING_REQUESTS_PER_EXECUTION`, and rewrites the file as the sealed
form. `InvestigateResult` (`:1409`) gains
`human_input_request: HumanInputRequest | None = None` — a defaulted field, per
the repo's serialization convention.

A prior answer is consumed through a new CLI flag,
`--human-input-response <json>`, threaded into `_build_prompt` inside the
untrusted-DATA envelope already used for issue bodies (`_neutralize_prompt_tags`
`:1098`, the wrapper in `_build_prompt` `:1137`), with an explicit sentence that
the answer is human-supplied information that resolves the named ambiguity and
**does not waive policy, authorization or approval**. The resolved
`question_hash` is listed as answered so the agent does not re-ask it.

### 4. Snapshot linkage

Continuation seals a `ContextSnapshot` (`context_snapshot.seal`, `:885`) that
includes the answer as a `ContextSource` of a new kind
`human-input-response` with `trust.tier = "reported"` (the tier ADR 009
sec. 6 already defines for human-authored platform state), plus an `EvidenceRef`
`{evidence_id: request_id, kind: "human-input-response"}`. `StepRef`
(`:480`) chains it to the pre-wait snapshot, so `snapshot_id` before/after is
recorded exactly as the issue asks. Adding a member to `SOURCE_KINDS`
(`context_snapshot.py:50-60`) is additive within
`context.mctl.ai/v1alpha1` — no field change, unknown-key rejection unaffected
— and ADR-011 says so explicitly. Because `context_snapshot.py` has no
production caller today, this proposal makes the investigator its first one, in
the position ADR 009's follow-up table already names.

### 5. Consumer side — `DevLoopWorkflow`

New activity `orchestrator/temporal/activities/human_input.py`:

```text
find_human_input_request(service: str, slug: str) -> str | None
```

A direct structural copy of `find_proposal_slug` (`proposals.py:61`) — same
`GITOPS_REPO`/`AGENTS_STATE_PREFIX` constants, same `_resolve_token`, same
retryable `HumanInputListingError` on transport/non-404 failure, same "404 means
genuinely absent" rule. It reads
`platform-gitops/agents-state/<service>/proposals/<slug>/human-input/request.json`
and returns its text; parsing happens in workflow code, which is pure.

New module-level state constants in `dev_loop.py`:

```text
RUNNING              = "RUNNING"
WAITING_FOR_APPROVAL = "WAITING_FOR_APPROVAL"
WAITING_FOR_INPUT    = "WAITING_FOR_INPUT"
INPUT_TIMED_OUT      = "INPUT_TIMED_OUT"
```

`WAITING_FOR_APPROVAL` names the existing `wait_condition` (`:827`) so the two
gates are distinguishable by construction rather than by comment.

New signal and query on `DevLoopWorkflow`:

- `@workflow.signal def human_input_response(self, *args: object) -> None` —
  defensive parsing exactly like `approve` (`:788`): signals must never raise,
  so a malformed payload is recorded and ignored rather than thrown. It appends
  to `self._input_responses` and never touches `self._approved`. That
  separation is the "clarification is not approval" invariant, and it is
  falsifiable: a test signals a response whose value literally says
  `"use option B and merge it"` and asserts the workflow is still parked on the
  approval wait.
- `@workflow.query def human_input_state(self) -> HumanInputState` — a frozen
  dataclass `{state, request_id, request_hash, question_hash, expires_at,
  round, resume_count}`, every field defaulted, so `mctl-api#261` and the
  portal can read pending-input state without owning it.

New method `_await_human_input(self, service: str, slug: str) -> HumanInputOutcome`,
called after investigate succeeds and **before** the approval wait, under
`workflow.patched("human-input")`:

```text
investigate Succeeded
  └── find_proposal_slug  (already needed later; hoisted under the patch)
        └── find_human_input_request
              ├── None                → WAITING_FOR_APPROVAL   (today's path)
              └── sealed request
                    ├── question_hash already answered → ignore, continue
                    ├── round > MAX_CLARIFICATION_ROUNDS → fail loudly
                    └── WAITING_FOR_INPUT
                          wait_condition(answered or cancelled,
                                         timeout = expires_at - now)
                            ├── valid response → RUNNING, resume_count += 1,
                            │                    re-run mctl-agents-investigate
                            │                    with human_input_response param
                            ├── timeout        → INPUT_TIMED_OUT, return
                            └── cancelled      → CANCELLED, return
```

The wait is `await workflow.wait_condition(pred, timeout=...)` — bounded, unlike
the approval wait. Rejected responses (id, hash, expiry, authorization, value)
are validated inside the workflow by `human_input.validate_response`, which is
pure and therefore legal in workflow code (ADR 010 sec. 9's rule that I/O lives
in activities is respected: there is none here). Rejections increment a counter
surfaced by the query; they never resume.

`DevLoopResult` (`:449`) gains `human_input: HumanInputOutcome | None = None` —
defaulted, so results recorded before this field exists still deserialize
(`:456-458`).

The continuation re-submits `mctl-agents-investigate` through the existing
`_run_cwft` funnel with one extra param, `human_input_response`. That parameter
must exist on the sibling CWFT — the same cross-repo coupling already documented
for `service` at `dev_loop.py:938-949`. The ordering is self-consistent and
needs no flag: with no catalog grant, no request file is ever written, so the
branch is never taken and the param is never sent.

## Alternatives

1. **A synchronous MCP tool that blocks the model until a human answers.**
   Rejected: the issue names this as the non-negotiable architecture boundary,
   and it is also unworkable here — `SDK_STEP_TIMEOUT` is 2 h
   (`dev_loop.py:96`) with a 2 min heartbeat, so a pod parked on a human would
   be killed and retried three times by `SDK_STEP_RETRY_POLICY` (`:95`),
   asking the same question three times.

2. **A new `outcome` field on `WorkflowResult` carrying `needs_input` from the
   Argo pod.** Architecturally the cleanest signal, and rejected only on
   boundary: `WorkflowResult` (`activities/argo.py:71`) is populated from
   mctl-api's Argo status response, so a typed outcome needs an mctl-api change
   — `mctl-api#261`'s territory, and this DevLoop must be completable in one
   mctl-agents PR. The gitops-file-plus-GitHub-read path reuses
   `find_proposal_slug`'s proven mechanism and costs one cheap GET.

3. **A dedicated `HumanInputWorkflow` child workflow per request.** Rejected:
   it buys isolation the loop does not need and costs a second durable identity
   that surfaces, the portal, the reconciler and `mctl_get_dev_loop` would all
   have to learn. The issue's requirement is that "the same canonical
   WorkItem/workflow remains active"; a field on `DevLoopWorkflow` plus a
   bounded `wait_condition` satisfies that with one patch marker.

4. **Make the request a *failed* investigate step with a typed
   `needs_input` error.** Rejected: `_landed_triplet_defects` (`:439`) would
   reject the publish, `SDK_STEP_RETRY_POLICY` would re-run the whole
   investigation twice more before the workflow ever saw it, and a failed
   investigate returns early at `dev_loop.py:821`. Succeeding with a
   best-effort proposal *plus* a request is strictly more useful — a human who
   declines to answer still has a proposal.

## Platform impact

**Migrations.** None. No schema, no stored state, no gitops file moves. The
first request document appears only after `mctl-gitops#1277` grants the
capability; until then `human-input/` directories do not exist.

**Backward compatibility.** Three separate guards. (a) `workflow.patched(
"human-input")` keeps every in-flight execution on its recorded command
sequence — mandatory, because an unconditional `find_human_input_request`
between investigate and the approval wait is exactly the command mismatch that
wedged loops before (`dev_loop.py:845-852`). Migration is by attrition
(`:491-498`). (b) Every new dataclass field is defaulted
(`DevLoopResult.human_input`, `InvestigateResult.human_input_request`), per the
convention stated at `activities/lifecycle.py:47-52`. (c) The capability is
absent from `plan.tools` today and absent entirely in `legacy` resolver mode, so
with no catalog change the producer path is unreachable.

**Resource impact.** One extra GitHub contents GET per successful investigate on
patched executions. A `WAITING_FOR_INPUT` wait costs Temporal history storage
only — no Argo workflow, no SDK session, no activity slot, which is the
pod-release requirement. A resumed loop runs one additional
`mctl-agents-investigate` (~$3 of subscription quota, bounded by
`MAX_CLARIFICATION_ROUNDS = 3`).

**Risks and mitigations.**

- *An agent asks a question on every retry.* Mitigated by `question_hash`
  dedupe plus deterministic `request_id` from `seal_request` — a retried step
  that seals the same inputs produces the same `request_id`, so the workflow
  sees one request, not three. Proved by T5/T6.
- *A human answer is read as an instruction or an approval.* Mitigated by the
  untrusted-DATA envelope (`_neutralize_prompt_tags`, `:1098`) and by
  `human_input_response` never touching `self._approved`. Proved by T12/T13 —
  both by mutation, in both directions.
- *A loop waits forever.* Mitigated by the bounded `wait_condition` timeout and
  `INPUT_TIMED_OUT`, unlike the approval wait it sits next to.
- *Question or answer text leaks into telemetry.* Mitigated by
  `request_log_dict`/`response_log_dict` being the only emitters, mirroring
  `to_log_dict`'s omission discipline (`context_snapshot.py:807`). Proved by T14.
- *The continuation CWFT rejects an unknown `human_input_response` param.*
  Unreachable before the catalog grant, and the grant and the CWFT parameter
  land together in `mctl-gitops#1277`. Recorded as an open question, with the
  `service`-param precedent (`dev_loop.py:938-949`) as the template.
- *The prompt edit changes the investigator's behaviour for everyone.* Mitigated
  by making the new paragraph conditional on the grant; the ungranted prompt is
  asserted byte-identical to today's by T15.

**Security.** A response is data with provenance, never a capability. Three
independent checks stand between a Telegram message and a resume: the request
must be the current, unexpired one; `request_hash` must match exactly; and the
respondent must appear in `requested_from.actor_refs`. None of them grants
anything — they only decide whether the loop un-parks. Authorization for any
subsequent consequential action still runs through `approve`
(`dev_loop.py:788`) and the profile's `approval.requiredBefore` gate.
