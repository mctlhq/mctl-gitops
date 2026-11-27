# Design: issue-432-spike-chatgpt-revalidate-push-delivery-i

Research-only spike. The issue is a follow-up to #300 Gate A. #300 stays as
recorded: `status: accepted`, `NOT_SUPPORTED_IN_STANDARD_CHAT` (2026-11-02, Plus
account), and nothing here reuses its approval.

## Current state

### This repository (`mctlhq/.github` @ `233dc60`)

- `events/README.md` defines the delivery chain: producer, then Valkey Streams, then the mctl-events Channel adapter (mctl-claude-remote), then the Claude session, then hydration through source tools, then `ack_event`, then `XACK`. Its rules:
  - "the event is disposable; the source is canonical";
  - delivery is at-least-once from a durable outbox;
  - dedupe is by `id`.
- Streams that exist today are only `mctl:events:{telegram,github,synthetic,audit}`. There is no Scout stream.
- `events/schemas/event-envelope.v1.schema.json` is closed, capped at 4096 bytes, and has no tenant field. Its required fields are `specversion`, `id`, `type`, `source`, `occurred_at`, `correlation_id` and `subject`:
  - `type` follows `^[a-z0-9_]+\.[a-z0-9_]+\.[a-z0-9_]+$`, so `scout.digest.ready` is valid;
  - `id` must be source-derived and stable;
  - `subject` holds string references only.
- `events/tests/test_envelope_schema.py` validates examples with `jsonschema.Draft202012Validator`.
- Spike conventions come from these files:
  - the SpikeDefinition format: `roadmap/schemas/spike-definition.schema.json` and `roadmap/spikes/edge-config-kv-instant.yaml`. The header comment there says the verdict lives in the report and the owner records the `decision` block;
  - the stdlib reference-model layout of `docs/spikes/finance-assistant/` (`model.py`, `fixtures/`, `tests/`);
  - the spike index in `AGENTS.md`.
- `docs/spikes/automation-control-plane.md` (around line 326) says "ChatGPT same-chat push is `unknown`, tracked in mctlhq/.github#300, and is not an acceptance dependency."
- `docs/spikes/mcp-events-sep-3415.md` does **not** exist on `main`, because #377's PR mctlhq/.github#386 is still open.

### Scout (mctlhq/mctl-agents, read via `gh api` contents of `orchestrator/run_scout.py`)

- `run_scout()` runs these steps: fetch feeds (`feeds.fetch_source`), window, URL dedupe against `spike:scout` issues, relevance pass, scoring pass with `SCOUT_BUDGET_USD`, rank, `render.render_digest(ranked, results, counts, run_id)`, then `send_message(token, chat_id, text, markup)` plus overflow replies.
- `run_id = os.getenv("WORKFLOW_NAME") or "local-<ts>"`.
- The digest text exists only in memory and in the Telegram message. It is never persisted, hashed or published as an event. A `--dry-run` prints it to the step log.

### Deployed state checked

- `[GITOPS]` `argo-workflows/cluster-templates/cronworkflow-mctl-agents-scout.yaml` (mctl-gitops @ `22c97ae`, 2026-11-27): schedule `40 6 * * *` UTC, `concurrencyPolicy: Forbid`, `suspend: false`. The comments say no MCP tool submits it ad hoc.
- `[GITOPS]` `argo-workflows/cluster-templates/cwft-mctl-agents-scout.yaml`:
  - image `ghcr.io/mctlhq/mctl-agents:1.117.1`;
  - "Model sessions have no tools, no MCP and no MCTL_TOKEN … the only write is one Telegram sendMessage. No gitops clone, no git push";
  - `emptyDir` workdir, egress via `agent-egress-proxy`, `WORKFLOW_NAME` passed as the run id;
  - `onExit: notify-telegram` is failure-only;
  - `ttlStrategy.secondsAfterCompletion: 259200`, so step logs are not a durable store.
