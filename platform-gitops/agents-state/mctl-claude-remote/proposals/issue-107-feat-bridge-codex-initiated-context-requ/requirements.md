# Bridge: Codex-initiated context requests to a Claude slot (bounded, source-bound, stale-safe)

## Context

`mctl-bridge` (`plugin/mctl-bridge/`, designed in `docs/chatgpt-orchestrator-bridge.md`) carries
work in one direction (orchestrator `send` -> slot task) and questions in the other (slot
`ask_orchestrator` -> orchestrator `claim`/`reply` -> slot `ack_reply`). The Codex orchestrator
has no typed way to ask a Claude slot for context or advice. Today it can only `send` a new
task, which waits behind `inflight` and so cannot reach a slot that is waiting on the
orchestrator's own reply. It also has no notion of scope, size, provenance or stale-session
refusal. Issue #107 asks for a first-class, typed `request_context` contract from Codex to a
chosen slot (A or B). The slot answers from its real session and workspace, or says honestly
that it cannot. Admission and busy fencing stay intact, A and B stay isolated, and Codex keeps
one shared orchestrator thread.

The issue covers protocol and design first, then implementation against this reviewed plan.
It does not authorize changes on the Mac mini. Working slots are not touched until the OS
isolation of #106 passes and the owner authorizes rollout. "Full context" here means the
user-visible session history and work artifacts that are explicitly approved. It never means
hidden model state, reasoning or unbounded memory. Transcript paging ships only if a probe
proves that a slot can read its own transcript accurately.

## User stories

- AS the Codex orchestrator I WANT to ask slot A (or B) a typed context/advice question bound to its current session SO THAT I can answer A's question or coordinate work without guessing.
- AS the Codex orchestrator I WANT bounded, paginated answers with provenance and a continuation cursor SO THAT large context never floods my shared thread.
- AS a Claude slot I WANT a context request to arrive only when I am idle, and never inside a tool result SO THAT my current tool call and attempt are not disturbed.
- AS a Claude slot that asked a question I WANT to answer the orchestrator's follow-up context request and still receive the reply on the same attempt SO THAT my task continues without a restart.
- AS the operator I WANT full-transcript access to require my explicit, scoped, time-limited grant SO THAT Codex has no ambient permission to read everything.
- AS the operator I WANT A's context never to reach B unless an action authorizes it SO THAT the sessions stay distinct.

## Acceptance criteria (EARS)

Request creation
- WHEN the orchestrator runs `mctl-bridge request-context --slot S --scope <scope> --purpose <text>` THE SYSTEM SHALL create a context request record (`kind=ctxreq`, id `cx-<uuid>`) that stores request_id, requester principal, target slot, the slot's current `uuid` and `epoch`, an optional `task_id`/`attempt_id`/`question_id`, purpose, scope, cursor, `max_bytes`, `expires_ms` and hop, all in one FCALL (`bridge_request_context`).
- THE SYSTEM SHALL accept only the scopes `summary`, `relevant`, `transcript_page`, `evidence_refs` and `advice`. It SHALL refuse any other scope with `bad_request`.
- IF `max_bytes` exceeds the library cap (`MAX_PAYLOAD`, 16384) or is not positive THEN THE SYSTEM SHALL refuse the request with `bad_request`.
- IF the target slot is not registered THEN THE SYSTEM SHALL refuse with `slot_not_registered`.
- IF the target slot's registration does not advertise context-request capability (an adapter older than library version 5) THEN THE SYSTEM SHALL refuse with `slot_unsupported`.
- WHEN a request carries an idempotency key that was used before THE SYSTEM SHALL return the existing request id with `dedup:true` and create nothing new.
- IF the per-task context budget, the per-slot hourly budget or the hop limit (`MAX_HOP`) would be exceeded THEN THE SYSTEM SHALL refuse with `ctx_budget` or `hop_limit` and create nothing.
- IF scope is `transcript_page` and no live operator grant covers this slot, session uuid and scope THEN THE SYSTEM SHALL refuse with `not_authorized`.

Delivery and admission
- WHILE the slot's registration says busy THE SYSTEM SHALL keep a context request queued and SHALL NOT emit it.
- WHEN a context request is unbound (no task) THE SYSTEM SHALL emit it only when the slot is idle and neither `inflight` nor `ctx_inflight` is set.
- WHEN a context request is bound to the task in `inflight` THE SYSTEM SHALL emit it only if its `task_id`, `attempt_id`, `uuid` and `epoch` match the registration, the slot is idle and `ctx_inflight` is empty.
- WHILE `ctx_inflight` is set THE SYSTEM SHALL NOT emit a new task to that slot.
- THE SYSTEM SHALL emit context requests through the existing emit protocol (`emit_intent -> emitted`). A crash between the steps SHALL become `delivery_unknown` and SHALL NOT be resent.
- WHEN the slot calls `ack_context` with the request id and attempt id THE SYSTEM SHALL return a context admission bound to `{ctx_id, attempt_id, uuid, epoch, conn_id}`. The adapter SHALL keep it and reject any mismatched grant as `stale_grant`.
- IF the slot's uuid or epoch changed after the request was created, or the slot was cleared or restarted, THEN THE SYSTEM SHALL cancel the queued request (`addressee_changed`), or move an emitted one to `delivery_unknown`. It SHALL refuse any later answer for it and record that answer as late evidence.

