# Action lifecycle (including UNKNOWN), correlation ids and a JSONL audit log

> **Amended at owner review (before approval):**
> (1) **No `EXECUTING -> FAILED` edge.** A synchronous MCP error response is still a completed
> call attempt and goes `EXECUTING -> EXECUTED -> VERIFYING`. `FAILED` is reachable only
> through `VERIFYING`, so "failed" always means verified failure; `verified_failure=True` on
> `FAILED -> EXECUTING` remains an additional guard.
> (2) **Attempt-scoped ids.** `observation_id` and `action_id` are immutable for the whole
> action. `tool_call_id` and `verification_id` belong to one attempt. Attempt 1 uses the ids
> created by `new_action_record()`. `AUTHORIZED -> EXECUTING` changes no id (only `attempt`
> 0 -> 1), and `EXECUTED/UNKNOWN -> VERIFYING` does not change `verification_id`. Only a retry
> `FAILED -> EXECUTING` opens a new attempt and replaces **both** `tool_call_id` and
> `verification_id` together. Explicitly supplied ids may override the generated pair only on
> that transition.
> (3) `observation_id` is normally propagated from `newton_propose_action`; generation in
> `new_action_record()` is a fallback only.

## Context

The action runtime in `src/newton_mcp/runtime/` can today discover MCP tools
(`runtime/catalog.py`), deterministically resolve a `PhysicalActionContract` into ranked
`CandidateAction`s (`runtime/resolver.py`), decide auto/confirm/deny (`action/policy.py`) and bind an
`Approval` to one exact resolved action (`action/approval.py`). Everything after that point is
missing: `docs/action-runtime.md` states outright that the package "still executes nothing: no
`call_tool`, no lifecycle, no audit, no LLM", and `README.md` repeats it. There is no way to say
*where* an action is, no correlation id beyond `action_id` (invented per-call by the caller of
`create_approval`), and nothing that records what happened.

