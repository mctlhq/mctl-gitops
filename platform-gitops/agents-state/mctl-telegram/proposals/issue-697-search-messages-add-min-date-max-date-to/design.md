# Design: issue-697-search-messages-add-min-date-max-date-to

## Current state

Everything relevant sits in two files, plus the generated tool-surface snapshot.

**`internal/telegram/search.go`** — `SearchMessages(ctx, c *gotdtelegram.Client,
peerSpec, query string, limit int, cache *PeerCache, userID int64) ([]Message, error)`:

- rejects an empty `query`, clamps `limit` to `(0, 100]` with a default of 20
  (lines 17-24);
- with no `peerSpec`, calls `api.MessagesSearchGlobal` with
  `&tg.MessagesSearchGlobalRequest{Q, Filter: &tg.InputMessagesFilterEmpty{},
  OffsetPeer: &tg.InputPeerEmpty{}, Limit}` and decodes via
  `extractSearchMaps` + `decodeGlobalSearchMessages` (lines 27-39);
- with a `peerSpec`, resolves it through `ResolvePeerCached` (in
  `internal/telegram/peers.go`, backed by `PeerCache` in `peercache.go`) and
  calls `api.MessagesSearch` with `&tg.MessagesSearchRequest{Peer, Q, Filter:
  &tg.InputMessagesFilterEmpty{}, Limit}`, decoding via `decodeMessages` with a
  `&Dialog{ID: peerSpec, Title: peerSpec}` hint (lines 41-56).

Neither request sets `MinDate`/`MaxDate`. There is no `internal/telegram/search_test.go`
at all, and no test anywhere in `internal/telegram` fakes an MTProto invoker —
`*gotdtelegram.Client` is taken concretely, so the RPC arguments are currently
unobservable from tests.

**`internal/mcp/tools.go`, `toolSearchMessages()`** (lines 2668-2733) — declares
`query` (required), `peer`, `limit`, the `readOnly/destructive/openWorld`
annotations, `outputSchema[searchMessagesResult]()` and a description block
listing required/optional inputs. The handler:

1. `requireScope(id, "telegram:messages:read")`;
2. reads arguments with `stringArg` / `intArg` (helpers at lines 2405-2425) and
   rejects an empty `query`;
3. when `s.Hub != nil` and `s.Store.GetAccountMode(ctx, id.UserID) == "local"`,
   returns the fixed refusal
   `search_messages is not yet supported for local-bridge accounts` (lines
   2703-2711);
4. `s.borrowWithRetry(ctx, "search_messages", ...)` → `telegram.SearchMessages`;
5. `s.audit(ctx, id, "search_messages", telegram.RedactPeer(peer), err, startedAt)`;
6. wraps results with `wrapMessages` (`internal/mcp/format.go`) into
   `searchMessagesResult` (`internal/mcp/tools.go:2483`), emits the
   `untrustedContentNotice` text plus `StructuredContent`.

There is a precedent in this same file for parsing a timestamp argument:
`get_my_audit_log` and the admin audit tool parse `before` with
`time.Parse(time.RFC3339, raw)` and return
`"before must be RFC3339 (e.g. 2026-05-14T00:00:00Z)"` on failure
(lines 1062-1068 and 1670-1676). `internal/productupdate/feed.go` already uses
`time.Parse(time.DateOnly, ...)` for plain dates, so both layouts are idiomatic
here.

**Surface evidence.** `docs/tool-descriptors.json` is a byte-exact snapshot of
the registered tools, held by `TestToolDescriptorsSnapshotMatchesRegistry`
(`internal/mcp/descriptors_test.go`) and regenerated with
`go test ./internal/mcp -run TestToolDescriptorsSnapshotMatchesRegistry -update-descriptors`.
Its current `search_messages` entry lists exactly `query`, `peer`, `limit`.
`docs/product-updates/README.md` describes a CI gate
(`go run ./cmd/productupdates gate`) that fails unless every schema change since
the baseline release is claimed by an approved feed entry. `docs/portal-allowlist.json`
pins the enabled tool set and is checked by `internal/mcp/portal_allowlist_test.go`
(names and hints, not schemas). Human-facing input lists live in the README "MCP
tools" table and the `/docs` "Available tools" table in `internal/web/docs.html`
— neither currently has a `search_messages` row at all. `docs/local-bridge.md`
and `internal/web/local-bridge.md` both list `search_messages` among the five
tools the daemon refuses.

`go.mod` pins `github.com/gotd/td v0.161.0`. In that generated schema,
`messages.search` and `messages.searchGlobal` carry `min_date:int` /
`max_date:int` as plain (non-flag) fields, so `0` means "unbounded" and is also
the Go zero value — which is why omitting the arguments can keep the encoded
request byte-identical.

## Proposed solution

Three small, separable pieces: argument parsing at the MCP layer, a params
struct plus a test seam in the telegram layer, and documentation/snapshot
updates.

