# Design: issue-1431-feat-pa-stream-the-answer-and-tool-statu

## Current state

Worker (`internal/agentworker`)
- `openaiclient.go`: `OpenAIClient.chat` marshals one request with
  `Stream: false` and decodes one JSON body (`io.LimitReader(resp.Body, 8<<20)`)
  into `ChatResult{Message, Usage, UsageReported, FinishReason}`.
  `UsageReported` is false when `usage` is missing or both token counts are 0.
  Non-2xx becomes `*ProviderError{Status, RetryAfter}` and the body is drained,
  never kept.
- `parunner.go`: `PAModel.ChatPA` is the model seam; `PAWorker.Run` loops
  `chat` (which is `/turn` then `ChatPA`, retried on 429/5xx only), counts
  cost with `Prices.Cost(res.Usage)` when `UsageReported`, otherwise sets
  `costKnown=false`; with tool calls and unknown cost the run is abandoned
  ("job cost limit reached or unknown"); a final answer is posted by `reply`
  with `cost_usd` nil when the cost is unknown. Routes are mirrored as
  `PARouteClaim/Turn/Reply/Tool` and kept equal to the server by
  `TestPARoutesMatchServer` / `worker_e2e_test.go`. The claim
  (`PAClaim`) is decoded without `DisallowUnknownFields`, so a new optional
  field is backward compatible.
- `cmd/agent-worker/pa_mode.go`: PA worker env (`AGENT_WORKER_PA`,
  `AGENT_PA_BASE_URL`, ...).

Server (`internal/pa`)
- `runloop.go`: `RouteClaim`, `RouteTurn`, `RouteReply` mounted by
  `RunLoop.Mount`. `verify` turns the pa-job token into a `jobs.Ref`
  (principal, job, attempt, context digest). `serveTurn` runs
  `store.AdmitPATurn(..., Gate: l.gate)`; `serveReply` runs
  `store.RunningPAJob(ctx, ref, now, l.gate)`, loads fragments, builds
  `safetext.AllowFromUserText(typed...)` from user-provenance fragments only,
  calls `safetext.Render` to refuse too-long answers, then `FinishPAJob` stores
  the assistant fragment and enqueues the outbox row; `deliverAfter` sends it.
  `stopRun` stops typing, sends any owed notice and writes the stop code.
  `gate` re-checks allowlist, disable, consent and conversation in the store
  transaction. `AdmitToolCall` (called by `connector/dispatch.go` before every
  tool dispatch) checks the signed tool set and `readTools`, admits in the store
  and touches typing. `StillRunning` re-checks after the call.
- `typing.go`: `typingTracker` keeps one `typingRun` per job (cancel, done,
  last activity), started at claim, touched by turn/tool admission, stopped by
  reply/stopRun/release, by `typingIdle` (2 min) and the lease end; its loop
  calls `TypingSender.SendTyping` every 4 s with a 5 s call deadline. It is
  in-memory per replica (documented in the file header).
- `output/sender.go`: the only Bot API call site under `internal/pa`
  (`TestS1O1_SenderIsTheOnlyBotAPICallSite` in `output_guard_test.go`, whose
  `botAPISendMethods` list already contains `sendMessageDraft`). `SendFrom`
  localises a `safetext.Text` with `s.langs.Of(chatID)` (`output.Languages`)
  and sends parts with `sendMessage`; `SendTyping` posts `sendChatAction`;
  `call` maps failures to `*APIError` or `ErrOutcomeUnknown`.
- `output/safetext/render.go`: `Render(model, allow)` = normalise, stripMarkup,
  neutralise (every link candidate not exactly an allowed token is defanged),
  `fit` into at most `MaxParts` (8) parts of `MaxPartUTF16` (4096) units, else
  `ErrTooLong`. `isBoundary` defines token runs; `findCandidates` finds link
  candidates. `templates.go` is the literal-only registry (`tpl(en, ru)`,
  guarded by `TestTemplatesAreLiteralRegistry`).
- `outbox.go`: `renderReply` re-renders the stored fragment at send time; the
  outbox is the only durable delivery (S1-O4 send-once).
- `connector/wiring.go`: `EnvFlags` shows the house pattern for runtime flags:
  read from the environment on every call, missing/empty is off, anything but
  `true`/`false` is unreadable and fails closed.
- `catalog/pin.json`: the pinned read tools are `tg/get_messages`,
  `tg/get_my_identity`, `tg/list_dialogs`, `tg/list_folders`,
  `tg/list_topics`, `tg/search_messages`, and `alice/alice_get_device_history`,
  `alice/alice_get_device_state`, `alice/alice_get_home_summary`,
  `alice/alice_list_devices`.