This proposal adds the missing spine: an explicit `ActionState` machine with a single allowed-transition
table, an `ActionRecord` carrying the four correlation ids named in `docs/architecture.md`
(`observation_id`, `action_id`, `tool_call_id`, `verification_id`), a guarded `transition()` function
that raises on any transition the table does not allow, and an append-only JSONL audit log with one
line per accepted transition. The central safety property is that the runtime must be able to say
"I do not know whether this happened": a tool-call timeout or transport failure is `UNKNOWN`, never
success, and `UNKNOWN` may never go straight back to `EXECUTING`, because blindly re-issuing a
non-idempotent physical action is exactly the failure mode this runtime exists to prevent. The
executor and verifier (#8) consume this module; they are not part of it.

## User stories

- AS an operator of the action runtime I WANT every physical action to carry an explicit state and
  four correlation ids SO THAT I can follow one observation through proposal, approval, tool call and
  verification in a single grep.
- AS an operator I WANT a tool-call timeout to land in a distinct `UNKNOWN` state SO THAT a failure
  to observe an outcome is never silently recorded as a success.
- AS an operator I WANT `UNKNOWN` to be unable to reach `EXECUTING` directly SO THAT a non-idempotent
  physical action is never retried while its first attempt's outcome is still unknown.
- AS a reviewer of this proposal I WANT the set of legal transitions to live in one readable table
  SO THAT the safety argument can be audited by reading a single data structure instead of tracing
  control flow.
- AS an incident responder I WANT an append-only JSONL line per transition, carrying all four ids,
  the from/to states, a reason and a timestamp SO THAT I can reconstruct what the runtime did after
  the fact, across process restarts.
- AS a security reviewer I WANT arguments in the audit log redacted by key name SO THAT a credential
  passed as a tool argument is not persisted in plaintext to disk.
- AS a test author I WANT auditing to default to an in-memory sink SO THAT the test suite writes no
  files and needs no environment variable.

## Acceptance criteria (EARS)

### States and the transition table

- WHEN `newton_mcp.runtime.lifecycle` is imported THE SYSTEM SHALL expose an `ActionState` StrEnum
  with exactly the members `PROPOSED`, `AUTHORIZED`, `DENIED`, `EXECUTING`, `EXECUTED`, `UNKNOWN`,
  `VERIFYING`, `SUCCEEDED`, `FAILED` and `ESCALATED`, whose values are the lowercase member names.
- WHEN `newton_mcp.runtime.lifecycle` is imported THE SYSTEM SHALL expose the allowed transitions as
  one module-level, immutable mapping that is the only source of truth consulted by `transition()`.
- WHILE an action is in `PROPOSED` THE SYSTEM SHALL allow transitions only to `AUTHORIZED` or
  `DENIED`.
- WHILE an action is in `AUTHORIZED` THE SYSTEM SHALL allow a transition only to `EXECUTING`.
- WHILE an action is in `EXECUTING` THE SYSTEM SHALL allow transitions only to `EXECUTED` or
  `UNKNOWN`. A synchronous MCP error response is a completed call attempt and goes to `EXECUTED`.
  `UNKNOWN` is reserved for a timeout or transport failure (owner amendment).
- WHILE the transition table is in force THE SYSTEM SHALL make `FAILED` reachable only from
  `VERIFYING`, so a `FAILED` record always means a verified failure.
- WHILE an action is in `EXECUTED` THE SYSTEM SHALL allow a transition only to `VERIFYING`.
- WHILE an action is in `UNKNOWN` THE SYSTEM SHALL allow transitions only to `VERIFYING` or
  `ESCALATED`.
- WHILE an action is in `VERIFYING` THE SYSTEM SHALL allow transitions only to `SUCCEEDED`, `FAILED`
  or `ESCALATED`.
- WHILE an action is in `FAILED` THE SYSTEM SHALL allow transitions only to `EXECUTING` (retry) or
  `ESCALATED`.
- WHILE an action is in `DENIED`, `SUCCEEDED` or `ESCALATED` THE SYSTEM SHALL allow no outgoing
  transition at all.
- IF a caller requests a transition that the table does not list, THEN THE SYSTEM SHALL raise
  `IllegalTransition` naming the current state, the requested state and the states that were allowed,
  and SHALL leave the input record unchanged.
- IF a caller requests `UNKNOWN -> EXECUTING` or `PROPOSED -> EXECUTING`, THEN THE SYSTEM SHALL raise
  `IllegalTransition` (these are named explicitly because they are the two transitions whose absence
  is the safety property).
- IF a caller requests a self-transition (any state to itself), THEN THE SYSTEM SHALL raise
  `IllegalTransition`.
- IF a caller requests `FAILED -> EXECUTING` without setting the transition's `verified_failure`
  flag, THEN THE SYSTEM SHALL raise `IllegalTransition` explaining that a retry requires a verified
  failure.
- WHEN a caller requests `FAILED -> EXECUTING` with `verified_failure=True` and a non-empty reason
  THE SYSTEM SHALL allow the transition and SHALL record `verified_failure` on the resulting audit
  line.

### `ActionRecord` and correlation ids

- WHEN an `ActionRecord` is created THE SYSTEM SHALL populate all four correlation ids
  (`observation_id`, `action_id`, `tool_call_id`, `verification_id`), generating any the caller did
  not supply, so that every audit line ever written for that record carries four non-null ids.
- WHEN the system generates a correlation id THE SYSTEM SHALL prefix it by kind (`obs-`, `act-`,
  `call-`, `ver-`) followed by 16 hex characters, and SHALL take the random source from an injectable
  factory so tests can make ids deterministic.
- WHEN an `ActionRecord` is created THE SYSTEM SHALL set its state to `PROPOSED`, its attempt counter
  to `0`, and both its created and updated timestamps to the supplied timezone-aware moment.
- WHILE an `ActionRecord` exists THE SYSTEM SHALL treat it as immutable: `transition()` SHALL return
  a new record and SHALL NOT mutate the one it was given.
- WHEN a transition enters `EXECUTING` THE SYSTEM SHALL increment the attempt counter by one, so the
  first execution is attempt `1` and a retry after `FAILED` is attempt `2`.
- WHILE an action exists THE SYSTEM SHALL treat `tool_call_id` and `verification_id` as scoped to one
  attempt: attempt 1 uses the ids created by `new_action_record()`, and neither
  `AUTHORIZED -> EXECUTING` nor `EXECUTED -> VERIFYING` nor `UNKNOWN -> VERIFYING` changes either id
  (owner amendment).
- WHEN a retry `FAILED -> EXECUTING` is accepted THE SYSTEM SHALL open a new attempt by replacing
  **both** `tool_call_id` and `verification_id` together, with freshly generated ids unless the
  caller supplied them, so a retry never reuses the previous attempt's ids and a call and its
  verification never belong to different attempts.
- IF a caller passes `observation_id` or `action_id` to `transition()`, THEN THE SYSTEM SHALL raise
  `ValueError`: those two ids are the correlation roots and are fixed at record creation.
- IF a caller passes `tool_call_id` or `verification_id` to any transition other than a retry
  `FAILED -> EXECUTING`, THEN THE SYSTEM SHALL raise `ValueError` rather than silently rewriting
  an id mid-attempt. That includes `AUTHORIZED -> EXECUTING` and any entry into `VERIFYING`. On a
  retry, either id may be supplied, and any id not supplied is generated.
- IF a caller passes an empty or whitespace-only `reason`, THEN THE SYSTEM SHALL raise `ValueError`:
  an unexplained state change is not auditable.
- IF a caller passes a naive (timezone-less) timestamp anywhere in this module, THEN THE SYSTEM SHALL
  raise `ValueError`, reusing `newton_mcp.canonical.canonical_timestamp`'s existing guard.

### Audit log

- WHEN `transition()` is called with a sink and the transition is allowed THE SYSTEM SHALL write
  exactly one audit event to that sink, after the new record has been computed.
- IF a transition is rejected as illegal, THEN THE SYSTEM SHALL write no audit event.
- WHEN an audit event is built THE SYSTEM SHALL include `observation_id`, `action_id`,
  `tool_call_id`, `verification_id`, `from`, `to`, `reason`, `attempt`, `verified_failure`, `at` (a
  canonical UTC timestamp via `newton_mcp.canonical.canonical_timestamp`), and, when the caller
  supplied arguments, both a redacted `args` mapping and an `args_digest`.
- WHEN `args` are supplied THE SYSTEM SHALL compute `args_digest` as
  `newton_mcp.canonical.sha256_hex(args)` over the unredacted arguments, so the value is
  byte-identical to `Approval.args_digest` for the same resolved action.
- WHEN `NEWTON_MCP_AUDIT_PATH` is unset or blank THE SYSTEM SHALL return an in-memory sink, so
  auditing is effectively disabled and the test suite writes no file.
- IF `NEWTON_MCP_AUDIT_PATH` is set but unusable (its parent directory does not exist, the path is a
  directory, or it is not writable), THEN THE SYSTEM SHALL raise `ValueError` naming the variable and
  the path rather than degrading silently to the in-memory sink.
- WHEN the JSONL sink writes an event THE SYSTEM SHALL open the file in append mode, so re-opening an
  existing audit file never truncates it and previously written lines survive a process restart.
- WHEN the JSONL sink writes an event THE SYSTEM SHALL emit exactly one line of compact UTF-8 JSON
  terminated by a single newline, with no trailing partial line.
- WHILE writing an audit event THE SYSTEM SHALL replace the value of any argument key whose name
  matches a documented secret-key pattern (case-insensitive substring match) with a fixed
  `"[redacted]"` marker, recursing into nested mappings and lists.
- WHILE writing an audit event THE SYSTEM SHALL truncate any individual redacted string value longer
  than a documented character cap, following the existing `_truncate` convention in
  `runtime/catalog.py`.

### Wiring and documentation

- WHEN `newton_mcp.runtime` is imported THE SYSTEM SHALL re-export the new public names
  (`ActionState`, `ActionRecord`, `IllegalTransition`, `transition`, `AuditEvent`, `AuditSink`,
  `MemoryAuditSink`, `JsonlAuditSink`, `load_audit_sink`, `redact_args`) from its `__init__.py`,
  matching the existing export style.
- WHEN this proposal is implemented THE SYSTEM SHALL update `docs/action-runtime.md`,
  `docs/architecture.md`, `README.md` and `.env.example` so that no document still claims the runtime
  has "no lifecycle, no audit", and `docs/architecture.md`'s lifecycle line includes `UNKNOWN` and
  `DENIED`.
- WHILE documenting this change THE SYSTEM SHALL keep describing the Physical Action Contract and the
  action runtime as this project's experimental proposal, not an Archetype standard, and SHALL NOT
  claim any live Newton or live MCP actuator validation.

## Out of scope

- Executing tools: no `call_tool`, no MCP session handling, no timeout policy. The executor is #8.
- Verification logic: nothing in this proposal decides whether a physical outcome happened, reads a
  `read_tool`, or evaluates `contract.verification.condition`.
- Retry decisions: this proposal only says a `FAILED -> EXECUTING` retry is *possible* and what it
  must carry. Whether, when and how often to retry (including `Verification.retry_limit` and
  `CandidateAction.idempotent`) belongs to #8.
- Escalation delivery: no notification, ticket, webhook or human-facing channel. `ESCALATED` is a
  state, not an action.
- Persisting `ActionRecord`s, any database, any queue, any workflow engine (no Temporal, no
  Kubernetes), and any new MCP tool. The audit log is a plain file.
- Signed approvals, an authenticated approver, approval revocation, or binding `approval_id` into the
  record. `action/approval.py` keeps its current scope.
- Log rotation, retention, fsync-per-line durability guarantees, multi-process write coordination, or
  a structured query interface over the JSONL file.
- Any change to `PhysicalActionContract`, so `schemas/physical-action-contract.schema.json` is not
  regenerated.

## Open questions

Recorded, not blocking; each has a chosen default already reflected above.

1. **`EXECUTING -> FAILED`: resolved at owner review, dropped.** An explicit MCP error response
   does not prove that the physical action did not happen, or did not partly happen. It is a
   completed call attempt (`EXECUTED`) whose physical outcome must still be verified. `FAILED` is
   therefore reachable only via `VERIFYING`.
2. **`FAILED -> ESCALATED`.** Not named in the issue. Allowed here so an exhausted retry budget has a
   terminal home other than staying `FAILED` forever.
3. **All four ids from creation.** "Every line carries all 4 ids" is read as four non-null ids, which
   requires minting `tool_call_id`/`verification_id` at record creation before any tool call exists.
   Per the owner amendment, those creation-time ids *are* attempt 1's ids, and they stay unchanged
   through attempt 1's `EXECUTING` and `VERIFYING`. `observation_id` is normally passed in from the
   `newton_propose_action` result (its deterministic `obs-<sha256>`); generating one in
   `new_action_record()` is a fallback only.
   The alternative reading (keys present but `null` until minted) is also defensible; the chosen one
   makes correlation work from the first line and keeps the audit schema non-optional.
4. **Verified failure as a flag, not a string.** `transition(..., verified_failure=True)` is an
   explicit keyword rather than a marker sniffed out of the free-text `reason`, because string
   sniffing would make a safety guard depend on prose.
5. **Redaction is key-name only and deliberately over-eager.** A key containing `key`, `token`,
   `secret`, `password`, `credential`, `auth`, `cookie` or `session` is redacted, so a benign key like
   `keypad_zone` is redacted too. There is no value-shape detection, so a secret passed under a
   harmless key name (for example `note`) still lands in the log. Over-redaction is the safe
   direction; the residual gap is documented rather than papered over.
6. **Unset audit path means disabled.** This differs from `load_runtime_config()` and `load_policy()`,
   which fail loudly when their variable is unset. The issue asks for it explicitly, and an audit sink
   is not an authority boundary the way an allow-list is. A *set but unusable* path still fails loudly,
   so only an intentionally unset variable disables auditing.
7. **`args_digest` over unredacted args.** Chosen so it equals `Approval.args_digest` for the same
   action, which is what makes an audit line provable against an approval. `action/approval.py`
   already persists exactly this digest, so the audit log introduces no new exposure class; the
   theoretical brute-forceability of a low-entropy secret from a sha256 is unchanged by this proposal.
8. **No `AUTHORIZED -> DENIED`.** The issue says `DENIED` is reachable from `PROPOSED`; approval
   revocation after authorization is therefore not modelled. `ESCALATED` covers the human-takeover
   case.
9. **Illegal transitions are not audited.** Only accepted transitions produce a line, so "one line per
   transition" holds literally. A rejected transition raises, which is loud enough for a programming
   error.
