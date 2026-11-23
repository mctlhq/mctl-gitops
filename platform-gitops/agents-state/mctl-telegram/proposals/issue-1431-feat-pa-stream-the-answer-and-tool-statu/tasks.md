# Tasks: issue-1431-feat-pa-stream-the-answer-and-tool-statu

- [ ] 1. Add `safetext.RenderPartial` in `internal/pa/output/safetext/render.go`
  (normalise, cut at the last `isBoundary` rune when the text does not end in
  one, then `Render`) — DoD: function documented; T1-T3 pass; existing
  `render_test.go` and `FuzzRender` unchanged and passing.
- [ ] 2. Add tool status templates (EN+RU literals, no placeholders) to
  `internal/pa/output/safetext/templates.go` — DoD:
  `TestTemplatesAreLiteralRegistry` passes; every template has a Russian text.
- [ ] 3. Add `Sender.SendDraft` and `methodSendMessageDraft` in
  `internal/pa/output/sender.go` (private chat only, non-zero `draft_id`, one
  part only, localised via `Languages`, no `parse_mode`/`can_stop`) — DoD: T4
  passes; `TestS1O1_SenderIsTheOnlyBotAPICallSite` passes with no allowlist
  change.
- [ ] 4. Add `internal/pa/streaming.go`: `PA_STREAMING_ENABLED` reader with
  `EnvFlags` semantics, `DraftSender` interface, `RunLoopConfig.Drafts` and
  `RunLoopConfig.Getenv`, `claimResponse.Streaming` (`omitempty`) (depends on
  3) — DoD: T10 (flag off byte-identical claim) passes.
- [ ] 5. Add `internal/pa/toolstatus.go` (`toolStatus` map over the pinned
  read tools, generic fallback) (depends on 2) — DoD: T8 passes.
- [ ] 6. Extend `typingTracker` in `internal/pa/typing.go` into typing-then-draft
  presence: `showDraft`, `showStatus`, `draftRefresh` with a gated `check`,
  allow-list cache, `draftID(ref)` (depends on 3, 4) — DoD: `typing_test.go`
  unchanged and passing; T6, T7 pass.
- [ ] 7. Add `RouteDraft` and `serveDraft` in `internal/pa/runloop.go`
  (verify, flag, body bound, per-job `draftLimiter`, `RunningPAJob` with
  `l.gate`, shared allow-list helper extracted from `serveReply` without
  behaviour change, `RenderPartial`, `presence.showDraft`); mount it; call
  `presence.showStatus` from `AdmitToolCall` when streaming (depends on 1, 5,
  6) — DoD: T5, T6, T9, T11 pass; `runloop_test.go`, `outbox_test.go`,
  `replies_test.go` unchanged and passing.
- [ ] 8. Wire `Drafts` and `Getenv` in `cmd/server/pa_wiring.go`; extend
  `paBotSender` and `cmd/server/pa_test.go` recorder (depends on 7) — DoD:
  server wiring test asserts drafts are wired and nothing is sent with the flag
  off.
- [ ] 9. Worker streaming client: `chatStream` in
  `internal/agentworker/openaiclient.go` with SSE parsing, tool-call delta
  assembly, `stream_options.include_usage`, same `ProviderError` and body bounds
  — DoD: T12, T13 pass; existing `openaiclient_test.go` unchanged.
- [ ] 10. Worker drafter: `PARouteDraft`, `PAClaim.Streaming`,
  `PAStreamModel`, `internal/agentworker/padraft.go` (interval, min delta,
  latest-wins, one in flight, stop on 404/409/over-limit, closed before reply),
  `PAWorker.Streaming` from `AGENT_PA_STREAMING` in
  `cmd/agent-worker/pa_mode.go` (depends on 9) — DoD: T14, T15 pass;
  `TestPARoutesMatchServer` covers `PARouteDraft`; existing `parunner_test.go`
  unchanged.
- [ ] 11. End-to-end test in `internal/pa/worker_tools_e2e_test.go` style with
  the flag on (depends on 7, 8, 10) — DoD: T16 passes.
- [ ] 12. Mutation check: for each new guard test remove its guard and record
  that the test fails, in the PR description — DoD: listed in the PR.