- `cmd/server/pa_wiring.go`: builds the `output.Sender` with `Languages` and
  passes it as `RunLoopConfig.Sender` and `Typing`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`:
  `PA_ENABLED: "true"`, `PA_EXTERNAL_TOOLS_ENABLED: "true"`,
  `PA_SERVER_TG_ENABLED: "true"`, `PA_SERVER_ALICE_ENABLED: "false"`,
  `PA_WRITES_ENABLED: "false"`, bot `mctl_pa_preview_bot`, host
  `tg-preview.mctl.ai`. No `PA_STREAMING_ENABLED` (new). Replica count not read.
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-pa-preview/values.yaml`:
  `replicaCount: 1`, `AGENT_WORKER_PA: "true"`, `AGENT_RUNNER: "openai"`,
  `AGENT_MODEL: "zai-org/GLM-5.3-Flash"`, `AGENT_OPENAI_BASE_URL` = Cloudflare
  AI Gateway `mctl-telegram/custom-nebius`, `AGENT_OPENAI_MAX_OUTPUT_TOKENS:
  "16384"`, `AGENT_WORKER_CONCURRENCY: "1"`, `AGENT_PA_BASE_URL` = in-cluster
  preview service.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml` (prod): no
  `PA_ENABLED` key found by grep, so PA is off in prod by default.
- `mctl_get_service_config(labs, mctl-telegram-preview)`: image `main-1a19b22`,
  host `tg-preview.mctl.ai`, port 8080, has database.
- `mctl_get_service_status(labs, agent-worker-pa-preview)`: Healthy, Synced,
  image `main-0ef3857`.
- Not observed: whether the gateway/provider returns usage on streamed
  responses, and the preview server's replica count (see Open questions in
  requirements.md).

## Proposed solution

Drafts are a presentation side channel next to the unchanged reply path.
Nothing about `serveReply`, `FinishPAJob`, the outbox or `renderReply` changes.

### 1. Flag and capability negotiation

- New `internal/pa/streaming.go` with `StreamingFlagEnv = "PA_STREAMING_ENABLED"`
  and `streamingOn(getenv) (bool, error)` following `connector.boolFlag`
  semantics (missing/empty off, non-bool unreadable = off).
  `RunLoopConfig` gains `Getenv func(string) string` (default `os.Getenv`) and
  `Drafts DraftSender` (optional; nil disables streaming entirely).
- `claimResponse` gains `Streaming bool \`json:"streaming,omitempty"\``, set when
  the flag reads `true` at claim and `Drafts != nil`. With the flag off the
  field is omitted, so the claim body is byte-identical to today.
- Worker: `PAClaim.Streaming bool`; `PAWorker.Streaming bool` from new env
  `AGENT_PA_STREAMING` (default false) in `cmd/agent-worker/pa_mode.go`. The
  worker streams a job only when both are true. An old server never sets the
  field, so a new worker against it never streams; an old worker ignores the
  field. A 404 from `RouteDraft` also turns drafting off for the rest of the
  job (flag turned off mid-run).

### 2. Worker: streaming client and draft batching

- `openaiclient.go`: factor request building out of `chat`; add
  `chatStream(ctx, msgs, wireTools, onText func(string))` sending
  `stream: true, stream_options: {include_usage: true}` (the `stream_options`
  key is only present on the streaming body, so the non-streaming body is
  unchanged). It reads SSE `data:` lines (bounded by the same 8 MiB total and a
  per-line bound), stops at `data: [DONE]`, and assembles: `delta.content`
  (calls `onText(accumulated)`), `delta.tool_calls` by `index` (id, name,
  argument fragments concatenated; final arguments normalised through the
  existing `ToolCall` rules), `finish_reason`, and the final `usage` chunk.
  `reasoning_content` and any other delta field is ignored and never passed
  to `onText`. Non-2xx before the stream is the same `*ProviderError` (retried
  by `PAWorker.chat` as today); a broken or malformed stream after 2xx is a
  plain error (not retried, the provider may have billed, same as today's
  decode error) and abandons the run. `UsageReported` keeps today's rule, so a
  stream with no usage chunk fails closed through the unchanged
  `costKnown=false` path.
- `parunner.go`: new optional interface
  `PAStreamModel { ChatPAStream(ctx, msgs, tools, onText func(string)) (*ChatResult, error) }`
  implemented by `*OpenAIClient`. `PAWorker.chat` takes an `onText`; it uses
  `ChatPAStream` only when the job streams and the model implements it.
