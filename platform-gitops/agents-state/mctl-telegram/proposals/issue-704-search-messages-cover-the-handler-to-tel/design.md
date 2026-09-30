# Design: issue-704-search-messages-cover-the-handler-to-tel

## Current state

**The handler.** `(*Server).toolSearchMessages` in `internal/mcp/tools.go`
(tool definition from line 2740, handler from 2776) does, in order:

1. `requireScope(id, "telegram:messages:read")`;
2. reads `query`, `peer`, `limit` via `stringArg` / `intArg`;
3. rejects an empty `query`;
4. refuses local-bridge accounts when `s.Hub != nil` and
   `s.Store.GetAccountMode` reports `"local"`;
5. rejects non-string `min_date` / `max_date` explicitly (a `stringArg`
   fallback would silently widen the search);
6. `parseSearchWindow(stringArg(args,"min_date",""), stringArg(args,"max_date",""))`;
7. borrows a client and searches:

```go
var msgs []telegram.Message
err := s.borrowWithRetry(ctx, "search_messages", id.UserID, func(ctx context.Context, c *gotdtelegram.Client) error {
        var inner error
        msgs, inner = telegram.SearchMessages(ctx, c, telegram.SearchParams{
                Peer:    peer,
                Query:   query,
                Limit:   limit,
                MinDate: minDate,
                MaxDate: maxDate,
        }, s.PeerCache, id.UserID)
        return inner
})
s.audit(ctx, id, "search_messages", telegram.RedactPeer(peer), err, startedAt)
```

8. on error, `borrowErrResult("search_messages", err)`; on success,
   `wrapMessages(msgs)` into `searchMessagesResult{Query, Matches}`
   (`internal/mcp/tools.go:2555`), marshalled with `json.MarshalIndent`, prefixed
   with `untrustedContentNotice`, and attached as `StructuredContent`.

**Why nothing covers step 7.** `borrowWithRetry` (`internal/mcp/tools.go:62`)
calls `s.Pool.Borrow(ctx, userID, fn)` on the concrete `*telegram.ClientPool`
field of `Server` (`internal/mcp/server.go:26`). There is no interface and no
injection point, so a unit test has only two options: a nil `Pool` (panic) or a
real pool with a live MTProto session (not available in CI). Consequently all
three existing handler tests —
`TestToolSearchMessages_MissingScope`, `TestToolSearchMessages_MissingQuery`,
`TestToolSearchMessages_InvalidDate` in `internal/mcp/tools_test.go:1145+` —
return before step 7, and `internal/mcp/record_test.go` reaches the handler
end-to-end via `callTool` only along error paths (scope denied, empty query,
mode unsupported). `grep -rn "SearchParams" internal/mcp` matches exactly one
line: the literal above. Nothing in the repository reads it.

**What is covered on either side.** `internal/mcp/searchwindow_test.go`
(`TestParseSearchWindow`) pins the parse: RFC3339 verbatim, plain min_date to
00:00:00Z, plain max_date to 23:59:59Z, inverted range rejected, range limits.
`internal/telegram/search_test.go` (`TestSearchGlobalWith_SetsDateBounds`,
`TestSearchPeerWith_SetsDateBounds`) drives `searchGlobalWith` / `searchPeerWith`
through the `searchInvoker` interface (`internal/telegram/search.go:32`) with a
`fakeSearchInvoker` and asserts `MinDate == min-1`, `MaxDate == max+1`, plus `Q`,
`Filter`, `OffsetPeer`, `Limit`. So `internal/telegram` already solves exactly
this problem for its own layer by extracting a narrow interface for the
dependency it cannot instantiate — the precedent this design follows one layer up.

**The seam precedent in `internal/mcp`.** `internal/mcp/bulk_media.go:69`
declares:

```go
var mediaDownloader = func(s *Server, ctx context.Context, userID int64, loc telegram.MediaFileLocation, maxBytes int64, sizeHint int64) (data []byte, consumed int64, err error, attemptedFn bool) {
        return s.downloadMediaViaPool(ctx, userID, loc, maxBytes, sizeHint)
}
```

with a doc comment stating that production always calls through to
`(*Server).downloadMediaViaPool` and that tests reassigning the variable must
restore it via `t.Cleanup`. `internal/mcp/bulk_media_test.go:52-68`
(`stubDownloader`) and `internal/mcp/bulk_media_alloc_test.go:181-186` do exactly
that. No test in `internal/mcp` calls `t.Parallel()` (`grep -c` returns 0), so a
package-level variable carries no data-race or ordering hazard in this package.

