# Fix Hub.Call send-on-closed-channel race in the Local Bridge relay

## Context

`internal/bridge/hub.go` multiplexes one daemon websocket connection per
user (`Hub.conn map[int64]*daemonConn`). `Hub.Call` (hub.go:193-228) reads
the `*daemonConn` under `h.mu`, releases the lock, and only then sends the
envelope on `dc.send`:

```go
h.mu.Lock()
dc, ok := h.conn[userID]
h.mu.Unlock()
...
select {
case dc.send <- env:
```

Every teardown path — `Unregister` (hub.go:120-130), `UnregisterSend`
(hub.go:137-154), and `EvictDevice` (hub.go:169-185, added by issue-483) —
removes the map entry and calls `close(dc.send)` while holding `h.mu`. If a
teardown lands between `Call`'s unlock and its `dc.send <- env`, the send
targets an already-closed channel: `panic: send on closed channel`. That
panic happens on a goroutine started by the HTTP/MCP handler, outside any
`recover`, and takes the whole `mctl-telegram` process down — not just the
one call.

This is a pre-existing bug in the `Unregister`/`Call` pair (`Unregister` is
invoked by `server.go`'s websocket cleanup path on every disconnect, which
is the common case), not something introduced by `EvictDevice`. It surfaced
during review of PR #494 (the issue-483 device-revocation work), and this
proposal fixes it as an independent PR against the underlying pattern
rather than folding a Hub-semantics change into a security PR.

Failure scenario: a daemon disconnects (websocket close, EvictDevice) at
the same instant an MCP call for that user is mid-dispatch. Probability is
low per event but rises with call volume and reconnect/revocation churn;
the consequence is a full process crash for every in-flight user on the
relay, not just the racing call.

## User stories

- AS the Local Bridge relay operator I WANT `Hub.Call` to never send on a
  channel that teardown has closed SO THAT a daemon disconnect or device
  eviction can never crash the `mctl-telegram` server process.
- AS an MCP tool caller racing a daemon teardown I WANT a clean
  `ErrNoDaemonConnected` SO THAT I can tell "no daemon" apart from a
  successful delivery, instead of the whole server dying under me.

## Acceptance criteria (EARS)

- WHEN `Hub.Call` looks up `dc` and then attempts to enqueue `env` on
  `dc.send`, AND a concurrent `Unregister`, `UnregisterSend`, or
  `EvictDevice` call for the same connection completes teardown in that
  window, THE SYSTEM SHALL return `ErrNoDaemonConnected` (or `ctx.Err()`
  if the context was cancelled) instead of panicking.
- WHEN `Unregister`, `UnregisterSend`, or `EvictDevice` tears down a
  `daemonConn`, THE SYSTEM SHALL signal that teardown through a dedicated
  `done chan struct{}` closed under `h.mu`, and SHALL NOT close
  `dc.send` as the teardown signal.
- WHILE a `daemonConn` is registered (its `done` channel is not yet
  closed), THE SYSTEM SHALL allow the writer goroutine in
  `internal/bridge/server.go` to keep draining `dc.send` and forwarding
  envelopes to the websocket.
- WHEN the writer goroutine in `server.go` observes `dc.done` closed, THE
  SYSTEM SHALL stop reading from `dc.send` and exit, exactly as it does
  today when it observes `dc.send` closed.
- IF two teardown calls race for the same `daemonConn` (e.g. a slow
  `Unregister` and a fast reconnect's `Register` followed by another
  teardown), THEN THE SYSTEM SHALL close each `done` channel at most
  once, preserving the existing "only touch the entry if it's still the
  one we mean" guard that `UnregisterSend` and `EvictDevice` already use
  for `h.conn[userID]` identity and `dc.send` / `dc.deviceID` matching.
- WHEN `go test ./internal/bridge/... -race` runs a test that interleaves
  `Hub.Call` with `Unregister` and with `EvictDevice` under `-race`, THE
  SYSTEM SHALL complete without a panic and without a race detector
  report.
- IF the fix is reverted to the old `close(dc.send)`-as-teardown-signal
  pattern, THEN THE SYSTEM's new interleaving test SHALL fail (either by
  panicking or by observing a wrong error), so the test is a real
  mutation check on the fix.

## Out of scope

- Changing `Hub.Deliver`'s locking pattern (hub.go:234-255) — it already
  reads `dc` under the lock and then operates on `dc.pending`, a
  `sync.Map`, which has no equivalent close-after-unlock hazard because
  nothing closes or replaces `dc.pending` itself.
- Changing `Register`'s eviction of a previous connection (hub.go:96-107)
  beyond swapping `close(prev.send)` for closing `prev.done` — the
  eviction policy (single connection per user) is unchanged.
- Any change to the `EvictDevice` device-matching semantics from
  issue-483 (hub.go:169-185) beyond reusing its existing "only touch the
  entry if it's still the one we mean" guard for the new `done` channel.
- Backpressure / `maxPendingCalls` behavior (hub.go:30-33, 204-208) — not
  touched by this fix.
- A `recover()`-based mitigation — the issue explicitly rejects this as
  hiding a real lifecycle bug and leaving the caller unable to
  distinguish disconnect from delivery; this proposal implements the
  `done`-channel fix instead.
- Any change to `internal/bridge/tokenhandler.go` or the JWT/auth path —
  unrelated to this race.

## Open questions

- The issue's suggested `select` in `Call` races `dc.send <- env` against
  `<-dc.done` and `<-ctx.Done()`. If both `dc.send <- env` and `<-dc.done`
  are simultaneously ready (teardown closes `done` in the same instant the
  writer goroutine drains `send`), Go's `select` picks pseudo-randomly;
  the envelope could still occasionally be delivered right as teardown
  begins. This is a strict improvement over today (no panic either way)
  and matches the issue's suggested shape, so this proposal treats it as
  acceptable rather than adding a second synchronization mechanism to
  make the two fully mutually exclusive. Recorded here, not blocking.
- Whether the same `done` idea should also close a narrow window in
  `Deliver` (hub.go:234-255) where a response arrives for an ID whose
  `Call` has already timed out and deleted its `pending` entry — that
  path already degrades gracefully (`ok` is false, the delivery is
  dropped) and does not panic, so it is left untouched. Recorded as an
  open question in case a reviewer wants it folded in; default is no
  change.
