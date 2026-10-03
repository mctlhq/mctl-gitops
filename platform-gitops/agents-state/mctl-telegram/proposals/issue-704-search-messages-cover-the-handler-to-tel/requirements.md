# search_messages: cover the handler-to-telegram SearchParams seam with a test

## Context

`search_messages` parses its optional `min_date` / `max_date` arguments in
`internal/mcp/searchwindow.go` (`parseSearchWindow`) and sends them to Telegram
through `telegram.SearchMessages` in `internal/telegram/search.go`. Both ends are
tested: `TestParseSearchWindow` (`internal/mcp/searchwindow_test.go`) pins the
parsing, and `TestSearchGlobalWith_SetsDateBounds` /
`TestSearchPeerWith_SetsDateBounds` (`internal/telegram/search_test.go`) pin the
resulting `tg.MessagesSearchGlobalRequest` / `tg.MessagesSearchRequest` fields.

The wiring between them is untested. In `toolSearchMessages`
(`internal/mcp/tools.go`, around line 2814) the handler builds a
`telegram.SearchParams` literal inside the `s.borrowWithRetry` callback, and no
`internal/mcp` test can reach that callback: `borrowWithRetry` calls
`s.Pool.Borrow`, which needs a real `*telegram.ClientPool` and a live MTProto
session. Every existing handler-level search test
(`TestToolSearchMessages_MissingScope`, `_MissingQuery`, `_InvalidDate`) returns
before the borrow. As a result, swapping `MinDate` and `MaxDate` in that literal,
or dropping one of them, leaves the whole suite green — a silent-wrong-results
bug class on a read-only tool users trust for date-scoped search. This proposal
introduces a test seam so a handler-level test can assert that the parsed bounds
reach `SearchParams` unchanged, and mutation-checks that the new test actually
fails when the literal is broken.

## User stories

- AS a maintainer of `mctl-telegram` I WANT a test that fails when the
  `SearchParams` literal in `toolSearchMessages` is mutated SO THAT a swapped or
  dropped date bound cannot reach production unnoticed.
- AS a contributor changing `search_messages` argument handling I WANT a
  handler-level seam that runs without a live Telegram session SO THAT I can
  cover the parse-to-request path in a fast unit test.
- AS an MCP client user scoping a search with `min_date` / `max_date` I WANT the
  bounds I passed to be the bounds that are searched SO THAT results are not
  silently drawn from the wrong window.

## Acceptance criteria (EARS)

- WHEN `toolSearchMessages` has parsed its arguments successfully THE SYSTEM
  SHALL dispatch the search through a single injectable indirection (a
  package-level function variable in `internal/mcp`) that receives the fully
  built `telegram.SearchParams` value.
- WHILE no test overrides that indirection THE SYSTEM SHALL behave exactly as
  today: `s.borrowWithRetry(ctx, "search_messages", id.UserID, ...)` followed by
  `telegram.SearchMessages(ctx, c, params, s.PeerCache, id.UserID)`, with the same
  flood-wait retry behaviour, the same `s.audit` call, the same
  `borrowErrResult("search_messages", err)` error rendering and the same
  `searchMessagesResult` payload.
- WHEN a test overrides the indirection and invokes the handler with
  `min_date` and `max_date` THE SYSTEM SHALL pass to `SearchParams.MinDate` and
  `SearchParams.MaxDate` exactly the `time.Time` values `parseSearchWindow`
  returned for those arguments, and SHALL pass `Peer`, `Query` and `Limit`
  through from the request arguments unchanged.
- WHEN only `min_date` is supplied THE SYSTEM SHALL pass a zero
  `SearchParams.MaxDate`, and WHEN only `max_date` is supplied THE SYSTEM SHALL
  pass a zero `SearchParams.MinDate`, so that "one bound dropped" and "both
  bounds set" are distinguishable at the seam.
- IF the two date bounds in the `SearchParams` literal are transposed, or either
  is replaced by the zero value, THEN THE SYSTEM SHALL fail at least one new
  test — verified by running the new test against each of those temporary local
  mutations before the change is proposed for merge.
- WHEN the overriding test's stub returns messages THE SYSTEM SHALL render them
  through `wrapMessages` into `searchMessagesResult{Query, Matches}`, and WHEN
  the stub returns an error THE SYSTEM SHALL return an error result for
  `search_messages`.
- WHILE the new test runs THE SYSTEM SHALL require no MTProto connection, no
  `*telegram.ClientPool` and no network access, and SHALL restore the
  package-level variable via `t.Cleanup` so test order stays irrelevant.
- WHEN a test fixture needs Telegram identifiers THE SYSTEM SHALL use synthetic
  ones drawn from the personas already in the suite (`Alice`, `Bob`, `Carol`,
  `Dana`), per `.claude/CLAUDE.md`.

## Out of scope

- Any change to the user-visible behaviour, schema, description or output of
  `search_messages`.
- Any change to `parseSearchWindow` / `parseSearchBound`
  (`internal/mcp/searchwindow.go`) or to `telegram.SearchMessages`,
  `minDateUnix`, `maxDateUnix`, `checkSearchBound`
  (`internal/telegram/search.go`).
- Limit clamping. `toolSearchMessages` passes the raw `limit` argument; the
  1..100 clamp lives in `telegram.SearchMessages` and is tested there. The new
  test asserts the raw value reaches the seam and does not assert clamping.
- Introducing a pool interface, refactoring `borrowWithRetry`, or adding seams to
  the other pool-backed handlers (`list_dialogs`, `get_messages`,
  `send_message`, media tools). If the pattern proves useful there, that is a
  separate proposal.
- Local-bridge routing for `search_messages`, which the handler still refuses
  ("not yet supported for local-bridge accounts").
- Adding a mutation-testing tool to CI. The mutation check here is a manual,
  documented step performed during implementation.

## Open questions

- The issue offers two seam shapes ("an injectable search function on `Server`,
  or a fake pool"). This proposal picks a third, closest-to-precedent option: a
  package-level function variable in `internal/mcp`, mirroring `mediaDownloader`
  in `internal/mcp/bulk_media.go`, which is already overridden with `t.Cleanup`
  restore by `bulk_media_test.go` and `bulk_media_alloc_test.go`. A reviewer who
  prefers an unexported `*Server` field (no global state) should say so: the test
  body is nearly identical either way. Proceeding with the package variable
  because no test in `internal/mcp` calls `t.Parallel()`, so global mutation is
  safe here, and because matching the existing seam keeps one pattern in the
  package rather than two.
- Whether the new test belongs in a new file `internal/mcp/search_messages_test.go`
  or appended to the existing `internal/mcp/tools_test.go` (1590 lines). This
  proposal uses a new file, next to the existing per-tool test files
  (`send_message_test.go`, `send_media_test.go`).
