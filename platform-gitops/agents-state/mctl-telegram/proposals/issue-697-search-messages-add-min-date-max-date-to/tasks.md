# Tasks: issue-697-search-messages-add-min-date-max-date-to

- [ ] 1. Confirm the gotd field shape: read `tl_messages_search_gen.go` and
      `tl_messages_search_global_gen.go` in `github.com/gotd/td@v0.161.0` and note
      whether `MinDate`/`MaxDate` are plain `int` fields or flag-gated (with
      `SetMinDate`/`SetMaxDate`) — DoD: a one-line note in the PR body stating
      which, and the assignment style used in task 3 chosen accordingly (plain
      assignment, or `Set*` only when the bound is non-zero so an unbounded call
      sets no flag bit).

- [ ] 2. Add `parseSearchWindow` in a new `internal/mcp/searchwindow.go`:
      signature `parseSearchWindow(minRaw, maxRaw string) (minDate, maxDate time.Time, err error)`;
      per bound try `time.Parse(time.RFC3339, raw)` then
      `time.Parse(time.DateOnly, raw)`; a plain-date `min_date` becomes UTC
      midnight, a plain-date `max_date` becomes `23:59:59` UTC of that day; empty
      input yields the zero time. Errors, in the style of the existing `before`
      message in `internal/mcp/tools.go`: unparseable →
      `min_date must be RFC3339 (e.g. 2026-08-27T00:00:00Z) or a plain date (e.g. 2026-08-27)`
      (likewise `max_date`); out of `[0, math.MaxInt32]` Unix seconds →
      `<arg> is out of range (supported: 1970-01-01 to 2038-01-19)`; inverted →
      `min_date must not be after max_date`. Equal bounds are valid — DoD:
      function compiles, is unexported, has a doc comment explaining the
      end-of-day rule, and T3 passes.

- [ ] 3. Rework `internal/telegram/search.go` (depends on 1): add
      `type SearchParams struct { Peer, Query string; Limit int; MinDate, MaxDate time.Time }`,
      change `SearchMessages` to
      `SearchMessages(ctx context.Context, c *gotdtelegram.Client, p SearchParams, cache *PeerCache, userID int64) ([]Message, error)`,
      add the private `searchInvoker` interface (`MessagesSearchGlobal`,
      `MessagesSearch`) plus `searchGlobalWith` / `searchPeerWith`, and a
      `unixSeconds(t time.Time) int` helper returning 0 for the zero time. Set
      `MinDate`/`MaxDate` on both request literals; leave `Q`, `Filter`,
      `OffsetPeer`, `Peer`, `Limit`, the limit clamp, the empty-query check and
      every decode path (`extractSearchMaps`, `decodeGlobalSearchMessages`,
      `decodeMessages` with the `&Dialog{ID: peerSpec, Title: peerSpec}` hint)
      exactly as they are — DoD: `go build ./...` clean, `*tg.Client` satisfies
      `searchInvoker` without an adapter, no behaviour change for zero dates.

- [ ] 4. Update `toolSearchMessages` in `internal/mcp/tools.go` (depends on 2, 3):
      add `mcplib.WithString("min_date", ...)` and `mcplib.WithString("max_date", ...)`
      descriptions; call `parseSearchWindow` **after** the `s.Hub != nil` /
      account-mode `local` refusal block and before `borrowWithRetry`, returning
      `mcplib.NewToolResultError(derr.Error())` on failure; pass a
      `telegram.SearchParams{Peer: peer, Query: query, Limit: limit, MinDate: minDate, MaxDate: maxDate}`
      into `telegram.SearchMessages`. Do not touch `outputSchema`,
      `searchMessagesResult`, `wrapMessages`, the `untrustedContentNotice` text,
      the audit call or the refusal string — DoD: `go build ./...` clean; the
      refusal string in the source is unchanged; no new result field.

- [ ] 5. Rewrite the `search_messages` description block (depends on 4) to state:
      results are newest-first; `min_date`/`max_date` are inclusive bounds in UTC;
      both RFC 3339 timestamps and plain `YYYY-MM-DD` dates are accepted (a plain
      `max_date` covers the whole day); a "last 30 days" example (`min_date` =
      today minus 30 days); and one sentence of guidance that Telegram's search
      matches word forms as its server does, so try alternative forms of a term
      rather than expecting morphology expansion — DoD: description renders in the
      descriptor snapshot, keeps the existing untrusted-content WARNING paragraph,
      and still lists required vs optional inputs in the current format.

- [ ] 6. Regenerate the tool surface snapshot (depends on 4, 5):
      `go test ./internal/mcp -run TestToolDescriptorsSnapshotMatchesRegistry -update-descriptors`
      — DoD: `docs/tool-descriptors.json` diff shows only the `search_messages`
      `inputSchema` and `description` changes, and the test passes without the
      flag.

- [ ] 7. Human-facing docs (depends on 5): add a `search_messages` row to the
      README "MCP tools" table and to the `/docs` "Available tools" table in
      `internal/web/docs.html` (mode read, scope `telegram:messages:read`, inputs
      `query`, optional `peer`, `limit` (default 20, max 100), `min_date`,
      `max_date`) — DoD: both tables mention `min_date`/`max_date`, HTML row
      matches the surrounding markup, `go test ./internal/web/...` passes.

- [ ] 8. Draft the product-update feed entry (depends on 6):
      `docs/product-updates/<id>.yaml`, `kind: changed_behavior`,
      `tools: [search_messages]`,
      `evidence.from: <latest release tag whose tree carries docs/tool-descriptors.json>`,
      `evidence.changes: [{tool: search_messages, change: schema}]`,
      `status: draft`, `provenance.author` + `assisted_by` filled,
      `reviewed_by` empty — DoD: `go run ./cmd/productupdates gate` output is
      understood and reported in the PR body, with an explicit note that a human
      reviewer must set `status: approved` and name themselves in `reviewed_by`
      before the gate can pass (a model may not approve).