### 1. Date parsing and validation in `internal/mcp` (new file `searchwindow.go`)

```go
// parseSearchWindow resolves the optional min_date/max_date arguments of
// search_messages into UTC instants. A zero time means "unbounded".
func parseSearchWindow(minRaw, maxRaw string) (minDate, maxDate time.Time, err error)
```

Per bound, in order: `time.Parse(time.RFC3339, raw)` (used verbatim, converted to
UTC); else `time.Parse(time.DateOnly, raw)` → UTC midnight for `min_date`, and
UTC `23:59:59` of that day for `max_date` so a plain-date range includes both
boundary days; else an error naming the argument and both accepted formats, in
the style of the existing `before` message:

```
min_date must be RFC3339 (e.g. 2026-08-27T00:00:00Z) or a plain date (e.g. 2026-08-27)
```

Then two range checks:

- each resolved bound must fall in `[0, math.MaxInt32]` Unix seconds, because the
  MTProto field is a 32-bit int: `max_date is out of range (supported: 1970-01-01
  to 2038-01-19)`;
- if both are set and `minDate.After(maxDate)`:
  `min_date must not be after max_date`.

Keeping this in `internal/mcp` matches where every other argument is parsed, and
makes it a plain unit-testable function with no Telegram dependency.

The handler in `toolSearchMessages` gains, **after** the existing local-bridge
refusal block and before `borrowWithRetry`:

```go
minDate, maxDate, derr := parseSearchWindow(
    stringArg(args, "min_date", ""), stringArg(args, "max_date", ""))
if derr != nil {
    return mcplib.NewToolResultError(derr.Error()), nil
}
```

Ordering is deliberate: scope → `query` → local-bridge refusal → dates. A
local-bridge account therefore always sees the identical refusal string, never a
date error, which is exactly what the issue asks for. A hosted account with a bad
date returns before any client is borrowed, so no RPC happens.

Schema additions (two `mcplib.WithString` options) and a rewritten description
block naming: newest-first ordering, inclusive UTC bounds, both accepted
formats, and the "last 30 days" example. `outputSchema[searchMessagesResult]()`
and the result construction are untouched.

### 2. `internal/telegram/search.go`: params struct + invoker seam

`SearchMessages` already takes seven positional arguments; two more would make
the call site unreadable. Replace the message-shaped arguments with a struct and
keep the client/cache/user arguments positional:

```go
// SearchParams describes one search_messages query. Zero MinDate/MaxDate mean
// unbounded, which is Telegram's own encoding for those fields.
type SearchParams struct {
    Peer    string
    Query   string
    Limit   int
    MinDate time.Time
    MaxDate time.Time
}

func SearchMessages(ctx context.Context, c *gotdtelegram.Client, p SearchParams,
    cache *PeerCache, userID int64) ([]Message, error)
```

To make the constructed requests observable from tests without a live MTProto
client, introduce a narrow interface satisfied by `*tg.Client` and split the two
branches into functions that take it:

```go
// searchInvoker is the slice of *tg.Client the search path uses. It exists so
// tests can capture the constructed requests.
type searchInvoker interface {
    MessagesSearchGlobal(ctx context.Context, req *tg.MessagesSearchGlobalRequest) (tg.MessagesMessagesClass, error)
    MessagesSearch(ctx context.Context, req *tg.MessagesSearchRequest) (tg.MessagesMessagesClass, error)
}

func searchGlobalWith(ctx context.Context, api searchInvoker, p SearchParams) ([]Message, error)
func searchPeerWith(ctx context.Context, api searchInvoker, peer tg.InputPeerClass, p SearchParams) ([]Message, error)
```

`SearchMessages` keeps ownership of validation (empty query, limit clamp) and of
peer resolution via `ResolvePeerCached` — the only step that genuinely needs the
concrete `*gotdtelegram.Client` — then delegates to whichever branch applies,
passing `c.API()`. The decode paths (`extractSearchMaps`,
`decodeGlobalSearchMessages`, `decodeMessages`) move with the branches unchanged,
so a fake invoker returning a canned `*tg.MessagesMessages` also exercises
decoding.

Date conversion is one helper, guarding the zero time (whose `Unix()` is a large
negative number):

```go
func unixSeconds(t time.Time) int {
    if t.IsZero() {
        return 0
    }
    return int(t.Unix())
}
```

and the two request literals gain `MinDate: unixSeconds(p.MinDate)`,
`MaxDate: unixSeconds(p.MaxDate)`. The implementer must confirm against
`gotd v0.161.0`'s generated `tl_messages_search_gen.go` /
`tl_messages_search_global_gen.go` that these are plain `int` fields; if either
turns out to be flag-gated in this version, use the generated
`SetMinDate`/`SetMaxDate` accessors and only when the bound is non-zero, so an
unbounded call still sets no flag bit and stays byte-identical.

