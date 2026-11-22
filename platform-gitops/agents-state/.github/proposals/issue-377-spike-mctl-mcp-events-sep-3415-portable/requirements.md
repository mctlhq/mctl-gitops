# Spike: MCTL MCP Events (SEP-3415) — portable event subscriptions and delivery over the existing event infrastructure

## Context

Issue mctlhq/.github#377 asks whether MCTL can expose the MCP Events extension
(SEP-3415, `io.modelcontextprotocol/events`) to external AI hosts (ChatGPT, Claude,
Codex, Antigravity, Grok) on top of the event path MCTL already runs. That path is
envelope v1 (`events/schemas/event-envelope.v1.schema.json`), mctl-api's
GitHub webhook outbox, the mctl-telegram producer, platform Valkey Streams
`mctl:events:{telegram,github,synthetic,audit}` with per-client ACLs, and the Claude
Code Channel consumer in mctl-claude-remote (epic `roadmap/epics/claude-remote-inbound-channels.yaml`,
completed). It must not add a second event bus, a second authorization or
approval plane, or a replacement for Claude Channels. The issue is P1, research
only. No implementer, production change, external account linking, paid
subscription, real user content or live webhook delivery happens without separate
explicit owner approval.

This matters because proactive agents (a DevLoop `proposal_ready`, a PR review
landing) currently reach a host only through the one Claude Channel session or
through polling skills. A portable, standard subscription surface could cut
polling cost and time-to-review, but only if host support, spec maturity and
security are proven rather than assumed. The investigator already found
discrepancies. The issue says SEP-3415 is "Final". On 2026-11-22 the official
tracker showed it as "Scheduled" with its pull request merged, and the working-group
repository labels the extension "Beta" and "Experimental", with no releases or SDK
packages. ChatGPT documents MCP Events only for Work chats (web, desktop with
Cloud) and dots, and only over webhooks. The spike therefore delivers a repository
report, a spike manifest and an offline reference model. It changes no runtime.

## User stories

- AS the platform owner I WANT a pinned, evidence-tagged matrix of SEP-3415 and each host's actual event support SO THAT I decide on adoption from facts, not announcements.
- AS the platform owner I WANT ADR options with one proposed verdict out of REUSE_NATIVE_EVENTS, ADOPT_THIN_MCP_EVENTS_ADAPTER, BOUNDED_HOST_PILOT or DEFER SO THAT the next step is a bounded, reversible decision.
- AS a security reviewer I WANT the adapter's subscription ownership, callback validation, signing, replay and revocation rules written down and exercised by offline tests SO THAT event delivery can never be mistaken for permission to act or leak across tenants.
- AS an operator I WANT a fixture-versus-live runbook with explicit gates SO THAT nobody runs a live host delivery, account link or real content without owner approval.
- AS the mctl-claude-remote maintainer I WANT the existing Claude Channel path left untouched and used as the comparison baseline SO THAT a new adapter cannot regress the working consumer.
- AS a product owner I WANT measurable hypotheses (time-to-review, noise, lag, cost per reaction) SO THAT a later pilot can be judged GO or NO-GO.

## Acceptance criteria (EARS)

Deliverables

- WHEN the spike is delivered THE SYSTEM SHALL add `docs/spikes/mcp-events-sep-3415.md`, `roadmap/spikes/mcp-events-sep-3415.yaml` and an offline reference model under `docs/spikes/mcp-events-sep-3415/`, plus one index entry in the `# Spikes` list of `AGENTS.md`.
- WHEN `roadmap/spikes/mcp-events-sep-3415.yaml` is validated by `roadmap/scripts/validate.py` THE SYSTEM SHALL pass with `lifecycle: proposed`, issue `mctlhq/.github#377`, the four outcomes from the issue, `execution.devloop: true`, `evidence.report` pointing at the report, and no `decision` block.
- WHILE the spike is in lifecycle `proposed` THE SYSTEM SHALL record the proposed verdict only in the report and never in the manifest. The owner records the decision.

Evidence