- [ ] 13. Preview rollout: mctl-gitops PR setting `PA_STREAMING_ENABLED: "true"`
  in `services/labs/mctl-telegram-preview/values.yaml` and
  `AGENT_PA_STREAMING: "true"` in `services/labs/agent-worker-pa-preview/values.yaml`;
  verify usage is reported on streamed responses (worker logs / settled cost
  not at reservation); manual check on Telegram Android and Desktop (status
  draft, growing partial, final message replaces draft, no duplicate) recorded
  in the PR — DoD: PR merged with the recorded results; prod untouched.

## Tests

- [ ] T1. `RenderPartial`: a disallowed URL `https://evil.example/p` streamed one
  character at a time (each prefix rendered) never yields a draft containing the
  live string `evil.example`; with a trailing space the final draft holds the
  defanged form.
- [ ] T2. `RenderPartial`: allow-list holds `https://a.example/x`; streaming
  `https://a.example/xevil` character by character never yields a draft that
  contains the live token `https://a.example/x` before the run ends, and the
  finished run is defanged.
- [ ] T3. `RenderPartial` over-limit: a partial longer than one part
  (`MaxPartUTF16` + 1) renders to more than one part / `ErrTooLong`, and
  `serveDraft` answers `{"shown": false}` with no send (no truncation).
- [ ] T4. `SendDraft`: body is exactly `{chat_id, draft_id, text}`, method
  `sendMessageDraft`; refuses `draft_id` 0, non-positive chat, multi-part text;
  RU chat gets the Russian template.
- [ ] T5. `serveDraft` refusals send nothing: consent withdrawn, conversation
  closed, principal disabled, principal off allowlist, stale attempt, wrong
  digest -> same status as `serveTurn`; flag off/unreadable -> 404
  `streaming_off`; rate cap -> 429.
- [ ] T6. Cancelled run sends no further draft: after a draft is shown, withdraw
  consent (and separately close the conversation, disable the principal); the
  refresher's next tick sends nothing and the presence entry is gone.
- [ ] T7. Presence: typing is sent before the first draft and never after it;
  `serveReply` stops the refresher; refresh re-sends the same rendered text only.
- [ ] T8. `toolStatus` covers every `TierAuto`/`ClassRead` tool of
  `catalog.LoadPin()`; `AdmitToolCall` with the flag on sends the template for
  `tg/get_messages`, and the sent text contains none of the call's arguments.
- [ ] T9. Guard: `serveDraft` and presence code never call `appendFragment`,
  `appendAssistant` or `EnqueuePAOutbox` (AST test in `internal/pa`), and a
  streamed run leaves exactly the fragments and outbox rows a non-streamed run
  leaves.
- [ ] T10. Flag off: claim response bytes equal today's (golden), no draft is
  sent, `AdmitToolCall` sends no status; existing run-loop and outbox tests
  untouched.
- [ ] T11. Allow-list for drafts is built from user-provenance fragments only (a
  URL present only in a tool fragment is defanged in the draft).
- [ ] T12. `chatStream`: content deltas, tool-call deltas split across chunks by
  `index`, object-shaped arguments, `reasoning_content` ignored, usage chunk ->
  `UsageReported`; non-2xx -> `ProviderError` with body discarded; truncated
  stream and over-bound stream -> error; request body has `stream: true` and
  `stream_options.include_usage: true`.
- [ ] T13. Missing usage on a stream fails closed: `UsageReported=false`; a
  tool-calling turn abandons the run; a final answer is replied with no
  `cost_usd`; the server settles at the full reservation (not zero).
- [ ] T14. Drafter: respects min interval and min delta, latest wins, at most
  one post in flight, stops on 404 and 409, posts nothing after `reply`, and a
  failing draft route leaves `PAOutcome` and the reply unchanged.
- [ ] T15. Negotiation: worker streams only when both `AGENT_PA_STREAMING` and
  `claim.streaming` are true; a claim without the field uses `stream: false`.
- [ ] T16. E2E with the flag on: a run calling `tg/get_messages` shows a tool
  status draft, then growing partials, then exactly one `sendMessage` whose text
  equals the non-streamed rendered reply for the same answer.

## Rollback

- Instant: set `PA_STREAMING_ENABLED` to `"false"` (or remove it) on
  `labs/mctl-telegram-preview`; it is re-read on every claim and every draft, so
  drafting stops at the next call without a restart once the env change rolls
  out. Independently set `AGENT_PA_STREAMING` to `"false"` on
  `labs/agent-worker-pa-preview` to return the worker to `stream: false`.
- Full: revert the PR. No schema or stored data depends on it; partials were
  never persisted, and the reply/outbox path was not changed.
