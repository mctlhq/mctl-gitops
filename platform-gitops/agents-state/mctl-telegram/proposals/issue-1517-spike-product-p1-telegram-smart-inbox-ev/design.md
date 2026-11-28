# Design: issue-1517-spike-product-p1-telegram-smart-inbox-ev

## Current state

Pinned SHA: `13fd2333a041c3a0a2634db29879bfa116250bf6`.

### Workspace surface (#650)

- `internal/mcp/workspace.go`: `toolTelegramDashboard` registers `telegram_dashboard`.
  - It takes no arguments and requires `telegram:dialogs:read`.
  - It composes `list_dialogs` (limit `workspaceDialogLimit` = 30, wrapped in
    `s.hiddenScopeGuard`), `list_folders`, `get_my_identity`, `get_my_send_status` and the last 5
    audit entries into `workspaceSnapshot` (schema `telegram-workspace/v1`).
  - Each read goes through `workspaceSection`, which returns nil when the read is unavailable;
    the missing section is then listed in `Unavailable`.
  - `summarizeWorkspace` gives the text fallback. It counts unread chats and unread messages
    only.
- `internal/mcpui/workspace.go` and `workspace.html` are served as
  `ui://mctl-telegram/workspace-3.html`, with v2 and v1 kept for cached descriptors.
  - The view has four sections: Overview, Inbox, Search, Account and security.
  - The Inbox filters by kind and an "Unread only" checkbox (`redrawInbox`, line 314).
  - Its summary tiles count unread messages, dialogs with unread messages and unread mentions
    (lines 244-246).
  - Conversations are opened with `get_messages` (limit 12) and searched with `search_messages`.
- `internal/mcp/apps.go`: `setWorkspaceToolVisibility` is the default-deny App allowlist. Only
  `telegram_dashboard`, `list_dialogs`, `get_messages` and `search_messages` carry
  `visibility: ["model","app"]`.
- `internal/mcp/server.go`: `toolPassesFilter` defines the `telegram-workspace-read-only`
  profile, which allows 9 tools. With that profile, `addTool` wraps `get_messages` and
  `get_unread_messages` in `withoutWorkspaceMedia`.
