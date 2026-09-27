# search_messages: bound searches to a time window with min_date/max_date

## Context

`search_messages` (MCP tool in `internal/mcp/tools.go`, backed by
`telegram.SearchMessages` in `internal/telegram/search.go`) runs every query over
the caller's full Telegram history and returns the newest `limit` matches
(default 20, clamped to 100 in `SearchMessages`). For a frequent term, or a chat
with years of history, the whole result budget can be consumed by messages older
than the window the caller cares about. The model then has to page, guess, or
post-filter by date — as happened on 2026-09-27 when a "last month" question
came back with 2024 results mixed in.

The underlying MTProto calls already support bounding: `messages.search` and
`messages.searchGlobal` both take `min_date` and `max_date` as Unix seconds, and
`gotd`'s generated `tg.MessagesSearchRequest` / `tg.MessagesSearchGlobalRequest`
expose them. Today `internal/telegram/search.go` simply never sets them. This
proposal adds two optional tool inputs, validates them at the MCP layer (same
shape as the existing `before` argument on `get_my_audit_log`), and passes them
down. No result field changes, no new tool, no change to the local-bridge
refusal behaviour.

## User stories

- AS an MCP client model I WANT to pass `min_date`/`max_date` to
  `search_messages` SO THAT a "in the last month" question spends the whole
  result budget inside that month instead of on older history.
- AS a user of a hosted account I WANT date-bounded search across all my chats
  and inside one chat SO THAT I get a directly usable answer without asking the
  model to filter dates itself.
- AS an MCP client model I WANT a clear, actionable tool error for a malformed or
  inverted date range SO THAT I can correct the call instead of silently getting
  unbounded results.
- AS a reviewer of this repository I WANT the tool-surface documentation
  (`docs/tool-descriptors.json`, README table, `/docs` page) to state the new
  inputs SO THAT the published surface matches the code.

## Acceptance criteria (EARS)

Tool surface and validation (`internal/mcp/tools.go`, `toolSearchMessages`)

- WHEN the MCP tool list is requested THE SYSTEM SHALL advertise
  `search_messages` with two additional optional string inputs, `min_date` and
  `max_date`, `query` still the only required input, and `outputSchema`
  unchanged.
- WHEN `search_messages` is described THE SYSTEM SHALL state in the description
  that results are newest-first, that `min_date`/`max_date` are inclusive bounds
  interpreted in UTC, that both RFC 3339 timestamps and plain `YYYY-MM-DD` dates
  are accepted, and SHALL give a worked example ("last 30 days" → `min_date` =
  today minus 30 days).
- WHEN `min_date` or `max_date` is supplied as an RFC 3339 timestamp (e.g.
  `2026-08-27T00:00:00Z`) THE SYSTEM SHALL use exactly that instant.
- WHEN `min_date` is supplied as a plain date (`2026-08-27`) THE SYSTEM SHALL
  interpret it as `2026-08-27T00:00:00Z`.
- WHEN `max_date` is supplied as a plain date (`2026-08-27`) THE SYSTEM SHALL
  interpret it as the end of that UTC day (`2026-08-27T23:59:59Z`) so that a
  plain-date range includes both boundary days.
- IF `min_date` or `max_date` cannot be parsed as either an RFC 3339 timestamp or
  a plain `YYYY-MM-DD` date THEN THE SYSTEM SHALL return an `IsError` tool result
  naming the offending argument and both accepted formats, and SHALL perform no
  Telegram RPC.
- IF the resolved `min_date` is after the resolved `max_date` THEN THE SYSTEM
  SHALL return an `IsError` tool result saying `min_date` must not be after
  `max_date`, and SHALL perform no Telegram RPC.
- IF a resolved bound falls outside the range representable in the MTProto
  32-bit-seconds field (before 1970-01-01 or after 2038-01-19) THEN THE SYSTEM
  SHALL return an `IsError` tool result naming that argument and the supported
  range, and SHALL perform no Telegram RPC.
- WHEN `min_date` equals `max_date` THE SYSTEM SHALL accept the call (an equal
  pair is a valid, possibly empty, window — not an inverted range).
- WHEN `min_date` and `max_date` are both absent or empty THE SYSTEM SHALL behave
  exactly as it does today (unbounded search).

Request construction (`internal/telegram/search.go`)

- WHEN a bounded global search runs (no `peer`) THE SYSTEM SHALL send
  `tg.MessagesSearchGlobalRequest` with `MinDate` and `MaxDate` set to the Unix
  second values of the resolved bounds, and every other field as today.
