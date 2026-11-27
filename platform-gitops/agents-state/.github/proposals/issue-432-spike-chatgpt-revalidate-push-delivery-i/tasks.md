# Tasks: issue-432-spike-chatgpt-revalidate-push-delivery-i

Research only. No runtime, permission, account or GitHub-write changes.

- [ ] 1. Re-fetch and pin first-party sources:
  - developers.openai.com/plugins/build/mcp-events;
  - learn.chatgpt.com/docs/dots;
  - help.openai.com articles 20001275 (Work), 20001274 (Voice), 20001638 (voice retirement) and 10291617 (Scheduled tasks);
  - the OpenAI Terms of Use;
  - developers.openai.com/apps-sdk/build/state-management;
  - modelcontextprotocol.io/docs/extensions/apps.

  Search once more for a first-party definition of "GRTC".

  DoD: every quote recorded with URL and retrieval date. Absent statements recorded as "not documented", not as "unsupported".
- [ ] 2. Write `roadmap/spikes/chatgpt-scout-push.yaml` (depends on 1). Content: a SpikeDefinition with issue `mctlhq/.github#432`, `lifecycle: proposed`, outcomes `GO_STANDARD_CHAT`, `PROPOSE_OFFICIAL_WORK_VOICE_PILOT`, `PROPOSE_USER_CONTROLLED_BROWSER_BRIDGE` and `DEFER_UNSUPPORTED`, `evidence.report`, and no `decision` block. DoD: the roadmap validator under `roadmap/scripts` and `roadmap/tests` passes.
- [ ] 3. Write the reference model `docs/spikes/chatgpt-scout-push/model.py`, `fixtures/` and `tests/` (depends on 1). Contents:
  - an immutable `DigestStore`;
  - `publish_digest`;
  - `project_event` producing an envelope-v1 dict;
  - `FakeStream`;
  - a `Subscription` with a `whsec_` secret, revoke and reconnect;
  - a `ChatGPTRecipient` that records `conversation_id` and dedupes `eventId`;
  - a `Clock` without a timer API;
  - an audit log.

  DoD: `python3 -I -m unittest discover docs/spikes/chatgpt-scout-push/tests` passes with no network.
- [ ] 4. Write the report `docs/spikes/chatgpt-scout-push.md` (depends on 1, 3). Sections:
  - the capability matrix with evidence tags;
  - the delivery-kind glossary;
  - the architecture and ownership map;
  - the owner sequence;
  - the threat model;
  - costs;
  - the test plan;
  - the operator proof checklist;
  - the verdict `PROPOSE_OFFICIAL_WORK_VOICE_PILOT` with alternatives;
  - a section stating #300 is unchanged.

  DoD: every capability claim is tagged. The Work chat is labelled as distinct from the existing standard chat. The report makes no unsupported delivery claim.
- [ ] 5. Add a Spikes index line to `AGENTS.md` pointing to the report (depends on 4). DoD: the entry says "proposed verdict" and "owner choice required".
- [ ] 6. Operator proof checklist, written in the report and not executed. Each step requires separate explicit owner approval:
  - (a) record the plan and confirm Work and MCP Events in the account;
  - (b) create one dedicated Work chat and record its conversation id from the URL;
  - (c) check Settings and Scheduled for any slot consumed by the subscription;
  - (d) deliver one synthetic `scout.digest.ready` and confirm the same conversation id;
  - (e) on Android, open the chat from Recents, start Voice, and confirm the transcript lands in the same chat;
  - (f) revoke the connector and confirm no delivery follows;
  - (g) reconnect with a fresh secret.

  DoD: each step names the evidence to capture and a fail outcome (`DEFER_UNSUPPORTED`).

## Tests

All offline, run with `python3 -I -m unittest`. Live steps are checklist items only.

- [ ] T1. Envelope conformity: the fixture `scout.digest.ready` validates against `events/schemas/event-envelope.v1.schema.json`. It must be at most 4096 bytes, have `id == "scout:" + run_id` and `correlation_id == run_id`, and hold no digest text in `subject`.
- [ ] T2. Immutability: a second `publish_digest` with the same `run_id` and text is a no-op. The same `run_id` with different text is refused and audited.
- [ ] T3. Authorized read: an admin read returns identical bytes and a sha256 equal to `subject.digest_sha256`. A non-admin or tenant-bound principal is refused.
- [ ] T4. No re-collection: a retried publish or a redelivery calls no feed-fetch or scoring stub. The test asserts a call count of 0.
- [ ] T5. Dedupe: two deliveries with the same `eventId` produce one recipient turn.
- [ ] T6. Same conversation: the recipient records the same `conversation_id` at subscription and at delivery. A model variant that opens a new chat makes the proof fail. This encodes the `DEFER_UNSUPPORTED` branch.
- [ ] T7. No polling or slot: the model exposes no `events/poll` and no timer. Delivery happens only on `FakeStream` append. Any scheduled trigger raises.
- [ ] T8. Retry: transient 5xx responses are retried with backoff up to a cap, then dead-lettered. `410` deactivates the subscription. Audit carries `run_id`.
- [ ] T9. Disconnect and reconnect: after revoke, nothing is delivered. Reconnect requires a new `whsec_` secret, and the old signature is rejected.
- [ ] T10. Secret hygiene: no audit record or captured output contains the secret, only a truncated sha256 fingerprint.
- [ ] T11. Telegram intact: the model's publish path runs after a stub `send_message` and never alters or suppresses it.
- [ ] T12. Report lint: every matrix row has an evidence tag, and the verdict is exactly one of the four outcomes.

## Rollback

The change is documentation, one manifest and offline code in `mctlhq/.github`.
Revert the PR to roll it back. No runtime component, secret, ACL, stream,
subscription or account link is created, so nothing else needs undoing. #300 and
#377 artifacts are never modified, so they need no restore.