- [ ] 9. Verify the untouched surfaces (depends on 4): `docs/portal-allowlist.json`,
      `docs/local-bridge.md`, `internal/web/local-bridge.md`,
      `internal/mcpui/triage.html` and `internal/mcp/output_schema_test.go`
      expectations — DoD: `git status` shows no change to those files and
      `go test ./...` passes (notably `portal_allowlist_test.go`,
      `annotations_test.go`, `output_schema_test.go`, `apps_surface_test.go`).

- [ ] 10. Repo hygiene (depends on all): `go fmt ./...`, `go vet ./...`,
      `golangci-lint run`, conventional commit
      `feat: bound search_messages with min_date/max_date`, no emoji, merge via
      `gh pr merge <N> --merge --delete-branch` — DoD: all three checks clean and
      the PR links issue #697.

## Tests

All new tests must use only the synthetic personas already in this repository
(`Alice`, `Bob`, `Carol`, `Dana`) and must not introduce a new numeric Telegram
id without `git grep <id>` first, per `.claude/CLAUDE.md`.

- [ ] T1. `internal/telegram/search_test.go` (new): a `fakeSearchInvoker`
      implementing `searchInvoker` that records the request it was given and
      returns a canned `&tg.MessagesMessages{Messages: []tg.MessageClass{&tg.Message{...}}}`.
      Two cases: `searchGlobalWith` with `MinDate`/`MaxDate` set asserts the
      captured `*tg.MessagesSearchGlobalRequest` carries the expected Unix
      seconds (and unchanged `Q`, `Filter`, `OffsetPeer`, `Limit`);
      `searchPeerWith` with an `&tg.InputPeerUser{...}` asserts the captured
      `*tg.MessagesSearchRequest` carries them too. Fails if task 3's field
      assignment is reverted.

- [ ] T2. `internal/telegram/search_test.go`: regression — with zero
      `MinDate`/`MaxDate`, encode the captured request with `bin.Buffer`
      (`github.com/gotd/td/bin`) and compare bytes against a locally built
      literal identical to today's (`{Q, Filter: &tg.InputMessagesFilterEmpty{},
      OffsetPeer: &tg.InputPeerEmpty{}, Limit}`), for both the global and the
      per-peer request. Fails if an unbounded call starts setting a flag or a
      non-zero date.

- [ ] T3. `internal/mcp/searchwindow_test.go` (new): table test over
      `parseSearchWindow` — RFC 3339 pair used verbatim; plain-date `min_date` →
      `00:00:00Z`; plain-date `max_date` → `23:59:59Z` same day; mixed formats;
      both empty → two zero times; `min_date` equal to `max_date` accepted;
      unparseable value → error naming that argument and both formats; inverted
      range → `min_date must not be after max_date`; a year-3000 date → the
      out-of-range error. Fails if task 2's end-of-day or range logic is reverted.

- [ ] T4. `internal/mcp/tools_test.go`: `TestToolSearchMessages_InvalidDate` —
      `&Server{Store: newToolsTestStore(t)}` (nil `Pool`, so any RPC attempt
      would fail differently), identity with `telegram:messages:read`, arguments
      `{"query": "roof rack", "min_date": "yesterday"}`; assert `result.IsError`
      and that the text names `min_date` and both accepted formats. Add a second
      case with an inverted range (`min_date` after `max_date`) asserting the
      inverted-range message. Fails if the handler stops validating before
      borrowing a client.

- [ ] T5. `internal/mcp/tools_test.go`: `TestToolSearchMessages_LocalBridgeRefusalUnchanged`
      — follow the existing `seedLocalAccount(t, store, ...)` + `bridge.NewHub()`
      pattern from `internal/mcp/send_message_test.go`; call `search_messages`
      twice, once with valid `min_date`/`max_date` and once with a deliberately
      invalid `min_date`, and assert both return exactly
      `search_messages is not yet supported for local-bridge accounts`. Fails if
      date parsing is moved ahead of the refusal block.

- [ ] T6. Existing suites must stay green unmodified except where the signature
      change forces it: `go test ./...`, with particular attention to
      `TestToolDescriptorsSnapshotMatchesRegistry`,
      `TestToolDescriptorsAreDeterministic`, `annotations_test.go`,
      `output_schema_test.go`, `portal_allowlist_test.go`,
      `apps_surface_test.go`, and the existing
      `TestToolSearchMessages_MissingScope` / `_MissingQuery`.

## Rollback

The change is additive, stateless and confined to one PR: no migration, no
config flag, no persisted data. Revert the merge commit
(`git revert -m 1 <merge-sha>`) and cut a patch release; the reverted tree
restores the previous `docs/tool-descriptors.json`, so the snapshot test passes
immediately and MCP clients see the old three-input schema on their next
`tools/list`. Clients that had started sending `min_date`/`max_date` keep working
— unknown properties are ignored by the argument helpers (`stringArg`) — they
simply get unbounded results again, which is today's behaviour. If only the
Telegram-side bounding is suspect (for example Telegram returning empty windows)
while the surface is fine, the narrower fix is to make `unixSeconds` return 0
unconditionally in `internal/telegram/search.go`: one function, requests back to
byte-identical, with T2 still passing and T1 failing loudly to mark the
suppression. Rolling back the drafted product-update entry means deleting its
YAML file; nothing has been sent from it.
