# Tasks: issue-108-test-bridge-prevent-unintended-claude-a

- [ ] 1. Canary routing tests against the current bridge: add `plugin/mctl-bridge/test/disclosure.test.ts` covering A to orchestrator to B flows (questions, results, late evidence, replies, reverse direction, concurrent questions, forged/replayed outbox entries, epoch and uuid swaps) with per-test random canaries and a full scan of B's `inbox`/`resp` streams and FakeClaude notifications. — DoD: passes on the unchanged library; no real secrets in fixtures.
- [ ] 2. Owner keys and ACL: add `%R~mctl:owner:*` for `bridge_orch` in `ops/install.sh` and `test/support.ts`; extend the install/test parity test to the ACL line. (depends on 1) — DoD: test proves `bridge_orch` cannot write `mctl:owner:*` and slots cannot read it.
- [ ] 3. Guard in `src/bridge.lua` (VERSION '5'): `bridge_private_mark`, `bridge_private_unmark`, `bridge_handoff_grant` (first key `mctl:owner`), `disclosure_check` called first in `send` and `reply`, `handoff_id`/`source_slot`/`purpose` on messages and in `next_message` output, audit entries without marker text. (depends on 2) — DoD: refusal codes `disclosure_blocked`, `handoff_invalid` with reasons `unknown|expired|used|target_mismatch|target_stale|excerpt_mismatch`; no write before the check.
- [ ] 4. Typed wrappers and CLIs: `handoffId` on `Bridge.send`/`Bridge.reply` in `src/store.ts`; `--handoff` on `send`/`reply` in `src/cli.ts`; new `src/owner.ts` (`mark`, `unmark`, `grant`, `grants`) computing `excerpt_sha256`; install as `mctl-bridge-owner` via `ops/install.sh`; leave `ops/codex-mctl-bridge.rules` unchanged and add a `not_match` example for `mctl-bridge-owner`. (depends on 3) — DoD: CLI tests for exit codes 0/1/2 and JSON output.
- [ ] 5. Adapter provenance: `notificationFor` in `src/channel.ts` adds `handoff_id` and `source_slot` to `meta` and a provenance header line. (depends on 3) — DoD: adapter test sees the meta on a handoff and its absence otherwise.
- [ ] 6. Extend `test/disclosure.test.ts` for the guard and handoffs (blocked markers incl. role-play/fake-approval/quoted-injection wrappers, exact-excerpt delivery, every invalid-grant reason, unreadable store fails closed with unchanged snapshot, owner functions refused for `bridge_orch`). Add scenario 6 `test.todo` entries referencing #107. (depends on 3, 4, 5) — DoD: green in `bun test`.
- [ ] 7. Mutations in `test/mutate.py`: guard off, grant target check off, epoch binding off, byte compare to prefix, used-marker off, provenance meta dropped. (depends on 6) — DoD: `python3 test/mutate.py` reports every mutation killed.
- [ ] 8. Live harness `test/e2e/disclosure-e2e.ts` with `--runs`, `--thread fresh|warm`, sanitized JSONL evidence and summary; exit non-zero on any `leak`; `unknown` when a delivery cannot be bound. (depends on 4) — DoD: dry run against `test/fakeapp.ts` produces valid evidence; a deliberately leaking fake reply yields `leak` and exit 1.
- [ ] 9. `ops/os-negative-controls.sh` (A reads B and B reads A: worktree, password files, `orch.pw`, `admin.pw`, Codex socket) writing separate evidence; prints `unavailable` and exits 3 while A and B share a uid. (depends on #106 for a real run) — DoD: shell syntax check and a shared-uid run that reports `unavailable`.
- [ ] 10. Docs: "Cross-slot disclosure" rules in `ops/orchestrator-AGENTS.md`; "Disclosure boundary (issue #108)" section in `docs/chatgpt-orchestrator-bridge.md` and a short note in `plugin/mctl-bridge/README.md` (what is proven, what is measured, gate, no automatic grants). Bump `package.json` version. (depends on 3-9) — DoD: docs match the implemented codes and evidence format.

## Tests

- [ ] T1. Routing: A canaries never in B's streams or notifications; reply and its `Question:` text only to the asker; reverse direction B to A symmetric.
- [ ] T2. Forged outbox entry naming B, stale epoch, replaced conn, replayed rid, `/clear` uuid swap: B unchanged (snapshot equality).
- [ ] T3. `send`/`reply` to B containing an A marker (plain and wrapped in role-play, fake owner approval, quoted injection): `disclosure_blocked`, no state change, audit has marker index but no marker text.
- [ ] T4. Valid handoff: byte-identical excerpt delivered once to B with `handoff_id`, `source_slot`, purpose; audit carries the sha256; a second use is `used`.
- [ ] T5. Invalid handoffs: unknown, expired, wrong target, B re-registered after grant, one byte changed, extra A canary appended: all refused, nothing delivered.
- [ ] T6. `bridge_orch` cannot call owner functions or write `mctl:owner:*`; slot users cannot read `mctl:owner:*`.
- [ ] T7. Marker/grant store unreadable: `send`/`reply` fail, snapshot unchanged.
- [ ] T8. Concurrent questions from A and B answered by one orchestrator: each reply reaches only its asker.
- [ ] T9. Mutation run kills every new mutation.
- [ ] T10. E2E harness against the fake app: pass, blocked, leak and unknown outcomes are classified correctly; evidence contains no canary values.
- [ ] T11 (manual, Mac mini, owner reviewed). Live runs fresh and warm, N repetitions; OS controls after #106; results reported as observed counts.

## Rollback

The change is confined to `plugin/mctl-bridge/`, its ops files and docs. Revert the PR,
re-run `mctl-bridge init` with the admin credential to load library VERSION '4', and
re-run `ops/install.sh` to restore the previous ACL file; delete `mctl:owner:*` and
`mctl:bridge:handoff-used:*` keys with `bridge_admin`. Messages created under VERSION
'5' keep extra hash fields that VERSION '4' ignores. The E2E harness and OS-controls
script are manual and have no runtime footprint.
