# Tasks: issue-377-spike-mctl-mcp-events-sep-3415-portable

Revision 2. This is an offline-only slice: report, manifest, model and tests in
`mctlhq/.github`. There is no live webhook, host, account or production
activity. Approval and the implementer wait for the independent review of the
P1 and P2 fixes.

- [ ] 1. Add `roadmap/spikes/mcp-events-sep-3415.yaml`:
  - SpikeDefinition with owner `mctlhq/.github`, issue `#377`, `lifecycle: proposed`;
  - the four outcomes and `evidence.report: docs/spikes/mcp-events-sep-3415.md`;
  - no `decision` block, and a header comment saying the verdict lives in the report only.

  DoD: `python3 roadmap/scripts/validate.py` and `roadmap/tests/test_validate_spike.py` pass.
- [ ] 2. Pin the sources in the report and in `docs/spikes/mcp-events-sep-3415/model/SPEC_PIN.md`:
  - `ext-events` `specification/beta/events/events.mdx` at `17c0c64a5edb89dc5081d00ed50c4f836bbb67ff`, introduced by `24727f38`, read in full and quoted for every rule used;
  - three separate maturity rows: governance (plan site, reported `final` 2026-11-19, observed or not), voting tracker (`Scheduled`, PR #3415 merged, 2026-11-04), and extension (`Beta`);
  - SDK packages and versions, or "none published";
  - the OpenAI doc quotes with retrieval date;
  - spec ordering rules, quoted or marked `[INFERRED]`.

  DoD: every row is tagged. A DEFER is proposed only on the triggers in design section 5.
- [ ] 3. (depends on 2) Write the finding-to-change matrix. It has one row for each of P1-EV-01..04 and P2-EV-05..07, with the spec quote, the revision 1 claim, the revision 2 change, the model file and the test ids.

  DoD: every row has a passing test id or a named doc-review check.
- [ ] 4. (depends on 2) Write the method map:
  - list exactly the pinned methods, notifications and control envelopes;
  - map each to the MCTL equivalent (envelope field, Valkey operation, delivery row, `ack_event`);
  - add a separate table for Events vs `resources/subscribe` + `notifications/resources/updated` vs Tasks status (#41) vs `notifications/claude/channel`.

  DoD: no name appears that the pinned spec does not define.
- [ ] 5. Write the WP1 inventory from design "Deployed state checked":
  - mctl-api `4.173.0` outbox relay and mctl-telegram producer;
  - streams, ACL users and consumer groups;
  - ACK, dedupe and replay;
  - paused `labs/claude-remote`, the tunnel consumer, #66, #82 and mctl-agents#712.

  DoD: every row is labeled merged, deployed or observed, with a citation; unobserved items are written as unknown.
- [ ] 6. (depends on 2) Write the WP2 host matrix and the ChatGPT-vs-spec divergence table: capability key, error code, `webhook-id`, and the unsupported poll, stream, `gap` and `terminated`.

  DoD: ChatGPT interoperability is marked `unknown (not observed)`, no cell infers support from another surface, and #300 is referenced as distinct.
- [ ] 7. (depends on 2) Write the reference model `docs/spikes/mcp-events-sep-3415/`:
  - `model/stream.py`, `store.py` (transactions, unique keys, CAS, crash-injection points), `subscriptions.py`, `projection.py`, `fanout.py`, `delivery.py` (barrier hooks), `cursor.py`, `webhooks.py`, `callback_guard.py`, `server.py`, `client.py`, `recipient.py`;
  - `fixtures/` with synthetic envelopes only, including `synthetic.devloop.proposal_ready` and a `github.pull_request` fixture;
  - `README.md`.

  DoD: stdlib only, no network, and `python3 -I -m unittest discover docs/spikes/mcp-events-sep-3415/tests` is green.
- [ ] 8. (depends on 4, 5, 6, 7) Write the remaining report sections:
  - adapter design;
  - ADR options for the four outcomes plus the dropped alternatives;
  - pilot: synthetic event, mock recipient, reference poll client, Channels compared unchanged, watchers kept;
  - hypotheses: time-to-review, duplicate and noise rate, delivery lag, retry/expiry/revocation counts, token cost per successful reaction vs polling, repeat usage;
  - future slices (Telegram PA, Alice, SeerrSense, Glovo if authorized, SecOps, release);
  - P1, P2 and P3 risks;
  - GO/NO-GO with the proposed verdict BOUNDED_HOST_PILOT (offline-first) and the DEFER triggers.

  DoD: no runtime claim without an `[OBSERVED]` measurement.
- [ ] 9. (depends on 8) Write the fixture-vs-live runbook.
  - Fixture mode: test commands and expected output.
  - Live gates, each needing separate owner approval:
    - G-L1: a Valkey ACL user plus a flagged mctl-api slice on `mctl:events:synthetic` only;
    - G-L2: one synthetic delivery to an operator-owned mock HTTPS recipient;
    - G-L3: one ChatGPT Work or dots subscription with a synthetic event, resolving the divergence table and coordinated with #300;
    - G-L4: any real producer or content.
  - Each gate lists preconditions, a kill switch and the evidence to capture. Secrets never appear in captures.

  DoD: no gate is executed by this spike.
- [ ] 10. (depends on 1, 8) Add one entry to the `# Spikes` list in `AGENTS.md` with the proposed verdict, and request an independent review on the PR.

  DoD: the entry matches the existing style, and the lifecycle stays `proposed`.

## Tests

- [ ] T1. Projection: each fixture yields an `EventOccurrence` with `eventId == envelope.id` and `data` limited to envelope references. `events/examples/invalid/body-field.json` is rejected, audited and acknowledged, and never delivered.
- [ ] T2. Cross-tenant: a tenant A subscription never materializes a delivery whose subject resolves to tenant B or to no tenant.
- [ ] T3. Secret validation: a missing secret, a secret without `whsec_`, one under 24 bytes and one over 64 bytes all get `InvalidParams` (`-32602`). No code path generates a server secret.
- [ ] T4. Secret refresh: a refresh with a new secret produces dual signatures during the grace window and only the new signature after it. The recipient verifies both phases. There is no server-initiated rotation.
- [ ] T5. Secret hygiene: across a full fixture run, no log, audit record, capture or error payload contains the secret or its base64 body. Only the fingerprint appears.
- [ ] T6. Two subscriptions, one event: both get a delivery with the same `eventId` and distinct `webhook-id`s. Neither recipient treats its delivery as a duplicate.
- [ ] T7. Retry identity: retries of one delivery reuse its `webhook-id` with a fresh `webhook-timestamp` and signature. `webhook-id` never equals `eventId`. `X-MCP-Subscription-Id` is present on every delivery and on control envelopes, and each control envelope has its own id.
- [ ] T8. Replay and spoofing: a timestamp older than 5 minutes is rejected. A seen `webhook-id` is rejected without a second side effect. A bad signature, a missing header or a secret past the grace window is rejected.
- [ ] T9. Cursor null: `events/poll` with `cursor: null` or no cursor returns no backfill, and the returned cursor starts at the current tail. `maxAgeMs` is ignored.
- [ ] T10. Gap: after trimming past MAXLEN, polling with an old cursor returns the earliest retained events, `truncated: true` and a fresh cursor, and no JSON-RPC error. The webhook subscribe or resume equivalent emits a signed `gap` envelope. `maxAgeMs` later than the cursor also yields `truncated: true`.
- [ ] T11. Pagination: more than `maxEvents` available yields `hasMore: true`, and following the cursors returns every event exactly once in order.
- [ ] T12. Crash before materialization commit: the entry stays pending, `XAUTOCLAIM` re-materializes it, and each subscription ends with exactly one delivery row.
- [ ] T13. Crash after commit, before `XACK`: replay inserts no new rows, and each recipient accepts exactly once.
- [ ] T14. Crash after POST, before marking `delivered`: the resend carries the same `webhook-id`, and the recipient dedupes.
- [ ] T15. Independent progress: with subscriptions S1 (recipient returns 500 until dead-letter, or is revoked mid-run) and S2 (healthy), S2 receives every event in order. S1 retries with capped backoff, then dead-letters with an audit record. `410` deactivates and `413` is not retried. The stream PEL drains regardless of S1. S1 over quota stops materializing and later gets a `gap`.
- [ ] T16. No extension: a server without `io.modelcontextprotocol/events` in `capabilities.extensions` answers `-32601` to `events/*`. The reference client sends no `events/*` call and reports only the existing fallbacks, with no Events cursor reuse.
- [ ] T17. Revocation race (controlled barrier):
  - an attempt claimed before the revoke commit may POST, and `events/unsubscribe` returns only after it completes or times out;
  - an attempt whose claim follows the revoke commit sends nothing;
  - after the unsubscribe response, zero attempts are in flight.
- [ ] T18. ACK facts: a 2xx sets `delivered` only. `processed` changes only through the explicit processing-ack call. Expiry without a refresh before `refreshBefore` stops delivery and sends `terminated`.
- [ ] T19. Verification: no delivery before activation. A wrong or delayed echo fails with `CallbackEndpointError` `-32027`. A constant-time match activates.
- [ ] T20. SSRF: the guard rejects:
  - http, userinfo, IP literals;
  - 127.0.0.1, 10/8, 169.254.169.254, 100.64/10, ::1 and fc00::/7;
  - an off-allowlist port and a 3xx response (not followed);
  - a resolver that answers public at registration and private at delivery.
- [ ] T21. Audit: each stage writes one record with envelope `id`, `correlation_id`, subscription id and `webhook-id`, and no content or secret.
- [ ] T22. Repository: `roadmap/scripts/validate.py` accepts the manifest, and `events/tests/test_envelope_schema.py` passes unchanged.

## Rollback

Only documentation, a roadmap manifest and offline model code in `mctlhq/.github`
change, so reverting the PR is a complete rollback. No service, stream, ACL,
secret, host subscription or Claude Channel configuration is touched. If the owner
rejects the verdict, a follow-up PR sets the manifest lifecycle to `parked` with
an `activation.trigger` (for example "a target host is observed accepting
spec-conformant deliveries"), or to `archived`.
