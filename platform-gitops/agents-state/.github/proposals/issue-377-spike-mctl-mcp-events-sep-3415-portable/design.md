# Design: issue-377-spike-mctl-mcp-events-sep-3415-portable

Revision 2. This revision answers the REQUEST_CHANGES review of 2026-11-22
(P1-EV-01 to P1-EV-04, P2-EV-05 to P2-EV-07). It remains a research-only spike
with no runtime change.

## Current state

### Event contract in this repository (`mctlhq/.github` @ `60e9db5`)

- `events/README.md` defines the delivery chain: producer (mctl-telegram,
  mctl-api), then Valkey Streams, then the mctl-events Channel adapter
  (mctl-claude-remote), then the running Claude session, then hydration through
  the source's tools, then `ack_event`, then `XACK`. The rules it states:
  - "the event is disposable; the source is canonical";
  - delivery is at-least-once from a durable producer outbox;
  - consumers dedupe by `id`, and there is "one consumer group per session";
  - producers trim with `XADD ... MAXLEN ~ 10000`.
- `events/schemas/event-envelope.v1.schema.json` is closed, capped at 4096 bytes
  by consumers, and has fields `specversion`, `id` (stable, source-derived dedup
  key), `type` (`<domain>.<entity>.<action>`), `source`, `occurred_at`,
  `correlation_id` and `subject` (string references only). There is **no tenant
  or principal field**.
- `events/examples/{valid,invalid,calendar-invalid}/` and
  `events/tests/test_envelope_schema.py` are fixtures the model reuses.
- `docs/spikes/automation-control-plane.md` (about lines 247 and 279) states
  that "crash-safe per-subscriber event fanout" was not proven. Revision 2 makes
  that the central contract the model must prove (P1-EV-04).
