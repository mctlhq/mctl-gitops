# Tasks: issue-704-search-messages-cover-the-handler-to-tel

- [ ] 1. Extract `(*Server).searchViaPool(ctx context.Context, userID int64, p telegram.SearchParams) ([]telegram.Message, error)` in `internal/mcp/tools.go`, containing the existing `s.borrowWithRetry(ctx, "search_messages", userID, ...)` + `telegram.SearchMessages(ctx, c, p, s.PeerCache, userID)` body verbatim — DoD: method compiles, no `beforeAttempt` hook added, doc comment references `downloadMediaViaPool` as the sibling pattern, `go vet ./...` clean.
- [ ] 2. Add the package-level seam `var messageSearcher = func(s *Server, ctx context.Context, userID int64, p telegram.SearchParams) ([]telegram.Message, error) { return s.searchViaPool(ctx, userID, p) }` (depends on 1) — DoD: doc comment states that production always calls through to `searchViaPool` and that tests reassigning it must restore via `t.Cleanup`, mirroring `mediaDownloader` in `internal/mcp/bulk_media.go:69`.
- [ ] 3. Rewire `toolSearchMessages` (depends on 2) to keep the `telegram.SearchParams{Peer, Query, Limit, MinDate, MaxDate}` literal in the handler and pass it to `messageSearcher(s, ctx, id.UserID, ...)` — DoD: the `s.audit(ctx, id, "search_messages", telegram.RedactPeer(peer), err, startedAt)` call, the `borrowErrResult("search_messages", err)` branch, `wrapMessages`, `searchMessagesResult`, `untrustedContentNotice` and `StructuredContent` are unchanged; `git diff` shows no behavioural change beyond the indirection.
- [ ] 4. Add `stubMessageSearcher(t *testing.T, fn ...)` helper in a new `internal/mcp/search_messages_test.go`, modelled on `stubDownloader` in `internal/mcp/bulk_media_test.go:52` (depends on 2) — DoD: helper saves the previous value, assigns the stub, restores via `t.Cleanup`, and exposes the captured `telegram.SearchParams` plus an invocation counter.
- [ ] 5. Write the handler-level seam tests listed under "## Tests" (depends on 3, 4) — DoD: all subtests pass with `srv := &Server{Store: newToolsTestStore(t)}`, `Pool` nil and `Hub` nil; no network, no MTProto session; fixtures use only the `Alice`/`Bob`/`Carol`/`Dana` personas and numeric ids checked with `git grep` first, per `.claude/CLAUDE.md`.
- [ ] 6. Run the mutation check (depends on 5): temporarily apply each mutation from the design's table — transpose `MinDate`/`MaxDate`, drop `MinDate`, drop `MaxDate`, set both to `minDate`, swap `Peer`/`Query` — and confirm `go test ./internal/mcp/ -run SearchMessages` fails for each, then revert — DoD: every mutation observed red, the working tree back to the unmutated state (`git status` clean apart from the intended change), and the outcome written into the PR description as a table.
- [ ] 7. Run the full gate (depends on 6): `go fmt ./...`, `go vet ./...`, `golangci-lint run`, `go test ./...` — DoD: all clean; in particular `internal/mcp/record_test.go`, `output_schema_test.go`, `annotations_test.go`, `apps_surface_test.go`, `descriptors_test.go` and `portal_allowlist_test.go` still pass unchanged, proving the tool surface did not move.
- [ ] 8. Open the PR (depends on 7) — DoD: branch `feat/agents-issue-704-...`, conventional-commit messages (`refactor:` for the seam, `test:` for the coverage, or one `test:` commit), body refs `#704` and `#699`, no emoji, English only, includes the mutation-check table; merged with `gh pr merge <N> --merge --delete-branch` (merge commit, never squash or rebase).

## Tests

- [ ] T1. `TestToolSearchMessages_PassesParsedBounds/both bounds`: `min_date: "2026-08-01"`, `max_date: "2026-08-31"` reach the seam as `2026-08-01T00:00:00Z` and `2026-08-31T23:59:59Z` respectively — asymmetric on purpose so a transposition cannot pass.
- [ ] T2. `.../RFC3339 bounds used verbatim`: `min_date: "2026-08-27T00:00:00Z"`, `max_date: "2026-09-27T12:34:56Z"` arrive unchanged in the matching fields (mirrors `TestParseSearchWindow`'s first case, one layer up).
- [ ] T3. `.../only min_date`: `SearchParams.MaxDate.IsZero()` is true while `MinDate` is the parsed instant — catches a dropped or duplicated bound.
- [ ] T4. `.../only max_date`: `SearchParams.MinDate.IsZero()` is true while `MaxDate` is 23:59:59Z of that day.
- [ ] T5. `.../no bounds`: both `MinDate` and `MaxDate` are zero, and `Peer`/`Query`/`Limit` still pass through — the unbounded-search regression guard, matching `TestSearchGlobalWith_UnboundedEncodingUnchanged` in `internal/telegram/search_test.go`.
- [ ] T6. `.../peer, query and limit pass through`: a synthetic peer string, the `query` argument and `limit` all arrive unchanged; an out-of-band `limit` (e.g. 500) reaches the seam unclamped, with a comment recording that the 1..100 clamp is `telegram.SearchMessages`'s job and is tested in `internal/telegram`.
- [ ] T7. `TestToolSearchMessages_RendersSeamResults`: the stub returns two synthetic `telegram.Message` values; the handler's `searchMessagesResult` carries the same `Query` and the messages as produced by `wrapMessages`, with `StructuredContent` populated.
- [ ] T8. `TestToolSearchMessages_SeamErrorIsToolError`: the stub returns an error; `result.IsError` is true, the handler does not panic on the nil `Pool`, and no Go error is returned (MCP tools surface errors in the result).
- [ ] T9. `TestToolSearchMessages_SeamNotReachedOnInvalidDate`: with `min_date: "yesterday"` the stub's invocation counter stays 0 — pins the existing early-return before any Telegram RPC, complementing `TestToolSearchMessages_InvalidDate`.
- [ ] T10. Regression: the pre-existing `TestToolSearchMessages_MissingScope`, `_MissingQuery`, `_InvalidDate` (`internal/mcp/tools_test.go:1145+`) and the `search_messages` cases in `internal/mcp/record_test.go` pass untouched.

## Rollback

The change is test-only plus one unexported indirection, with no schema,
migration, config or exported-API surface. To roll back, revert the merge commit
(`git revert -m 1 <merge-sha>`): `toolSearchMessages` returns to calling
`s.borrowWithRetry` inline, `searchViaPool` / `messageSearcher` and
`internal/mcp/search_messages_test.go` disappear, and no deployed behaviour
changes — no redeploy is required for correctness, and no data or session state
is involved. If only the test is flaky or wrong, delete
`internal/mcp/search_messages_test.go` and keep the seam: production behaviour is
identical either way.