- WHEN a claim about a spec, SDK or host is written THE SYSTEM SHALL tag it `[OBSERVED]` (measured by the investigator, with command and date), `[DOC]` (URL plus retrieval date plus quoted text), `[CODE]` (repo plus commit SHA plus path), `[GITOPS]` (mctl-gitops path plus commit) or `[INFERRED]`, and SHALL write `unknown (not observed)` where no source was read.
- WHEN SEP-3415 is cited THE SYSTEM SHALL pin the tracker state, the merged PR, the spec text revision (commit SHA of the spec file) and the extension identifier. IF the tracker state, the issue text and the spec text disagree THEN THE SYSTEM SHALL record all three and SHALL NOT call the extension "Final".
- WHEN the method surface is mapped THE SYSTEM SHALL list each method or notification exactly as the pinned spec defines it (for example `events/list`, `events/subscribe`, `events/unsubscribe`, any poll or stream mode), and SHALL keep three things distinct: Events, core `resources/subscribe` with `notifications/resources/updated`, and Tasks status notifications (#41).
- WHEN a host row is filled (ChatGPT, Claude Code Channels, Claude apps, Codex, Antigravity, Grok) THE SYSTEM SHALL state host, build or plan, surface, transport, extension and protocol revision, and SHALL NOT imply compatibility from support on another surface of the same vendor.
- WHEN the MCTL inventory is written THE SYSTEM SHALL label each producer, stream, consumer group, ACL user, ACK, dedupe and replay mechanism as merged, deployed or observed, and SHALL cite the operational failures mctl-claude-remote#66 (fake ack, inflight saturation) and #82 (token renewal), plus the paused in-cluster consumer (`replicaCount: 0`).

Adapter design (reference model only)

- WHEN an MCP Events item is produced from an envelope THE SYSTEM SHALL carry only envelope v1 fields (`id`, `type`, `source`, `occurred_at`, `correlation_id`, `subject` references) and SHALL NOT carry a Telegram message body, PR title, body or diff.
- WHEN a subscription is created THE SYSTEM SHALL bind it to `(tenant, principal, oauth client, subscription id)` taken from authentication, never from arguments, and SHALL authorize each filter (`type` allowlist, `subject` scope) against that principal.
- WHEN an event is about to be delivered THE SYSTEM SHALL re-check the subscription's state (active, not expired, not revoked, fencing epoch current) and the principal's authorization for the event's subject. IF either check fails THEN THE SYSTEM SHALL drop the delivery, audit it, and not retry.
- IF an envelope carries no tenant-resolvable subject THEN THE SYSTEM SHALL deliver it to no tenant-scoped subscription (fail closed).
- WHEN a callback URL is registered THE SYSTEM SHALL reject non-HTTPS URLs, userinfo, non-default ports outside an allowlist, IP literals, and hostnames that resolve to private, loopback, link-local, CGNAT, multicast or metadata addresses. It SHALL re-resolve and re-check the address on every delivery (DNS rebinding) and SHALL NOT follow redirects.
- WHEN a callback is activated THE SYSTEM SHALL complete a single-use signed challenge compared in constant time before any delivery.
- WHEN an event is delivered by webhook THE SYSTEM SHALL sign it with Standard Webhooks (`webhook-id` equal to the envelope `id`, a fresh `webhook-timestamp` and `webhook-signature` per attempt) using a per-subscription secret that supports overlapping rotation.
- IF a delivery's timestamp is outside the tolerance window, or its `webhook-id` was already accepted, THEN the reference recipient SHALL reject it as a replay or duplicate.
- WHEN a delivery attempt fails transiently THE SYSTEM SHALL retry with bounded exponential backoff, keeping the same event id. IF the response is 410 THEN it SHALL deactivate the subscription. IF the response is 413 THEN it SHALL not retry. IF attempts are exhausted THEN it SHALL dead-letter the event with an audit record.
- WHEN a subscriber polls or resumes with a cursor THE SYSTEM SHALL return events after that cursor in stream order. IF the cursor is older than the retained window (the stream was trimmed by `MAXLEN ~ 10000`) THEN it SHALL return an explicit cursor-expired error and never silently skip.
- WHILE a subscription has more undelivered events than its quota THE SYSTEM SHALL apply backpressure: pause reading for that subscription and never evict other tenants' events.
- THE SYSTEM SHALL record delivery acknowledgement (HTTP 2xx from the host) separately from agent processing acknowledgement, and SHALL NOT report a delivery as processed.
- THE SYSTEM SHALL write one audit record per stage with the envelope `id`, `correlation_id` and subscription id, consistent with `mctl:events:audit`.
- WHILE any delivery is configured THE SYSTEM SHALL NOT treat receipt of an event as authority to act. Any side effect still goes through the existing authorized tools and approval gates.

Pilot and decision

- WHEN the pilot is proposed THE SYSTEM SHALL use a synthetic DevLoop `proposal_ready` or a synthetic `github.pull_request` event published to `mctl:events:synthetic`, an isolated read-only mock recipient and a reference polling client, and SHALL leave the Claude Channel consumer and existing watchers running unchanged.
- WHEN the GO/NO-GO is written THE SYSTEM SHALL define the smallest reversible pilot, the owner repository, dependencies, rollback, measurable hypotheses, and acceptance tests for stale subscriber, cross-tenant, spoofed event, replay, duplicate, cursor expiry, recovery after restart and host fallback.
- IF a live host session, account link, paid plan or real content would be needed THEN THE SYSTEM SHALL list it as a separate owner-approved gate and SHALL NOT perform it in this spike.

## Out of scope

- Any change to mctl-api, mctl-telegram, mctl-claude-remote, mctl-gitops, platform Valkey, ACLs or Cloudflare.
- A new event bus, broker, queue, second approval plane or a replacement of Claude Code Channels.
- Changes to envelope v1 (`events/schemas/event-envelope.v1.schema.json`). A tenant field or envelope v2 is only an ADR option.
- Live webhook deliveries, real ChatGPT, Claude, Codex, Antigravity or Grok sessions, external account linking, new paid subscriptions and real user content.
- Retiring `codex-watch`, pr-steward ticks or any existing polling watcher.
- Telegram PA, Alice alerts, SeerrSense, Glovo status, SecOps and release-change producers beyond naming them as future slices.
- Recording the owner decision or flipping the spike lifecycle beyond `proposed`.

## Open questions

- Spec maturity. The issue says SEP-3415 is "Final/Merged per official tracker 2026-11-19". On 2026-11-22 the investigator read the tracker as State "Scheduled" with the PR "Merged". The WG repo `modelcontextprotocol/experimental-ext-triggers-events` says "Beta" and "Experimental", with no releases or packages. The exact spec file revision was not pinned and must be pinned in task 2. Proceeding on "not Final".
- Method surface. The tracker page exposed no method names. The OpenAI doc names `events/list`, `events/subscribe`, `events/unsubscribe` and capability `events`. Whether SEP-3415 itself defines poll or stream delivery is unknown (not observed).
- Tenant resolution. Envelope v1 has no tenant field, and the streams are platform-wide. Should tenant come from a subject-to-tenant binding (for example repository to tenant, as `mctl_get_repo_binding` does), or from a future envelope field? The reference model takes the binding route and fails closed.
- "#375" in the issue's Related list is ambiguous between mctlhq/.github#375 and mctl-api#375 (cited in `docs/plans/mcp-gateway.md` for api.mctl.ai). Both are treated as boundaries to preserve.
- Which public endpoint would advertise the `events` capability: `api.mctl.ai/mcp` (mctl-api) or the future MCP gateway (.github#236, moved to Q1 per `docs/plans/q4-2026-plan.md`)? Recorded as an ADR option.
- DevLoop `proposal_ready` (mctl-agents#712) has no producer on Valkey today (no ACL user for it in `infra-components/data/valkey/externalsecret.yaml`). The pilot uses the synthetic stream until that producer exists.
- Whether the owner's ChatGPT workspace exposes Work chats with Cloud or dots is unknown. That is a live gate, coordinated with #300, which is still blocked with `execution-unauthorized`.