## Proposed solution

Apply the `mediaDownloader` pattern to the search path, keeping the
`SearchParams` literal in the handler (that literal is the thing under test — if
it moved below the seam the test would no longer cover it).

**1. Extract the pool-bound half into a method** in `internal/mcp/tools.go`,
next to `toolSearchMessages`:

```go
// searchViaPool borrows a pooled client and runs one search_messages query,
// mirroring the pattern downloadMediaViaPool uses (s.borrowWithRetry +
// a single telegram call).
func (s *Server) searchViaPool(ctx context.Context, userID int64, p telegram.SearchParams) ([]telegram.Message, error) {
        var msgs []telegram.Message
        err := s.borrowWithRetry(ctx, "search_messages", userID, func(ctx context.Context, c *gotdtelegram.Client) error {
                var inner error
                msgs, inner = telegram.SearchMessages(ctx, c, p, s.PeerCache, userID)
                return inner
        })
        return msgs, err
}
```

**2. Add the seam variable** in the same file (or a small new
`internal/mcp/search.go` if the reviewer prefers), documented in the same terms
as `mediaDownloader`:

```go
// messageSearcher abstracts the pool-borrow step of toolSearchMessages so unit
// tests can assert that the arguments the handler parsed reach
// telegram.SearchParams unchanged, without a live MTProto connection.
// Production code always calls through to (*Server).searchViaPool; tests that
// reassign this package variable must restore the original via t.Cleanup.
var messageSearcher = func(s *Server, ctx context.Context, userID int64, p telegram.SearchParams) ([]telegram.Message, error) {
        return s.searchViaPool(ctx, userID, p)
}
```

**3. Rewrite step 7 of the handler** to build the literal and hand it to the
seam — the literal stays verbatim, including field order and names:

```go
msgs, err := messageSearcher(s, ctx, id.UserID, telegram.SearchParams{
        Peer:    peer,
        Query:   query,
        Limit:   limit,
        MinDate: minDate,
        MaxDate: maxDate,
})
s.audit(ctx, id, "search_messages", telegram.RedactPeer(peer), err, startedAt)
```

Everything after that (audit, `borrowErrResult`, `wrapMessages`, marshalling,
`StructuredContent`) is untouched. Behaviour is byte-identical in production: the
only difference is one extra function-value call.

**4. New test file `internal/mcp/search_messages_test.go`** with a
`stubMessageSearcher(t, fn)` helper in the shape of `stubDownloader`, capturing
the `telegram.SearchParams` it received, and table-driven subtests over the
handler obtained from `srv.toolSearchMessages()` with
`srv := &Server{Store: newToolsTestStore(t)}`, `Hub` nil (so step 4 is skipped)
and `Pool` nil (never dereferenced, because the seam is stubbed):

- `both bounds` — `min_date: "2026-08-01"`, `max_date: "2026-08-31"` must arrive
  as `2026-08-01T00:00:00Z` and `2026-08-31T23:59:59Z`. Deliberately asymmetric
  (midnight vs end-of-day, different days) so a transposition cannot pass.
- `RFC3339 bounds used verbatim` — the exact instants arrive unchanged and in the
  right fields.
- `only min_date` / `only max_date` — the other field is the zero `time.Time`,
  which catches "one bound dropped" and "bounds copied from the same variable".
- `no bounds` — both zero; `Peer`, `Query`, `Limit` still pass through.
- `peer, query and limit pass through` — `peer: "user:1001"` (reuse an existing
  synthetic persona id; run `git grep` before choosing, per `.claude/CLAUDE.md`),
  `query`, `limit: 55`; plus a case asserting the raw out-of-band `limit` reaches
  the seam unclamped, documenting that clamping is `telegram.SearchMessages`'s
  job.
- `results are rendered` — stub returns two synthetic `telegram.Message` values;
  assert `searchMessagesResult.Query` and that `Matches` came through
  `wrapMessages`.
- `search error becomes a tool error` — stub returns an error; assert
  `result.IsError` and that the handler did not panic on a nil `Pool`, proving
  the seam fully replaces the borrow.
- `seam is not reached on an invalid date` — stub records invocation; assert it
  was never called when `min_date` is unparseable, so the existing early-return
  guarantee stays pinned.

**5. Mutation check (manual, during implementation).** With the new test in
place, apply each mutation below locally, confirm `go test ./internal/mcp/ -run
SearchMessages` fails, then revert:

