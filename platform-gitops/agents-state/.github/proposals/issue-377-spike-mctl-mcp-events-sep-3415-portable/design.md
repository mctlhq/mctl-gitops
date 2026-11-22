# Design: issue-377-spike-mctl-mcp-events-sep-3415-portable

## Current state

### Event contract in this repository (`mctlhq/.github` @ `7a0659c5`)

- `events/README.md` defines the delivery chain: producer (mctl-telegram,
  mctl-api), then Valkey Streams (`platform-events`), then the mctl-events Channel
  adapter in mctl-claude-remote, then the running Claude session, then hydration
  through the source's MCP or GitHub tools, then `ack_event`, then `XACK`. The
  contract says "the event is disposable; the source is canonical". Delivery is
  at-least-once from a durable producer outbox. Consumers dedupe by `id`, the
  consumer group is per session, `attempt > 1` marks a redelivery, and producers
  trim with `XADD ... MAXLEN ~ 10000`.
- `events/schemas/event-envelope.v1.schema.json` is closed
  (`additionalProperties: false`) and capped at 4096 bytes by consumers. Its fields
  are `specversion` = `mctl.events/v1`, `id`, a three-segment `type`, `source`,
  `occurred_at`, `correlation_id`, and `subject` (string references only, at most
  12 properties). It has **no tenant or principal field**.
- `events/examples/{valid,invalid,calendar-invalid}/` and
  `events/tests/test_envelope_schema.py` are run by `.github/workflows/events-validate.yml`.
