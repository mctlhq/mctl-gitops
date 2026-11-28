# Telegram Smart Inbox: evidence-backed reply-state triage research spike inside the existing Workspace

## Context

Issue mctlhq/mctl-telegram#1517 asks for bounded research and design (P1, PROPOSED) on a
read-only "What did I miss, and who actually needs my reply?" capability. It must live inside the
existing Telegram Workspace (`telegram_dashboard` tool, `ui://mctl-telegram/workspace-3.html` in
`internal/mcpui/workspace.html`). It must not add a second MCP App, connector, endpoint, service,
scheduler or assistant runtime. Today the Workspace inbox can only sort and filter on
`unread_count` and `unread_mentions_count` (`internal/mcpui/workspace.html` lines 214-246 and 314).
An unread counter is not reply state: a read receipt is not a reply, and an outgoing message is not
always an answer.

The owner authorized research only. Implementation, live account inspection, model spend,
`agents:intake`, preview or production rollout, and external publication are all excluded.
This proposal therefore delivers four things: an inventory, a research report, labeled synthetic
fixtures, and an offline, test-only evaluation harness. The harness compares the existing unread
baseline with a deterministic reply-state heuristic. The proposal also gives an exact design for a
later read-model extension, which would need a separate owner GO before anything is wired into a
served tool. The evidence in the issue (eight Reddit threads, no LurkAPI data) is a hypothesis and
not proven demand.

## User stories

- AS a Telegram Workspace user I WANT an attention queue that separates chats that need my reply
  from chats I have already answered or that are waiting on someone else SO THAT I spend less time
  reviewing conversations by hand.
- AS a Workspace user I WANT every triage status to carry the message references, timestamps,
  reason and freshness that support it SO THAT I can check it and do not have to trust it blindly.
- AS the account owner I WANT chats I hid on the manage page (#1152) to stay out of every count,
  snippet, piece of evidence and classifier input SO THAT the triage never widens access.
- AS the product owner I WANT a measured comparison of the baseline against the candidate on
  frozen synthetic fixtures SO THAT I can choose REUSE_EXISTING_VIEW, EXTEND_READ_MODEL,
  PROMPT_ONLY or DEFER on evidence.
- AS a security reviewer I WANT negative tests and a mutation test on scope enforcement SO THAT any
  later PoC cannot leak hidden or unauthorized peers.

## Acceptance criteria (EARS)

Research and inventory (SI0):
- WHEN the spike is delivered THE SYSTEM SHALL include a report at
  `docs/research/smart-inbox-1517.md` covering the following, each with file and symbol
  references at the pinned SHA:
  - every Workspace tool and every App-visible tool (`setWorkspaceToolVisibility` in
    `internal/mcp/apps.go`);
  - the `telegram-workspace-read-only` filter (`toolPassesFilter` in `internal/mcp/server.go`);
  - the `workspaceSnapshot` schema (`internal/mcp/workspace.go`);
  - the #1152 hidden-chat layers (`internal/mcp/hidden.go`, `internal/db/hidden_dialogs.go`,
    `internal/web/manage_hidden.go`) and their tests;
  - hosted versus Local Bridge dispatch (`s.Hub.Call` in `internal/mcp/tools.go`);
  - the #1155 folder and topic read primitives and the #1175 write tools (`mark_read`,
    `save_draft`, `draft_reply`).
- WHEN the report states a decision THE SYSTEM SHALL state exactly one of REUSE_EXISTING_VIEW,
  EXTEND_READ_MODEL, PROMPT_ONLY or DEFER, with the evidence for it.
- THE SYSTEM SHALL record in the report that the current `telegram.Message` projection
  (`internal/telegram/messages.go`) carries no outgoing flag, reply-to reference, edit date or
  topic id. It shall also record that reply state therefore cannot be derived from today's tool
  outputs without either inference from `From` or a read-model extension.

Fixtures and evaluation (SI1, SI3 design):
- WHEN the fixtures are built THE SYSTEM SHALL use only synthetic identifiers and the existing
  personas Alice, Bob, Carol and Dana, with no real account id, name, handle or message text.
- THE SYSTEM SHALL label every fixture with exactly one expected status from NEEDS_REPLY,
  WAITING_ON_OTHER, ANSWERED or UNCLEAR. The fixtures shall cover each of these cases:
  - unread/answered mismatch;
  - multi-turn DM;
  - group addressed question;
  - group reply to someone else;
  - mention;
  - several threads in one group;
  - announcement channel;
  - forum topic;
  - manual reply and agent-sent reply;
  - waiting-on-other;
  - edited, deleted and out-of-order messages;
  - incomplete history;
  - hidden peer;
  - revoke during refresh;
  - cross-account isolation;
  - Local Bridge offline.