| Mutation in the `SearchParams` literal | Test that must fail |
| --- | --- |
| `MinDate: maxDate, MaxDate: minDate` | `both bounds`, `RFC3339 bounds` |
| drop `MinDate` | `both bounds`, `only min_date` |
| drop `MaxDate` | `both bounds`, `only max_date` |
| `MinDate: minDate, MaxDate: minDate` | `both bounds`, `only max_date` |
| `Query: peer` / `Peer: query` | `peer, query and limit pass through` |

Record the outcome in the PR description. This is documentation of a check that
was run, not a CI job.

## Alternatives

**A pool interface (`type clientBorrower interface { Borrow(...) error }`) with a
fake pool.** The issue's second suggestion, and the most general: it would unlock
handler tests for `list_dialogs`, `get_messages`, `send_message` and the media
tools too. Dropped for this P3 scope because `Pool.Borrow`'s callback takes a
`*gotdtelegram.Client` — a fake pool must still hand the callback a real
`*telegram.Client` value or `nil`, and `telegram.SearchMessages` immediately calls
`c.API()`, so a `nil` client panics before the assertion. Making it work means
either abstracting the gotd client (a large, cross-package change touching every
`internal/telegram` entry point) or asserting only that Borrow was called, which
does not observe `SearchParams`. The chosen seam sits one level above that
problem: it observes the params directly and needs no client at all. Widening to a
pool interface later remains possible and is not foreclosed.

**An exported injectable field on `Server` (`SearchFn func(...)`).** Direct, no
global state, and closest to the issue's first suggestion. Dropped because
`Server`'s fields are the package's configuration surface, consumed by
`cmd/server/main.go` and the `With*` builders in `internal/mcp/server.go:102+`; a
field that exists only for tests invites production wiring and would want a
`WithSearchFn` builder plus a nil-check on every call. An *unexported* field
(`searchFn`, nil meaning "use the pool") is a genuinely reasonable variant and is
recorded as an open question — it is strictly safer under `t.Parallel()`, which
this package does not use today.

**Move the whole call below a `telegram`-level seam and test there.** `internal/
telegram` already has `searchInvoker`, so one could pass a fake invoker down from
`internal/mcp`. Dropped because it inverts the dependency the wrong way (the MCP
layer would have to know about MTProto request shapes) and because it still would
not observe the `SearchParams` literal built in `toolSearchMessages` — which is
precisely the untested line.

**Do nothing / rely on an end-to-end test against Telegram.** Dropped: no CI
credentials, non-deterministic results, and a date-window bug would surface as
"fewer results than expected", the hardest failure mode to notice.

## Platform impact

- **Migrations:** none. No schema, no config, no environment variables.
- **Backward compatibility:** total. No exported API changes (`searchViaPool`
  and `messageSearcher` are unexported), no tool-schema change, so
  `internal/mcp/output_schema_test.go`, `annotations_test.go`,
  `apps_surface_test.go`, `descriptors_test.go`, `portal_allowlist_test.go` and
  `docs/portal-allowlist.json` are unaffected. `search_messages` keeps
  `readOnlyHint: true` and its position in the portal allowlist.
- **Resource impact:** one indirect function call per `search_messages`
  invocation. Unmeasurable next to an MTProto round trip. No new allocation in
  the hot path: `SearchParams` is a value passed by copy, as today.
- **Risks and mitigations:**
  - *Risk:* the extraction accidentally changes flood-wait retry semantics.
    *Mitigation:* `searchViaPool` keeps the identical `borrowWithRetry(ctx,
    "search_messages", userID, fn)` call with no `beforeAttempt` hook, matching
    today's code exactly; the `s.audit` call site and `borrowErrResult` stay in
    the handler so the audited error is still the borrow's error.
  - *Risk:* a leaked override makes an unrelated test search through a stub.
    *Mitigation:* `t.Cleanup` restore inside the `stubMessageSearcher` helper,
    exactly as `stubDownloader` does; no `t.Parallel()` in this package.
  - *Risk:* the new test asserts on the stub rather than on the handler and so is
    vacuous. *Mitigation:* the mutation table above is the acceptance gate — each
    mutation must be shown to turn the suite red.
  - *Risk:* a fixture leaks real Telegram identity data. *Mitigation:*
    `.claude/CLAUDE.md` forbids it; reuse `Alice`/`Bob`/`Carol`/`Dana` and
    `git grep` any numeric id before using it.
- **Conventions:** `go fmt`, `go vet`, `golangci-lint`; commit prefix `test:`
  for the test plus `refactor:` for the seam, or a single `test:` commit if kept
  together; merge with `gh pr merge <N> --merge --delete-branch` (merge commits
  only, per `.claude/CLAUDE.md`).