### 3. Documentation and surface evidence

- Regenerate `docs/tool-descriptors.json` (the snapshot test fails otherwise).
- Add a `search_messages` row to the README "MCP tools" table and to the
  `/docs` "Available tools" table in `internal/web/docs.html`, listing
  `query`, optional `peer`, `limit`, `min_date`, `max_date`. The tool is missing
  from both tables today, so this closes that gap in the same change.
- Draft `docs/product-updates/<id>.yaml` as a `changed_behavior` entry with
  `tools: [search_messages]` and
  `evidence: {from: <latest release tag carrying a snapshot>, changes: [{tool: search_messages, change: schema}]}`,
  `status: draft`, `provenance.assisted_by` set and `reviewed_by` left for the
  human reviewer. Call this out in the PR body: the gate stays red until a human
  approves the entry, by design.
- `docs/portal-allowlist.json`, `docs/local-bridge.md` and
  `internal/web/local-bridge.md` need no change: no tool is added or removed,
  the read-only hint is unchanged, and the bridge still refuses the tool.

## Alternatives

1. **Filter by date in Go after the RPC.** Keep the requests as they are and drop
   out-of-window messages from the decoded `[]Message`. Rejected: it does not fix
   the actual problem. Telegram still returns the newest `limit` matches from all
   of history, so a filtered response would just be shorter (often empty) while
   burning the same result budget — the exact failure the issue describes.

2. **Grow `SearchMessages`' positional parameter list.** Add `minDate, maxDate
   time.Time` after `limit`, no struct. Smaller diff, and it keeps the one caller
   simple to update. Rejected: nine positional arguments, four of them
   interchangeable scalars/strings, is how a wrong-order bug gets written; the
   struct also gives the new test seam a natural single argument. Worth
   revisiting only if a reviewer prefers minimal churn.

3. **Test through a real `*gotdtelegram.Client` with an injected middleware.**
   `internal/telegram/login.go` already wraps invokers with
   `telegram.MiddlewareFunc`, so a test could in principle build a client whose
   invoker records requests. Rejected: it requires constructing and connecting a
   gotd client in a unit test (session storage, DC config, `bin.Encoder`
   round-trips) to observe a struct literal. The narrow `searchInvoker` interface
   gets the same assertion with none of that machinery, and the seam is private
   to the package.

4. **Accept only RFC 3339, no plain dates.** Simplest parsing and no end-of-day
   ambiguity. Rejected: the issue explicitly asks for plain dates, which is also
   the form a model most naturally produces for "last month".

5. **Put the date parsing in `internal/telegram`.** Rejected: argument shape is a
   tool-surface concern, and every other string/number/timestamp argument
   (including `before`) is parsed in `internal/mcp/tools.go`. Keeping
   `SearchParams` typed as `time.Time` also keeps the telegram layer free of
   input-format policy.

## Platform impact

- **Migrations:** none. No database schema, no Vault path, no config flag, no
  new environment variable.
- **Backward compatibility:** additive and optional. Existing callers that send
  only `query`/`peer`/`limit` produce byte-identical MTProto requests
  (`MinDate`/`MaxDate` stay `0`, already the encoded zero) and identical results.
  `outputSchema` and `structuredContent` are unchanged, so MCP clients that
  validate the output contract — including the MCP Apps triage surface in
  `internal/mcpui/triage.html`, which calls `search_messages` with `query` only —
  are unaffected. The only Go-level break is `telegram.SearchMessages`' signature,
  and its single caller is in this repository.
- **Local Bridge:** behaviour unchanged by construction (refusal evaluated before
  date parsing); `docs/local-bridge.md` stays accurate.
- **Resource impact:** neutral to positive. One extra RPC field; bounded searches
  return fewer, more relevant messages, so no extra Telegram round trips and no
  additional flood-wait exposure (`internal/telegram/floodwait.go` unchanged).
- **Privacy/audit:** no new logging. Dates are not written to the audit row and
  `internal/audit/redact.go` needs no new field name. Message bodies remain out
  of logs.
- **Risks and mitigations:**
  - *Silent regression for date-less calls* — mitigated by a regression test that
    encodes the constructed request with `bin.Buffer` and compares bytes against a
    literal built exactly as today's code builds it.
  - *`MinDate`/`MaxDate` turning out to be flag-gated in gotd v0.161.0*, which
    would change the encoded flags for unbounded calls — mitigated by the
    conditional `Set*` fallback above plus the same byte-comparison test.
  - *Model confusion over inclusivity at day granularity* — mitigated by
    expanding a plain-date `max_date` to end of day and stating the rule in the
    tool description.
  - *Wire overflow for far-future dates* — mitigated by the explicit
    `[0, MaxInt32]` range check, which returns a tool error rather than sending a
    truncated int.
  - *CI red on the product-updates gate* — expected and documented: the feed
    entry needs a human approval, which no tool in this repository can give.
