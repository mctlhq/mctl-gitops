# Add opt-in flag for bulk media fetching in message-history tools

## Context

`get_messages` and `get_unread_messages` today return a `media_info` metadata
block for each message that carries media (type, MIME type, file name, size,
duration). No bytes are fetched; bytes require a separate two-step round-trip —
`prepare_get_media` to mint a server-side download reference, then `get_media`
to consume it and stream the file.

During end-to-end validation of the PR #280 pagination fix (issue #283,
raised alongside #282), bulk-fetching media across even a small history page
exposed two concrete problems: `get_media` responses for files larger than
roughly 1-2 MB already exceed typical MCP client inline tool-result size limits
and get spilled to disk, and the confirm/download race tracked in #282 means
looping `prepare_get_media`+`get_media` over many messages produces
non-deterministic failures once file sizes cross a few MB. If any future
convenience feature adds an automatic or bulk media-fetch mode — for example a
"resolve media inline" option on `get_messages` — it must be strictly opt-in
and capped to avoid these failure modes landing on callers by surprise.

This proposal codifies that policy as a concrete, implementable flag: a
`fetch_media` boolean parameter on `get_messages` and `get_unread_messages`
that defaults to `false`. When `false` the tools behave exactly as today; when
explicitly set to `true` the server fetches up to a fixed per-call cap of
downloadable media items inline and returns their bytes in a `media_data` field
alongside the existing `media_info` metadata, subject to the existing per-item
byte cap already enforced by `get_media`.

## User stories

- AS a developer building an export or archival tool I WANT to call
  `get_messages` with `fetch_media: true` on a bounded page SO THAT I can
  retrieve a small set of message bodies and their media in a single round-trip
  without a separate prepare/confirm cycle per item.
- AS an operator I WANT the default behavior of `get_messages` and
  `get_unread_messages` to remain metadata-only SO THAT existing integrations
  are not broken and accidental media fetches do not unexpectedly inflate
  response size.
- AS an LLM agent looping over paginated history I WANT the per-call fetch cap
  to be enforced server-side SO THAT a naive loop cannot exhaust memory or
  produce a context-window-blowing response even when every message on the page
  carries large attachments.

## Acceptance criteria (EARS)

- WHILE `fetch_media` is absent or `false` (the default), THE SYSTEM SHALL
  return only `media_info` metadata for messages that carry media and SHALL NOT
  download any file bytes, preserving behavior identical to the current
  implementation.

- WHEN a caller sets `fetch_media: true` on a `get_messages` or
  `get_unread_messages` call, THE SYSTEM SHALL attempt to download the bytes of
  each downloadable media item in the result page, in message order, up to a
  maximum of `BulkMediaFetchCap` items per call.

- WHEN `fetch_media: true` is set and an item is successfully downloaded, THE
  SYSTEM SHALL include its bytes as a standard-base64 string in a `media_data`
  field on the corresponding `Message` object in the response.

- WHEN `fetch_media: true` is set and the number of downloadable media items
  in the page exceeds `BulkMediaFetchCap`, THE SYSTEM SHALL fetch the first
  `BulkMediaFetchCap` items (by message order) and SHALL leave `media_data`
  absent on remaining messages, counting them as skipped.

- WHEN `fetch_media: true` is set and a media item's reported size exceeds the
  server's `MediaDownloadMaxBytes` limit, THE SYSTEM SHALL skip that item's
  download (leaving `media_data` absent on that message) and SHALL NOT return
  an error for the overall call.

- WHEN `fetch_media: true` is set and a media item has a non-downloadable type
  (web_page, contact, location, poll, unsupported), THE SYSTEM SHALL skip that
  item silently; it does not count toward `BulkMediaFetchCap`.

- WHEN `fetch_media: true` is set and an individual item download fails (network
  error, Telegram API error), THE SYSTEM SHALL skip that item and continue
  fetching remaining items up to the cap; it SHALL NOT abort the entire call.

- THE SYSTEM SHALL include a `fetch_media_summary` object in the response
  whenever `fetch_media: true` is set. The summary SHALL contain at minimum:
  `fetched` (count of items downloaded), `skipped` (count of items that could
  have been downloaded but were not, due to cap or size), and
  `cap` (the server-side `BulkMediaFetchCap` value in effect).

- THE SYSTEM SHALL NOT modify the behavior of `prepare_get_media` or
  `get_media`. The two-step confirmation flow for single-message on-demand
  downloads remains unchanged and is still the only path for single downloads.

- IF `fetch_media: true` is passed and the call is dispatched via the Local
  Bridge path (account mode "local"), THE SYSTEM SHALL return an error
  indicating that inline bulk media fetch is not supported in Local Bridge mode,
  so that the caller falls back to the two-step flow manually.

## Out of scope

- Any export or archival tool that uses `fetch_media` as a building block —
  this proposal only defines the flag and its guard semantics.
- Changes to the two-step `prepare_get_media` / `get_media` flow.
- Auto-fetching media without an explicit caller opt-in (fetch_media defaulting
  to true under any condition).
- Persistent or disk-backed result caching for fetched media bytes.
- Streaming or chunked delivery of large media items.
- Adding `fetch_media` to tools other than `get_messages` and
  `get_unread_messages`.

## Open questions

1. **Cap value.** The issue says the cap should exist but does not specify a
   number. This proposal assumes `BulkMediaFetchCap = 5` (a named constant in
   `internal/mcp/bulk_media.go`). The reviewer should confirm whether 5 is an
   appropriate default given the inline tool-result size limits observed during
   validation, or whether a lower cap (e.g. 3) is safer.

2. **Local Bridge support.** The Local Bridge daemon (`cmd/local/`) handles MCP
   tool calls independently. Extending `fetch_media` through the bridge would
   require a protocol change; the simplest safe stance is to return an error
   when `fetch_media: true` arrives on a local-mode account. This should be
   confirmed before implementation.

3. **Partial-success shape.** The proposal adds `fetch_media_summary` at the
   response root. An alternative is to add an `error` or `skipped_reason` field
   per message. The root-level summary is simpler for callers to inspect but
   loses per-item skip reasons. If per-item diagnostics are needed the schema
   must change.

4. **Scope of tools.** Should `get_unread_messages` also receive `fetch_media`?
   Unread-message fetches tend to be smaller and less "history-walk" in nature
   than `get_messages`. Including it is consistent but adds surface area.
   Reviewer should confirm both tools or only `get_messages`.