- New `internal/agentworker/padraft.go`: `paDrafter` per job. `onText` stores
  the latest accumulated text; a single goroutine posts it to `PARouteDraft`
  (`"/api/pa/v1/jobs/draft"`, body `{"text": ...}`) with the pa-job token when
  at least `minInterval` (1 s) passed since the last post and the text grew by
  at least `minDelta` (64 UTF-16 units) or it is the first post. Latest wins;
  at most one post in flight; a short per-post timeout (3 s). It stops posting
  once the text exceeds `safetext.MaxPartUTF16` (the server would skip it), on
  `404` (streaming off), and on `409`/stop codes (the run itself will see the
  stop at its next `/turn` or reply). Any other failure is ignored. The drafter
  is closed before `reply` is posted, so no draft can be posted after the
  answer. Draft errors never change `PAOutcome`.

### 3. Server: `RouteDraft`

`RunLoop.serveDraft`, mounted at `RouteDraft = "/api/pa/v1/jobs/draft"`:

1. `verify` (POST, pa-job token) as every route.
2. Flag re-read: off or unreadable -> `404 {"stop":"streaming_off"}`; also 404
   when `Drafts == nil`.
3. Body: `http.MaxBytesReader` at `6*MaxPartUTF16 + 1 KiB`; larger, or empty
   text, -> `200 {"shown": false}` (a skipped draft, never an error that could
   end the run).
4. Per-job cap (in `draftLimiter`, in-memory, keyed by job id, entries dropped
   on stop): at most one send per 700 ms and 120 per job -> else `429`.
5. `store.RunningPAJob(ctx, ref, now, l.gate)`; an error -> `l.stopRun` (same
   409/stop codes and owed notice as `serveTurn`). Nothing is sent.
6. Allow-list: `AllowFromUserText` over the user-provenance fragments, exactly
   as `serveReply` (shared helper `typedAllowList(ctx, principal, conv)`
   extracted from `serveReply` without behaviour change). The allow-list is
   cached on the job's presence entry after the first draft: a later user
   message can only add tokens, so the cache is a subset and fails closed. A
   failed read -> `stop(w, err)`, nothing sent.
7. `safetext.RenderPartial(text, allow)`; `ErrTooLong` or `Parts() != 1` ->
   `200 {"shown": false}`.
8. `l.presence.showDraft(ref, rendered)`, which sends via
   `DraftSender.SendDraft(ctx, chat, draftID(ref), rendered)` with a 5 s
   deadline, stops typing for the job, and records the text and time for the
   refresher. A send error is logged at debug (no text) and answered
   `200 {"shown": false}`.

Partials are never passed to `appendFragment`/`EnqueuePAOutbox`; a guard test
asserts `serveDraft` and `presence` reference neither.

### 4. `safetext.RenderPartial`

New function in `output/safetext/render.go`:
`RenderPartial(model string, allow UserText) (Text, error)` normalises, then
cuts the text at the last `isBoundary` character when the text does not end in
one (the trailing run may still grow into a different token), then calls
`Render` on the cut text. Consequences:
- A disallowed URL streamed one character at a time is never shown live: while
  unfinished it is withheld; once a boundary follows, `Render` defangs it.
- A prefix of a disallowed URL that happens to equal an allowed token
  (`https://a.example/x` allowed, `https://a.example/xevil` streamed) is never
  shown live, because the run is withheld until it ends.
- An unfinished Markdown link `[docs](https://a.ex` is one run and is withheld.
Its output is always a `Render` output, so every existing `Render` property
(idempotence, neutralisation, `ErrTooLong`) holds for drafts.

### 5. Tool status

- `templates.go` gains literal EN+RU templates, no placeholders:
  `TextStatusReadingMessages` ("Reading messages..." / "Читаю сообщения..."),
  `TextStatusSearchingMessages`, `TextStatusListingChats`,
  `TextStatusListingFolders`, `TextStatusListingTopics`,
  `TextStatusCheckingAccount`, `TextStatusCheckingHome`, and a generic
  `TextStatusUsingTool` ("Working on it..." / "Работаю над запросом...").
- `internal/pa/toolstatus.go`: `toolStatus(name string) safetext.Template`, a
  literal map from the pinned `"server/tool"` names to those templates,
  generic for anything else. A test asserts every `TierAuto`/`ClassRead` tool
  in `catalog.LoadPin()` has an entry, so a newly pinned tool is a visible
  decision.