- `[GITOPS]` `infra-components/data/valkey/externalsecret.yaml`, `users.acl`: ACL users exist only for `telegram-producer`, `github-producer`, `synthetic-producer`, `claude-remote`, `events-observer` and `exporter`. Scout has no user and no stream.
- `[GITOPS]` `services/labs/claude-remote/values.yaml`: tag `0.31.0`, `replicaCount: 0`.
- `[MCP]` `mctl_get_service_status(labs, claude-remote)` 2026-11-27: Healthy/Synced, image `0.31.0`, so no in-cluster consumer is running.
- `[GITOPS]` `bootstrap/templates/mctl-platform/mctl-api.yaml`: mctl-api tag `4.178.1`. `OAUTH_ALLOWED_REDIRECT_URIS` includes `https://chatgpt.com/connector/oauth/*`, so ChatGPT can already be an OAuth MCP client of mctl-api. Lines around 430 (per #377's read) describe the GitHub webhook outbox-to-`mctl:events:github` relay.
- `[GITOPS]` `agents-state/.github/proposals/issue-300-*/.status.yaml`: `accepted`, `blocked.code: execution-unauthorized`.
- `[GITOPS]` `agents-state/.github/proposals/issue-377-*/.status.yaml`: `implemented`, PR #386, which is `OPEN` per `gh pr view`.
- `[GH]` #300's Gate A comment: Plus account, verdict `NOT_SUPPORTED_IN_STANDARD_CHAT`. #407 is the open MCP Events epic.
- Not observed, and recorded as unknown rather than absent:
  - whether any Scout run succeeded today;
  - the owner's ChatGPT account UI and plan rollout;
  - whether Work/MCP Events or Voice is enabled for this account;
  - whether mctl-api's MCP endpoint advertises any `events` capability (assumed not; no evidence either way in gitops).

### First-party capability matrix (retrieved 2026-11-27)

Tags: `D` = documented (URL, retrieved 2026-11-27); `C` = community report only (not first-party); `U` = unknown.

| Mechanism | Surface / host | Plan | Delivery kind | Gesture or open app | Polling or slot | Evidence |
|---|---|---|---|---|---|---|
| MCP Events | Work chats on ChatGPT web; desktop app with Cloud; dots | Not stated ("Workspace controls for plugins and event-triggered tasks apply") | "ChatGPT receives the event in the subscribed chat"; events may be batched "into one task run". Same-chat vs new run is U. | U | Webhook push; "Polling, streaming … not supported" | D https://developers.openai.com/plugins/build/mcp-events |
| Native event-triggered tasks | Work (web/mobile create; desktop views only) | Eligible Plus, Pro, Business, Enterprise, Edu, Healthcare; not Free/Go | Task run in Work; per-run chat shape U | No gesture per event | Managed under **Scheduled**; 30/hour, 720/day; only Gmail, Slack, GitHub PR triggers, so no custom/MCTL source | D help.openai.com "Scheduled tasks in ChatGPT", "ChatGPT Work and Codex" |
| Scheduled tasks | Chat/Work | paid | New run on a timer | No | Time-based slot: rejected by the issue | D help.openai.com/en/articles/10291617 |
| dots | Own dot conversation; mobile app, desktop, desktop browser (not mobile web) | Pro; Plus "rolling out to select users"; Business; Enterprise | Messages in the dot's own thread; dot "decides when to pause and resume" | No | Dot conversations do not count against Pro limits; schedules via Scheduled | D https://learn.chatgpt.com/docs/dots |
| Voice in dots | Phone button in the dot conversation | as dots | Call in the same dot thread | User starts | — | D learn.chatgpt.com/docs/dots |
| Work chats, Recents | Work and Chat chats "appear together in Recents" | eligible paid | — | — | Work usage counts toward limits | D help.openai.com/en/articles/20001275 |
| Voice in Work | "available in Work on web, iOS, and Android" | eligible paid | Same chat | User starts | Daily Voice allowance | D help.openai.com/en/articles/20001275 |
| Voice in standard chat on Android | In-chat Voice icon; transcript added to the same chat; GPT-Live-1 since 2026-07-08; Advanced/Standard retire 2026-12-11 | all with Voice | Same chat | User starts | Voice allowance | D help.openai.com/en/articles/20001274, /20001638 |
| MCP Apps `ui/message` / `sendFollowUpMessage` | Inside a rendered widget iframe in a conversation | as Apps | Visible user-role message (`ui/message`) or hidden follow-up (C) | Needs the widget rendered in an open conversation; gesture rule U | No background push: the View exists only while rendered | D developers.openai.com/apps-sdk/build/state-management, modelcontextprotocol.io/docs/extensions/apps; C community.openai.com threads |
| Push into an ordinary existing standard chat | — | — | **No first-party mechanism documented** | — | — | D (absence in the pages above); not account-observed |
| Mobile/OS notification | Device | — | Notification only, not a message | — | — | inferred |
| Responses / Conversations API | API | API billing | API conversation, not in the ChatGPT chat list | — | — | D (as #300) |
| Browser extension / CDP bridge | User's desktop browser on chatgpt.com | any | Would type into an existing chat via the UI | Browser must be open and logged in | Not a supported interface | D OpenAI Terms of Use (updated 2026-01-16) forbid "Automatically or programmatically extracting data or Output" and "bypassing any protective measures"; no supported API |
| "GRTC" | — | — | — | — | — | U: no first-party source found (web search 2026-11-27). Candidates CDP, WebRTC, gRPC are hypotheses only. |

Conclusion of the matrix: the primary requirement (an ordinary existing chat)
remains unsupported by any documented mechanism, as #300 found. What changed
since 2026-11-02 is that the docs now give a documented supported path that is
close to it: MCP Events into a subscribed Work chat, plus Voice in Work on
Android. The Work chat also appears in Recents next to ordinary chats. That
path is an alternative destination, not the existing chat.

## Proposed solution

Deliver a research spike in `mctlhq/.github`, with no runtime change, made of
five artifacts.

### 1. Manifest `roadmap/spikes/chatgpt-scout-push.yaml`

A SpikeDefinition: owner `mctlhq/.github`, issue `#432`, `lifecycle: proposed`, the
four outcomes, `execution.devloop: true`,
`evidence.report: docs/spikes/chatgpt-scout-push.md`, and no `decision` block.
The header comment says the verdict lives in the report.

### 2. Report `docs/spikes/chatgpt-scout-push.md`

Sections:
1. Status and non-claims.
2. The capability matrix above, re-fetched and quoted.
3. Delivery-kind glossary: notification, new message in existing chat, assistant turn, API conversation, background Work, task chat.
4. Architecture and ownership.
5. Owner-facing sequence.
6. Threat model.
7. Costs.
8. Test plan and operator proof checklist.
9. Verdict and alternatives.
10. The #300 relationship: #300 is unchanged and cited only.

### 3. Minimal architecture (designed, not built)

```
CronWorkflow mctl-agents-scout (06:40 UTC, unchanged)
  run_scout: fetch -> score -> render_digest(..., run_id)          (unchanged)
    |-- send_message -> Telegram                                    (unchanged, still first)
    '-- [future slice] persist_digest(run_id, text, sha256)  -- one PUT, idempotent
          -> mctl-api: scout_digest(run_id PK, sha256, text, created_at)  immutable
          -> same DB txn: outbox row -> relay XADD mctl:events:scout
                 envelope {type: scout.digest.ready, id: "scout:"+run_id,
                           correlation_id: run_id, source: mctl-agents,
                           subject: {kind: scout.digest, run_id, digest_sha256}}
mctl:events:scout -> [#377 adapter, ChatGPT dialect, flag default-off]
          -> events/subscribe from ONE owner-chosen Work chat (webhook, whsec_ secret)
          -> POST to ChatGPT callback; eventId = envelope.id
ChatGPT Work chat -> model calls mctl MCP read tool mctl_get_scout_digest(run_id)
          -> admin-only, returns text + sha256 (hash must equal subject.digest_sha256)
Owner on Android -> opens the Work chat from Recents -> taps Voice -> discusses
          -> any issue change goes through existing GitHub/mctl tools and their gates
```

Ownership map:

| Part | Owner | Change in a later slice |
|---|---|---|
| Scout collection and scoring | mctl-agents `run_scout.py` | none |
| Digest persistence call | mctl-agents (`orchestrator/scout/publish.py`, new) | one idempotent PUT after Telegram, behind `SCOUT_PUBLISH_DIGEST=false` |
| Digest record, outbox, read tool | mctl-api (existing DB and outbox pattern) | `scout_digest` table and `mctl_get_scout_digest` tool |
| Stream and ACL | mctl-gitops Valkey | `mctl:events:scout`; producer ACL `+xadd` only, mirroring `github-producer` |
| ChatGPT delivery | the #377 MCP Events adapter in mctl-api | needs the #377 PR merged and an ADR on the ChatGPT dialect |
| Destination choice, account link, Voice | owner | manual |

The design reuses mctl-api's existing outbox-to-stream relay and its OAuth
client registration for `chatgpt.com/connector`. It adds no new service.
`concurrencyPolicy: Forbid` and the run id already give one digest per run.

Dedupe, retries and audit:
- Persisting the digest is `INSERT … ON CONFLICT (run_id) DO NOTHING`. A conflicting hash is refused and audited.
- An Argo retry or re-run of the publish step re-sends the same `run_id` and is a no-op. It never re-runs `feeds` or `scoring`, because publish takes the already-rendered text.
- Envelope `id` = `scout:<run_id>`. The ChatGPT `eventId` equals it. The recipient dedupes.
- Adapter retries follow #377: exponential backoff, a cap, then dead-letter.
- Every stage writes `mctl:events:audit` with `correlation_id = run_id`, and audit never contains the secret.

### 4. Offline reference model `docs/spikes/chatgpt-scout-push/`

Stdlib Python, run with `python3 -I -m unittest`, no network. Modules:

| File | Contents |
|---|---|
| `model.py` | `DigestStore` (immutable, hash-checked); `publish_digest(run_id, text)`; `project_event(record)` producing an envelope-v1 dict; `FakeStream`; `ChatGPTRecipient` (records `conversation_id`, dedupes `eventId`, rejects bad signatures and revoked subscriptions); `Subscription` (`whsec_` secret, revoke, reconnect with a fresh secret); `Clock` with no timer API, so any time-based trigger is a test failure; audit list |
| `fixtures/` | A synthetic digest and an envelope that passes the envelope v1 schema |
| `tests/` | The test suite |

### 5. Index entry and verdict

`AGENTS.md` gains a Spikes index line.

The proposed verdict is **`PROPOSE_OFFICIAL_WORK_VOICE_PILOT`**: one dedicated Work
chat subscribed to `scout.digest.ready` through MCP Events, opened from Recents on
Android, with in-chat Voice. It is explicitly *not* the owner's ordinary
existing chat. It is offered only if the owner accepts that destination.
Otherwise the verdict falls back to `DEFER_UNSUPPORTED`.

### Owner-facing sequence (target, after separate approvals)

1. 06:40 UTC: Scout runs and the Telegram digest is sent, as today.
2. Scout persists the digest, and mctl-api emits `scout.digest.ready`.
3. The MCP Events adapter POSTs to the ChatGPT webhook of the subscribed Work chat. ChatGPT runs a turn in that chat and calls `mctl_get_scout_digest`.
4. The owner opens ChatGPT on Android, then Recents, then the same Work chat. The conversation id is equal to the one recorded at subscription.
5. The owner taps Voice and discusses the digest. The transcript stays in that chat.
6. To change an issue, the owner asks explicitly, and the existing authorized GitHub or mctl tools run with their own gates. The event itself carries no authority.

### Threat model (summary for the report)

| Threat | Mitigation |
|---|---|
| Digest content leak to a wrong principal | References-only event; read is admin-only and audited; envelope v1 has no tenant field, so Scout events never reach tenant subscriptions |
| Prompt injection from news items into ChatGPT | Content is already untrusted (`<untrusted_articles>` in the prompts); the read tool returns it marked as data; the delivery grants no write authority |
| Replay or forgery of webhooks | `whsec_` HMAC, 5-minute timestamp window, dedupe on `eventId` |
| Duplicate delivery from Argo retry | `run_id` primary key and stable `id` |
| SSRF via callback URL | #377 callback guard (HTTPS, routable IPs only, no redirects) |
| Revocation race | #377 linearized revoke; nothing sent after unsubscribe returns |
| Browser bridge: session custody | Rejected. It would need a logged-in chatgpt.com session driven by automation, which is account credential custody plus "programmatically extracting … Output", a terms violation |
| Fabricated capability claims | Every matrix row is tagged; `unknown` is never shown as `supported` |

### Costs

- This spike: one investigator run and offline tests only.
- A future pilot:
  - one Work turn per day (counts toward Work/Codex usage limits);
  - Voice from the daily Voice allowance;
  - one row and one webhook per day;
  - no added model spend in Scout.
- The browser bridge would add a permanently running desktop and is not costed further.

## Alternatives

1. **`GO_STANDARD_CHAT`.** Dropped. No first-party mechanism on 2026-11-27 can append to an ordinary existing chat from an external event. `ui/message` needs a rendered widget inside an open conversation and is not background push. Reopen only if OpenAI documents it, or the owner's account shows an MCP Events or event-task binding on a standard chat.
2. **Native event-triggered task in Work (no MCTL adapter).** Dropped. Triggers are limited to Gmail, Slack and GitHub PR activity. Routing the digest through, for example, a GitHub PR or a Gmail message would be a GitHub write or a mail side channel. The tasks also live under Scheduled, so slot accounting is unknown.
3. **A dot.** Kept as a second official option. A dot has Voice and its own thread, but it is another new conversation, Plus access is "rolling out to select users", and no MCTL webhook trigger is documented for dots beyond MCP Events.
4. **`PROPOSE_USER_CONTROLLED_BROWSER_BRIDGE`** (a browser extension or CDP driving chatgpt.com). Research-only and not proposed. There is no supported interface, it conflicts with the Terms of Use clauses quoted above, it needs session custody, it is fragile with browser lifecycle and UI changes, and "GRTC" is unverified.
5. **Keep Telegram only (`DEFER_UNSUPPORTED`).** This is the fallback if the owner rejects a Work-chat destination. Telegram stays primary either way.

## Platform impact

- **Migrations:** none. The spike adds docs, a manifest and offline code.
- **Unchanged:** envelope v1, streams, ACLs, Scout templates and code, and Telegram delivery.
- **Backward compatibility:**
  - the roadmap validator must accept the new SpikeDefinition;
  - `events/tests` are untouched, because the fixture stays under the spike directory;
  - #300 and #377 artifacts are not modified.
- **Resources:** none at runtime.
- **Future slices, each separately approved:**
  1. merge #377 and an ADR on the ChatGPT dialect;
  2. the mctl-api `scout_digest` table, the read tool and `mctl:events:scout` with its ACL;
  3. Scout publish behind a flag, with a narrow write credential;
  4. owner account link and a single-chat live proof.
- **Risks:**
  - P1: presenting the Work chat as "the existing chat". Mitigation: explicit labelling and owner choice.
  - P1: unknown same-chat behaviour of MCP Events in Work. Mitigation: the operator proof records conversation ids, and a different id means `DEFER_UNSUPPORTED`.
  - P2: a Scheduled-slot cost that is not documented. Mitigation: an observation step before the pilot.
  - P2: drift in the Beta spec or the ChatGPT dialect. Mitigation: pinned sources and dated retrieval.
  - P3: docs change quickly (the Work page said "Updated 9 hours ago"). Mitigation: re-fetch on report day.