- Separately, the older triage App (`internal/mcpui/app.go`, `ui://mctl-telegram/triage`, #569)
  still exists.

### Read projection

- `internal/telegram/dialogs.go` `Dialog` carries:
  - `UnreadCount`, `UnreadMentionsCount`, `LastMessageDate` and `TopMessageID`;
  - `Pinned`, `Muted` and `Archived`;
  - `IsBroadcast`, `IsMegagroup` and `IsForum`.
- `internal/telegram/messages.go` `Message` carries `ID`, `Peer`, `PeerTitle`, `From`, `Text`,
  `Date` and `MediaInfo`. `decodeMessagesRaw` drops service messages and does not project
  `msg.Out`, `msg.ReplyTo`, `msg.EditDate` or the forum top id, although the raw `*tg.Message` has
  all of them. Reply state today can only be guessed by comparing `From` with the caller's
  identity. That guess is unreliable in groups and gives no reply-to evidence. This is the
  central finding for the decision.

### Hidden chats (#1152)

- `internal/mcp/hidden.go` enforces the hidden set in three layers:
  - `hiddenScopeGuard` fails closed when the set cannot be read and refuses a call whose peer
    argument is hidden;
  - the set is placed in ctx, so the telegram package refuses hidden peers however they are
    spelled;
  - `dropHiddenFromResult` filters results on the way out, which also covers Local Bridge
    responses.
- `toolDialogScope` classifies every tool, and `TestToolDialogScope_CoversRegistry` fails for an
  unclassified one. `telegram_dashboard` is `scopeExempt` because it delegates to scoped
  handlers.
- The set is stored in `internal/db/hidden_dialogs.go` and edited only on the manage page
  (`internal/web/manage_hidden.go`). It is account-wide, which matches the owner decision on
  #1152.

### Hosted versus Local Bridge

- `internal/mcp/tools.go` dispatches reads to `s.Hub.Call` when the account is in local mode and
  `s.Hub.HasDaemon` is true.
- The decoded projection for those reads is produced by the daemon (`cmd/local`, which reuses
  `internal/telegram`). Any field added to `Message` is therefore absent from older daemons until
  they upgrade.

### Writes kept separate (#1175)

- `mark_read_tools.go`, `draft_tools.go` and `reply_tools.go`/`reply_store.go` are writes or
  confirmations and are scoped `scopeDialogs`.
- `ReplyStore` drafts are in memory and single-shot. A local UI draft is not a Telegram saved
  draft.
- `prepare_send_message` (`apps.go`) issues a confirmation bound to
  `HashSendPayload(peer, text)`.

### Deployed state checked

- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`:
  - image tag `0.151.0`;
  - `MCP_APPS_ENABLED: "true"`, `MCP_APPS_WORKSPACE_ONLY: "true"` and `ALLOW_SEND: "true"`;
  - `AUTH_MODE: local-jwt` and `PUBLIC_BASE_URL https://tg.mctl.ai`;
  - a comment that names `ui://mctl-telegram/workspace-2.html` for #650/#1491.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`: image tag
  `main-13fd233` (this SHA). No `MCP_APPS_*` or `MCP_TOOL_FILTER` keys were matched by grep. I
  did not read the whole file, so whether the preview has the Apps flags is unverified.
- mctl MCP tools: not called in this run. Live sync and health and the served resource URI
  version were not observed, and are listed under Open questions in requirements.md.
  Nothing in this spike depends on them, because nothing is rolled out.

## Proposed solution

Decision recorded by this proposal: **EXTEND_READ_MODEL (provisional)**. It is confirmed or
downgraded to PROMPT_ONLY or DEFER by the measured harness results. The reasoning is that a
correct reply state needs `out`, `reply_to_msg_id`, `reply_to_top_id` and `edit_date`. Prompting
over today's `get_messages` output cannot supply them, and unread counts alone are the baseline
being beaten. The spike itself changes no served behaviour.

### 1. Research report: `docs/research/smart-inbox-1517.md`

The report contains:
- The SI0 inventory above, extended with exact test names covering #1152:
  - `internal/mcp/hidden_test.go`;
  - `internal/db/hidden_dialogs_test.go`;
  - `internal/web/manage_hidden_test.go`;
  - the workspace tests `workspace_test.go`, `workspace_pilot_test.go` and
    `apps_surface_test.go`.
  It should note coverage gaps, for example whether a test proves `telegram_dashboard` drops a
  hidden chat when the data comes through the bridge.
- The baseline definition, "prompt-only/unread": a chat is NEEDS_REPLY iff
  `unread_count > 0 || unread_mentions_count > 0`, and otherwise ANSWERED.
- Results of the harness (section 3), the decision, and a cost and latency model. The model is
  based on bounded reads, at most 30 dialogs x 1 `get_messages` page of at most 12 messages,
  reusing the Workspace limits. It also estimates optional LLM token cost on paper only.
- The SI2 UX proposal and the SI3 validation protocol (sections 4 and 5).

### 2. Synthetic fixtures: `internal/inbox/testdata/fixtures/*.json`

Each fixture holds:
- `{account, hidden, dialogs[], messages_by_peer{}, history_complete, bridge_online,
  revoke_after_refresh}`;
- an `expected` map from peer (and topic) to a status and reason code.

Messages use a test-only shape that adds `out`, `reply_to_msg_id`, `reply_to_top_id`,
`edit_date` and `deleted` to the existing `telegram.Message` fields. The fixture can then express
both "field present" and "field absent (old daemon / today's projection)". Personas are Alice,
Bob, Carol and Dana, with ids checked with `git grep` before use. All text is neutral placeholder
text.

### 3. Offline harness: `internal/inbox` (test-only use)

A small package with pure functions and no I/O:

- `Scope(in Input, hidden telegram.HiddenPeers) Input`. Drops hidden peers from dialogs, messages
  and counts. It reuses the `telegram.HiddenPeers` type so that membership semantics are
  identical to `hidden.go`. Scope runs before any classifier, and again before evidence is
  returned.
- `Baseline(in Input) []Item`. Applies the unread rule.
- `Classify(in Input) []Item`. Deterministic rules applied per peer or topic thread, in this
  order:
  1. Incomplete history, a required field absent, or the bridge offline gives UNCLEAR (reason
     `incomplete_history`, `field_absent` or `source_unavailable`).
  2. The last inbound message after the last outgoing message, addressed to the user (DM, a
     reply_to one of the user's messages, or a mention), gives NEEDS_REPLY.
  3. The last relevant message outgoing and itself a question or request, with no newer inbound
     message, gives WAITING_ON_OTHER. Question detection is lexical (`?`) and is flagged low
     confidence.
  4. An outgoing reply_to the latest addressed inbound message gives ANSWERED.
  5. An outgoing message in a group not replying to the addressed message, several open
     threads, or a broadcast channel gives UNCLEAR (`ambiguous_thread`) unless rule 2 applies
     per thread.
  6. Edits and deletes: the effective message order is by id, and `edit_date` never reorders. A
     deleted addressed message gives UNCLEAR (`evidence_deleted`).
- `Item{Peer, TopicID, Status, Reason, Evidence []Ref{Peer, TopicID, MsgID}, LastObservedAt,
  Provenance:"deterministic", Confidence, ObservedAt}`. Every `Ref` must come from the scoped
  input, and `validateEvidence` asserts this.
- `Evaluate(expected, got) Metrics`. Reports per-status precision and recall, NEEDS_REPLY false
  negatives, abstention rate and reads used.

The package is not imported by `internal/mcp`, so no tool registration changes. A test asserts
that `go list -deps ./internal/mcp` does not contain `internal/inbox`.

### 4. SI2 proposal (paper only, needs a separate GO)

- The proposal is a headless projection, `inbox_triage` in `telegram-workspace/v2`. It would be
  added as an optional `Triage` section of `workspaceSnapshot`, computed inside
  `telegram_dashboard` from the same scoped `list_dialogs` result plus bounded scoped
  `get_messages` reads. It is not a new tool, so the App allowlist does not change. It is
  recomputed on every refresh, with no persisted state, and `UpdatedAt` serves as freshness.
- The Inbox section gets a status filter and sort, and an expandable evidence view that opens
  through the existing `get_messages` call. That call re-checks scope at open time through
  `hiddenScopeGuard`. `summarizeWorkspace` gains an equivalent text line.
- Fields absent from an older Local Bridge daemon lead to UNCLEAR, never inferred.
- Any LLM classification is a separate, explicitly labeled path (`provenance: model`). It is
  gated by existing PA/provider consent and is not part of refresh.
- Flags: a new dedicated flag would be needed. Production `MCP_APPS_*` flags are not reused.

### 5. SI3 validation design (paper only)

- The protocol uses matched tasks on synthetic fixtures and measures:
  - time to identify actionable chats;
  - precision and recall, with false negatives weighted highest;
  - false positive burden, abstention coverage and freshness;
  - cost and correction friction.
- Proposed gates for the owner to confirm: NEEDS_REPLY recall >= 0.95, abstention <= 30
  percent, and a review budget set before any pilot. Only aggregate counts are kept, with no
  text or peer ids.

## Alternatives

- **PROMPT_ONLY** (let the model read `get_unread_messages`/`get_messages` and decide). This
  needs no code, but it has no outgoing flag or reply-to evidence, so it fabricates or guesses
  provenance. It is also non-deterministic and spends model budget. It is kept as a measured
  comparison point, and stays the fallback decision if the harness shows the deterministic gain
  is small.
- **New `smart_inbox` MCP tool or a second App resource.** This is explicitly forbidden by the
  issue. It would also need an allowlist change in `setWorkspaceToolVisibility` and a
  `toolDialogScope` entry, and it would duplicate the scope path. Dropped.
- **Persisted triage state (DB table of thread status).** This would add a cache of private data
  that has to be invalidated on hide or revoke, and it conflicts with the ephemeral default and
  #1325 HOLD. Dropped unless the measured refresh latency later justifies it.
- **REUSE_EXISTING_VIEW unchanged (unread and mentions only).** This is the baseline. It is
  rejected as the target because the issue's core distinction (read is not replied) is not
  representable, though it remains the control in the evaluation.

## Platform impact

- Migrations: none. No DB, schema, gitops, flag or tool-registry change.
- Backward compatibility: no served behaviour changes. The new `internal/inbox` package and its
  testdata are not linked into `cmd/server` or `cmd/local`.
- Resources: CI only, a few milliseconds of pure Go tests.
- Risks and mitigations:
  - Real data leaking into public fixtures. Mitigated by the personas-only rule, a fixture lint
    test that rejects digit runs outside a known synthetic id allowlist, and review.
  - The harness diverging from production hidden semantics. Mitigated by reusing
    `telegram.HiddenPeers` and by a mutation test that disables `Scope`.
  - The research being misread as production readiness. Mitigated by the report stating that
    the results are synthetic-only and that demand is unproven.
  - Version skew on Local Bridge for a later PoC. The design maps absent fields to UNCLEAR.
