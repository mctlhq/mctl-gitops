# Bridge disclosure boundary: no unintended Claude A to B disclosure through a shared Codex thread

## Context

The owner runs one shared Codex orchestrator thread that coordinates several Claude
Code slots through `mctl-bridge` (`plugin/mctl-bridge/`). That thread deliberately
remembers what slots A and B said. Issue #108 asks for evidence that this shared memory
does not turn into unintended disclosure: A's messages must never be routed to B by the
adapter or Valkey, and an ordinary answer delivered to B must not carry A-only content
just because it sits in Codex's history. A cross-slot transfer is allowed only as an
explicit, owner-authorized, audited, narrowly scoped handoff.

Model behavior is not a confidentiality boundary. This proposal therefore adds
deterministic checks where the bridge controls the bytes (routing, output delivery
through `bridge_send` / `bridge_reply`, and an owner-issued handoff grant), a repeatable
CI test suite with synthetic canaries, and a separate, manually run mini end-to-end
harness on the Mac mini that measures the actual Codex behavior and reports observed
results and nondeterminism. Test success grants nothing: no permissions, merges, deploys
or admission of working slots follow automatically.

## User stories

- AS the owner I WANT one Codex thread that can read and coordinate both slots SO THAT
  I do not have to split the orchestrator per slot.
- AS the owner I WANT deterministic, mutation-tested proof that A's messages are never
  routed to B and that a payload carrying A-private markers cannot be delivered to B
  without my grant SO THAT model behavior is not the only control.
- AS the owner I WANT to authorize one exact excerpt from A to B, with purpose, source,
  target and expiry, SO THAT intentional coordination is possible and auditable.
- AS a reviewer I WANT sanitized, hash-bound evidence from repeated live runs (fresh and
  warm Codex threads) SO THAT I can judge the residual model risk from observed data, not
  from a blanket claim.

## Acceptance criteria (EARS)

Routing (deterministic, CI):
- WHEN slot A asks a question, reports a result or acknowledges a task THE SYSTEM SHALL
  record it only under A's keys, and no entry of `mctl:bridge:s:b:inbox` or
  `mctl:bridge:s:b:resp` and no channel notification seen by B's adapter SHALL contain
  any of A's canary strings.
- WHEN the orchestrator replies to a question THE SYSTEM SHALL deliver the reply, and
  the question text it repeats, only to the slot that asked it, bound to that question's
  `task_id`, `attempt_id`, `uuid` and `epoch`.
- IF a request in A's outbox names slot B, a stale epoch, a replaced connection, a
  replayed request id or another slot's task THEN THE SYSTEM SHALL refuse it and leave
  B's registration, inbox and messages unchanged.

Output delivery guard (deterministic, CI):
- WHILE a slot has owner-registered private markers THE SYSTEM SHALL refuse any
  `bridge_send` or `bridge_reply` whose payload addressed to a different slot contains
  one of those markers verbatim, with code `disclosure_blocked`, change no message,
  queue or claim state, and append an audit entry naming the source slot and marker
  index but never the marker text.
- WHEN `send` or `reply` carries a handoff grant id THE SYSTEM SHALL deliver the payload
  only if the grant exists, is unexpired, unused, names the same source and target slot,
  is bound to the target's current `uuid` and `epoch`, and the payload is byte-identical
  to the granted excerpt; it SHALL then mark the grant used, store `handoff_id`,
  `source_slot` and `purpose` on the message, and audit the transfer with the excerpt's
  sha256.
- IF the grant is missing, unknown, expired, used, bound to another target or epoch, or
  the payload differs from the excerpt by any byte THEN THE SYSTEM SHALL refuse the
  delivery (`handoff_invalid` with a reason) and deliver nothing (fail closed).
- IF the private-marker or grant store cannot be read THEN THE SYSTEM SHALL refuse the
  delivery rather than skip the check.
- WHILE the orchestrator role (`bridge_orch`) is in use THE SYSTEM SHALL NOT let it create,
  change or delete private markers or handoff grants; only the owner role can.
- WHEN a handoff message is delivered THE SYSTEM SHALL include `handoff_id` and
  `source_slot` in the channel notification meta so the receiving slot sees provenance.

Live evidence (manual, Mac mini):
- WHEN the mini E2E harness runs THE SYSTEM SHALL execute scenarios 1-4 and 7 of issue
  #108 for a configurable number of repetitions against both a fresh Codex thread and a
  thread with prior A+B history, and SHALL write sanitized JSONL evidence per delivery:
  run id, thread mode, scenario, recipient slot, recipient uuid/epoch, payload sha256,
  canary ids found (never canary values), guard outcome, and an outcome of `pass`,
  `leak`, `blocked` or `unknown`.
- IF a delivery cannot be observed or bound to a recipient THEN THE SYSTEM SHALL record
  `unknown`, never `pass`.
- WHEN any run records `leak` THE SYSTEM SHALL exit non-zero and the summary SHALL state
  that working slots stay blocked.
- WHEN OS negative controls run (after #106) THE SYSTEM SHALL record them in a separate
  evidence file from model-output checks.

## Out of scope

- Host isolation (separate OS accounts, protected credentials and Codex socket): issue
  #106. The OS negative-control script is delivered but only runs once #106 exists.
- The bounded context API for Codex (pagination, evidence references): issue #107.
  Scenario 6 tests are written as `test.todo` placeholders against that contract.
- A general data-loss-prevention filter. The guard matches registered markers
  verbatim; paraphrase, translation or encoding by the model can evade it. Live runs
  measure that residual risk; they do not eliminate it.
- Any automatic permission, merge, deploy, release or slot admission on test success.
- Cluster Valkey (slice 5).

## Open questions

- Who holds the owner role on the Mac mini today? Until #106, `bridge_orch` and the
  Codex process share a uid with `admin.pw`, so the owner/orchestrator separation is
  only as strong as the Codex command rules. Assumed: the owner CLI uses `bridge_admin`
  and is excluded from `ops/codex-mctl-bridge.rules`; the gap is recorded as accepted
  until #106.
- Should a handoff be single-use (assumed) or reusable until expiry?
- Should the guard also cover the `status`/`tasks` CLI reads by Codex? Assumed no: Codex
  is authorized to read both slots; the boundary is at delivery to a slot.
- How many repetitions are enough for the live evidence? Assumed default 5 per scenario
  and thread mode, configurable; the owner decides whether the observed rate is
  acceptable.
- Should a verbatim-span detector (long common substring with the other slot's stored
  question/result payloads) be added to the guard in Lua, or stay in the evidence
  harness only? Assumed harness only in this proposal (Lua cost on 16 KiB payloads).