- In `AdmitToolCall`, after a successful admission and only when the flag reads
  `true` and `Drafts != nil`, `l.presence.showStatus(ref, safetext.ServerText(toolStatus(name)))`.
  This is asynchronous (handed to the job's presence goroutine) so it never
  delays the dispatch; it uses the same `draft_id`, so it replaces the partial
  and the next partial replaces it. No chat title or argument is used.

### 6. Presence: typing becomes typing-then-draft

`typing.go`'s `typingTracker` is extended rather than duplicated (renamed
in-file comments only; type names kept to keep `typing_test.go` unchanged):
- `typingRun` gains `ref jobs.Ref`, `draft *safetext.Text`, `drafted time.Time`
  and `allow *safetext.UserText`.
- Before the first draft the loop sends typing every 4 s exactly as today.
- After the first draft it sends no typing. If the last draft is older than
  `draftRefresh` (20 s, inside the ~30 s draft lifetime) it calls a
  `check(ref)` func (wired to `store.RunningPAJob` with `l.gate`) and re-sends
  the same rendered draft only if the job still runs; a failed check stops the
  run's presence. This keeps the status visible across a long `get_messages`
  call and guarantees a cancelled run sends no further draft.
- Every existing stop (reply, `stopRun`, `release`, idle, lease) stops drafts
  too. `serveReply` already calls `l.typing.stop` first, so no draft can be sent
  after the reply is queued on this replica.
- `draftID(ref)` = `ref.JobID` (positive, non-zero, stable across attempts so a
  retry animates the same draft).

### 7. Sender

`output/sender.go` gains `methodSendMessageDraft = "sendMessageDraft"` and
`SendDraft(ctx, chatID, draftID int64, text safetext.Text) error`: refuses
`draftID == 0`, `chatID <= 0` (private chats only), and any `Text` with
`Parts() != 1` (`ErrPartTooLong`); localises with `s.langs.Of(chatID)` like
`SendFrom`; body `{chat_id, draft_id, text}` with no `parse_mode`, no
`can_stop`. Interfaces: `pa.DraftSender { SendDraft(...) error }`; the guard
test list needs no change.

### 8. Wiring

`cmd/server/pa_wiring.go` passes the sender as `RunLoopConfig.Drafts` and
`os.Getenv` as `Getenv`. `paBotSender` gains `SendDraft`. The worker's
`paWorkerFromEnv` reads `AGENT_PA_STREAMING`.

## Alternatives

- `editMessageText` on a placeholder message: rejected by the issue and here;
  the persisted message would become mutable and the outbox would no longer be
  the single, once-only delivery (S1-O4, T14).
- Server-side streaming (the server proxies the model stream): rejected; the
  server does not call the model, and moving that would change the trust and
  cost-accounting boundary of the worker split.
- Posting raw deltas and assembling on the server: rejected; the server would
  need per-job state of the whole partial across replicas. Posting the
  accumulated text is stateless, idempotent and latest-wins; the body is
  bounded by one message part.
- A separate draft refresher goroutine beside `typingTracker`: rejected; two
  per-job loops would have to agree on stop conditions. One presence loop with
  two modes keeps every existing stop path.
- 404 probing instead of a claim field: kept only as the mid-run off switch;
  the claim field decides before the first model call whether to stream, which
  a 404 cannot.

## Platform impact

- Migrations: none. No schema change; partials are never stored.
- Backward compatibility: flag off is byte-identical (claim field omitted,
  `stream: false` body unchanged, no new sends). Old worker + new server: no
  streaming. New worker + old server: no streaming (no claim field).
- Resource impact: per streaming job at most ~1 draft/s plus one refresh per
  20 s, one `RunningPAJob` read and one Bot API call each; allow-list read once
  per job. Bot API rate: Telegram per-chat limits (~1 msg/s) are respected by
  the 700 ms server cap combined with the 1 s worker interval; a 429 from
  Telegram is ignored for drafts (no retry).
- Risks and mitigations:
  - Provider omits usage on streams -> every run settles at full reservation:
    fail closed by design; verify on preview first, flag off if so.
  - A half-written link shown live -> `RenderPartial` withholds the trailing
    run; tests stream character by character.
  - Draft lingering after a failed run -> drafts lapse in ~30 s; the run-failed
    notice from the outbox replaces it.
  - Duplicate final message on some client -> manual check on Android and
    Desktop recorded in the PR; flag off reverts instantly.
  - Multi-replica: presence and caps are per replica, as typing is today;
    gating is in the database, so no replica can send a draft for a cancelled
    job.
- Threat model: T5 (no model text in statuses, partials never stored), T14
  (every partial is a `Render` output with the reply allow-list), I9 (any
  failed read refuses and sends nothing), S1-O1 (sender is the only call site).