- Spike conventions come from `roadmap/schemas/spike-definition.schema.json`,
  `roadmap/spikes/journey-intent-correlation.yaml`,
  `roadmap/spikes/mcp-tasks-durable-execution.yaml` (#41) and the stdlib-Python
  model style of `docs/spikes/finance-assistant/`.

### Deployed state checked

- `[GITOPS]` `infra-components/data/valkey/configmap.yaml` (mctl-gitops @ `e1d0b67`): `appendfsync everysec`, `maxmemory 200mb`, `maxmemory-policy noeviction`.
- `[GITOPS]` `infra-components/data/valkey/externalsecret.yaml` lines 48-54:
  - `default` is off;
  - `telegram-producer`, `github-producer` and `synthetic-producer` may only `+xadd` to their own stream and `mctl:events:audit`;
  - `claude-remote` has `xreadgroup`/`xack`/`xautoclaim`/`xclaim`/`xpending`/`xgroup|create` on the three streams, `xadd` on audit and state keys `mctl:events:state:*`;
  - `events-observer` has read-only access to audit;
  - no ACL user exists for any other consumer.
- `[GITOPS]` `services/labs/claude-remote/values.yaml`: tag `0.31.0`, `replicaCount: 0` (in-cluster consumer paused). The comments record the #66 fake-ack / inflight failure and the #82 token-renewal metrics.
- `[GITOPS]` `bootstrap/templates/mctl-platform/mctl-api.yaml`: mctl-api tag `4.173.0`. Lines 430-431: the GitHub webhook "enqueues into the audit database's outbox and a relay XADDs to mctl:events:github". mctl-api therefore already owns a transactional database and an outbox pattern, which revision 2 reuses for per-subscription delivery records.
- `[OBSERVED]` `mctl_get_service_status(labs, claude-remote)` on 2026-11-22: Argo `Healthy`/`Synced`, image `0.31.0`. With `replicaCount: 0` this means no in-cluster consumer is running.
- `[GITOPS]` `agents-state/.github/proposals/issue-300-spike-events-push-github-events-into-exi/.status.yaml`: `status: accepted`, `blocked.code: execution-unauthorized`. The existing-ChatGPT-chat question (#300) is unresolved.
- Not observed: live stream lengths, consumer-group lag, the Mac mini tunnel consumer's liveness, audit stream contents, the `mctl-events-policy` ConfigMap. These are recorded as unknown, not absent.

### External sources (retrieved 2026-11-22)

- `[DOC]` Normative spec, `modelcontextprotocol/ext-events` `specification/beta/events/events.mdx`:
  - pinned at commit `17c0c64a5edb89dc5081d00ed50c4f836bbb67ff` (2026-11-19T15:41:56Z); the file was added by `24727f38a180b1bde5df1c6eae580ea0a0b703ee` ("Add Events extension specification at Beta");
  - header: "Stage: Beta · Extension identifier: `io.modelcontextprotocol/events`", for protocol revision `2026-07-28` and later.

  Rules quoted from that file:

  | Topic | What the spec says |
  |---|---|
  | Capability | Advertised as a key in `capabilities.extensions`; "A client MUST NOT send them to a server that has not advertised the extension" (`-32601` otherwise). |
  | Methods | `events/list`, `events/poll` (`name`, `arguments`, `cursor`, `maxAgeMs`, `maxEvents`), `events/stream` (`heartbeatMs`), `events/subscribe` (`delivery{mode,url,secret}`, `cursor`, `maxAgeMs`, `ttlMs`), `events/unsubscribe` (`name`, `arguments`, `delivery.url`). |
  | Notifications | "The only message this extension adds outside an `events/*` request is `notifications/events/list_changed`". Push uses `notifications/events/{event,active,error,heartbeat,terminated}`. |
  | Webhook control envelopes | Discriminated by top-level `type`: `gap`, `terminated`, `verification`. |
  | Subscription key | "The subscription key is `(principal, delivery.url, name, arguments)`"; "`principal` comes from the authorization layer"; unauthenticated calls get `Forbidden`. |
  | Secret | "`delivery.secret` is REQUIRED. The client supplies the HMAC signing secret, and the server never generates one". Format `whsec_` plus base64 of 24 to 64 random bytes; other values are rejected with `InvalidParams`. Rotation is a client refresh with a new secret; the server "SHOULD dual-sign ... for a short grace window"; "There is no server-initiated rotation." |
  | Webhook identity | `webhook-id` "MUST NOT be derived from `eventId`", is "reused across retries of that message", and receivers "SHOULD deduplicate on `webhook-id`"; "the same `eventId` delivered on two subscriptions is two deliveries"; `X-MCP-Subscription-Id` carries the subscription id. |
  | Cursors | "`null` means "start from now""; absent is the same as `null`; a `null` cursor must not be persisted. "`truncated: true` is the single signal" of a possible gap, returned with a fresh `cursor`. With `maxAgeMs`, replay starts from the later of the cursor and `now − maxAgeMs`, and `maxAgeMs` is ignored for a `null` cursor. With `hasMore`, the client polls again immediately. |
  | Occurrence | `eventId`, `name`, `timestamp`, `data` are required; `cursor` and `_meta` are optional. |
  | Retry | Each event is retried independently with exponential backoff; attempts and elapsed window are capped; `410` and `413` are non-retryable. |
  | Verification | Delivery starts only after a constant-time echo match; failure gives `CallbackEndpointError` `-32027`. |
  | Expiry | `refreshBefore` is the grant, and the subscription must be refreshed before it. |
  | Webhook safety | Receivers SHOULD reject a `webhook-timestamp` older than 5 minutes. The server validates the callback at delivery time, rejects non-globally-routable IPs, and "MUST NOT follow HTTP redirects". |
  | Errors | `NotFound` `-32023`, `Forbidden` `-32024`, `ResourceExhausted` `-32025`, `Unsupported` `-32026`, `CallbackEndpointError` `-32027`, `HeaderMismatch` `-32020`. |

  The last 380 characters of the file were not read in this run, so task 2 re-reads the whole file.
- `[DOC]` https://voting.modelcontextprotocol.io/p/seps/3415: State "Scheduled", linked PR `modelcontextprotocol/modelcontextprotocol#3415` "Merged", meeting 2026-11-04 "passed".
- plan.modelcontextprotocol.io: the fetch rendered only the title "MCP Spec TPM", so it is unknown (not observed). The review reports `final` 2026-11-19, and this design records that as reported.
- `[DOC]` https://developers.openai.com/plugins/build/mcp-events: "available in Work chats on ChatGPT web", plus the desktop app with Cloud and dots. Webhook only: "Polling, streaming, and the draft's gap and terminated control notifications are not supported". ChatGPT supplies the callback URL and a `whsec_` secret. It diverges from the pinned spec in three places:
  - the capability key is `events` in `initialize` / `server/discover` capabilities;
  - `CallbackEndpointError` is `-32015`;
  - `webhook-id` is "The same value as the body's `eventId`".
- Claude Code Channels (`claude/channel`, `notifications/claude/channel`): known only as used by mctl-claude-remote. Codex, Antigravity, Grok: unknown (not observed).

## Proposed solution

A research-only spike in `mctlhq/.github` with four artifacts and no runtime
change: a spike manifest, a report, an offline reference model with tests, and an
`AGENTS.md` index entry.

### 1. Manifest `roadmap/spikes/mcp-events-sep-3415.yaml`

A SpikeDefinition with:
- owner `mctlhq/.github`, issue `#377`, `lifecycle: proposed`;
- the four outcomes and `evidence.report: docs/spikes/mcp-events-sep-3415.md`;
- no `decision` block, and a header comment saying the verdict lives only in the report.

### 2. Report `docs/spikes/mcp-events-sep-3415.md`

Sections:

1. Status and non-claims.
2. Pinned sources, with three separate maturity rows (governance, voting, extension).
3. Finding-to-change matrix (below).
4. Method map, with the comparison against core subscriptions, Tasks and Channels.
5. WP1 inventory.
6. WP2 host matrix, including the ChatGPT-vs-spec divergence table.
7. Adapter reference design.
8. ADR options.
9. Pilot and hypotheses.
10. Fixture-vs-live runbook.
11. P1, P2 and P3 risks.
12. GO/NO-GO.

Finding-to-change matrix (seeded here; the report adds spec quotes and test ids):

| Finding | Revision 1 claim | Revision 2 change | Model | Tests |
|---|---|---|---|---|
| P1-EV-01 | server generates secret | client-supplied `whsec_` secret validated; `InvalidParams` otherwise; client-initiated refresh with dual-sign grace; no server rotation; secrets never logged | `model/webhooks.py`, `model/subscriptions.py` | T3, T4, T5 |
| P1-EV-02 | `webhook-id = envelope.id` | `eventId = envelope.id`; random `webhook-id` per (subscription, occurrence) and per control envelope, persisted for retries; `X-MCP-Subscription-Id`; dedupe scoped correctly | `model/projection.py`, `model/fanout.py` | T6, T7, T8 |
| P1-EV-03 | `cursor_expired` error | `null` = now; `maxAgeMs` later-of; gap is `truncated: true` plus fresh cursor, or a `gap` envelope for webhooks; `hasMore`; internal condition never on the wire | `model/cursor.py` | T9, T10, T11 |
| P1-EV-04 | one PEL, XACK after delivery | transactional materialization of per-subscription delivery records before `XACK`; independent per-subscription progress, retry and quotas | `model/store.py`, `model/fanout.py`, `model/delivery.py` | T12, T13, T14, T15 |
| P2-EV-05 | polling fallback with same cursor | no `events/*` without the advertised extension (`-32601`); only existing fallbacks, with no shared cursor | `model/client.py`, `model/server.py` | T16 |
| P2-EV-06 | epoch check before POST | revocation linearized at commit; CAS claim; unsubscribe returns after drain; three distinct ACK facts | `model/delivery.py` | T17, T18 |
| P2-EV-07 | "not Final" as DEFER trigger | three maturity rows; DEFER triggers redefined | report section 2 and 12 | doc review |

### 3. Adapter reference design (model and report; a future slice would live in mctl-api)

```
existing producers --XADD--> mctl:events:{github,telegram,synthetic}   (unchanged)
          | XREADGROUP (future ACL user "mcp-events-relay", one group for the adapter)
          v
  fanout: for each entry, ONE transaction in mctl-api's existing DB:
      match active subscriptions (tenant-resolved, authorized filters)
      INSERT delivery(subscription_id, event_id, webhook_id=random, state=pending,
                      sub_seq=next per subscription) ON CONFLICT DO NOTHING
      UPDATE adapter_position(stream, entry_id)
    COMMIT  -> then XACK (stream PEL never waits on a recipient)
          v
  per-subscription delivery worker (independent backoff, inflight cap, quota)
      CAS claim attempt WHERE sub.state=active AND sub.epoch=e
      re-resolve + pin callback IP, sign (dual-sign in grace), POST, no redirects
      2xx -> delivered (transport ACK) | 410 -> deactivate | 413 -> failed_final
      other -> retry until caps -> dead_letter (+audit)
          v
  host / mock recipient -> hydrates via existing authorized tools; no authority
  poll/stream clients: read stream directly through cursor.py (no per-sub rows)
```

The design decisions behind this diagram:

- **Projection (EV-02).**
  - `EventOccurrence` fields: `eventId = envelope.id`, `name = envelope.type`, `timestamp = occurred_at`, `data = {source, correlation_id, subject}` references only, and `cursor` = an opaque encoding of the position.
  - `payloadSchema` in `events/list` is derived from envelope v1's `subject` constraints.
  - A `webhook-id` is a random 128-bit id minted at materialization, persisted on the delivery row and reused on every retry.
  - Control envelopes (`gap`, `terminated`, `verification`) get their own rows and ids.
- **Ownership (EV-01).** The subscription key is `(principal, delivery.url, name, arguments)`. Tenant, principal and OAuth client come from authentication, using the same derivation as the WorkItem tools. The subscription id is server-minted and sent as `X-MCP-Subscription-Id`. The secret is client-supplied and held by reference: in memory in the model, Vault in a future slice. Only a fingerprint (`sha256` of the secret, truncated) appears in audit. During refresh the subscription holds `secret_current` and `secret_previous` with a `grace_until`.
- **Tenant resolution.** Subject-to-tenant bindings (for example the GitHub repository goes through the repo binding). An unresolvable subject reaches no tenant subscription. Telegram events are admin-only in any first slice.
- **Durable fanout (EV-04).**
  - Stream entries are ACKed only after the materialization commit.
  - Crash recovery rules:
    - before commit: the entry stays in the PEL and `XAUTOCLAIM` re-materializes it, with `ON CONFLICT DO NOTHING` making that idempotent;
    - after commit and before `XACK`: replay inserts nothing new;
    - after POST and before marking `delivered`: the same `webhook-id` is resent and the recipient dedupes.
  - Each subscription's progress is its own delivery rows and `sub_seq`, so one failing or revoked subscription cannot block another.
  - Trim cannot lose a materialized delivery. A subscription paused by quota records `gap_from`, and on resume it receives a `gap` envelope.
  - This reuses mctl-api's existing database and outbox pattern. No new bus.
- **Cursors (EV-03).**
  - Poll and stream cursors encode a stream entry id, and webhook cursors encode `sub_seq` or the entry id.
  - `null` / absent means the current tail.
  - Start = max(cursor, first retained entry, now − maxAgeMs). If that is later than the requested cursor, the response returns `truncated: true` with a fresh cursor.
  - `maxEvents` drives `hasMore`.
  - The internal `below_retention` flag goes to audit only.
  - Ordering: per stream and per subscription. There is no cross-stream ordering.
- **Revocation (EV-06).**
  - The linearization point is the commit of `UPDATE subscription SET state='revoked', epoch=epoch+1`.
  - An attempt must commit a claim row with `WHERE state='active' AND epoch=e` before POST.
  - A claim that loses the race sends nothing.
  - An attempt claimed before revocation may complete. `events/unsubscribe` responds only after such attempts finish or hit the HTTP timeout, so after the response nothing is in flight.
  - Server-initiated termination (expiry, principal revoked, sustained failure) sends `terminated`.
- **ACK facts.** `delivered` (transport 2xx), the delivery row state (persisted progress) and `processed` are separate. `processed` is set only via an explicit MCTL tool, which is an MCTL extension and not part of the spec. This follows the #66 lesson that a fake ack is worse than none.
- **Fallback (EV-05).** Without the negotiated extension the model's client never calls `events/*`, and the server answers `-32601`. The documented fallbacks are Claude Channels (active Claude Code session) and host-scheduled reads through existing tools, with no shared cursor.
- **Callback safety.**
  - HTTPS only, no userinfo, a port allowlist and no IP literals.
  - Every A and AAAA answer is checked against the deny ranges, at registration and at every delivery, and the connection goes to the pinned IP.
  - Redirects are never followed.
  - A `verification` envelope with constant-time echo is required before activation.
- **Host profile.** The model's server is spec-conformant (`ext-events@17c0c64a`). The ChatGPT divergences are listed and **not** implemented as a compatibility mode. `webhook-id = eventId` breaks multi-subscription dedupe, and adopting it would need an owner ADR after live evidence. This decision is not taken here.
- **Authority.** A delivery carries no grant. Acting uses existing tools and gates.

### 4. Offline reference model `docs/spikes/mcp-events-sep-3415/`

Stdlib Python, run with `python3 -I -m unittest`, no network. Modules:

| File | Contents |
|---|---|
| `model/stream.py` | In-memory XADD/XREADGROUP/XACK/XAUTOCLAIM/MAXLEN fake |
| `model/store.py` | Transactional in-memory DB with unique constraints, CAS updates and crash-injection points |
| `model/subscriptions.py` | Key, secret validation and refresh, TTL and `refreshBefore`, epoch |
| `model/projection.py` | Envelope to `EventOccurrence` |
| `model/fanout.py` | Materialize-then-ACK |
| `model/delivery.py` | Per-subscription workers, claim CAS, retry, 410/413, dead-letter, drain-on-unsubscribe, barrier hooks |
| `model/cursor.py` | Cursor rules |
| `model/webhooks.py` | Standard Webhooks signing, dual-sign, verification envelope |
| `model/callback_guard.py` | Injectable resolver |
| `model/server.py`, `model/client.py` | Capability negotiation |
| `model/recipient.py` | Read-only mock recipient that dedupes on `webhook-id` |
| `fixtures/` | Synthetic only, reusing `events/examples/valid/` |
| `tests/` | The test suite |

The spec quotes and the pinned commit live in `model/SPEC_PIN.md`.

### 5. Verdict and DEFER triggers (report section 12)

The proposed verdict is **BOUNDED_HOST_PILOT, offline-first**. The first approvable slice is this report, model and tests only. A flagged mctl-api slice on the synthetic stream, and any host delivery, are separate later gates.

DEFER triggers, none of which is "not Final" alone:
- the full spec text cannot be pinned at a commit;
- the model cannot prove T12 to T15 (the fanout contract);
- no target host is observed accepting spec-conformant deliveries, which leaves no interoperable consumer;
- the owner rejects adding per-subscription rows to mctl-api's database.

## Alternatives

1. **REUSE_NATIVE_EVENTS.** Keep Channels and polling skills only. It is cheap and deployed, but it is not portable, and the in-cluster consumer is paused. It remains the fallback.
2. **ADOPT_THIN_MCP_EVENTS_ADAPTER now.** Rejected as the immediate step. The extension is Beta, no SDK was observed, the only documented host diverges from the spec on wire identity, envelope v1 lacks a tenant, and the gateway (#236) that may own the surface is moving.
3. **Per-subscription consumer groups on Valkey instead of DB rows.** Dropped. It multiplies PELs on a `200mb noeviction` instance, needs dynamic ACL and group management per tenant subscriber, and makes revocation and retention per subscriber harder to fence. Reusing mctl-api's transactional DB keeps one authorization plane.
4. **Adapter in mctl-claude-remote, or a new webhook fan-out service.** Dropped. The first is a single-session, paused consumer. The second would be a second bus and authorization plane.

## Platform impact

- **Migrations:** none. The spike adds only docs, a manifest and offline code. Envelope v1, streams, ACLs and Channels are unchanged.
- **Backward compatibility:** the roadmap validator must accept the manifest, and the `events/tests` suite is untouched.
- **Resources:** none at runtime. A few seconds of offline unittest.
- **Future slice (documented, not done):**
  - ACL user `mcp-events-relay`;
  - mctl-api tables `mcp_event_subscription`, `mcp_event_delivery` and `mcp_event_adapter_position`;
  - Vault references for client secrets;
  - an egress policy for webhooks;
  - one adapter consumer group whose PEL is bounded by the materialization latency, not by recipients.
- **Risks:**
  - P1: claiming host interop from spec conformance (or the reverse). Mitigation: a separate divergence table, with ChatGPT marked unknown until G-L3.
  - P1: lost or duplicated per-subscriber delivery. Mitigation: materialize-then-ACK with crash tests T12 to T15.
  - P1: cross-tenant leak through platform-wide streams. Mitigation: fail-closed tenant resolution and re-authorization at materialization and at claim.
  - P1: secret leakage. Mitigation: client-supplied secrets, fingerprint-only audit, and a test scanning logs and captures (T5).
  - P2: revocation race. Mitigation: the linearization point plus the barrier test T17.
  - P2: SSRF and rebinding. Mitigation: the guard plus T20.
  - P2: Channels regression. Mitigation: no change to that path.
  - P3: spec churn from Beta. Mitigation: the pinned commit and isolated projection and cursor modules.
  - P3: cost. Mitigation: no live runs.