Answer
- WHEN the slot calls `answer_context` with a valid context admission THE SYSTEM SHALL store the answer in orchestrator-owned keys. It SHALL also store the content's sha256 digest, the source kind and source revision or offset, redaction and unavailable markers, a continuation cursor and the answering `{slot, uuid, epoch}`. Then it SHALL move the request to `answered` and append `context_answered` to the feed.
- IF the answer exceeds the request's `max_bytes` THEN THE SYSTEM SHALL refuse with `too_large` and keep the request open for a smaller answer.
- WHEN the slot cannot provide the scope THE SYSTEM SHALL let it answer with `status=unavailable` and a reason (for example `busy`, `unsupported`, `compacted`, `not_in_session`). It SHALL record that as a terminal `unavailable` state, never as empty content.
- WHEN scope is `transcript_page` THE SYSTEM SHALL produce the page in the adapter process, running as the slot's OS user, from the session transcript source proved in task 1. The model SHALL NOT write it. The page SHALL hold only user-visible message text and tool names or results, SHALL leave out thinking blocks, and SHALL pass through secret redaction.
- IF the transcript source is unproven or unreadable THEN THE SYSTEM SHALL answer `unavailable` with reason `unsupported` and SHALL NOT generate a transcript from model recall.
- WHEN a request passes `expires_ms` unanswered THE SYSTEM SHALL move it to `expired` and clear `ctx_inflight`, so the slot is not wedged.

Interaction with questions and tasks
- WHILE a slot's question is `asked` and a bound context request for the same task is open THE SYSTEM SHALL keep the question and its claim valid. A reply committed afterwards SHALL still be emitted to the same attempt.
- WHEN a task reaches a terminal state THE SYSTEM SHALL cancel any open context request bound to it.
- THE SYSTEM SHALL keep `ask_orchestrator`, `ack_reply` and `report_result` byte-compatible with library version 4 semantics. It SHALL keep enforcing one open question per task and the hop limit, so ping-pong stays bounded.

Isolation and trust
- THE SYSTEM SHALL store context answers outside every `s:<slot>:*` namespace, so no slot ACL user can read another slot's answers.
- THE SYSTEM SHALL NOT deliver one slot's context answer to another slot. Forwarding between slots is not provided by this proposal.
- THE SYSTEM SHALL present context answers to the orchestrator as untrusted data. The orchestrator workspace rules SHALL state that an answer is never approval, a tool instruction, a permission escalation, a merge or a deployment.
- THE SYSTEM SHALL NOT write context content to the global `audit` stream, the feed, GitHub or any log. Audit entries SHALL carry ids, digests, sizes and states only.

## Out of scope

- Rollout to working slots or any operation on the Mac mini. That is gated on #106 OS isolation and the owner's authorization.
- Cross-slot forwarding of context (A's content to B). That needs a separate authorized action.
- Hidden model state, chain-of-thought or memory beyond the session's visible transcript.
- Giving Codex filesystem access to slot HOME, or giving Codex any "share all" permission.
- Cluster Valkey (slice 5) and ACL changes in mctl-gitops.
- Interrupting a busy slot or preempting a running tool call.
- Changes to the `labs/claude-remote` Kubernetes deployment.

## Open questions

- Transcript source: does Claude Code expose a stable, documented per-session transcript (for example the `transcript_path` field in hook input) that remains accurate after `/compact`? Task 1 probes this. Until it is proven, `transcript_page` answers `unsupported`.
- Grant authority: Codex runs as the operator's uid with `bridge_orch` credentials. Until #106 lands, the only separation between "Codex" and "operator" for `context-grant` is the Codex command rule that leaves `context-grant` out of the allow list, so it always prompts. Is that sufficient for the owner, or should grants require a separate credential?
- Budgets: the proposed defaults are 8 context requests per task, 30 per slot per hour, `max_bytes` 16384 per page and a 10-minute TTL. These need owner confirmation.
- Should the waker wake the orchestrator thread on `context_answered`? This proposal uses the existing wake budget and lock.
- Should an unbound context request to an idle slot with no task be allowed at all, or should every request be bound to a task? This proposal allows unbound requests but counts them against the hourly budget.