- WHEN the harness runs THE SYSTEM SHALL report, separately for the unread baseline and for the
  deterministic candidate:
  - precision and recall per status;
  - the false negative count for NEEDS_REPLY;
  - the abstention (UNCLEAR) rate;
  - the number of bounded reads consumed per fixture.
- IF history in a fixture is incomplete or a required field is absent THEN THE SYSTEM SHALL
  classify the chat as UNCLEAR with a reason code and SHALL NOT emit a confident status.
- WHEN a candidate status is emitted THE SYSTEM SHALL attach only these fields:
  - message references drawn from the input: peer, optional topic id and message id;
  - the timestamp of the last observed message;
  - a reason code;
  - provenance `deterministic`;
  - `observed_at`.
  It SHALL NOT attach any reference that is absent from the input.
- THE SYSTEM SHALL keep the harness deterministic: the same fixtures produce the same metrics,
  with no network, Telegram or model call.

Scope and safety (all slices):
- WHILE a chat is in the account's hidden set THE SYSTEM SHALL exclude it from classifier input,
  counts, snippets, evidence, cache and output. A negative test shall prove this.
- WHEN the scope-filtering step is removed from the harness pipeline (mutation test) THE SYSTEM
  SHALL fail the hidden-peer negative test.
- IF scope is revoked or the hidden set changes between two refreshes in a fixture THEN THE SYSTEM
  SHALL drop the affected entries before output and SHALL NOT serve them from any earlier result.
- THE SYSTEM SHALL NOT log message text, peer identifiers or phone numbers from the harness, and
  SHALL NOT add analytics containing private text or peer ids.
- THE SYSTEM SHALL NOT register any new MCP tool or App resource. It shall not change the
  `setWorkspaceToolVisibility` allowlist, `toolPassesFilter`, `toolDialogScope`, release gates,
  production or preview flags, or the gitops values in this spike.

Proposed future UX (SI2, design only):
- THE SYSTEM SHALL describe the candidate UX in the report as a read-only view inside the
  existing Workspace inbox section, with an equivalent text summary. It shall name #650 as the
  canonical rollout and host-evidence owner.
- THE SYSTEM SHALL specify that any future send, draft or mark-read action goes through the
  existing `prepare_send_message`/`draft_reply` confirmation, send consent, scope check and
  server-side authority. It shall specify that no iframe click is an authorization.

## Out of scope

- Registering a served tool, changing `telegram_dashboard`, editing `workspace.html`, or rolling
  out to preview or production. Each needs a separate owner GO.
- Any Telegram write (send, draft saved to Telegram, mark read, topic writes; #1175) and any
  automatic action.
- Model or LLM classification runs and any model spend. The bounded optional LLM path is
  specified on paper only.
- Live account inspection, real user data, user studies and external posting.
- Persistent triage state, memory (#1325 HOLD), new schedulers or routines (#1398), PA
  presentation or notifications (#1312/#1317/#1486/#1497).
- Per-client or per-fork hidden-chat restrictions. #1152 owner decision: the set is account-wide.
- A new manifest or roadmap apply.

## Open questions

- Whether FYI/NO_ACTION should be a fifth status. Default: the research does not emit it. It
  records the announcement and channel cases under UNCLEAR or WAITING_ON_OTHER and reports
  whether the fixtures justify the split.
- Whether "agent-sent" outgoing messages can be told apart from manual ones. Telegram reports
  both as outgoing. The only local signal is this server's audit log (`ListAuditFor`), which
  holds no message ids for sends today. Default: treat both as ANSWERED-capable and flag the
  limitation in the report.
- Which minimal field additions to `telegram.Message` (`out`, `reply_to_msg_id`,
  `reply_to_top_id`, `edit_date`) an approved PoC may add. These must reach both the hosted path
  and the Local Bridge daemon (`cmd/local`), and older daemons will omit them. Default: design
  marks absent fields as UNCLEAR, never as inferred.
- Thresholds for a pilot (minimum NEEDS_REPLY recall and maximum false positive burden). The
  issue asks for them to be set before any pilot. The proposal suggests recall >= 0.95 on
  NEEDS_REPLY with abstention <= 30 percent, for the owner to confirm.
- Production values reference `workspace-2.html` in a comment, while the code at the pinned SHA
  serves `workspace-3.html`. The report should note which resource each environment actually
  serves. This proposal did not query the live server.
