# Spike (revision 2): MCTL MCP Events (SEP-3415) — portable event subscriptions and delivery over the existing event infrastructure

## Context

Issue mctlhq/.github#377 asks whether MCTL can expose the MCP Events extension
(SEP-3415, extension identifier `io.modelcontextprotocol/events`) to external AI
hosts on top of the event path MCTL already runs, without a second event bus or
authorization plane. That path is envelope v1
(`events/schemas/event-envelope.v1.schema.json`), mctl-api's GitHub webhook
outbox relay, the mctl-telegram producer, the platform Valkey Streams
`mctl:events:{telegram,github,synthetic,audit}` with per-client ACLs, and the
Claude Code Channel consumer in mctl-claude-remote (epic #87, completed). The
issue is P1 and research only. Nothing in this spike runs an implementer, changes
production, links an external account, buys a subscription, touches real user
content or sends a live webhook.

This is revision 2. The first proposal received REQUEST_CHANGES on 2026-11-22
(4 P1, 3 P2: P1-EV-01 to P1-EV-04, P2-EV-05 to P2-EV-07, recorded in the issue
body). The normative source is now pinned. It is
`modelcontextprotocol/ext-events` `specification/beta/events/events.mdx` at
commit `17c0c64a5edb89dc5081d00ed50c4f836bbb67ff` (2026-11-19). The file was
introduced by `24727f38a180b1bde5df1c6eae580ea0a0b703ee` ("Add Events extension
specification at Beta"), and its header reads "Stage: Beta". Every finding is
answered by a row in the finding-to-change matrix (requirement group "Revision
control" below), and the reference model is corrected on the protocol fields. One
new fact matters for the verdict. The OpenAI ChatGPT MCP Events doc, as retrieved
2026-11-22, contradicts the pinned spec on three wire points: the capability key,
the `CallbackEndpointError` code, and the `webhook-id` derivation. The spike
therefore treats "spec-conformant" and "ChatGPT-compatible" as separate,
unproven claims.

## User stories

- AS the platform owner I WANT a source-pinned matrix that maps each review finding to the change made SO THAT I can verify revision 2 without re-reading revision 1.
- AS the platform owner I WANT SEP governance state, voting-tracker state and extension maturity recorded separately SO THAT the verdict does not rest on a conflated "Final / not Final" reading.
- AS a security reviewer I WANT client-supplied webhook secrets, per-message `webhook-id`s, durable per-subscription fanout and a defined revocation linearization point, all exercised by offline tests, SO THAT one subscriber can neither starve, leak to nor be spoofed as another.
- AS an operator I WANT a fixture-versus-live runbook whose live gates are all separately owner-approved SO THAT no host, account, webhook or real content is touched by accident.
- AS the mctl-claude-remote maintainer I WANT Claude Channels left unchanged and used only as a comparison baseline SO THAT the working consumer cannot regress.
- AS a product owner I WANT measurable hypotheses for a later pilot SO THAT GO or NO-GO is decided on numbers.

## Acceptance criteria (EARS)

### Deliverables

- WHEN the spike is delivered THE SYSTEM SHALL add `docs/spikes/mcp-events-sep-3415.md`, `roadmap/spikes/mcp-events-sep-3415.yaml` and an offline reference model under `docs/spikes/mcp-events-sep-3415/`, plus one entry in the `# Spikes` list of `AGENTS.md`.
- WHEN `roadmap/spikes/mcp-events-sep-3415.yaml` is validated by `roadmap/scripts/validate.py` THE SYSTEM SHALL pass with `lifecycle: proposed`, issue `mctlhq/.github#377`, the four outcomes from the issue, `evidence.report` pointing at the report, and no `decision` block.
- WHILE the spike is `proposed` THE SYSTEM SHALL keep the proposed verdict in the report only. The owner records the decision after an independent review.

### Revision control

- WHEN the report is delivered THE SYSTEM SHALL contain a finding-to-change matrix with one row per finding P1-EV-01 to P1-EV-04 and P2-EV-05 to P2-EV-07. Each row names the spec section quoted at commit `17c0c64a`, the changed requirement, the model file and the test id that proves it.
- WHEN a protocol rule is stated THE SYSTEM SHALL cite the pinned `events.mdx` commit and quote the normative sentence. IF the rule cannot be quoted at that commit THEN it SHALL be tagged `[INFERRED]` and SHALL NOT be tested as a spec requirement.

### Evidence and maturity (P2-EV-07)

- WHEN SEP-3415 status is reported THE SYSTEM SHALL record three separate rows:
  - SEP governance state on plan.modelcontextprotocol.io (reported as `final` 2026-11-19 by the review; not observable by the investigator on 2026-11-22, because the page rendered no content);
  - voting tracker state (`Scheduled`, linked PR `modelcontextprotocol/modelcontextprotocol#3415` `Merged`, meeting 2026-11-04 passed);
  - extension maturity (`Beta` at `ext-events@17c0c64a`).
- IF these states disagree THEN THE SYSTEM SHALL report the disagreement and SHALL NOT use "not Final" by itself as a DEFER trigger.
- WHEN a claim about a spec, SDK or host is written THE SYSTEM SHALL tag it `[OBSERVED]`, `[DOC]` (URL, retrieval date, quote), `[CODE]` (repo, SHA, path), `[GITOPS]` (path, commit) or `[INFERRED]`, and SHALL write `unknown (not observed)` where nothing was read.
- WHEN the method surface is mapped THE SYSTEM SHALL list exactly the pinned methods: `events/list`, `events/poll`, `events/stream`, `events/subscribe`, `events/unsubscribe`, the notification `notifications/events/list_changed` and the push-stream notifications `notifications/events/{event,active,error,heartbeat,terminated}`. It SHALL also list the webhook control envelopes `gap`, `terminated` and `verification`. It SHALL keep Events, core `resources/subscribe` / `notifications/resources/updated`, Tasks status notifications (#41) and `notifications/claude/channel` distinct.
- WHEN a host row is filled THE SYSTEM SHALL state host, build or plan, surface, transport, capability key, protocol revision and evidence tag. It SHALL NOT imply compatibility from another surface of the same vendor or from spec conformance.
- WHEN the ChatGPT row is filled THE SYSTEM SHALL record every documented divergence from the pinned spec as `[DOC]` and SHALL mark ChatGPT interoperability `unknown (not observed)` until a separately approved live gate measures it. The documented divergences are:
  - the capability key is `events` in `capabilities`, where the spec uses `extensions["io.modelcontextprotocol/events"]`;
  - `CallbackEndpointError` is `-32015`, where the spec uses `-32027`;
  - `webhook-id` is "the same value as the body's `eventId`", where the spec says MUST NOT derive from `eventId`;
  - polling, streaming and the `gap` and `terminated` envelopes are unsupported.
- WHEN the MCTL inventory is written THE SYSTEM SHALL label each producer, stream, consumer group, ACL user, ACK, dedupe and replay mechanism as merged, deployed or observed, and SHALL cite mctl-claude-remote#66, #82, the paused in-cluster consumer (`replicaCount: 0`) and DevLoop human-facing events (mctl-agents#712).

### Capability negotiation and fallback (P2-EV-05)

- WHILE the server has not advertised `io.modelcontextprotocol/events` in `capabilities.extensions` THE reference client SHALL NOT send any `events/*` request, and THE reference server SHALL answer any such request with `-32601`.
- IF a client lacks the extension THEN THE SYSTEM SHALL offer only fallbacks that exist today. These are the Claude Code Channel path for an active Claude Code session, or host-scheduled reads through existing authorized read tools (for example `mctl_get_dev_loop`, `mctl_list_incidents`, `gh pr view`). The SYSTEM SHALL state that these share no Events cursor, ordering or dedupe semantics.

### Subscription identity and webhook secret (P1-EV-01)

- WHEN `events/subscribe` is called THE SYSTEM SHALL require an authenticated principal (`Forbidden` `-32024` otherwise). It SHALL take tenant, principal and OAuth client from authentication, never from arguments. It SHALL identify the subscription by the spec key `(principal, delivery.url, name, arguments)` and SHALL authorize `name` and `arguments` for that principal.
- WHEN `events/subscribe` is called THE SYSTEM SHALL require a client-supplied `delivery.secret` matching `whsec_` plus base64 of 24 to 64 bytes. IF the value is absent or malformed THEN it SHALL fail with `InvalidParams` (`-32602`). The SYSTEM SHALL NOT generate a secret.
- WHEN a refresh `events/subscribe` with the same key carries a new `delivery.secret` THE SYSTEM SHALL dual-sign deliveries with the old and new secrets for a bounded grace window and then sign with the new secret only. THE SYSTEM SHALL NOT rotate a secret on its own initiative.
- WHILE a secret is held THE SYSTEM SHALL NOT write it, or any HMAC key material, to logs, audit records, fixtures, captures or error data. The only value it may record is a non-reversible fingerprint.
- WHEN `ttlMs` is granted THE SYSTEM SHALL return `refreshBefore`, SHALL NOT return `null` unless the client suggested `ttlMs: null`, and SHALL stop delivery to a subscription not refreshed before expiry.

### Occurrences and webhook identity (P1-EV-02)

- WHEN an envelope is projected THE SYSTEM SHALL set `EventOccurrence.eventId` to envelope `id`, `name` to the event type name, `timestamp` from `occurred_at`, and `data` to envelope v1 references only, conforming to the advertised `payloadSchema`. It SHALL NOT include a Telegram message body or a PR title, body or diff.
- WHEN a webhook message is created THE SYSTEM SHALL mint a high-entropy `webhook-id` per delivery message, for each (subscription, occurrence) pair and for each control envelope. It SHALL persist the id with the delivery and reuse it on every retry of that message, and SHALL NOT derive it from `eventId`.
- WHEN a webhook is sent THE SYSTEM SHALL include `webhook-id`, a fresh `webhook-timestamp` and `webhook-signature` per attempt, and `X-MCP-Subscription-Id`.
- WHEN one envelope matches two subscriptions THE SYSTEM SHALL create two deliveries with distinct `webhook-id`s and the same `eventId`. The reference recipient SHALL deduplicate on `webhook-id`, and on `eventId` only within one subscription.
- IF a `webhook-timestamp` is more than 5 minutes old, or a `webhook-id` was already accepted for that endpoint, THEN the reference recipient SHALL reject the delivery.

### Cursors, retention and gaps (P1-EV-03)

- WHEN a request carries `cursor: null` or no `cursor` THE SYSTEM SHALL start from now, without backfill, and SHALL ignore `maxAgeMs`.
- WHEN a request carries a cursor and `maxAgeMs` THE SYSTEM SHALL begin from the later of the cursor and `now - maxAgeMs`.
- IF the requested start position is earlier than the oldest retained entry (the stream was trimmed by `MAXLEN ~ 10000`) or earlier than `now - maxAgeMs` THEN THE SYSTEM SHALL deliver from the earliest available position, return `truncated: true` with a fresh cursor (on `events/poll`, the `events/stream` activation and `events/subscribe`), and in webhook mode send a signed `gap` control envelope. It SHALL NOT return a JSON-RPC error for a retention gap.
- WHEN `events/poll` has more than `maxEvents` available THE SYSTEM SHALL return `hasMore: true` with the updated cursor.
- WHERE MCTL keeps an internal "cursor below retention" condition THE SYSTEM SHALL use it only in internal state and audit, never as an MCP wire error.

### Durable per-subscription fanout (P1-EV-04)

- WHEN the adapter reads a stream entry THE SYSTEM SHALL, in one transaction in mctl-api's existing database, insert one delivery record per matching active subscription (unique on `(subscription_id, event_id)`) with its minted `webhook-id`. It SHALL `XACK` the stream entry only after that transaction commits. No new broker or queue is added.
- IF the adapter crashes before the commit THEN THE SYSTEM SHALL re-materialize from the pending entry (`XAUTOCLAIM`), and the unique key SHALL make re-materialization idempotent. IF it crashes after the commit but before `XACK` THEN re-materialization SHALL insert nothing new.
- WHILE one subscription is failing, slow, revoked or over quota THE SYSTEM SHALL keep delivering to every other subscription. Stream ACK SHALL NOT wait on any recipient, so one recipient cannot grow the PEL on the `maxmemory 200mb noeviction` instance.
- WHILE a subscription holds more undelivered records than its quota THE SYSTEM SHALL stop materializing for that subscription, record a gap position, and on resume deliver a `gap` envelope / `truncated: true`. It SHALL NOT evict another subscription's records.
- WHEN a delivery attempt gets a non-2xx response or times out THE SYSTEM SHALL retry that delivery independently with capped exponential backoff, a capped attempt count and a capped elapsed window. `410` and `413` SHALL be non-retryable for that delivery. Exhaustion SHALL dead-letter the record with an audit entry.

### Revocation and acknowledgement (P2-EV-06)

- WHEN a subscription is unsubscribed, expired, or its principal's access is revoked THE SYSTEM SHALL linearize the revocation at the commit of the transaction that sets `state = revoked` and increments `epoch`.
- WHEN a delivery attempt starts THE SYSTEM SHALL claim it with a compare-and-set on `(subscription_id, epoch, state = active)`. IF the claim happens after the revocation commit THEN the attempt SHALL NOT be sent.
- WHEN `events/unsubscribe` returns success THE SYSTEM SHALL have committed the revocation and drained or abandoned, within the HTTP timeout bound, every attempt claimed before it. After that response no attempt for the subscription is in flight.
- WHEN a server-initiated termination occurs THE SYSTEM SHALL send a signed `terminated` envelope in webhook mode, and `notifications/events/terminated` in push mode.
- THE SYSTEM SHALL record three distinct facts:
  - a transport ACK (recipient 2xx);
  - persisted per-subscription progress (delivery record state);
  - a processing ACK, recorded only through an explicit MCTL tool call and never inferred from a 2xx.

### Callback safety, audit and authority

- WHEN a callback URL is registered or delivered to THE SYSTEM SHALL require HTTPS and reject userinfo, off-allowlist ports, IP literals and any name resolving to non-globally-routable addresses (RFC 1918, loopback, link-local and metadata, CGNAT, ULA, multicast, unspecified). It SHALL re-resolve and pin the address at every delivery and SHALL NOT follow redirects.
- WHEN a callback is first registered THE SYSTEM SHALL send a signed `verification` envelope and activate only on a constant-time echo match. On failure it SHALL return `CallbackEndpointError` with the spec code, and SHALL NOT deliver before activation.
- THE SYSTEM SHALL write audit records carrying envelope `id`, `correlation_id`, subscription id and `webhook-id`, consistent with `mctl:events:audit`, and no secret or content.
- WHILE any delivery exists THE SYSTEM SHALL NOT treat receipt of an event as authority to act. Side effects go through existing authorized tools and approval gates (DevLoop decide page, #375 boundaries).

### Pilot and decision

- WHEN the pilot is proposed THE SYSTEM SHALL use only synthetic events (a synthetic DevLoop `proposal_ready` or `github.pull_request`), an in-process mock recipient and a reference poll client. It SHALL leave Claude Channels and existing watchers unchanged, and SHALL assume no push into an ordinary ChatGPT chat (#300).
- WHEN the GO/NO-GO is written THE SYSTEM SHALL propose a verdict, list the DEFER triggers (see design), define the smallest reversible pilot, and list acceptance tests for stale subscriber, cross-tenant, spoofed event, replay, duplicate, two-subscriber fanout, cursor gap, crash recovery, revocation race and host fallback.
- IF a live host session, account link, paid plan, live webhook or real content would be needed THEN THE SYSTEM SHALL list it as a separate owner-approved gate and SHALL NOT perform it.

## Out of scope

- Any change to mctl-api, mctl-telegram, mctl-claude-remote, mctl-agents, mctl-gitops, platform Valkey, ACLs, egress policy or Cloudflare.
- A new event bus, broker, queue, second approval plane, or replacement of Claude Code Channels.
- Changes to envelope v1. A tenant field or envelope v2 appears only as an ADR option.
- Live webhooks, real host sessions (ChatGPT, Claude, Codex, Antigravity, Grok), account linking, paid subscriptions and real user content.
- Retiring `codex-watch`, pr-steward ticks or any existing watcher.
- Producers for Telegram PA, Alice, SeerrSense, Glovo, SecOps and release changes, beyond naming them as future slices.
- Approving the proposal or starting an implementer before the independent review of revision 2.

## Open questions

- ChatGPT profile versus the spec. The OpenAI doc diverges from `ext-events@17c0c64a` on the capability key, the error code and `webhook-id` derivation. The spike does not bend the spec to match. Whether ChatGPT actually accepts a spec-conformant server, or whether OpenAI's doc predates the Beta text, is unknown (not observed). This blocks only live gate G-L3, not the offline slice.
- SEP governance state. The review reports plan.modelcontextprotocol.io as `final` 2026-11-19. The investigator could not observe that page (it rendered no content). It is recorded as reported, not observed.
- Spec ordering guarantees across occurrences were not quoted in this run. The model guarantees per-subscription materialization order only, and task 2 must quote or mark `[INFERRED]`.
- SDK support. No SDK package or version implementing `io.modelcontextprotocol/events` was observed. Task 2 records the versions or "none published".
- Tenant resolution. Envelope v1 has no tenant. The model resolves the tenant through subject-to-tenant bindings (as `mctl_get_repo_binding` does) and fails closed.
- "#375" is ambiguous between mctlhq/.github#375 and mctl-api#375. Both are treated as boundaries to preserve.
- Which endpoint would advertise the extension: `api.mctl.ai/mcp` (mctl-api), or the MCP gateway (#236, moved to Q1)? This is an ADR option.
- DevLoop `proposal_ready` (mctl-agents#712) has no Valkey producer or ACL user today. The pilot uses `mctl:events:synthetic`.
- Live stream length, consumer lag, the Mac mini tunnel consumer's liveness and the `mctl-events-policy` contents were not observed.