- WHEN a bounded per-peer search runs (`peer` supplied) THE SYSTEM SHALL send
  `tg.MessagesSearchRequest` with `MinDate` and `MaxDate` set to the Unix second
  values of the resolved bounds, and every other field as today.
- IF a bound is absent THEN THE SYSTEM SHALL send `0` for that field, which is
  the Telegram "unbounded" value and the field's current zero value.
- WHILE no date argument is supplied THE SYSTEM SHALL produce requests whose
  encoded bytes are identical to those produced before this change.

Unchanged behaviour

- WHILE the caller's account mode is `local` (Local Bridge) THE SYSTEM SHALL
  return the existing refusal text
  `search_messages is not yet supported for local-bridge accounts`, byte for
  byte, whether or not `min_date`/`max_date` were supplied, and SHALL evaluate
  that refusal before date validation so the refusal is never replaced by a date
  error.
- WHILE `search_messages` runs THE SYSTEM SHALL keep `outputSchema`,
  `structuredContent` and the `searchMessagesResult` shape unchanged — no new
  result fields.
- WHEN the call is audited THE SYSTEM SHALL keep writing only the existing
  fields (tool name, `telegram.RedactPeer(peer)`, status) — date bounds are not
  added to the audit row, and no message body, date-bearing or otherwise, is
  logged.
- WHILE the identity lacks `telegram:messages:read` THE SYSTEM SHALL keep
  refusing on scope before parsing any argument.

Documentation and surface evidence

- WHEN this change lands THE SYSTEM SHALL ship a regenerated
  `docs/tool-descriptors.json` whose `search_messages` entry carries the new
  `inputSchema` properties and the new description text
  (`TestToolDescriptorsSnapshotMatchesRegistry` must pass).
- WHEN the tool inputs are listed for humans THE SYSTEM SHALL mention `min_date`
  and `max_date` in the README MCP tools table and on the `/docs` "Available
  tools" table (`internal/web/docs.html`).
- WHILE `docs/portal-allowlist.json` describes the enabled tool set THE SYSTEM
  SHALL leave it unchanged: no tool is added or removed and `search_messages`
  stays `readOnlyHint: true`.

## Out of scope

- Morphology, stemming and synonym expansion for the query itself (for example
  Russian `багажник` vs `багажники`). That is Telegram's server-side search
  behaviour; at most it is guidance in the tool description.
- Implementing `search_messages` in the Local Bridge daemon (`internal/bridge`,
  `cmd/local`). It stays refused there.
- Pagination / offset arguments (`offset_id`, `add_offset`, `offset_rate`),
  `from_id`, folder or media-type filters (`tg.InputMessagesFilter*`).
- Any new result field, any change to `outputSchema` / `structuredContent`, or a
  count of how many matches the window contained.
- Relative or natural-language date inputs ("last month", "30d"). The caller
  computes absolute bounds.
- Server-side re-filtering of results returned by Telegram: the bounds are
  passed to Telegram and the response is decoded as today.

## Open questions

- **Plain-date `max_date` semantics.** The issue says plain dates are
  "interpreted as UTC" and that bounds are inclusive, but a literal midnight
  reading of `max_date: 2026-08-27` would exclude almost all of 27 August, which
  contradicts "inclusive". This proposal resolves the ambiguity by expanding a
  plain-date `max_date` to `23:59:59Z` of that day and documenting it in the
  tool description. An RFC 3339 `max_date` is used verbatim.
- **Telegram's own boundary semantics.** Whether Telegram treats `min_date` /
  `max_date` as strict or inclusive at the exact second is server behaviour and
  is not observable from unit tests. The tool description claims inclusivity at
  day granularity, which holds either way given the end-of-day expansion.
  Proceeding without a live-API experiment.
- **Product-updates release gate.** A change to a tool's `inputSchema` is a
  `schema` claim that `go run ./cmd/productupdates gate` requires an *approved*
  `docs/product-updates/<id>.yaml` entry to cover (see
  `docs/product-updates/README.md`). No entry files exist in the repo yet, and
  an agent may not be the reviewer (`provenance.reviewed_by` must be a human,
  never the assisting model). This proposal therefore has the implementer draft
  the entry with `status: draft` and the correct `evidence.from` baseline, and
  calls out in the PR body that a human reviewer must flip it to `approved` and
  name themselves before the gate goes green.
- **`SearchParams` struct vs positional arguments.** The chosen design changes
  `telegram.SearchMessages` to take a params struct rather than growing to nine
  positional arguments. There is exactly one caller (`internal/mcp/tools.go`),
  so the churn is small, but a reviewer may prefer the smaller diff.
