# Design: issue-300-spike-events-push-github-events-into-exi

## Current state

### In this repository (`mctlhq/.github`)

- `events/README.md` defines the platform event contract from epic
  mctlhq/.github#87: `producer (mctl-telegram, mctl-api) -> Valkey Streams
  (platform-events) -> mctl-events Channel adapter (mctl-claude-remote) ->
  running Claude session -> hydration -> ack_event -> XACK`. Its central rule:
  "The event is disposable; the source is canonical". Envelopes carry
  references, never content. Delivery is at-least-once, deduplicated by `id`,
  and redelivered with `attempt > 1`.
- `events/schemas/event-envelope.v1.schema.json` is the closed envelope
  `mctl.events/v1`, capped at 4096 bytes. Its fields are `id`
  (`X-GitHub-Delivery` for GitHub), `type` `<domain>.<entity>.<action>`,
  `source`, `occurred_at`, `correlation_id` and `subject`, which holds string
  references only. `events/examples/valid/github-pull-request-synchronize.json`
  is the GitHub shape. `events/tests/test_envelope_schema.py` runs in
  `.github/workflows/events-validate.yml`.
- Stream table in `events/README.md`: `mctl:events:github` is produced by
  mctl-api (ACL user `github-producer`) with types `github.pull_request.<action>`
  and `github.pull_request_review.submitted`. No CI (`workflow_run`/
  `check_suite`), release or deploy types exist yet. `mctl:events:audit` is
  written by every stage.
- `roadmap/epics/claude-remote-inbound-channels.yaml` is `lifecycle: completed`.
  Its success criteria are "Nothing on the delivery path polls", "No message
  body or pull request content is ever written to the event transport", and
  traceability by `event_id`/`correlation_id`. The GitHub producer is
  mctlhq/mctl-api#323.
- Spikes are declared as `SpikeDefinition` documents in `roadmap/spikes/*.yaml`
  (schema `roadmap/schemas/spike-definition.schema.json`, which requires
  `title`, `question`, `lifecycle`, `github` and `outcomes`; see
  `roadmap/spikes/agent-ui-ag-ui.yaml`). Each has a report in `docs/spikes/*.md`,
  indexed in `AGENTS.md`. `docs/spikes/edge-config-kv-instant.md` shows the
  house style: non-claims, evidence tags and pins, gate result and verdict.
  `roadmap/tests/test_validate_spike.py` validates spike files.
- Nothing in this repository refers to ChatGPT delivery. "ChatGPT" appears
  only in the OAuth/CORS host lists of the mctl-telegram connector (see
  below).

### Deployed state checked

- `mctl_get_service_status(labs, claude-remote)`: Healthy, Synced, image
  `0.14.1`, host `claude-remote.mctl.ai`.
- `$MCTL_GITOPS_ROOT/services/labs/claude-remote/values.yaml`: has
  `MCTL_EVENTS_ENABLED: "true"` and
  `MCTL_EVENTS_VALKEY_URL: redis://claude-remote@valkey.platform-events.svc.cluster.local:6379/0`.
  Its `mctl-events-policy` lets the session wake on stream `mctl:events:github`,
  types `github.pull_request.*` and `github.pull_request_review.submitted`,
  subject repository `mctlhq/*`. The same file ships the `codex-watch` skill: a
  detached `nohup` shell that polls `gh api` every 180 s for up to 10 ticks.
  This is the polling watcher the issue says must not be disabled before a
  verified replacement exists.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml` and
  `mctl-telegram-preview/values.yaml`: mctl-telegram is already a ChatGPT
  connector. `ALLOWED_ORIGINS` includes `https://chatgpt.com`, `chatgpt.com`
  is in `OAUTH_CIMD_ALLOWED_HOSTS`, and there is a comment about ChatGPT App
  Directory review. The preview also produces to Valkey as `telegram-producer`.
  So MCTL already runs an OAuth-protected MCP server that ChatGPT can connect
  to, which is the prerequisite for MCP Events.
- `mctl_list_services(admins)`: complete. It lists mctl-agents workers,
  mctl-design, mctl-docs, mctl-support, mctl-web and umami. mctl-api is not a
  catalogue service under `services/`, so its deployed config (webhook ingress
  path, MCP endpoint hostname, MCP protocol version) was **not observed** in
  this run. This is recorded as an open question.
- Valkey `platform-events` is seen only through the consumer/producer URLs
  above. Its stream lengths and retention were not observed.
- External documentation (retrieved 2026-11-02):
  - `developers.openai.com/plugins/build/mcp-events` (fetched). ChatGPT
    supports MCP Events over Streamable HTTP or MCP 2.0 (`2026-07-28`). The
    server advertises `events` and implements
    `events/list|subscribe|unsubscribe` on the same authenticated endpoint as
    its tools. ChatGPT supplies a callback URL and signing secret; delivery is
    signed with Standard Webhooks after a single-use challenge, one event per
    request, at most 256 KiB, and events may be batched into one task run.
    Polling, streaming, and `gap`/`terminated` are unsupported. "ChatGPT
    receives the event in the subscribed chat". The listed surfaces are Work
    chats (web, desktop with Cloud) and dots, and workspace controls for
    event-triggered tasks apply.
  - `help.openai.com/en/articles/10291617` (scheduled tasks): **HTTP 403 to
    this run**. Search snippets say GitHub tasks "can respond to supported pull
    request activity in an authorized github.com repository", that Free/Go
    cannot create event-triggered tasks, and that Enterprise/Edu admins must
    enable "Allow event-triggered scheduled tasks". Whether these consume
    task slots was not observed.

## Proposed solution

This is a timeboxed spike in three gates. A gate that fails ends the spike
with an honest verdict. Nothing reaches production.

### Gate A: authoritative capability matrix (no code)

Write `docs/spikes/chatgpt-github-event-push.md` in the style of
`docs/spikes/edge-config-kv-instant.md`. It contains a matrix of every
candidate mechanism, with each cell tagged observed, documented (with URL and
retrieval date) or inferred:

| Mechanism | Trigger | Lands in | Slot/quota | Tier | Polling? |
|---|---|---|---|---|---|
| MCP Events (plugin subscription) | MCTL webhook POST to ChatGPT callback | "subscribed chat" (Work/dots) | to verify | Work workspace controls | no |
| Native ChatGPT GitHub event-triggered task | GitHub PR activity via ChatGPT's GitHub connector | task run / conversation (to verify) | to verify | not Free/Go | no |
| Time-based scheduled task | clock | task conversation | uses a slot | all | yes (rejected by issue) |
| Connected Slack/Gmail read | user prompt | none, pull only | n/a | n/a | not a push |
| OpenAI Responses/Assistants API | API call | standalone API response, never the user's chat | n/a | API | n/a |
| ChatGPT mobile/OS push | ChatGPT-owned | notification only | n/a | n/a | n/a |

The matrix separates the delivery classes the issue asks for: notification
only, a message in an existing chat, a new conversation or task run, and an
API response. The decisive manual check is whether a subscription or event
task can be attached to the user's own pre-existing standard chat or only to
a Work/dots chat. The user does this check in their own account; the spike
records screenshots and the plan tier.

### Gate B: proof relay (only if Gate A shows class (b) is reachable)

The proof reuses the existing pipeline unchanged up to Valkey and adds one
consumer:

```
GitHub webhook (mctlhq org) -> mctl-api ingress (HMAC X-Hub-Signature-256,
dedupe on X-GitHub-Delivery) -> XADD mctl:events:github (envelope v1)
  -> consumer group "chatgpt-relay" (new) -> filter/suppress/prioritize
  -> Standard-Webhooks-signed POST to ChatGPT callback -> ack -> XACK
  -> audit entry on mctl:events:audit at every stage
```

- **Subscription side.** The MCP server ChatGPT is already connected to
  advertises the `events` capability. The candidates are the mctl connector
  served by mctl-api, which carries tenant/admin authorization, or
  mctl-telegram's server, which is already allowlisted for `chatgpt.com`. The
  default is mctl-api, because GitHub authorization lives there. That server
  exposes `events/list` with one event, `mctl.github.activity`, whose
  arguments are `repositories[]`, `types[]` and `min_priority`. On
  `events/subscribe` it authorizes the repositories against the caller's
  tenant, validates the filters, runs the challenge, and stores
  `{subscription_id, callback_url, signing_secret (Vault), filters, expires_at}`.
  It honours `refreshBefore` and handles unsubscribe by deleting the row and
  the secret.
- **Relay.** A small consumer (consumer group `chatgpt-relay`) inside the
  same service reads `mctl:events:github`. It needs its own Valkey ACL user
  with read-only rights on that stream plus write rights on the audit stream,
  following the per-producer ACL pattern in `events/README.md`. It blocks on
  `XREADGROUP BLOCK`, which is push-style stream consumption and not polling
  of GitHub or ChatGPT. On ChatGPT 2xx it calls `XACK`; on failure it applies
  bounded exponential backoff and the entry stays pending for redelivery with
  `attempt > 1`.
- **Payload.** The JSON body is the envelope reference fields plus a
  one-line, non-content `summary` built from `type` and `subject` only (for
  example "PR mctlhq/.github#89 merged"). ChatGPT hydrates detail through its
  GitHub connector or the mctl MCP tools, which matches the "source is
  canonical" rule in `events/README.md`. This keeps PR text, diffs and logs
  off the OpenAI event transport.
- **Noise suppression and priority.** Repository allowlist, drop bot authors
  and draft PRs, collapse `synchronize` bursts per PR within a 60 s window
  (keep the latest `head_sha`), and drop events older than the subscription.
  Priority order: CI failure on default branch > review `changes_requested` >
  merge/release/deploy > review approved > opened/synchronize. ChatGPT's own
  batching may group events further, and the report notes this.
- **Replay and reconciliation.** Replay is an operator command that re-reads
  a stream range by id or `correlation_id` and re-sends it. Envelope `id`
  dedupe makes this safe. Reconciliation is on demand only, never periodic.
- **New event families (design only in the spike).** These are
  `github.workflow_run.completed`, `github.release.published` and
  `mctl.deploy.<status>`, each added to the `events/README.md` stream table
  and to `events/examples/valid/`. The proof itself uses only PR/review
  events, which are produced today.
- **Latency and privacy measures.** Record GitHub delivery time ->
  `occurred_at` -> XADD -> relay POST -> visible in chat, p50 over at least
  10 events. Record exactly which fields left MCTL.

The proof runs against one test PR in an mctlhq sandbox repository and one
ChatGPT conversation that the user created beforehand.

### Gate C: verdict and decision

The SpikeDefinition `roadmap/spikes/chatgpt-github-event-push.yaml` has
`lifecycle: proposed` and `execution.devloop: false`, because the proof needs
the user's ChatGPT account. Its outcomes are:

- `GO_MCP_EVENTS_EXISTING_CHAT`: class (b) is observed in the user's
  existing chat via MCP Events.
- `GO_NATIVE_GITHUB_TASK`: ChatGPT's own GitHub event task reaches the
  existing chat with no slot cost. MCTL builds nothing, but this covers PR
  activity only.
- `NOT_SUPPORTED_IN_STANDARD_CHAT`: delivery is possible only in a Work
  chat, dots or a new conversation. The report lists the alternatives and
  waits for the user. The alternatives are: (1) move the conversation to a
  Work chat that subscribes to MCP Events; (2) native GitHub event task with
  its own conversation; (3) keep the existing Claude Channel and Telegram;
  (4) wait for OpenAI support and re-open on documented triggers.
- `BLOCKED_PLAN_TIER`: the user's plan or workspace cannot create
  event-triggered tasks.

Only after a GO verdict and explicit approval is a follow-up implementation
proposal filed. That proposal would cover a production relay, the new
producers, and the retirement plan for `codex-watch`.

## Alternatives

1. **A time-based ChatGPT scheduled task that checks GitHub.** Rejected. It
   is polling, it uses a scheduled-task slot (the issue forbids both), and
   its cadence is at least hourly.
2. **Deliver to Slack/Telegram and read them from ChatGPT through a
   connector.** Rejected. A connector read is a pull and never pushes into
   ChatGPT, and the issue forbids substituting another surface silently.
   Telegram/Slack stay only as user-chosen fallbacks.
3. **OpenAI Responses/Assistants API from MCTL.** Rejected as a solution.
   It creates a standalone API conversation that the user's ChatGPT chat
   list does not show. It is listed in the matrix only so that delivery
   class (d) is documented.
4. **ChatGPT's native GitHub event-triggered task alone.** Kept as a
   candidate outcome, not the default. It needs no MCTL code, but it
   covers PR activity only, with no CI/deploy/release-from-MCTL events.
   It bypasses MCTL dedupe, priority and audit, and its slot cost is
   unknown.

## Platform impact

- **Migrations.** None in the spike. The proof adds one Valkey consumer
  group and ACL user, and one subscription table or Vault path in the
  chosen MCP server. Both are reversible and behind a feature flag (for
  example `MCTL_EVENTS_CHATGPT_RELAY_ENABLED`, default false).
- **Backward compatibility.** The envelope v1 schema is unchanged. The new
  consumer group does not affect the `claude-remote` group, because each
  group has its own pending list. `codex-watch` and the Channel are
  untouched.
- **Resources and cost.** The relay is a goroutine/process in an existing
  service, with negligible CPU and memory. ChatGPT side: any task run
  quota, which is unverified. Engineering: about 1 day for Gate A, about
  3-4 days for Gate B. No model cost on the MCTL side.
- **Risks and mitigations.**
  - Data leaves for OpenAI. Mitigation: references-only payload and a
    repository allowlist, with every POST audited.
  - A subscription secret is a credential (the WorkOS write-up makes the
    same point). Mitigation: store it in Vault, delete it on unsubscribe
    or expiry, and never log it.
  - The spec is a draft and may change. Mitigation: proof only; re-check
    the docs version in the report.
  - Callback SSRF. Mitigation: HTTPS only, no redirects, and reject
    private addresses, as the OpenAI doc requires.
  - Event storms. Mitigation: suppression window, priority floor, and
    backoff with a per-subscription rate cap.
  - The proof could be mistaken for a replacement. Mitigation: AC to keep
    every watcher until a verified replacement exists and the user
    approves.