- `roadmap/epics/claude-remote-inbound-channels.yaml` (#87) is `lifecycle: completed`,
  with work items valkey (gitops#1260), channel-skeleton (claude-remote#54),
  envelope (#88), telegram-producer (telegram#646), github-producer (api#323),
  delivery-guarantees (claude-remote#55) and e2e-audit (#89).
- Spike conventions come from `roadmap/schemas/spike-definition.schema.json`
  (required `title`, `question`, `lifecycle`, `github`, `outcomes`; `decision`
  only when `decided`), examples `roadmap/spikes/journey-intent-correlation.yaml`
  and `roadmap/spikes/mcp-tasks-durable-execution.yaml` (#41), and reports with
  evidence tags in `docs/spikes/agent-client-compatibility.md` and
  `docs/spikes/automation-control-plane.md`. The latter already models an
  `event` trigger over envelope v1 and states that crash-safe per-subscriber
  fanout is not proven (lines 247-248, 279).
- `docs/plans/mcp-gateway.md` line 122: "Tasks and Apps pass through untouched
  once measured (.github#41, ...)". The gateway epic #236 moved to Q1
  (`docs/plans/q4-2026-plan.md` line 31).

### Deployed state checked

- `[GITOPS]` `infra-components/data/valkey/configmap.yaml` (mctl-gitops @ `d08c0b0b`):
  AOF `appendfsync everysec`, `maxmemory 200mb`, `maxmemory-policy noeviction`.
  The comment says up to about 1s of loss is acceptable because producers republish
  from their outbox.
- `[GITOPS]` `infra-components/data/valkey/externalsecret.yaml`: the `default`
  user is off. `telegram-producer`, `github-producer` and `synthetic-producer` may
  only `XADD` to their own stream and `mctl:events:audit`. `claude-remote` has
  `XREADGROUP`, `XACK` and `XAUTOCLAIM` on the three streams, may `XADD` only to
  audit, and has state keys `mctl:events:state:*`. `events-observer` has read-only
  access to audit. **There is no ACL user for any other consumer**, so an adapter
  needs a new least-privilege user (gitops change, out of scope here).
- `[GITOPS]` `infra-components/data/valkey/cloudflared.yaml`: tunnel
  `events-valkey.mctl.ai` lets the operator's Claude Code session on a home Mac mini
  consume the streams after labs/claude-remote was paused (#2247). Access admits a
  single service token.
- `[GITOPS]` `services/labs/claude-remote/values.yaml`: image `0.31.0`,
  `replicaCount: 0` ("Paused 2026-10-29: the Claude account ... on hold"),
  `MCTL_EVENTS_ENABLED: "true"`, Valkey user `claude-remote`, policy file
  `mctl-events-policy` (deny by default), and `CLAUDE_REMOTE_MODEL:
  "claude-haiku-5-5"`. The comment records that the #66 fake-ack failure (Haiku
  4.5 wrote an ack to /tmp, `max_inflight` saturated) must be re-proven. Telegram
  MCP token renewal has metrics to Pushgateway (#82).
- `[GITOPS]` `services/labs/mctl-telegram/values.yaml` lines 352-358: producer
  `telegram-producer` publishes to `mctl:events:telegram` after the ingest
  transaction. The stream is shared with preview.
- `[GITOPS]` `bootstrap/templates/mctl-platform/mctl-api.yaml`: mctl-api tag
  `4.172.0`. Lines 424-430: the GitHub webhook enqueues into the audit DB outbox
  and a relay `XADD`s to `mctl:events:github` as `github-producer`.
- `[OBSERVED]` `mctl_get_service_status(labs, claude-remote)` on 2026-11-22
  returned Argo `Healthy`/`Synced`, tag 0.31.0. With `replicaCount: 0` this means
  no in-cluster consumer, not a running one.
- `[OBSERVED]` `mctl_list_services(admins)` returned 8 catalogue services and no
  mctl-api row. mctl-api is platform-bootstrapped, and its config was read from the
  bootstrap template above.
- Not observed: live stream lengths, consumer-group lag, the Mac mini consumer's
  liveness, audit stream contents, and the `mctl-events-policy` ConfigMap contents
  (not found as a separate file in the gitops checkout). These are open questions,
  not "absent".
- `[OBSERVED]` gitops `agents-state/.github/proposals/issue-300-.../.status.yaml`:
  status `accepted`, but `blocked.code: execution-unauthorized`. The #300 Gate A
  (ChatGPT existing-chat capability) has not run.

### External sources (retrieved 2026-11-22 via WebFetch, summarized; to be re-pinned verbatim in task 2)

- `[DOC]` https://voting.modelcontextprotocol.io/p/seps/3415: SEP 3415 "Events
  Extension", State "Scheduled", linked PR "Merged". The page shows no method names,
  capability key or delivery modes. This **contradicts the issue's "Final"**.
- `[DOC]` https://github.com/modelcontextprotocol/experimental-ext-triggers-events:
  "Incubation space for the MCP Triggers & Events Working Group", stage "Beta",
  "Experimental ... do not represent official MCP specifications". The extension id
  is `io.modelcontextprotocol/events`. No releases or packages. The callback mechanism
  is "webhooks or similar".
- `[DOC]` https://developers.openai.com/plugins/build/mcp-events: "available in
  Work chats on ChatGPT web", plus the desktop app with Cloud and dots. Webhook
  delivery only. Methods `events/list`, `events/subscribe`, `events/unsubscribe`;
  capability `events` in the `initialize` or `server/discover` result. Standard
  Webhooks headers `webhook-id`, `webhook-timestamp`, `webhook-signature`, plus
  `X-MCP-Subscription-Id`. A single-use challenge is compared in constant time.
  Error `-32015` `CallbackEndpointError` (`challenge_failed`, `timeout`). Retries
  keep the event id and get a fresh timestamp and signature, and 410 and 413 are not
  retried. MCP HTTP protocol version `2026-07-28`.
- Claude Code Channels (`claude/channel` capability, `notifications/claude/channel`):
  only as used by mctl-claude-remote (per `events/README.md` and the values.yaml
  comments). The vendor doc revision was not re-read in this run: unknown (not
  observed). Codex, Antigravity, Grok: unknown (not observed).

## Proposed solution

A research-only spike in this repository with four artifacts and no runtime change.

### 1. Spike manifest `roadmap/spikes/mcp-events-sep-3415.yaml`

A `SpikeDefinition` with `metadata.owner: mctlhq/.github`, issue
`mctlhq/.github#377`, `lifecycle: proposed`, outcomes `REUSE_NATIVE_EVENTS`,
`ADOPT_THIN_MCP_EVENTS_ADAPTER`, `BOUNDED_HOST_PILOT`, `DEFER`,
`execution.devloop: true`, and `evidence.report: docs/spikes/mcp-events-sep-3415.md`.
It has no `decision` block. The header comment says the proposed verdict lives in the
report only, as in `journey-intent-correlation.yaml`.

### 2. Report `docs/spikes/mcp-events-sep-3415.md`

Sections:

1. **Status and non-claims.** No host was run, no webhook was delivered, no account was linked.
2. **Pinned sources.** The SEP tracker state, PR URL and merge SHA, spec file path
   and commit SHA, extension id, SDK package names and versions (or "none
   published"), the OpenAI doc retrieval date and quotes, and the Claude Channels doc revision.
   It notes the tracker/issue discrepancy explicitly.
3. **Method map.** One table maps each spec method or notification
   (`events/list`, `events/subscribe`, `events/unsubscribe`, any poll or stream form,
   delivery notification shape) to its MCTL equivalent: the envelope field, the Valkey
   operation, and the existing Channel tool (`ack_event`). A separate table contrasts
   Events with core `resources/subscribe` plus `notifications/resources/updated`,
   with Tasks status notifications (#41), and with `notifications/claude/channel`.
4. **Inventory (WP1)** from the "Deployed state checked" list above. Each row is
   labeled merged, deployed or observed, and the incident rows are #66, #82, the paused
   in-cluster consumer and the Mac mini tunnel consumer.
5. **Host evidence matrix (WP2).** Columns: host, build or plan, surface,
   transport, extension or capability, protocol revision, evidence tag, and
   proven vs documented vs unknown. Rows: ChatGPT Work chat web, ChatGPT desktop
   Cloud, ChatGPT dots, ChatGPT standard chat (unproven, see #300), Claude Code
   Channels (active session only), Claude apps, Codex, Antigravity, Grok.
6. **Thin adapter reference design (WP3)**, described below.
7. **ADR options**, mapped to the four outcomes (see Alternatives).
8. **Pilot proposal (WP4)** and **product hypotheses (WP5)**.
9. **Fixture vs live operator runbook**, P1, P2 and P3 risks, and **GO/NO-GO**
   with a proposed verdict.

### 3. Thin adapter reference design (lives in the report and the model)

```
existing producers --XADD--> mctl:events:{github,telegram,synthetic}   (unchanged)
                                   |
                  XREADGROUP (new ACL user "mcp-events-relay", group per adapter)
                                   v
        mctl-api MCP Events adapter (future, behind a flag; owner mctl-api)
          - events/list      -> allowlisted types the caller may subscribe to
          - events/subscribe -> subscription row (tenant, principal, client, filters,
                                callback, secret refs, expiry, epoch)
          - events/unsubscribe / revocation -> epoch++ (fences in-flight deliveries)
          - delivery: re-authorize -> project envelope -> sign -> POST (no redirects)
          - cursor = stream entry id; poll/resume for reference client
          - audit: XADD mctl:events:audit {id, correlation_id, subscription, stage}
                                   v
             host webhook (ChatGPT Work/dots) | reference polling client | mock recipient
                                   v
        host agent hydrates via existing authorized MCP/GitHub tools (no payload content)
```

Key rules:

- **Projection.** The Events item is the envelope v1 object plus the MCP framing
  required by the pinned spec. No body, title or diff is added. Hydration
  stays with `mctl-telegram` MCP or `gh pr view`, as in `events/README.md`.
- **Ownership.** Subscription identity comes from authentication (the same
  principal and OAuth-client derivation the WorkItem tools use). Filters are
  `type` from an allowlist plus `subject` scopes. Each scope is authorized at
  subscribe time and re-checked at delivery.
- **Tenant resolution.** Envelope v1 has no tenant. The adapter maps the subject
  to a tenant through existing bindings (for example `github.pull_request.repository`
  goes through the repo binding the platform already uses for
  `mctl_get_repo_binding`). An unresolvable subject reaches no tenant subscription.
  Telegram events are operator-account events and are admin-only in a first slice.
- **Durability and cursors.** Cursors are Valkey stream entry ids. The replay window is
  bounded by `MAXLEN ~ 10000` and `maxmemory 200mb` (count-bounded, not
  time-bounded), so the subscription advertises a retention hint and returns
  `cursor_expired` when a cursor falls below `XINFO STREAM first-entry`. Ordering is
  per stream. There is no cross-stream ordering guarantee.
- **Dedupe.** `webhook-id` = envelope `id`. The adapter keeps a per-subscription
  delivered set with a TTL at least the retry horizon. The reference recipient rejects a
  seen `webhook-id`.
- **Backpressure.** There is a per-subscription inflight cap and a queued quota. When
  the quota is exceeded the adapter stops claiming for that subscription. The PEL
  holds the entries, and other subscriptions are unaffected. `noeviction` means a
  stuck group must never grow unbounded memory. The adapter therefore dead-letters
  after the retry budget and `XACK`s with an audit record, mirroring the "reject,
  audit and acknowledge" rule.
- **Retries.** Bounded exponential backoff with jitter. 410 deactivates the
  subscription. 413 is dropped and not retried. Other 4xx responses are dropped
  after one attempt. 5xx responses and timeouts are retried.
- **Callback safety.** HTTPS only; no userinfo; a port allowlist; no IP literal;
  DNS resolution with every A/AAAA answer checked against deny ranges (RFC1918,
  loopback, link-local 169.254/16 including metadata, CGNAT 100.64/10, ULA fc00::/7,
  multicast, unspecified); connect to the checked IP (pinning) on every
  delivery; redirects are not followed; a single-use challenge with constant-time compare before
  activation.
- **Secrets.** The per-subscription signing secret is generated server-side and stored
  by reference (Vault in a future slice), with two-secret overlap for rotation. The
  reference model keeps it in memory only.
- **Replay protection.** Timestamp tolerance (default 5 minutes) plus the id set.
- **Expiry, revocation and fencing.** Subscriptions carry `expires_at` and an
  `epoch`. Unsubscribe, principal revocation or tenant removal increments the epoch,
  and a delivery checks the epoch after signing and before sending, so a revoked
  subscription never receives an event claimed before revocation.
- **Two acks.** `delivered` means host 2xx. `processed` is only reported if the host
  calls an explicit MCTL tool, and is never inferred. This mirrors the #66 lesson
  that a fake ack is worse than none.
- **Authority.** The delivery carries no grant. Acting still needs the existing tools,
  approvals and the DevLoop decide page.

### 4. Offline reference model `docs/spikes/mcp-events-sep-3415/`

Stdlib Python, the same style as `docs/spikes/finance-assistant/`:

- `model/adapter.py`: the subscription store, filter authorization, projection,
  cursor and retention, delivery state machine, retry, dead-letter and epoch fencing,
  over an in-memory stream fake with `XADD`/`XREADGROUP`/`XACK`/trim semantics.
- `model/webhooks.py`: Standard Webhooks sign and verify (HMAC-SHA256 over
  `id.timestamp.body`), the challenge, and rotation.
- `model/callback_guard.py`: URL and IP validation with an injectable resolver.
- `model/recipient.py`: the read-only mock recipient and the reference polling client.
- `fixtures/`: synthetic envelopes reused from `events/examples/valid/` plus a
  synthetic `synthetic.devloop.proposal_ready` and a `github.pull_request` fixture.
  No real content.
- `tests/`: unittest, run with `python3 -I -m unittest`, no network.

## Alternatives

ADR options, mapped to the issue's outcomes:

1. **REUSE_NATIVE_EVENTS** (no MCP adapter; keep Claude Channels and give
   other hosts polling skills). It is cheap and already deployed, but it is not
   portable: only an active Claude Code session is woken, and that consumer is paused
   in-cluster. It stays the fallback if the spec is not stable.
2. **ADOPT_THIN_MCP_EVENTS_ADAPTER** in mctl-api now. Rejected as the
   immediate step: the spec is "Scheduled" or Beta, not Final, no SDK is published,
   the only documented host is ChatGPT Work or dots over webhook, the envelope lacks
   a tenant, and the gateway (#236) that may own the public surface is moving.
   Building production code against a moving extension risks rework and
   a second authorization path.
3. **BOUNDED_HOST_PILOT** (proposed). An offline reference model now. Then a
   flagged, synthetic-stream-only adapter slice in mctl-api with a mock recipient,
   and only after separate owner approval one ChatGPT Work webhook delivery of a
   synthetic event. It is reversible, exercises every security rule, and does not touch the
   Channel path.
4. **DEFER.** Chosen automatically if task 2 cannot pin a spec text and revision, or
   if the pinned spec diverges from the OpenAI-documented methods.

Also dropped: a new broker or webhook fan-out service (it violates the "no second bus" rule).
Putting the adapter in mctl-claude-remote was also dropped: that is a single-session consumer and
currently paused, and a tenant-facing subscription store there would create a second
authorization plane.

## Platform impact

- **Migrations:** none. The spike adds only docs, a manifest and offline code to
  `mctlhq/.github`. Envelope v1, the streams, ACLs and the Channel consumer are unchanged.
- **Backward compatibility:** the roadmap validator must accept the new
  SpikeDefinition. The `events-validate.yml` examples are untouched.
- **Resources:** none at runtime. CI adds a few seconds of offline unittest, if it is
  wired at all. Otherwise it is run by hand, as other spike models are.
- **Future-slice impact (documented, not done):** a new Valkey ACL user
  `mcp-events-relay` (read and group only on chosen streams, audit `XADD`), a
  subscription table in mctl-api, Vault secret refs, an outbound egress policy for
  webhooks, and a consumer group whose PEL counts against `maxmemory 200mb noeviction`.
- **Risks and mitigations:**
  - P1: claiming host or spec support that is only announced. Mitigation: evidence
    tags, `unknown (not observed)`, and no "Final" wording.
  - P1: cross-tenant leak through platform-wide streams. Mitigation: fail closed
    on unresolvable tenant, plus re-authorization at delivery (tested).
  - P1: SSRF through callback URLs. Mitigation: the guard with DNS re-check and IP pinning (tested).
  - P2: a stuck subscriber filling Valkey under `noeviction`. Mitigation: quotas,
    a bounded retry budget, then dead-letter and `XACK`.
  - P2: treating delivery as authority. Mitigation: a no-grant rule and separate ack types.
  - P2: regressing Claude Channels. Mitigation: a separate group and ACL user, with the
    baseline compared and not modified.
  - P3: spec churn before Final. Mitigation: the DEFER trigger and isolating the projection
    in one function.
  - P3: cost. Mitigation: no live runs. Every later live run is a separate owner-approved gate.
