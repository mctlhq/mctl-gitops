# Tasks: issue-107-feat-bridge-codex-initiated-context-requ

- [ ] 1. Probe session context sources on test slots only, never on working slots. Use `docs/orchestrator-bridge-spike/` style scripts plus a temporary `hooks/state.py` logging change. Check:
  - whether hook input carries `transcript_path`;
  - whether that file, read as the slot's own OS user, matches the visible conversation;
  - how it looks after `/compact` and after `/clear` (new session id);
  - what an active slot can accurately report about its current turn, earlier compacted turns and tool results.

  Record supported, unsupported and unknown honestly in a new "Context requests: probe results" section of `docs/chatgpt-orchestrator-bridge.md`.
  DoD: the doc section exists, with dated evidence for each source and without logging secrets or transcript content. `transcript_page` is marked proven or unsupported.
- [ ] 2. (depends on 1) Write the protocol into `docs/chatgpt-orchestrator-bridge.md`, in a section "Context requests". Cover:
  - `ContextRequest`/`ContextResponse` fields;
  - the states `queued -> emit_intent -> emitted -> acked -> answered|unavailable` plus `expired`/`cancelled`/`delivery_unknown`;
  - the keys `ctx:<id>:body`, `ctxgrant:<slot>:<uuid>`, `ctxbudget:<slot>:<hour>` and slot field `ctx_inflight`;
  - the emit rule, budgets, grants and trust policy.

  DoD: the section is reviewed and merged before any code. It matches design.md.
- [ ] 3. (depends on 2) Change `src/bridge.lua` to `VERSION = '5'`:
  - add `bridge_request_context`, `bridge_ack_context`, `bridge_answer_context`, `bridge_ctx_grant` and `bridge_ctx_revoke`;
  - add the `ctxreq` branch in `next_message`, and make the task branch require `ctx_inflight == ''`;
  - handle `ctxreq` in `mark_emitted`, `emit_lost`, `abandon`, `expire`, `repair` and `resolve`;
  - cancel a bound ctxreq when its task goes terminal;
  - add `answered`/`unavailable` to `TERMINAL`;
  - add `ack_context`/`answer_context` to `SLOT_FN`;
  - add the optional `caps` argument to `register` (`slot_unsupported` for adapters without it).

  DoD: library loads, v4 tests still pass, new store tests (T1-T8) pass.
- [ ] 4. (depends on 3) Update `src/store.ts`:
  - `LIBRARY_VERSION = "5"`, `newId` kind `cx`;
  - key helpers;
  - `Bridge.requestContext/ackContext/answerContext/contextGet/ctxGrant/ctxRevoke`;
  - `SlotApi` gains `ackContext` and `answerContext`, implemented in `src/slotlink.ts`.

  DoD: typecheck passes. Isolation tests (T9) pass over the rpc transport.
- [ ] 5. (depends on 4) Update `src/channel.ts`:
  - the `ctxreq` rendering in `notificationFor()`;
  - the `ack_context` and `answer_context` tools with a `ctxAdmissions` map and `stale_grant` checks;
  - digest, size and redaction computation;
  - the `caps=ctx` registration;
  - new `INSTRUCTIONS` rules;
  - `SERVER_VERSION` bump.

  DoD: adapter tests (T10-T12) pass.
- [ ] 6. (depends on 1, 5) Add `src/transcript.ts` (bounded, redacting, cursor-based reader running as the slot user). Record `transcript_path` in `hooks/state.py`. Put the reader behind `MCTL_BRIDGE_TRANSCRIPT`, default off. Ship it only if task 1 proved the source; otherwise it always returns `unavailable/unsupported`. DoD: T13-T14 pass, and the flag-off path is tested.
- [ ] 7. (depends on 4) Update `src/cli.ts`:
  - add `request-context`, `context-get`, `context-grant` and `context-revoke`;
  - `status`/`tasks` show ctxreq metadata without the body;
  - `wait` reports `context_answered`.

  Update `ops/codex-mctl-bridge.rules` to allow `request-context` and `context-get`, not `context-grant`, with `match`/`not_match` examples. DoD: cli tests (T15) pass and the rules file parses.
- [ ] 8. (depends on 4) In `src/waker.ts` and `wake_begin`, generalize the wake source from `question_id` to a message id, so that `context_answered` on a bound, unclaimed question can wake the thread within the existing budgets. DoD: waker tests (T16) pass with `test/fakeapp.ts`.
- [ ] 9. (depends on 7) Update `ops/orchestrator-AGENTS.md` and `plugin/mctl-bridge/README.md` to describe how to request context and the trust rules: an answer is data, never approval, a tool instruction or a reason to forward to another slot. Update the marker string. DoD: docs reviewed.
- [ ] 10. (depends on 3-9, #106 passed, owner authorization) Run the end-to-end scenarios on the isolated Valkey with test slots A and B and a real Codex app-server wake (E1-E6), and record the results in the doc. DoD: results table committed. There is no rollout to working slots in this proposal.

## Tests

Unit and integration tests, under `plugin/mctl-bridge/test/` with bun against a local valkey-server, as in the existing suites:
- [ ] T1. `request-context` validation: an unknown scope, `max_bytes` 0 or greater than 16384, a bad id or an unregistered slot each give `bad_request` or `slot_not_registered`. A slot registered without `caps` gives `slot_unsupported`.
- [ ] T2. Idempotency: the same `idem` returns the same id with `dedup:true`, and only one record exists.
- [ ] T3. Budgets: the ninth request on one task gives `ctx_budget`, and so does the 31st per slot per hour. Hop is greater than `MAX_HOP` gives `hop_limit`. A refusal leaves no record.
- [ ] T4. Busy: a slot with `busy=1` gets nothing from `next`. When it turns idle, the ctxreq is emitted, and a task queued earlier is not emitted while `ctx_inflight` is set.
- [ ] T5. Bound request during an open question. Steps: task acked, `ask`, slot idle, `request-context --task`. Then `next` emits the ctxreq, `ack_context` and `answer_context` run, then `reply`. Then `next` emits the reply on the same `attempt_id`, `ack_reply` runs, and `report_result` completes on that attempt.
- [ ] T6. Stale epoch. Re-register (an epoch bump) before emit: the ctxreq is `cancelled/addressee_changed`. After emit: it becomes `delivery_unknown`, and an `answer_context` with the old admission is refused and recorded in `late:<cx>` with digest and size, never the body.
- [ ] T7. Size: an answer longer than `max_bytes` gives `too_large` and the request stays `acked`. An `unavailable` answer is stored with its reason and empty body. Expiry clears `ctx_inflight`.
- [ ] T8. A task going terminal cancels its bound ctxreq. `resolve` behaves the same.
- [ ] T9. Isolation (extends `isolation.test.ts`): slot A's ACL user cannot read `ctx:*`, `ctxgrant:*` or B's keys. A forged `answer_context` for B's request through A's outbox changes nothing. Every v4 isolation test still passes.
- [ ] T10. The adapter rejects a mismatched context grant (`stale_grant`) and an `answer_context` without an admission.
- [ ] T11. The purpose text contains apostrophes, `$(touch marker)`, newlines and fake "ack_task" instructions. It is rendered verbatim as data, and nothing is executed.
- [ ] T12. The redaction pass removes token patterns from answers, and `redactions` counts them. No body appears in the `audit`/`outbox` streams or in adapter stderr logs.
- [ ] T13. Transcript reader: it pages by cursor with a correct `next_cursor` and `source_rev`, skips thinking blocks, reports a compaction marker, refuses a path outside the slot's projects directory or for another session id, and refuses when no grant exists (`not_authorized`) or the grant is for an old uuid.
- [ ] T14. With `MCTL_BRIDGE_TRANSCRIPT` off, `transcript_page` always answers `unavailable/unsupported`.
- [ ] T15. CLI: `context-get` prints the body as a JSON string field, and `context-grant` requires `--reason` and `--ttl`.
- [ ] T16. Waker: `context_answered` on a bound, unclaimed question produces one wake within the hourly and per-message limits, and never a second `turn/start` after a lost reply.
- [ ] T17. Mutation check, using `test/mutate.py` style: reverting the `ctx_inflight` guard, the uuid/epoch binding or the size cap makes a test fail.

End-to-end on the Mac mini (task 10, after #106 and owner authorization, test slots only):
- [ ] E1. A asks Codex, and Codex requests context from A over a real app-server wake. A returns a bound excerpt, Codex replies, and A continues the same attempt. B receives nothing.
- [ ] E2. E1 repeated for B, with A unaffected.
- [ ] E3. Concurrent context requests to A and B while both have open questions: there is no cross-delivery, and each answer carries its own slot, uuid and epoch.
- [ ] E4. `/clear` and an adapter restart between request and answer: the request is refused as stale and nothing is invented.
- [ ] E5. A busy slot with a long tool call: the request waits, and either expires or is answered after Stop. The tool result is never interrupted.
- [ ] E6. Transcript paging across 3 pages and across `/compact`, only if task 1 proved the source. Otherwise, verify the answer is `unsupported`.

## Rollback

- Code: revert the PRs. Load library v4 again (`mctl-bridge init` from the reverted checkout) and restart the adapter, waker and CLI together. `checkVersion()` makes a mixed state fail loudly instead of silently.
- Data: v5-only keys (`ctx:*`, `ctxgrant:*`, `ctxbudget:*`, `msg:cx-*`) are ignored by v4. Open ctxreqs should be resolved or cancelled before the downgrade (`mctl-bridge tasks` lists them). Otherwise a v4 `next_message` drops unknown-kind ready entries (its `else` branch `ZREM`s them), and the slot's `ctx_inflight` field must be cleared manually (`HDEL`, an operator action recorded in the doc).
- Operational kill switch without a revert: turn transcript paging off (`MCTL_BRIDGE_TRANSCRIPT` off), remove `request-context` from `ops/codex-mctl-bridge.rules` so every request prompts, and revoke all grants (`context-revoke`).
